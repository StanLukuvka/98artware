"""The CLI turns known failures into one `error:` line, and doctor reads a container-only host."""

import os

import pytest
from art98 import cli, freshness
from art98.bridge import BridgeTimeout
from art98.container.host import ContainerError
from art98.desktop import DesktopError
from art98.guestfiles import GuestBuildMissing
from art98.qemu import QemuError
from art98.recorder import RecorderError
from art98.session import ImageMissing
from art98.state import StateError

REAL_WARN = freshness.warn
REAL_STALE = freshness.stale_warnings

SCENE = "from art98.anim import Scene\n\n\nclass Demo(Scene):\n    def play(self):\n        pass\n"


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr(cli.freshness, "warn", lambda *a: None)
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
    def boot(*args, **kwargs):
        raise ImageMissing("no image")

    monkeypatch.setattr(cli, "boot", boot)
    assert cli.main(["ping", "--work", str(tmp_path)]) == 1
    assert capsys.readouterr().err.startswith("error: ")


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
    assert code == 0 and "Both backends are usable" in out


def test_doctor_container_only_host_passes(monkeypatch, capsys):
    code, out = doctor(monkeypatch, capsys, {"ffmpeg", "docker"})
    assert code == 0 and "container backend is usable" in out
    assert "only the local backend needs it" in out


def test_doctor_without_ffmpeg_fails(monkeypatch, capsys):
    assert doctor(monkeypatch, capsys, {"docker"})[0] == 1


def test_doctor_nothing_fails(monkeypatch, capsys):
    code, out = doctor(monkeypatch, capsys, {"ffmpeg"})
    assert code == 1 and "sudo dnf install" in out


def test_doctor_local_only(monkeypatch, capsys):
    code, out = doctor(monkeypatch, capsys, {"ffmpeg", *LOCAL})
    assert code == 0 and "local backend is usable" in out


def test_bad_backend_env_is_one_error_line(monkeypatch, capsys):
    monkeypatch.setenv("ART98_BACKEND", "bogus")
    assert cli.main(["ping"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: ") and "bogus" in err and err.count("\n") == 1


def test_bad_backend_flag_is_rejected_by_argparse(capsys):
    with pytest.raises(SystemExit) as stop:
        cli.main(["ping", "--backend", "bogus"])
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
        lambda work, backend: REAL_STALE(work, backend, root=root),
    )

    def boot(*args, **kwargs):
        raise ImageMissing("no image")

    monkeypatch.setattr(cli, "boot", boot)
    assert cli.main(["ping", "--work", str(tmp_path / "work")]) == 1
    lines = capsys.readouterr().err.splitlines()
    assert lines[0].startswith("warning: ") and lines[-1].startswith("error: ")
