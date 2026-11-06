"""A running stage: the VM, the bridge to it, and frame capture."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .bridge import Bridge
from .qemu import VM, VMConfig

SNAPSHOT = "ready"
IMAGE_FILE = "image.json"


class FrameRecorder:
    """Encodes captured frames to a video, one explicit frame at a time.

    Frames are taken when the script says so, not on a wall clock, so a slow
    host produces the same video as a fast one.
    """

    def __init__(self, session: "Session", path: Path | str, fps: int = 30):
        self._session = session
        self._fps = fps
        self._dir = Path(tempfile.mkdtemp(prefix="art98-frames-"))
        self._frame = self._dir / "frame.ppm"
        self.count = 0
        self._ffmpeg = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-c:v", "ppm",
             "-framerate", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "veryfast",
             "-pix_fmt", "yuv420p", "-crf", "12", str(path)],
            stdin=subprocess.PIPE,
        )

    def frame(self, hold: int = 1) -> None:
        """Wait for the guest to settle, capture, and write hold copies."""
        self._session.bridge.sync()
        self._capture(hold)

    def live(self, seconds: float) -> None:
        """Record something that moves by itself, such as a screensaver.

        Frames follow the host's clock and skip the sync, so this stretch of
        video does depend on how fast the host runs.
        """
        start = time.monotonic()
        for index in range(round(seconds * self._fps)):
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

    def record(self, path: Path | str, fps: int = 30) -> FrameRecorder:
        return FrameRecorder(self, path, fps)

    def close(self) -> None:
        self.bridge.close()
        self.vm.close()

    def __enter__(self) -> "Session":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def boot(work: Path | str = "work", display: str = "none", ready_timeout: float = 30.0) -> Session:
    """Restore the prepared desktop and connect to it.

    Each boot starts from the same snapshot, so nothing a previous run did to
    the guest survives.
    """
    image = Path(work) / IMAGE_FILE
    if not image.exists():
        raise FileNotFoundError(f"{image} not found; run `art98 prep` first")
    config = VMConfig.from_json(json.loads(image.read_text()))
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
