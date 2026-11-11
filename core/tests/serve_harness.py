"""The serve side without a VM: the real serve.Server, a fake VM, and a fake
agent behind a Unix socket like QEMU's COM1. Shared by test_container and test_serve."""

import socket
import threading
import time
from pathlib import Path

from art98.container.host import ContainerError, RemoteVM, open_channel
from art98.container.serve import Server
from art98.protocol import frame, unframe
from art98.qemu import QemuError

TOKEN = "s3cret-token"
PPM = b"P6\n2 1\n255\n" + bytes(range(6))


class FakeVM:
    """Records every call in `calls`. `running` is settable; `fail` maps a method
    name to an exception it raises; `gates` maps a method name to an Event the
    call waits on after it is recorded."""

    def __init__(self, snapshots=("ready",)):
        self.calls = []
        self.running = True
        self.disc = False
        self.fail = {}
        self.gates = {}
        self._snapshots = list(snapshots)

    def _enter(self, name, *args):
        self.calls.append((name, *args))
        if name in self.gates:
            self.gates[name].wait(5)
        if name in self.fail:
            raise self.fail[name]

    def snapshots(self):
        return list(self._snapshots)

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
        self.disc = True
        self.calls.append(("insert_disc", iso))

    def eject_disc(self):
        self.disc = False
        self._enter("eject_disc")

    def pause(self):
        self._enter("pause")

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
    def __init__(
        self, tmp_path, snapshots=("ready",), started_at="2026-11-11T20:00:00Z"
    ):
        self.vm = FakeVM(snapshots)
        self.serial = FakeSerial(tmp_path / "serial")
        self.logs = []
        self.server = Server.listen(
            self.vm,
            self.serial.path,
            TOKEN,
            host="127.0.0.1",
            port=0,
            log=self.logs.append,
            snapshots=self.vm.snapshots(),
            started_at=started_at,
        )
        self.address = self.server.address
        self.thread = threading.Thread(target=self.server.serve, daemon=True)
        self.thread.start()

    def channel(self, name, token=TOKEN):
        return open_channel(self.address, token, name, timeout=2)

    def remote(self):
        return RemoteVM(self.channel("control"))

    def remote_when_free(self, timeout=5.0):
        """remote(), retried while the previous owner's release is still running."""
        deadline = time.monotonic() + timeout
        while True:
            try:
                return self.remote()
            except ContainerError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.01)

    def close(self):
        self.server.stop()
        self.thread.join(5)
        self.serial.listener.close()
