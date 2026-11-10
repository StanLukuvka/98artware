"""The container end of a stage: QEMU, its run copy, and the link to the host.

`art98 serve` runs inside the container. It boots the `ready` snapshot on a
copy-on-write copy of the disk, then listens on one TCP port, or on a Unix
socket in a folder the host mounts, which is faster on Linux. Every connection
starts with two lines, the token and the channel name, and gets `ok` back:

- `agent` relays bytes both ways between the connection and the guest's COM1,
  untouched, so the host's Bridge speaks the agent protocol as it always has.
- `control` takes one JSON request per line and answers each with one JSON
  line, followed by raw bytes for a screenshot. On a Unix socket a screenshot
  can instead be written into the mounted folder, so no frame crosses the socket.

The first control connection owns the stage. When it closes, QEMU quits and
`serve` exits, so a host script that dies can't leave a VM running.
"""

from __future__ import annotations

import hmac
import json
import os
import signal
import socket
import tempfile
import threading
import time
from pathlib import Path

PORT = 7598
VNC_PORT = 5900
TOKEN_FILE = Path("/run/secrets/art98_token")
HANDSHAKE_TIMEOUT = 10.0
OWNER_TIMEOUT = 120.0
MAX_LINE = 4096
SCREENSHOT_FORMATS = ("ppm", "png")


def nodelay(sock: socket.socket) -> socket.socket:
    """Send small messages at once: every sync and key press is a round trip."""
    if sock.family in (socket.AF_INET, socket.AF_INET6):
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    return sock


def read_line(sock: socket.socket, limit: int = MAX_LINE) -> bytes:
    """One line without its newline, read a byte at a time so nothing after it is taken."""
    data = bytearray()
    while len(data) < limit:
        byte = sock.recv(1)
        if not byte:
            raise ConnectionError("connection closed during the handshake")
        if byte == b"\n":
            return bytes(data)
        data += byte
    raise ConnectionError("handshake line too long")


class ControlError(RuntimeError):
    pass


class Server:
    """Answers the host on one listening socket until the owner goes away.

    vm is anything with the VM methods used here (a real art98.qemu.VM in the
    container, a fake in tests); serial_path is the guest's COM1 socket.
    """

    def __init__(self, vm, serial_path: Path | str, token: str,
                 listener: socket.socket, log=print):
        self.vm = vm
        self.serial_path = str(serial_path)
        self._token = token.encode()
        self._listener = listener
        self._log = log
        self._stop = threading.Event()
        self._owner_seen = threading.Event()
        self._relay_lock = threading.Lock()
        self._relay: tuple[socket.socket, socket.socket] | None = None
        self._vm_lock = threading.Lock()
        self._shots = Path(tempfile.mkdtemp(
            prefix="art98-shots-", dir="/dev/shm" if os.path.isdir("/dev/shm") else None))
        # The folder holding a Unix socket is shared with the host.
        self._shared = (Path(listener.getsockname()).parent
                        if listener.family == socket.AF_UNIX else None)

    @classmethod
    def listen(cls, vm, serial_path, token: str, host: str = "0.0.0.0", port: int = PORT,
               unix: Path | str | None = None, log=print) -> "Server":
        """Listen on TCP, or on the Unix socket `unix` if given."""
        if unix:
            Path(unix).unlink(missing_ok=True)
            listener = socket.socket(socket.AF_UNIX)
            listener.bind(str(unix))
            # The folder is the host's private one; the token guards the rest.
            os.chmod(unix, 0o666)
        else:
            listener = socket.socket(socket.AF_INET)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((host, port))
        listener.listen(8)
        return cls(vm, serial_path, token, listener, log)

    @property
    def address(self) -> tuple[str, int] | str:
        name = self._listener.getsockname()
        return name if isinstance(name, str) else name[:2]

    def stop(self) -> None:
        self._stop.set()
        try:
            self._listener.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def serve(self, owner_timeout: float = OWNER_TIMEOUT) -> None:
        """Accept connections until the owner's control connection ends or quit is asked."""
        self._listener.settimeout(0.5)
        started = time.monotonic()
        try:
            while not self._stop.is_set():
                if not self._owner_seen.is_set() and time.monotonic() - started > owner_timeout:
                    self._log(f"no control connection within {owner_timeout:.0f}s; quitting")
                    break
                try:
                    conn, _ = self._listener.accept()
                except TimeoutError:
                    continue
                except OSError:
                    break
                threading.Thread(target=self._handshake, args=(conn,), daemon=True).start()
        finally:
            if self._shared:
                Path(self._listener.getsockname()).unlink(missing_ok=True)
                for path in self._shared.glob("frame.*"):
                    path.unlink(missing_ok=True)
            self._listener.close()
            self._drop_relay()
            for path in self._shots.iterdir():
                path.unlink(missing_ok=True)
            self._shots.rmdir()

    # ---- connections ----

    def _handshake(self, conn: socket.socket) -> None:
        nodelay(conn)
        conn.settimeout(HANDSHAKE_TIMEOUT)
        try:
            token = read_line(conn)
            channel = read_line(conn).decode("ascii", "replace")
        except (OSError, ConnectionError):
            conn.close()
            return
        if not hmac.compare_digest(token, self._token):
            self._log("refused a connection with a wrong token")
            self._refuse(conn, "wrong token")
            return
        conn.settimeout(None)
        if channel == "agent":
            self._start_relay(conn)
        elif channel == "control":
            if self._owner_seen.is_set():
                self._refuse(conn, "the stage already has a control connection")
                return
            self._owner_seen.set()
            conn.sendall(b"ok\n")
            self._control(conn)
        else:
            self._refuse(conn, f"unknown channel {channel!r}")

    @staticmethod
    def _refuse(conn: socket.socket, reason: str) -> None:
        try:
            conn.sendall(f"error {reason}\n".encode())
        except OSError:
            pass
        conn.close()

    # agent: a byte relay to COM1, one client at a time

    def _start_relay(self, conn: socket.socket) -> None:
        self._drop_relay()  # QEMU's serial socket takes one client; the newest wins
        serial = socket.socket(socket.AF_UNIX)
        deadline = time.monotonic() + 5
        while True:
            try:
                serial.connect(self.serial_path)
                break
            except (ConnectionRefusedError, FileNotFoundError):
                if time.monotonic() > deadline:
                    self._refuse(conn, "the guest's serial port is not reachable")
                    serial.close()
                    return
                time.sleep(0.05)
        with self._relay_lock:
            self._relay = (conn, serial)
        conn.sendall(b"ok\n")
        threading.Thread(target=self._pump, args=(conn, serial), daemon=True).start()
        threading.Thread(target=self._pump, args=(serial, conn), daemon=True).start()

    def _pump(self, source: socket.socket, sink: socket.socket) -> None:
        try:
            while chunk := source.recv(65536):
                sink.sendall(chunk)
        except OSError:
            pass
        for sock in (source, sink):
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        with self._relay_lock:
            if self._relay and source in self._relay:
                self._relay = None
        source.close()

    def _drop_relay(self) -> None:
        with self._relay_lock:
            relay, self._relay = self._relay, None
        if relay:
            for sock in relay:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    # control: JSON lines

    def _control(self, conn: socket.socket) -> None:
        reader = conn.makefile("rb")
        try:
            while not self._stop.is_set():
                line = reader.readline(MAX_LINE)
                if not line:
                    self._log("the control connection closed; quitting")
                    break
                try:
                    request = json.loads(line)
                    reply, payload = self.handle(request)
                except (ValueError, TypeError, KeyError, ControlError) as error:
                    reply, payload = {"ok": False, "error": str(error)}, b""
                except Exception as error:  # QEMU errors and the like go back to the host
                    reply, payload = {"ok": False, "error": f"{type(error).__name__}: {error}"}, b""
                conn.sendall(json.dumps(reply).encode() + b"\n" + payload)
                if reply.get("ok") and request.get("op") == "quit":
                    break
        except OSError:
            self._log("the control connection failed; quitting")
        finally:
            reader.close()
            conn.close()
            self.stop()

    def handle(self, request: dict) -> tuple[dict, bytes]:
        if not isinstance(request, dict):
            raise ControlError("a request is a JSON object")
        op = request.get("op")
        with self._vm_lock:
            if op == "screenshot":
                fmt = request.get("format", "ppm")
                if fmt not in SCREENSHOT_FORMATS:
                    raise ControlError(f"format must be one of {', '.join(SCREENSHOT_FORMATS)}")
                if request.get("shared") and self._shared:
                    name = f"frame.{fmt}"
                    self.vm.screenshot(self._shared / name, format=fmt)
                    return {"ok": True, "file": name}, b""
                path = self._shots / f"frame.{fmt}"
                self.vm.screenshot(path, format=fmt)
                data = path.read_bytes()
                return {"ok": True, "size": len(data)}, data
            if op == "send_keys":
                keys = request["keys"]
                if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys):
                    raise ControlError("keys is a list of QEMU key names")
                self.vm.send_keys(*keys, hold_ms=int(request.get("hold_ms", 80)))
            elif op == "revert":
                self.vm.load_snapshot(str(request.get("snapshot", "ready")))
            elif op == "save_snapshot":
                self.vm.save_snapshot(str(request["snapshot"]))
            elif op == "pause":
                self.vm.pause()
            elif op == "resume":
                self.vm.resume()
            elif op == "quit":
                pass
            else:
                raise ControlError(f"unknown op {op!r}")
        return {"ok": True}, b""


def read_token(path: Path | str | None = None) -> str:
    path = Path(path or os.environ.get("ART98_TOKEN_FILE") or TOKEN_FILE)
    try:
        token = path.read_text().strip()
    except FileNotFoundError:
        raise SystemExit(f"error: no token at {path}; pass one as the secret art98_token") from None
    if not token:
        raise SystemExit(f"error: the token in {path} is empty")
    return token


def run(work: Path | str = "/work", port: int = PORT, token_file: Path | str | None = None,
        vnc: bool = False, ready_timeout: float = 60.0, unix: Path | str | None = None) -> int:
    """Boot the stage and serve it. Used by `art98 serve` inside the container."""
    from art98.bridge import Bridge
    from art98.qemu import VM, VMConfig
    from art98.session import SNAPSHOT, IMAGE_FILE, private_stage

    token = read_token(token_file)

    def log(message: str) -> None:
        print(f"[serve] {message}", flush=True)

    def on_term(signum, _frame):
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, on_term)
    with private_stage(work) as stage:
        config = VMConfig.from_json(json.loads((stage / IMAGE_FILE).read_text()))
        config.loadvm = SNAPSHOT
        config.display = f"vnc=0.0.0.0:{VNC_PORT - 5900}" if vnc else "none"
        started = time.monotonic()
        with VM(config, log=Path(work) / "qemu.log") as vm:
            probe = Bridge.connect(vm.serial_path)
            try:
                probe.wait_ready(ready_timeout)
            finally:
                probe.close()
            server = Server.listen(vm, vm.serial_path, token, port=port, unix=unix, log=log)
            where = unix or f"port {port}"
            log(f"guest ready in {time.monotonic() - started:.2f}s; listening on {where}")
            server.serve()
    log("stopped")
    return 0
