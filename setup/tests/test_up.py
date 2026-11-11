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
    monkeypatch.setattr(
        up, "boot", lambda *a, **k: (_ for _ in ()).throw(ContainerError("stop"))
    )
    with pytest.raises(ContainerError):
        up.up(tmp_path, engine=engine, log=lines.append)
    assert "[up] warning: old image" in lines
