"""The CLI turns known failures into one `error:` line, and doctor reads a container-only host."""

import contextlib
import os
from pathlib import Path

import pytest
from art98 import cli, freshness
from art98.bridge import BridgeTimeout
from art98.container.host import ContainerError
from art98.desktop import DesktopError
from art98.guestfiles import GuestBuildMissing
from art98.qemu import QemuError
from art98.recorder import RecorderError
from art98.service import NotRunning, ServiceError
from art98.session import ImageMissing
from art98.state import StateError

REAL_WARN = freshness.warn
REAL_STALE = freshness.stale_warnings

SCENE = "from art98.anim import Scene\n\n\nclass Demo(Scene):\n    def play(self):\n        pass\n"


@contextlib.contextmanager
def fake_attach(*args, **kwargs):
    yield object()  # a session the patched render never touches


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr(cli.freshness, "warn", lambda *a: None)
    monkeypatch.setattr(cli.service, "attach", fake_attach)
    monkeypatch.delenv("ART98_TRACE", raising=False)


@pytest.fixture
def scene(tmp_path):
    path = tmp_path / "demo.py"
    path.write_text(SCENE)
    return path


def fail_with(monkeypatch, error):
    def render(*args, **kwargs):
        raise error

    monkeypatch.setattr("art98.anim.render", render)


@pytest.mark.parametrize(
    "error",
    [
        ImageMissing("no image"),
        ContainerError("no engine"),
        RecorderError("ffmpeg died"),
        StateError("a.json", ["bad"]),
        DesktopError("no desktop"),
        BridgeTimeout("slow"),
        QemuError("qemu died"),
        GuestBuildMissing("view.exe missing"),
    ],
)
def test_known_failures_are_one_error_line(monkeypatch, capsys, scene, error):
    fail_with(monkeypatch, error)
    assert cli.main(["render", str(scene)]) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: ") and "Traceback" not in err


RAISING_SCENE = (
    "from art98.anim import Scene\n"
    "from art98.bridge import BridgeTimeout\n\n\n"
    "def helper():\n"
    '    raise BridgeTimeout("no window for Notepad")\n\n\n'
    "class Demo(Scene):\n"
    "    def construct(self):\n"
    "        helper()\n"
)


def test_error_names_the_scene_line(monkeypatch, capsys, tmp_path):
    path = tmp_path / "scene.py"
    path.write_text(RAISING_SCENE)

    def render(scene, *args, **kwargs):
        scene().construct()

    monkeypatch.setattr("art98.anim.render", render)
    assert cli.main(["render", str(path)]) == 1
    # innermost scene frame is the raise in helper(), not the construct call
    assert capsys.readouterr().err == (
        "error: no window for Notepad (scene.py:6, in helper)\n"
    )


def test_error_outside_the_scene_is_unchanged(monkeypatch, capsys, scene):
    fail_with(monkeypatch, BridgeTimeout("slow"))
    assert cli.main(["render", str(scene)]) == 1
    assert capsys.readouterr().err == "error: slow\n"


def test_trace_keeps_the_traceback(monkeypatch, scene):
    fail_with(monkeypatch, RecorderError("ffmpeg died"))
    monkeypatch.setenv("ART98_TRACE", "1")
    with pytest.raises(RecorderError):
        cli.main(["render", str(scene)])


def test_ctrl_c_exits_130(monkeypatch, capsys, scene):
    fail_with(monkeypatch, KeyboardInterrupt())
    assert cli.main(["render", str(scene)]) == 130
    assert "interrupted" in capsys.readouterr().err


def test_a_scenes_own_bug_keeps_its_traceback(monkeypatch, scene):
    fail_with(monkeypatch, KeyError("mine"))
    with pytest.raises(KeyError):
        cli.main(["render", str(scene)])


def test_ping_is_guarded(monkeypatch, capsys, tmp_path):
    def attach(*args, **kwargs):
        raise ServiceError("no VM")

    monkeypatch.setattr(cli.service, "attach", attach)
    assert cli.main(["ping", "--work", str(tmp_path)]) == 1
    assert capsys.readouterr().err == "error: no VM\n"


def test_render_and_ping_pass_wait_and_revert(monkeypatch, tmp_path, scene):
    seen = []

    def attach(settings, **kwargs):
        seen.append(kwargs)
        raise NotRunning("down")

    monkeypatch.setattr(cli.service, "attach", attach)
    cli.main(["ping", "--work", str(tmp_path), "--wait", "2.5"])
    cli.main(["render", str(scene), "--work", str(tmp_path)])
    assert seen == [{"revert": False, "wait": 2.5}, {"wait": 0.0}]


def test_render_hands_the_attached_session_to_the_renderer(
    monkeypatch, tmp_path, scene
):
    sentinel, attach_kwargs, got = object(), [], {}

    @contextlib.contextmanager
    def attach(settings, **kwargs):
        attach_kwargs.append(kwargs)
        yield sentinel

    def render(scene_class, output, **kwargs):
        got.update(kwargs)
        return tmp_path / "x.mp4"

    monkeypatch.setattr(cli.service, "attach", attach)
    monkeypatch.setattr("art98.anim.render", render)
    assert cli.main(["render", str(scene), "--work", str(tmp_path)]) == 0
    assert got["session"] is sentinel
    assert "revert" not in attach_kwargs[0]


def test_a_bad_art98_toml_is_one_error_line(monkeypatch, capsys, tmp_path):
    (tmp_path / "art98.toml").write_text("[vm]\nbogus = 1\n")
    monkeypatch.chdir(tmp_path)
    assert cli.main(["vm", "status"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: ") and "bogus" in err and "Traceback" not in err


def test_vm_and_wait_parse_and_help(capsys):
    for argv in (["vm", "--help"], ["vm", "start", "--help"], ["render", "--help"]):
        with pytest.raises(SystemExit) as stop:
            cli.main(argv)
        assert stop.value.code == 0
    out = capsys.readouterr().out
    assert "--vnc" in out and "--wait S" in out and "status" in out
    with pytest.raises(SystemExit) as stop:
        cli.main(["vm"])
    assert stop.value.code == 2


def test_vm_status_exit_codes(monkeypatch, capsys, tmp_path):
    info = {"running": True, "busy": False, "paused": True, "snapshots": ["ready"],
            "started_at": "t", "vnc": None, "image_stale": False}  # fmt: skip
    monkeypatch.setattr(cli.service, "status", lambda settings: info)
    assert cli.main(["vm", "status", "--work", str(tmp_path)]) == 0
    assert "paused" in capsys.readouterr().out
    info["snapshots"] = []
    assert cli.main(["vm", "status", "--work", str(tmp_path)]) == 1
    info["running"] = False
    assert cli.main(["vm", "status", "--work", str(tmp_path)]) == 1
    assert "art98 vm start" in capsys.readouterr().out


def test_vm_start_and_stop_call_the_service(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        cli.service, "start", lambda s, vnc: calls.append(("start", vnc))
    )
    monkeypatch.setattr(cli.service, "stop", lambda s: calls.append(("stop",)))
    assert cli.main(["vm", "start", "--vnc", "--work", str(tmp_path)]) == 0
    assert cli.main(["vm", "stop", "--work", str(tmp_path)]) == 0
    assert calls == [("start", True), ("stop",)]


def test_a_missing_scene_file(tmp_path):
    with pytest.raises(SystemExit) as stop:
        cli.main(["render", str(tmp_path / "nope.py")])
    assert "nope.py not found" in str(stop.value)


def test_up_with_a_missing_disc_is_one_line(monkeypatch, capsys, tmp_path):
    def up(*args, **kwargs):
        raise FileNotFoundError("x.iso not found")

    monkeypatch.setattr("art98_setup.up.up", up)
    assert cli.main(["up", "--work", str(tmp_path)]) == 1
    assert capsys.readouterr().err == "error: x.iso not found\n"


def test_render_without_ffmpeg_says_so(monkeypatch, capsys, scene, tmp_path):
    monkeypatch.setattr("shutil.which", lambda tool: None)
    assert cli.main(["render", str(scene), "--work", str(tmp_path)]) == 1
    assert "error: ffmpeg isn't on PATH" in capsys.readouterr().err


# doctor

LOCAL = [
    "qemu-system-i386",
    "qemu-img",
    "mcopy",
    "7z",
    "make",
    "as",
    "i686-w64-mingw32-gcc",
]


def doctor(monkeypatch, capsys, have):
    from art98_setup import builder

    monkeypatch.setattr(
        builder,
        "doctor",
        lambda: [
            (tool, f"/usr/bin/{tool}" if tool in have else None, tool)
            for tool in ["ffmpeg", *LOCAL]
        ],
    )
    monkeypatch.setattr(
        "shutil.which", lambda tool: f"/usr/bin/{tool}" if tool in have else None
    )
    monkeypatch.delenv("ART98_ENGINE", raising=False)
    code = cli.cmd_doctor(None)
    return code, capsys.readouterr().out


def test_doctor_everything(monkeypatch, capsys):
    code, out = doctor(monkeypatch, capsys, {"ffmpeg", "docker", *LOCAL})
    assert code == 0 and "Everything is usable" in out


def test_doctor_container_only_host_passes(monkeypatch, capsys):
    code, out = doctor(monkeypatch, capsys, {"ffmpeg", "docker"})
    assert code == 0 and "VM is usable" in out
    assert "only `art98 setup` on the host needs it" in out


def test_doctor_without_ffmpeg_fails(monkeypatch, capsys):
    assert doctor(monkeypatch, capsys, {"docker"})[0] == 1


def test_doctor_nothing_fails(monkeypatch, capsys):
    code, out = doctor(monkeypatch, capsys, {"ffmpeg"})
    assert code == 1 and "sudo dnf install" in out


def test_doctor_local_only(monkeypatch, capsys):
    code, out = doctor(monkeypatch, capsys, {"ffmpeg", *LOCAL})
    assert code == 0 and "`art98 setup` is usable here" in out


def test_the_backend_flag_is_gone(capsys):
    with pytest.raises(SystemExit) as stop:
        cli.main(["ping", "--backend", "local"])
    assert stop.value.code == 2 and "Traceback" not in capsys.readouterr().err


def test_ping_warns_about_stale_programs_before_the_error(
    monkeypatch, capsys, tmp_path
):
    """The autouse fixtures silence warn; this keeps the real one on a stale temp tree."""
    root = tmp_path / "repo"
    for built, source in freshness.PROGRAMS:
        for path, when in (
            (root / "guest" / source, 2_000_000_000),
            (root / "guest" / "build" / built, 1_000_000_000),
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x")
            os.utime(path, (when, when))
    monkeypatch.setattr(freshness, "warn", REAL_WARN)
    monkeypatch.setattr(
        freshness,
        "stale_warnings",
        lambda work: REAL_STALE(work, root=root),
    )

    def attach(*args, **kwargs):
        raise NotRunning("down")

    monkeypatch.setattr(cli.service, "attach", attach)
    assert cli.main(["ping", "--work", str(tmp_path / "work")]) == 1
    lines = capsys.readouterr().err.splitlines()
    assert lines[0].startswith("warning: ") and lines[-1].startswith("error: ")


def test_setup_takes_the_work_folder_from_art98_toml(monkeypatch, tmp_path):
    (tmp_path / "art98.toml").write_text('[vm]\nwork = "elsewhere"\n')
    monkeypatch.chdir(tmp_path)
    seen = []

    class Setup:
        def __init__(self, work, **kwargs):
            seen.append(work)

        def run(self, from_stage):
            pass

    monkeypatch.setattr("art98_setup.builder.Setup", Setup)
    assert cli.main(["setup"]) == 0
    assert cli.main(["setup", "--work", "flag"]) == 0
    assert seen == [(tmp_path / "elsewhere").resolve(), (tmp_path / "flag").resolve()]


def test_up_leaves_work_to_art98_toml_unless_the_flag_is_given(monkeypatch):
    seen = []
    monkeypatch.setattr("art98_setup.up.up", lambda work, **kw: seen.append(work) or 0)
    assert cli.main(["up"]) == 0
    assert cli.main(["up", "--work", "flag"]) == 0
    assert seen == [None, Path("flag")]
