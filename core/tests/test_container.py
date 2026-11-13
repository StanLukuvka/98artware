"""The container stage with no container and no VM: the real serve.Server and
host client, a fake VM and a fake agent behind a Unix socket like QEMU's COM1."""

import json
import socket
import stat
import threading
import time
from pathlib import Path

import pytest
from art98 import session as session_module
from art98.bridge import Bridge, BridgeError
from art98.container import host as container
from art98.container.host import (
    ContainerError,
    Engine,
    RemoteVM,
    open_channel,
)
from art98.container.serve import MAX_DISC, Server
from art98.qemu import VM, QemuError, VMConfig
from serve_harness import PPM, TOKEN, FakeSerial, FakeVM, Served


@pytest.fixture
def served(tmp_path):
    served = Served(tmp_path)
    yield served
    served.close()


def test_wrong_token_is_refused(served):
    with pytest.raises(ContainerError, match="wrong token"):
        served.channel("control", token="guess")
    assert "refused a connection with a wrong token" in served.logs


def test_unknown_channel_is_refused(served):
    with pytest.raises(ContainerError, match="unknown channel"):
        served.channel("shell")


def test_the_agent_channel_needs_a_control_connection(served):
    with pytest.raises(ContainerError, match="no control connection"):
        served.channel("agent")


def test_the_agent_channel_relays_the_protocol_untouched(served):
    owner = served.channel("control")
    bridge = Bridge(served.channel("agent"), timeout=2)
    try:
        bridge.wait_ready(2)
        assert bridge.ping() == 1
    finally:
        bridge.close()
        owner.close()


def test_a_new_agent_connection_replaces_the_old(served):
    owner = served.channel("control")
    first = Bridge(served.channel("agent"), timeout=2)
    assert first.ping() == 1
    second = Bridge(served.channel("agent"), timeout=2)
    try:
        assert second.ping() == 2
        with pytest.raises(BridgeError):
            first.ping(timeout=2)
    finally:
        first.close()
        second.close()
        owner.close()


def test_control_screenshot_keys_revert_pause_resume(served, tmp_path):
    vm = served.remote()
    shot = vm.screenshot(tmp_path / "shot.ppm", format="ppm")
    assert shot.read_bytes() == PPM
    assert vm.screenshot(tmp_path / "shot.png").read_bytes() == b"\x89PNG fake"
    vm.send_keys("alt", "f", hold_ms=50)
    vm.load_snapshot("ready")
    vm.pause()
    vm.resume()
    assert served.vm.calls == [
        ("screenshot", "ppm"),
        ("screenshot", "png"),
        ("send_keys", ("alt", "f"), 50),
        ("eject_disc",),
        ("load_snapshot", "ready"),
        ("pause",),
        ("resume",),
    ]
    vm.close()


def test_errors_come_back_as_qemu_errors_and_the_link_stays_up(served, tmp_path):
    vm = served.remote()
    with pytest.raises(QemuError, match="no such snapshot"):
        vm.load_snapshot("missing")
    with pytest.raises(QemuError, match="format must be"):
        vm.screenshot(tmp_path / "x.bmp", format="bmp")
    with pytest.raises(QemuError, match="unknown op"):
        vm._request("shell", command="rm -rf /")
    with pytest.raises(QemuError, match="list of QEMU key names"):
        vm._request("send_keys", keys="alt")
    vm.pause()  # still answering
    vm.close()


def test_a_session_reverts_through_the_container(served):
    vm = served.remote()
    bridge = Bridge(served.channel("agent"), timeout=2)
    with session_module.Session(vm, bridge) as session:
        session.revert()
        assert ("load_snapshot", "ready") in served.vm.calls


def test_only_one_control_connection_owns_the_stage(served):
    vm = served.remote()
    with pytest.raises(ContainerError, match="busy"):
        served.channel("control")
    vm.close()
    served.remote_when_free().close()  # accepted again once the first is released


def test_dropping_the_control_connection_releases_the_stage(served):
    sock = served.channel("control")
    sock.close()
    deadline = time.monotonic() + 5
    while "the control connection was released" not in served.logs:
        assert time.monotonic() < deadline
        time.sleep(0.02)
    assert served.thread.is_alive()
    served.channel("control").close()


def test_open_channel_waits_for_a_forward_that_hangs_up_first(tmp_path):
    """A rootless port forward accepts before serve listens, then hangs up."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(4)
    address = listener.getsockname()

    def forward():
        for attempt in range(3):
            conn, _ = listener.accept()
            if attempt < 2:
                conn.close()
                continue
            conn.recv(1024)
            conn.sendall(b"ok\n")
            time.sleep(0.5)
            conn.close()

    threading.Thread(target=forward, daemon=True).start()
    sock = open_channel(address, TOKEN, "control", timeout=5)
    sock.close()
    listener.close()


def test_open_channel_gives_up_when_the_stage_dies():
    def check():
        raise ContainerError("the stage container exited with status 1")

    with pytest.raises(ContainerError, match="exited"):
        open_channel(("127.0.0.1", 9), TOKEN, "control", timeout=5, check=check)


# ---- host side, without an engine ----


def fake_engine(monkeypatch, name):
    monkeypatch.setattr(container.shutil, "which", lambda tool: f"/usr/bin/{tool}")
    return Engine(name)


def test_the_engine_is_docker_unless_art98_engine_names_another_binary(monkeypatch):
    monkeypatch.delenv("ART98_ENGINE", raising=False)
    engine = fake_engine(monkeypatch, None)
    assert (engine.name, engine.path) == ("docker", "/usr/bin/docker")
    monkeypatch.setenv("ART98_ENGINE", "/opt/bin/docker-ce")
    assert Engine().name == "docker-ce"
    monkeypatch.setattr(container.shutil, "which", lambda tool: None)
    with pytest.raises(ContainerError, match="podman-docker"):
        Engine()


def test_a_secret_is_a_private_file_mounted_read_only(tmp_path, monkeypatch):
    engine = fake_engine(monkeypatch, None)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    args, cleanup = engine.secret_args(b"tok", "art98_token")
    source = Path(args[1].split(":")[0])
    assert args[0] == "-v" and args[1].endswith(":/run/secrets/art98_token:ro")
    assert source.read_bytes() == b"tok"
    assert stat.S_IMODE(source.stat().st_mode) == 0o600
    cleanup()
    assert not source.exists()


# ---- session ----


def test_a_disk_recorded_in_the_container_is_found_beside_image_json(tmp_path):
    (tmp_path / "golden.qcow2").write_bytes(b"disk")
    config = {"disk": "/work/golden.qcow2"}
    assert session_module.image_disk(tmp_path, config) == tmp_path / "golden.qcow2"
    (tmp_path / "image.json").write_text(json.dumps(config))
    with session_module.private_stage(tmp_path) as stage:
        assert (stage / "golden.qcow2").read_bytes() == b"disk"
    missing = {"disk": str(tmp_path / "elsewhere" / "other.qcow2")}
    assert session_module.image_disk(tmp_path, missing) == Path(missing["disk"])


def test_on_a_unix_socket_screenshots_go_through_the_shared_folder(tmp_path):
    import tempfile

    shared = Path(
        tempfile.mkdtemp(prefix="art98-t-")
    )  # short: socket paths are limited
    vm = FakeVM()
    serial = FakeSerial(tmp_path / "serial")
    server = Server.listen(
        vm, serial.path, TOKEN, unix=shared / "serve.sock", log=lambda m: None
    )
    thread = threading.Thread(target=server.serve, daemon=True)
    thread.start()
    try:
        remote = RemoteVM(
            open_channel(str(shared / "serve.sock"), TOKEN, "control", 2),
            shared_dir=shared,
        )
        assert remote.screenshot(tmp_path / "f.ppm", format="ppm").read_bytes() == PPM
        bridge = Bridge(
            open_channel(str(shared / "serve.sock"), TOKEN, "agent", 2), timeout=2
        )
        assert bridge.ping() == 1
        bridge.close()
        remote.close()
        server.stop()
        thread.join(5)
        assert not thread.is_alive()
        assert list(shared.iterdir()) == []  # the socket and the frame are gone
    finally:
        server.stop()
        serial.listener.close()
        shared.rmdir()


def test_the_transport_is_a_unix_socket_on_linux_unless_asked(monkeypatch):
    monkeypatch.delenv("ART98_TRANSPORT", raising=False)
    monkeypatch.setattr(container.sys, "platform", "linux")
    assert container.transport_name() == "unix"
    monkeypatch.setattr(container.sys, "platform", "darwin")
    assert container.transport_name() == "tcp"
    monkeypatch.setenv("ART98_TRANSPORT", "unix")
    assert container.transport_name() == "unix"
    with pytest.raises(ValueError):
        container.transport_name("pipe")


def test_cli_says_the_vm_is_not_running_without_a_traceback(tmp_path, capsys):
    from art98.cli import main

    scene = Path(__file__).resolve().parents[2] / "recipes/scenes/mvp/mvp.py"
    for argv in (["ping"], ["render", str(scene), "-o", str(tmp_path / "x.mp4")]):
        assert main([*argv, "--work", str(tmp_path)]) == 1
        error = capsys.readouterr().err
        assert error.startswith("error: the VM is not running")
        assert "run `art98 vm start`" in error and "Traceback" not in error


# ---- the image's entry point ----

ROOTLESS = "         0       1000          1\n         1     524288      65536\n"
ROOTFUL = "         0          0 4294967295\n"
HOST = {"ART98_HOST_UID": "1000", "ART98_HOST_GID": "1000"}


def test_the_entry_point_drops_to_the_host_user_only_on_a_rootful_engine():
    from art98.container.entry import host_user, is_rootful

    assert is_rootful(ROOTFUL) and not is_rootful(ROOTLESS)
    assert not is_rootful("0 0 65536\n")  # a namespace that maps part of the range
    assert host_user(HOST, ROOTFUL, uid=0) == (1000, 1000)
    assert (
        host_user(HOST, ROOTLESS, uid=0) is None
    )  # root here is the host user already
    assert (
        host_user(HOST, ROOTFUL, uid=1000) is None
    )  # run with --user: nothing to drop
    assert host_user({}, ROOTFUL, uid=0) is None  # an old host passes nothing
    assert host_user({**HOST, "ART98_HOST_UID": "0"}, ROOTFUL, uid=0) is None
    assert host_user({**HOST, "ART98_HOST_GID": "x"}, ROOTFUL, uid=0) is None


def test_the_entry_point_changes_nothing_without_a_uid_map(tmp_path, monkeypatch):
    from art98.container import entry

    def refuse(*_):
        raise AssertionError("dropped privileges")

    monkeypatch.setattr(entry.os, "setuid", refuse)
    environ = dict(HOST)
    entry.become_host_user(environ, tmp_path / "missing")
    (tmp_path / "uid_map").write_text(ROOTLESS)
    entry.become_host_user(environ, tmp_path / "uid_map")
    assert "HOME" not in environ


def test_insert_and_eject_disc_carry_the_bytes(served):
    vm = served.remote()
    iso = bytes(range(256)) * 20
    vm.insert_disc(iso)
    vm.eject_disc()
    vm.pause()  # the stream is still in step after the payload
    assert served.vm.calls == [("insert_disc", iso), ("eject_disc",), ("pause",)]
    vm.close()


@pytest.mark.parametrize("size", [0, MAX_DISC + 1, "big"])
def test_a_disc_of_the_wrong_size_is_refused_and_ends_the_connection(served, size):
    vm = served.remote()
    with pytest.raises(QemuError, match="insert_disc size"):
        vm._request("insert_disc", size=size)
    with pytest.raises(QemuError):
        vm.pause()  # serve hung up: the stream was out of step
    again = served.remote_when_free()  # the slot is free once the release is done
    assert served.thread.is_alive()
    # the bad request ran nothing; only the release's cleanup shows
    assert served.vm.calls == [("eject_disc",), ("pause",)]
    again.close()


def test_the_real_vm_methods_run_behind_serve(tmp_path):
    """serve calls vm.insert_disc(data) / eject_disc() on the real qemu.VM, QMP stubbed."""

    class StubQMP:
        def __init__(self):
            self.calls = []
            self.medium = False

        def execute(self, command, **arguments):
            self.calls.append((command, arguments))
            if command == "query-block":
                cd = {"device": "ide1-cd0", "qdev": "/machine/unattached/device[9]"}
                return [
                    {"device": "ide0-hd0"},
                    dict(cd, inserted={"file": "x"}) if self.medium else cd,
                ]
            if command == "blockdev-change-medium":
                self.medium = True
            if command == "blockdev-remove-medium":
                self.medium = False

    vm = VM(VMConfig(disk=tmp_path / "unused"))
    vm.qmp = StubQMP()
    vm._process = type("Alive", (), {"poll": lambda self: None})()
    served = Served(tmp_path)
    served.server.vm = vm
    try:
        remote = served.remote()
        remote.insert_disc(b"ISO-BYTES")
        change = next(a for c, a in vm.qmp.calls if c == "blockdev-change-medium")
        assert Path(change["filename"]).read_bytes() == b"ISO-BYTES"
        assert Path(change["filename"]).parent == vm._dir
        assert change["device"] == "ide1-cd0" and change["format"] == "raw"
        remote.eject_disc()
        names = [c for c, _ in vm.qmp.calls if c != "query-block"]
        assert names[-3:] == [
            "blockdev-open-tray",
            "blockdev-remove-medium",
            "blockdev-close-tray",
        ]
        assert (
            "blockdev-remove-medium",
            {"id": "/machine/unattached/device[9]"},
        ) in vm.qmp.calls
        remote.eject_disc()  # empty drive: nothing more is sent
        assert [c for c, _ in vm.qmp.calls].count("blockdev-open-tray") == 1
        remote.close()
    finally:
        served.close()
        vm.qmp = None
        vm._process = None
        vm.close()


def test_the_settings_transport_beats_the_platform_but_not_the_env(monkeypatch):
    monkeypatch.delenv("ART98_TRANSPORT", raising=False)
    monkeypatch.setattr(container.sys, "platform", "linux")
    assert container.transport_name(default="tcp") == "tcp"
    monkeypatch.setenv("ART98_TRANSPORT", "unix")
    assert container.transport_name(default="tcp") == "unix"
