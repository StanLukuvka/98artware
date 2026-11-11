"""The container stage with no container and no VM: the real serve.Server and
host client, a fake VM and a fake agent behind a Unix socket like QEMU's COM1."""

import json
import os
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
    ContainerStage,
    Engine,
    RemoteVM,
    open_channel,
)
from art98.container.serve import MAX_DISC, Server
from art98.protocol import frame, unframe
from art98.qemu import VM, QemuError, VMConfig

TOKEN = "s3cret-token"
PPM = b"P6\n2 1\n255\n" + bytes(range(6))


class FakeVM:
    def __init__(self):
        self.calls = []

    def screenshot(self, path, format="png"):
        self.calls.append(("screenshot", format))
        Path(path).write_bytes(PPM if format == "ppm" else b"\x89PNG fake")
        return Path(path)

    def send_keys(self, *keys, hold_ms=80):
        self.calls.append(("send_keys", keys, hold_ms))

    def load_snapshot(self, name):
        if name == "missing":
            raise QemuError(f"loadvm {name}: no such snapshot")
        self.calls.append(("load_snapshot", name))

    def save_snapshot(self, name):
        self.calls.append(("save_snapshot", name))

    def insert_disc(self, iso):
        self.calls.append(("insert_disc", iso))

    def eject_disc(self):
        self.calls.append(("eject_disc",))

    def pause(self):
        self.calls.append(("pause",))

    def resume(self):
        self.calls.append(("resume",))


class FakeSerial:
    """QEMU's COM1 socket: one client at a time, answering PING like the agent."""

    def __init__(self, path: Path):
        self.path = path
        self.clients = 0
        self.listener = socket.socket(socket.AF_UNIX)
        self.listener.bind(str(path))
        self.listener.listen(1)
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while True:
            try:
                conn, _ = self.listener.accept()
            except OSError:
                return
            self.clients += 1
            self._serve(conn, self.clients)

    def _serve(self, conn, client):
        buffer = b""
        try:
            while chunk := conn.recv(65536):
                buffer += chunk
                *lines, buffer = buffer.split(b"\n")
                for line in lines:
                    request_id, verb, *_ = unframe(line).split(b" ", 2)
                    if verb == b"PING":
                        # The tick count says which client this is.
                        conn.sendall(frame(b"%s OK %d 1" % (request_id, client)))
        except OSError:
            pass
        conn.close()


class Served:
    def __init__(self, tmp_path, owner_timeout=10.0):
        self.vm = FakeVM()
        self.serial = FakeSerial(tmp_path / "serial")
        self.logs = []
        self.server = Server.listen(
            self.vm,
            self.serial.path,
            TOKEN,
            host="127.0.0.1",
            port=0,
            log=self.logs.append,
        )
        self.address = self.server.address
        self.thread = threading.Thread(
            target=self.server.serve, args=(owner_timeout,), daemon=True
        )
        self.thread.start()

    def channel(self, name, token=TOKEN):
        return open_channel(self.address, token, name, timeout=2)

    def remote(self):
        return RemoteVM(StubStage(), self.channel("control"))


class StubStage:
    running = True
    shared_dir = None

    def close(self):
        self.closed = True


@pytest.fixture
def served(tmp_path):
    served = Served(tmp_path)
    yield served
    served.server.stop()
    served.thread.join(5)
    served.serial.listener.close()


def test_wrong_token_is_refused(served):
    with pytest.raises(ContainerError, match="wrong token"):
        served.channel("control", token="guess")
    assert "refused a connection with a wrong token" in served.logs


def test_unknown_channel_is_refused(served):
    with pytest.raises(ContainerError, match="unknown channel"):
        served.channel("shell")


def test_the_agent_channel_relays_the_protocol_untouched(served):
    bridge = Bridge(served.channel("agent"), timeout=2)
    try:
        bridge.wait_ready(2)
        assert bridge.ping() == 1
    finally:
        bridge.close()


def test_a_new_agent_connection_replaces_the_old(served):
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


def test_control_screenshot_keys_revert_pause_resume(served, tmp_path):
    vm = served.remote()
    shot = vm.screenshot(tmp_path / "shot.ppm", format="ppm")
    assert shot.read_bytes() == PPM
    assert vm.screenshot(tmp_path / "shot.png").read_bytes() == b"\x89PNG fake"
    vm.send_keys("alt", "f", hold_ms=50)
    vm.load_snapshot("ready")
    vm.save_snapshot("warm")
    vm.pause()
    vm.resume()
    assert served.vm.calls == [
        ("screenshot", "ppm"),
        ("screenshot", "png"),
        ("send_keys", ("alt", "f"), 50),
        ("load_snapshot", "ready"),
        ("save_snapshot", "warm"),
        ("pause",),
        ("resume",),
    ]
    vm.quit()


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
    vm.quit()


def test_a_session_reverts_through_the_container(served):
    vm = served.remote()
    bridge = Bridge(served.channel("agent"), timeout=2)
    with session_module.Session(vm, bridge) as session:
        session.revert()
        assert ("load_snapshot", "ready") in served.vm.calls


def test_only_one_control_connection_owns_the_stage(served):
    vm = served.remote()
    with pytest.raises(ContainerError, match="already has a control connection"):
        served.channel("control")
    vm.quit()


def test_dropping_the_control_connection_stops_the_server(served):
    sock = served.channel("control")
    sock.close()
    served.thread.join(5)
    assert not served.thread.is_alive()
    assert "the control connection closed; quitting" in served.logs


def test_quit_stops_the_server(served):
    vm = served.remote()
    vm.quit()
    served.thread.join(5)
    assert not served.thread.is_alive()
    with pytest.raises(QemuError, match="closed"):
        vm.pause()


def test_a_stage_nobody_connects_to_stops_by_itself(tmp_path):
    served = Served(tmp_path, owner_timeout=0.5)
    served.thread.join(5)
    assert not served.thread.is_alive()
    assert any("no control connection" in line for line in served.logs)
    served.serial.listener.close()


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


def test_the_stage_publishes_on_loopback_only_and_keeps_secrets_out_of_argv(
    tmp_path, monkeypatch
):
    engine = fake_engine(monkeypatch, None)
    stage = ContainerStage(
        tmp_path, engine, image="art98:test", vnc=True, transport="tcp"
    )
    argv = stage.argv(
        ["-v", "/run/user/1/art98-secret-x/art98_token:/run/secrets/art98_token:ro"]
    )
    assert argv[:4] == ["/usr/bin/docker", "run", "--rm", "--init"]
    assert (
        f"ART98_HOST_UID={os.getuid()}" in argv
        and f"ART98_HOST_GID={os.getgid()}" in argv
    )
    published = [argv[i + 1] for i, arg in enumerate(argv) if arg == "-p"]
    assert published == ["127.0.0.1::7598", "127.0.0.1::5900"]
    assert ["--security-opt", "label=disable"] == argv[argv.index("--security-opt") :][
        :2
    ]
    assert f"{tmp_path.resolve()}:/work" in argv
    assert stage._token not in " ".join(argv)
    assert argv[-4:] == ["serve", "--work", "/work", "--vnc"]


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


def test_backend_comes_from_the_argument_then_the_environment(monkeypatch):
    monkeypatch.delenv("ART98_BACKEND", raising=False)
    assert session_module.backend_name() == "container"
    monkeypatch.setenv("ART98_BACKEND", "local")
    assert session_module.backend_name() == "local"
    assert session_module.backend_name("container") == "container"
    with pytest.raises(ValueError, match="unknown backend"):
        session_module.backend_name("kvm")


def test_boot_hands_the_container_backend_to_the_container(tmp_path, monkeypatch):
    (tmp_path / "image.json").write_text(json.dumps({"disk": "/work/golden.qcow2"}))
    seen = {}
    monkeypatch.setattr(
        container, "boot", lambda work, **kw: seen.update(work=work, **kw)
    )
    session_module.boot(tmp_path, backend="container")
    assert seen["work"] == tmp_path and seen["display"] == "none"


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
        stage = StubStage()
        stage.shared_dir = shared
        remote = RemoteVM(
            stage, open_channel(str(shared / "serve.sock"), TOKEN, "control", 2)
        )
        assert remote.screenshot(tmp_path / "f.ppm", format="ppm").read_bytes() == PPM
        bridge = Bridge(
            open_channel(str(shared / "serve.sock"), TOKEN, "agent", 2), timeout=2
        )
        assert bridge.ping() == 1
        bridge.close()
        remote.quit()
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


def test_a_unix_stage_mounts_its_socket_folder_and_publishes_no_port(
    tmp_path, monkeypatch
):
    engine = fake_engine(monkeypatch, None)
    stage = ContainerStage(tmp_path, engine, image="art98:test", transport="unix")
    stage._socket_dir = tmp_path / "sock"
    argv = stage.argv([])
    assert f"{tmp_path / 'sock'}:/run/art98" in argv and "-p" not in argv
    assert argv[-2:] == ["--unix", "/run/art98/serve.sock"]


def test_cli_explains_a_missing_disk_image_without_a_traceback(tmp_path, capsys):
    from art98.cli import main

    assert main(["ping", "--work", str(tmp_path), "--backend", "local"]) == 1
    error = capsys.readouterr().err
    assert error.startswith("error: ") and "run `art98 setup` first" in error
    assert "Traceback" not in error

    assert main(["ping", "--work", str(tmp_path), "--backend", "container"]) == 1
    assert "run `art98 up` first" in capsys.readouterr().err


def test_cli_explains_a_missing_container_image(tmp_path, monkeypatch, capsys):
    from art98.cli import main

    (tmp_path / "image.json").write_text("{}")

    def no_image(*args, **kwargs):
        raise ContainerError(
            "no image localhost/art98:latest; run `art98 up` to build it"
        )

    monkeypatch.setattr(container, "boot", no_image)
    scene = Path(__file__).resolve().parents[2] / "examples/mvp/mvp.py"
    for argv in (["ping"], ["render", str(scene), "-o", str(tmp_path / "x.mp4")]):
        assert main([*argv, "--work", str(tmp_path), "--backend", "container"]) == 1
        assert capsys.readouterr().err == (
            "error: no image localhost/art98:latest; run `art98 up` to build it\n"
        )


def test_a_stage_that_cannot_start_leaves_no_files(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    engine = fake_engine(monkeypatch, None)
    monkeypatch.setattr(engine, "has_image", lambda image: False)
    work = tmp_path / "work"
    work.mkdir()
    with pytest.raises(container.ImageMissing):
        ContainerStage(work, engine, image="art98:test").start()
    (work / "image.json").write_text("{}")
    with pytest.raises(ContainerError, match="no image art98:test"):
        ContainerStage(work, engine, image="art98:test").start()
    assert list(runtime.iterdir()) == []


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
    vm.quit()


@pytest.mark.parametrize("size", [0, MAX_DISC + 1, "big"])
def test_a_disc_of_the_wrong_size_is_refused_and_ends_the_connection(served, size):
    vm = served.remote()
    with pytest.raises(QemuError, match="insert_disc size"):
        vm._request("insert_disc", size=size)
    served.thread.join(5)  # the stream is out of step, so serve hung up and stopped
    assert not served.thread.is_alive()
    with pytest.raises(QemuError):
        vm.pause()
    assert served.vm.calls == []


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
        remote.quit()
    finally:
        served.server.stop()
        served.thread.join(5)
        served.serial.listener.close()
        vm.qmp = None
        vm.close()
