"""`art98 up` without an engine: the setup run's arguments and the host tool hints."""

import os

from art98.container.host import Engine
from art98_setup import builder, up


def fake_engine(monkeypatch, name):
    monkeypatch.setattr("art98.container.host.shutil.which", lambda tool: f"/usr/bin/{tool}")
    return Engine(name)


def test_setup_mounts_the_disc_read_only_and_takes_the_key_as_a_file(tmp_path, monkeypatch):
    engine = fake_engine(monkeypatch, "docker")
    monkeypatch.setenv("ART98_PRODUCT_KEY", "AAAAA-BBBBB-CCCCC-DDDDD-EEEEE")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    iso = tmp_path / "win98.iso"
    secret, cleanup = engine.secret_args(up._read_key(), up.KEY_SECRET)
    argv = up.setup_argv(engine, tmp_path / "work", iso, "art98:test", secret, watch=True)
    cleanup()
    assert secret[1].endswith(":/run/secrets/art98_key:ro")
    assert f"ART98_HOST_UID={os.getuid()}" in argv
    assert f"{iso.resolve()}:/media/win98.iso:ro" in argv
    assert "127.0.0.1:5998:5900" in argv
    assert "ART98_WATCH_DISPLAY=vnc=0.0.0.0:0" in argv
    assert "AAAAA" not in " ".join(argv)
    assert argv[argv.index("art98:test") + 1:][:1] == ["setup"]


def test_install_hints_cover_fedora_and_debian():
    hints = dict((system, packages) for system, _, packages in
                 builder.install_hints(["qemu-img", "i686-w64-mingw32-gcc"]))
    assert hints["Fedora"] == ["qemu-img", "mingw32-gcc"]
    assert hints["Debian, Ubuntu"] == ["qemu-utils", "gcc-mingw-w64-i686"]


def test_the_image_builds_from_setup_dockerfile_at_the_repo_root(monkeypatch):
    engine = fake_engine(monkeypatch, "docker")
    calls = []
    monkeypatch.setattr(Engine, "__call__", lambda self, *args, **kw: calls.append(args))
    up.build_image(engine, "art98:test")
    assert calls == [("build", "-t", "art98:test", "-f", str(up.DOCKERFILE), str(up.ROOT))]
    assert (up.ROOT / ".dockerignore").read_text().splitlines()[1] == "work/"
