"""The host end of a stage that runs in a Docker container.

The container (see serve.py) owns QEMU and the run copy of the disk. The host
keeps the Bridge, which talks to the agent through the container's relay, and
a RemoteVM, which asks the container for screenshots, keys and reverts. The
scene layer sees the same Session either way.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from art98.bridge import DEFAULT_TIMEOUT, Bridge
from art98.qemu import QemuError
from art98.session import ImageMissing

from .serve import PORT, VNC_PORT, nodelay, read_line

IMAGE = "localhost/art98:latest"
ENGINE = "docker"
TOKEN_TARGET = "art98_token"
CONNECT_TIMEOUT = 5.0
TRANSPORTS = ("unix", "tcp")
SOCKET_DIR = "/run/art98"
# A stage boots in under a second on an idle host; a busy one, or the first
# run copy off btrfs and XFS, takes longer.
START_TIMEOUT = 120.0


class ContainerError(RuntimeError):
    pass


def image_name() -> str:
    return os.environ.get("ART98_IMAGE", IMAGE)


def transport_name(transport: str | None = None) -> str:
    """How the host reaches serve: a Unix socket in a mounted folder on Linux,
    which skips the rootless port forward, and loopback TCP everywhere else.
    ART98_TRANSPORT overrides it."""
    name = transport or os.environ.get("ART98_TRANSPORT") or (
        "unix" if sys.platform == "linux" else "tcp")
    if name not in TRANSPORTS:
        raise ValueError(f"unknown transport {name!r}; choose from {', '.join(TRANSPORTS)}")
    return name


class Engine:
    """The `docker` command, or the one ART98_ENGINE names.

    art98 speaks only Docker's command line. Podman serves it through its
    podman-docker package. ART98_ENGINE only names the binary: nothing else
    changes with it.
    """

    def __init__(self, name: str | None = None):
        wanted = name or os.environ.get("ART98_ENGINE") or ENGINE
        path = shutil.which(wanted)
        if not path:
            raise ContainerError(
                f"{wanted} not found; install Docker, or podman-docker on a Podman host")
        self.name = Path(wanted).name
        self.path = path

    def __call__(self, *args: str, check: bool = True, input: bytes | None = None,
                 capture: bool = True) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                [self.path, *args], check=check, input=input,
                stdout=subprocess.PIPE if capture else None,
                stderr=subprocess.PIPE if capture else None,
            )
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or b"").decode(errors="replace").strip()
            raise ContainerError(f"{self.name} {args[0]} failed: {detail}") from None

    def has_image(self, image: str) -> bool:
        return self("image", "inspect", image, check=False).returncode == 0

    def port(self, container: str, port: int) -> tuple[str, int]:
        output = self("port", container, f"{port}/tcp").stdout.decode().split()
        if not output:
            raise ContainerError(f"{container} publishes no port {port}")
        host, _, number = output[0].rpartition(":")
        return host.strip("[]") or "127.0.0.1", int(number)

    def copy_out(self, image: str, source: str, dest: Path) -> None:
        """Copy a folder out of an image, without running it."""
        created = self("create", image).stdout.decode().strip()
        try:
            dest.mkdir(parents=True, exist_ok=True)
            self("cp", f"{created}:{source}/.", str(dest))
        finally:
            self("rm", created, check=False)

    # secrets

    def secret_args(self, data: bytes, target: str) -> tuple[list[str], "callable"]:
        """Arguments that put data at /run/secrets/<target>, and a cleanup.

        `docker run` has no secrets outside swarm, so the data goes in a private
        file, mode 0600 in a folder of our own, mounted read-only. The cleanup can
        run once the container exists: its mount keeps the file.
        """
        folder = Path(tempfile.mkdtemp(prefix="art98-secret-", dir=os.environ.get("XDG_RUNTIME_DIR")))
        path = folder / target
        path.touch(mode=0o600)
        path.write_bytes(data)
        return ["-v", f"{path}:/run/secrets/{target}:ro"], (
            lambda: shutil.rmtree(folder, ignore_errors=True))


def mount_args(work: Path) -> list[str]:
    # label=disable lets the container use work/ without relabelling the files in it.
    return ["--security-opt", "label=disable", "-v", f"{Path(work).resolve()}:/work",
            *owner_args()]


def owner_args() -> list[str]:
    """Our uid and gid, for the container to drop to on a rootful engine, so what
    it writes in work/ is ours. See art98.container.entry."""
    if not hasattr(os, "getuid"):
        return []
    return ["-e", f"ART98_HOST_UID={os.getuid()}", "-e", f"ART98_HOST_GID={os.getgid()}"]


def open_channel(address: tuple[str, int] | str, token: str, channel: str,
                 timeout: float = START_TIMEOUT, check=None) -> socket.socket:
    """Connect and pass the handshake, retrying while the guest boots.

    Until serve listens, a rootless port forward accepts and then hangs up, so
    a connection only counts once serve has answered. address is (host, port)
    or the path of a Unix socket. check, if given, is called before each try
    and raises if the stage has gone.
    """
    deadline = time.monotonic() + timeout
    while True:
        if check:
            check()
        sock = None
        try:
            if isinstance(address, (str, Path)):
                sock = socket.socket(socket.AF_UNIX)
                sock.settimeout(CONNECT_TIMEOUT)
                sock.connect(str(address))
            else:
                sock = nodelay(socket.create_connection(address, CONNECT_TIMEOUT))
            sock.settimeout(CONNECT_TIMEOUT)
            sock.sendall(f"{token}\n{channel}\n".encode())
            answer = read_line(sock).decode(errors="replace")
        except (OSError, ConnectionError):
            if sock:
                sock.close()
            if time.monotonic() > deadline:
                raise TimeoutError(f"nothing answered on {address}") from None
            time.sleep(0.1)
            continue
        if answer != "ok":
            sock.close()
            raise ContainerError(f"the stage refused the {channel} channel: "
                                 f"{answer.removeprefix('error ')}")
        sock.settimeout(None)
        return sock


class ContainerStage:
    """One running container, from `run` until the control connection closes."""

    def __init__(self, work: Path | str = "work", engine: Engine | None = None,
                 image: str | None = None, vnc: bool = False, transport: str | None = None):
        self.work = Path(work).resolve()
        self.engine = engine or Engine()
        self.image = image or image_name()
        self.vnc = vnc
        self.transport = transport_name(transport)
        self.name = f"art98-stage-{secrets.token_hex(4)}"
        self.address: tuple[str, int] | str | None = None
        self._socket_dir: Path | None = None
        self.vnc_address: tuple[str, int] | None = None
        self._token = secrets.token_hex(32)
        self._process: subprocess.Popen | None = None
        self._log = None  # the container's output, made by start()

    def argv(self, secret: list[str]) -> list[str]:
        if self.transport == "unix":
            # A private folder of ours, mounted in, holds serve's socket.
            listen = ["-v", f"{self._socket_dir}:{SOCKET_DIR}"]
            serve = ["--unix", f"{SOCKET_DIR}/serve.sock"]
        else:
            listen, serve = ["-p", f"127.0.0.1::{PORT}"], []
        if self.vnc:
            listen += ["-p", f"127.0.0.1::{VNC_PORT}"]
        return [
            self.engine.path, "run", "--rm", "--init", "--name", self.name,
            *mount_args(self.work), *listen, *secret,
            self.image, "serve", "--work", "/work", *serve, *(["--vnc"] if self.vnc else []),
        ]

    def log_tail(self, lines: int = 20) -> str:
        if self._log is None:
            return ""
        try:
            text = Path(self._log.name).read_text(errors="replace")
        except OSError:
            return ""
        return "\n".join(text.splitlines()[-lines:])

    def _fail(self, message: str) -> ContainerError:
        tail = self.log_tail()
        return ContainerError(message + (f"\n{tail}" if tail else ""))

    def start(self, timeout: float = START_TIMEOUT) -> "ContainerStage":
        if not (self.work / "image.json").exists():
            raise ImageMissing(f"{self.work / 'image.json'} not found; run `art98 up` first")
        if not self.engine.has_image(self.image):
            raise ContainerError(f"no image {self.image}; run `art98 up` to build it")
        if self.transport == "unix":
            self._socket_dir = Path(tempfile.mkdtemp(
                prefix="art98-stage-", dir=os.environ.get("XDG_RUNTIME_DIR")))
            self.address = str(self._socket_dir / "serve.sock")
        self._log = tempfile.NamedTemporaryFile(
            prefix="art98-serve-", suffix=".log", dir=os.environ.get("XDG_RUNTIME_DIR"),
            delete=False)
        secret, cleanup = self.engine.secret_args(self._token.encode(), TOKEN_TARGET)
        try:
            self._process = subprocess.Popen(
                self.argv(secret), stdin=subprocess.DEVNULL, stdout=self._log,
                stderr=subprocess.STDOUT)
            deadline = time.monotonic() + timeout
            self._wait_for_container(deadline)
            if self.transport == "tcp":
                self.address = self._wait_for_port(PORT, deadline)
            if self.vnc:
                self.vnc_address = self._wait_for_port(VNC_PORT, deadline)
        except BaseException:
            cleanup()
            self.close()
            raise
        cleanup()
        return self

    def _wait_for_container(self, deadline: float) -> None:
        """Wait until the container exists, which is when the token file is mounted."""
        while self.engine("container", "inspect", self.name, check=False).returncode != 0:
            self._check_alive()
            if time.monotonic() > deadline:
                raise self._fail(f"{self.name} did not start")
            time.sleep(0.05)

    def _wait_for_port(self, port: int, deadline: float) -> tuple[str, int]:
        while True:
            self._check_alive()
            try:
                return self.engine.port(self.name, port)
            except ContainerError:
                if time.monotonic() > deadline:
                    raise self._fail(f"{self.name} did not publish port {port}") from None
                time.sleep(0.1)

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def shared_dir(self) -> Path | None:
        """The folder shared with serve, for screenshots, when on a Unix socket."""
        return self._socket_dir

    def _check_alive(self) -> None:
        if not self.running:
            code = self._process.returncode if self._process else None
            raise self._fail(f"the stage container exited with status {code}")

    def connect(self, channel: str, timeout: float = START_TIMEOUT) -> socket.socket:
        try:
            return open_channel(self.address, self._token, channel, timeout, self._check_alive)
        except TimeoutError:
            raise self._fail(f"{self.name} did not answer on {self.address}") from None

    def close(self, timeout: float = 20.0) -> None:
        if self._process and self._process.poll() is None:
            try:
                self._process.wait(timeout)
            except subprocess.TimeoutExpired:
                self.engine("stop", "-t", "5", self.name, check=False)
                self._process.wait()
        if self._log is not None:
            self._log.close()
            Path(self._log.name).unlink(missing_ok=True)
        if self._socket_dir:
            shutil.rmtree(self._socket_dir, ignore_errors=True)


class RemoteVM:
    """The VM methods the scene layer uses, carried out by the container."""

    def __init__(self, stage: ContainerStage, sock: socket.socket):
        self.stage = stage
        self._sock = sock
        self._reader = sock.makefile("rb")
        self._lock = threading.Lock()
        self._closed = False

    @property
    def running(self) -> bool:
        return not self._closed and self.stage.running

    def _request(self, op: str, **arguments) -> tuple[dict, bytes]:
        message = json.dumps({"op": op, **arguments}).encode() + b"\n"
        with self._lock:
            if self._closed:
                raise QemuError("the stage is closed")
            try:
                self._sock.sendall(message)
                line = self._reader.readline()
                if not line:
                    raise QemuError("the stage closed the control connection")
                reply = json.loads(line)
                payload = self._read_exact(reply.get("size", 0)) if reply.get("ok") else b""
            except OSError as error:
                raise QemuError(f"the stage control connection failed: {error}") from None
        if not reply.get("ok"):
            raise QemuError(f"{op}: {reply.get('error')}")
        return reply, payload

    def _read_exact(self, size: int) -> bytes:
        data = self._reader.read(size)
        if len(data) != size:
            raise QemuError("the stage closed the connection inside a screenshot")
        return data

    def screenshot(self, path: Path | str, format: str = "png") -> Path:
        shared = self.stage.shared_dir
        reply, data = self._request("screenshot", format=format, shared=shared is not None)
        if "file" in reply:
            # Written by QEMU into the folder we share with the container.
            shutil.copyfile(shared / reply["file"], path)
        else:
            Path(path).write_bytes(data)
        return Path(path)

    def send_keys(self, *qcodes: str, hold_ms: int = 80) -> None:
        self._request("send_keys", keys=list(qcodes), hold_ms=hold_ms)

    def pause(self) -> None:
        self._request("pause")

    def resume(self) -> None:
        self._request("resume")

    def load_snapshot(self, name: str) -> None:
        self._request("revert", snapshot=name)

    def save_snapshot(self, name: str) -> None:
        """Saves into the container's run copy, which goes when the stage closes."""
        self._request("save_snapshot", snapshot=name)

    def quit(self) -> None:
        if self._closed:
            return
        try:
            self._request("quit")
        except QemuError:
            pass
        self._closed = True
        self._reader.close()
        self._sock.close()

    def close(self) -> None:
        self.quit()
        self.stage.close()


def boot(work: Path | str = "work", display: str = "none",
         ready_timeout: float = START_TIMEOUT, engine: Engine | None = None):
    """Start a stage container and connect a Session to it.

    Any display other than "none" shows the screen over VNC on a loopback
    port, since a window can't open from inside the container.
    """
    from art98.session import Session

    stage = ContainerStage(work, engine, vnc=display != "none").start(ready_timeout)
    try:
        if stage.vnc_address:
            host, port = stage.vnc_address
            print(f"art98: the stage's screen is on VNC at {host}:{port}", flush=True)
        vm = RemoteVM(stage, stage.connect("control", ready_timeout))
        try:
            bridge = Bridge(stage.connect("agent", ready_timeout), DEFAULT_TIMEOUT)
            bridge.wait_ready(30)
        except BaseException:
            vm.close()
            raise
    except BaseException:
        stage.close()
        raise
    return Session(vm, bridge)
