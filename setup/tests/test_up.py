"""`art98 up` without an engine: the setup run's arguments and the host tool hints."""

import os
import subprocess
from pathlib import Path

import pytest
from art98.container.host import ContainerError, Engine
from art98_setup import builder, up


def fake_engine(monkeypatch, name):
    monkeypatch.setattr(
        "art98.container.host.shutil.which", lambda tool: f"/usr/bin/{tool}"
    )
    return Engine(name)


def test_setup_mounts_the_disc_read_only_and_takes_the_key_as_a_file(
    tmp_path, monkeypatch
):
    engine = fake_engine(monkeypatch, "docker")
    monkeypatch.setenv("ART98_PRODUCT_KEY", "AAAAA-BBBBB-CCCCC-DDDDD-EEEEE")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    iso = tmp_path / "win98.iso"
    secret, cleanup = engine.secret_args(up._read_key(), up.KEY_SECRET)
    argv = up.setup_argv(
        engine, tmp_path / "work", iso, "art98:test", secret, watch=True
    )
    cleanup()
    assert secret[1].endswith(":/run/secrets/art98_key:ro")
    assert f"ART98_HOST_UID={os.getuid()}" in argv
    assert f"{iso.resolve()}:/media/win98.iso:ro" in argv
    assert "127.0.0.1:5998:5900" in argv
    assert "ART98_WATCH_DISPLAY=vnc=0.0.0.0:0" in argv
    assert "AAAAA" not in " ".join(argv)
    assert argv[argv.index("art98:test") + 1 :][:1] == ["setup"]


def test_install_hints_cover_fedora_and_debian():
    hints = {
        system: packages
        for system, _, packages in builder.install_hints(
            ["qemu-img", "i686-w64-mingw32-gcc"]
        )
    }
    assert hints["Fedora"] == ["qemu-img", "mingw32-gcc"]
    assert hints["Debian, Ubuntu"] == ["qemu-utils", "gcc-mingw-w64-i686"]


def scripted_engine(
    monkeypatch, help_text=b"", stored="sha256:abc", built="sha256:abc"
):
    """A docker whose build reports `built` and whose image store holds `stored`."""
    engine = fake_engine(monkeypatch, "docker")
    calls = []

    def run(self, *args, **kw):
        calls.append(args)
        out = subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")
        if args[:2] == ("build", "--help"):
            out.stdout = help_text
        elif args[0] == "build":
            Path(args[args.index("--iidfile") + 1]).write_text(built)
        elif args[:2] == ("image", "inspect"):
            out.stdout = stored.encode()
        return out

    monkeypatch.setattr(Engine, "__call__", run)
    return engine, calls


def test_the_image_builds_from_setup_dockerfile_at_the_repo_root(monkeypatch):
    engine, calls = scripted_engine(monkeypatch)
    up.build_image(engine, "art98:test")
    build = next(c for c in calls if c[0] == "build" and c[1] != "--help")
    assert build[1] == "--iidfile"
    assert build[3:] == ("-t", "art98:test", "-f", str(up.DOCKERFILE), str(up.ROOT))
    assert (up.ROOT / ".dockerignore").read_text().splitlines()[1] == "work/"


def test_the_build_loads_the_image_only_where_the_cli_has_load(monkeypatch):
    engine, calls = scripted_engine(monkeypatch, help_text=b"      --load   Shorthand")
    up.build_image(engine, "art98:test")
    assert "--load" in next(c for c in calls if c[0] == "build" and c[1] != "--help")
    engine, calls = scripted_engine(monkeypatch, help_text=b"podman build")
    up.build_image(engine, "art98:test")
    assert all("--load" not in c for c in calls)


def test_an_image_ID_without_the_sha256_prefix_still_matches(monkeypatch):
    engine, _ = scripted_engine(monkeypatch, stored="abc\n", built="sha256:abc")
    up.build_image(engine, "art98:test")


def test_a_build_that_leaves_the_old_image_fails_loudly(monkeypatch):
    engine, _ = scripted_engine(monkeypatch, stored="sha256:old", built="sha256:new")
    with pytest.raises(ContainerError, match="did not store it"):
        up.build_image(engine, "art98:test")


def test_up_warns_when_it_reuses_an_old_image(tmp_path, monkeypatch):
    engine = fake_engine(monkeypatch, "docker")
    monkeypatch.setattr(up, "inspect_created", lambda eng, image: (True, 1.0))
    monkeypatch.setattr(up, "container_warning", lambda created, image: ["old image"])
    (tmp_path / "image.json").write_text("{}")
    lines = []
    monkeypatch.setattr(up, "ROOT", tmp_path)  # the guest programs are "there"
    (tmp_path / "guest" / "build").mkdir(parents=True)
    (tmp_path / "guest" / "build" / "view.exe").write_bytes(b"x")
    (tmp_path / "guest" / "build" / "sources.sha256").write_text("")
    calls = []
    monkeypatch.setattr(Engine, "__call__", lambda self, *a, **k: calls.append(a))
    monkeypatch.setattr(up.subprocess, "run", lambda *a, **k: calls.append(a))
    assert up.up(tmp_path, engine=engine, log=lines.append) == 0
    assert calls == []  # setup is done: no run/start/snapshot of any VM
    assert not hasattr(up, "boot")
    assert "[up] warning: old image" in lines
    assert "art98 vm start" in lines[-1]


def test_up_copies_out_when_the_digest_file_is_missing(tmp_path, monkeypatch):
    engine = fake_engine(monkeypatch, "docker")
    monkeypatch.setattr(up, "inspect_created", lambda eng, image: (True, 1.0))
    monkeypatch.setattr(up, "container_warning", lambda created, image: [])
    monkeypatch.setattr(up, "ROOT", tmp_path)
    (tmp_path / "guest" / "build").mkdir(parents=True)
    (tmp_path / "guest" / "build" / "view.exe").write_bytes(b"x")  # an old build
    (tmp_path / "image.json").write_text("{}")
    copied = []
    monkeypatch.setattr(Engine, "copy_out", lambda self, *a: copied.append(a))
    assert up.up(tmp_path, engine=engine, log=lambda _: None) == 0
    assert len(copied) == 1


def test_up_resolves_a_missing_work_through_art98_toml(tmp_path, monkeypatch):
    (tmp_path / "art98.toml").write_text('[vm]\nwork = "elsewhere"\n')
    monkeypatch.chdir(tmp_path)
    engine = fake_engine(monkeypatch, "docker")
    monkeypatch.setattr(up, "inspect_created", lambda eng, image: (True, 1.0))
    monkeypatch.setattr(up, "container_warning", lambda created, image: [])
    monkeypatch.setattr(up, "ROOT", tmp_path)
    (tmp_path / "guest" / "build").mkdir(parents=True)
    (tmp_path / "guest" / "build" / "view.exe").write_bytes(b"x")
    (tmp_path / "guest" / "build" / "sources.sha256").write_text("")
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "image.json").write_text("{}")
    lines = []
    assert up.up(engine=engine, log=lines.append) == 0
    assert f"{tmp_path / 'elsewhere'}/image.json exists" in lines[-2]


def test_watch_publishes_vnc_on_the_configured_bind(tmp_path, monkeypatch):
    (tmp_path / "art98.toml").write_text(
        '[ports]\nbind = "0.0.0.0"\nsetup_vnc = 5999\n'
    )
    monkeypatch.chdir(tmp_path)
    engine = fake_engine(monkeypatch, "docker")
    argv = up.setup_argv(engine, tmp_path, tmp_path / "x.iso", "art98:test", [], True)
    assert "0.0.0.0:5999:5900" in argv
    assert not any(a.startswith("127.0.0.1") for a in argv)


def test_the_key_prompt_is_visible_and_stripped(monkeypatch):
    monkeypatch.delenv("ART98_PRODUCT_KEY", raising=False)
    prompts = []
    monkeypatch.setattr(
        "builtins.input", lambda p="": prompts.append(p) or " AAAAA-BBBBB \n"
    )
    assert up._read_key() == b"AAAAA-BBBBB"
    assert prompts == ["Windows 98 product key: "]


def test_a_failed_setup_hint_does_not_promise_a_clean_resume(tmp_path, monkeypatch):
    engine = fake_engine(monkeypatch, "docker")
    monkeypatch.setattr(up, "inspect_created", lambda eng, image: (True, 1.0))
    monkeypatch.setattr(up, "container_warning", lambda created, image: [])
    monkeypatch.setattr(up, "ROOT", tmp_path)
    (tmp_path / "guest" / "build").mkdir(parents=True)
    (tmp_path / "guest" / "build" / "view.exe").write_bytes(b"x")
    (tmp_path / "guest" / "build" / "sources.sha256").write_text("")
    iso = tmp_path / "win98.iso"
    iso.write_bytes(b"x")
    monkeypatch.setenv("ART98_PRODUCT_KEY", "AAAAA-BBBBB-CCCCC-DDDDD-EEEEE")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(
        up.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 3)
    )
    lines = []
    assert up.up(tmp_path / "work", iso, engine=engine, log=lines.append) == 3
    assert "see the error above" in lines[-1]
    assert "to resume" not in lines[-1]
