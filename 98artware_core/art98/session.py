"""A running stage: the VM, the bridge to it, and frame capture."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from .bridge import Bridge
from .qemu import VM, VMConfig

SNAPSHOT = "ready"
IMAGE_FILE = "image.json"
BACKENDS = ("local", "container")


class ImageMissing(FileNotFoundError):
    """The work directory has no finished image: setup hasn't run there."""


def backend_name(backend: str | None = None) -> str:
    """The backend to use: the argument, else ART98_BACKEND, else "local"."""
    name = backend or os.environ.get("ART98_BACKEND") or "local"
    if name not in BACKENDS:
        raise ValueError(f"unknown backend {name!r}; choose from {', '.join(BACKENDS)}")
    return name


def image_disk(work: Path | str, config: dict) -> Path:
    """The disk image.json names, or the file of that name beside it.

    A work folder can be prepared in the container, which records
    /work/golden.qcow2, and used on the host, or the other way round.
    """
    disk = Path(config["disk"])
    beside = Path(work) / disk.name
    return disk if disk.exists() or not beside.exists() else beside


class FrameRecorder:
    """Encodes captured frames to a video, one explicit frame at a time.

    Frames are taken when the script says so, not on a wall clock, so a slow
    host produces the same video as a fast one.
    """

    def __init__(self, session: "Session", path: Path | str, fps: int = 30,
                 lossless: bool = False):
        self._session = session
        self._fps = fps
        self._dir = Path(tempfile.mkdtemp(prefix="art98-frames-"))
        self._frame = self._dir / "frame.ppm"
        self.count = 0
        codec = (["-c:v", "ffv1", "-pix_fmt", "bgr0"] if lossless else
                 ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-crf", "12"])
        self._ffmpeg = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-c:v", "ppm",
             "-framerate", str(fps), "-i", "-", *codec, str(path)],
            stdin=subprocess.PIPE,
        )

    def frame(self, hold: int = 1) -> None:
        """Wait for the guest to settle, capture, and write hold copies."""
        self._session.bridge.sync()
        self._capture(hold)

    def live(self, seconds: float, stop_condition: Callable[[], bool] | None = None) -> None:
        """Record something that moves by itself, such as a screensaver.

        Frames follow the host's clock and skip the sync, so this stretch of
        video does depend on how fast the host runs. stop_condition, if given,
        is checked before each frame and ends the stretch early.
        """
        start = time.monotonic()
        for index in range(round(seconds * self._fps)):
            if stop_condition is not None and stop_condition():
                return
            time.sleep(max(0.0, start + index / self._fps - time.monotonic()))
            self._capture(1)

    def _capture(self, hold: int) -> None:
        self._session.vm.screenshot(self._frame, format="ppm")
        data = self._frame.read_bytes()
        for _ in range(hold):
            self._ffmpeg.stdin.write(data)
        self.count += hold

    def close(self) -> None:
        self._ffmpeg.stdin.close()
        self._ffmpeg.wait()
        shutil.rmtree(self._dir, ignore_errors=True)

    def __enter__(self) -> "FrameRecorder":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class Session:
    def __init__(self, vm: VM, bridge: Bridge):
        self.vm = vm
        self.bridge = bridge

    def record(self, path: Path | str, fps: int = 30, lossless: bool = False) -> FrameRecorder:
        return FrameRecorder(self, path, fps, lossless)

    def revert(self, snapshot: str = SNAPSHOT) -> None:
        """Put the running guest back to the snapshot, keeping the bridge.

        Took 0.06 to 0.2 s in tests. Every window handle and process from
        before is gone, and open calls fail at once instead of timing out.
        """
        self.bridge.abandon(f"the desktop was reverted to {snapshot!r}")
        self.vm.load_snapshot(snapshot)
        self.bridge.ping()

    def close(self) -> None:
        self.bridge.close()
        self.vm.close()

    def __enter__(self) -> "Session":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


@contextmanager
def private_stage(work: Path | str = "work") -> Iterator[Path]:
    """A throwaway copy of the prepared image, for one run.

    A VM writes to its disk, and two can't share one, so a run takes a
    copy-on-write copy under `work/runs` and it is deleted afterwards.
    """
    config = json.loads((Path(work) / IMAGE_FILE).read_text())
    runs = Path(work) / "runs"
    runs.mkdir(exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="render-", dir=runs))
    try:
        source = image_disk(work, config)
        disk = stage / source.name
        subprocess.run(["cp", "--reflink=auto", str(source), str(disk)], check=True)
        config["disk"] = str(disk.resolve())
        (stage / IMAGE_FILE).write_text(json.dumps(config, indent=2))
        yield stage
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def boot(work: Path | str = "work", display: str = "none", ready_timeout: float = 30.0,
         backend: str | None = None) -> Session:
    """Restore the prepared desktop and connect to it.

    Each boot starts from the same snapshot, so nothing a previous run did to
    the guest survives. backend "local" runs QEMU here; "container" runs it in
    the art98 container, which works on its own copy of the disk. ART98_BACKEND
    sets the default.
    """
    image = Path(work) / IMAGE_FILE
    if not image.exists():
        builder = "art98 up" if backend_name(backend) == "container" else "art98 setup"
        raise ImageMissing(f"{image} not found; run `{builder}` first")
    if backend_name(backend) == "container":
        from art98_container import host  # 98artware_container/, beside this package

        return host.boot(work, display=display,
                         ready_timeout=max(ready_timeout, host.START_TIMEOUT))
    data = json.loads(image.read_text())
    data["disk"] = str(image_disk(work, data))
    config = VMConfig.from_json(data)
    config.loadvm = SNAPSHOT
    config.display = display
    vm = VM(config, log=Path(work) / "qemu.log").start()
    try:
        bridge = Bridge.connect(vm.serial_path)
        bridge.wait_ready(ready_timeout)
    except BaseException:
        vm.close()
        raise
    return Session(vm, bridge)


@contextmanager
def stage(work: Path | str = "work", display: str = "none",
          backend: str | None = None) -> Iterator[Session]:
    """A booted session on a throwaway copy of the image, closed afterwards.

    The local backend copies the disk under work/runs here; the container
    makes its own copy there, so it is only made once either way.
    """
    if backend_name(backend) == "container":
        with boot(work, display=display, backend="container") as session:
            yield session
        return
    with private_stage(work) as copy, boot(copy, display=display, backend="local") as session:
        yield session
