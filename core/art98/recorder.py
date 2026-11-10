"""The frame recorder: one video per render, and the GIF defaults."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .session import Session


# The libx264 settings for every MP4 art98 writes.
H264 = ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-crf", "12"]

# The GIF defaults, here so the command line can read them without loading the
# animation package.
GIF_FPS = 15
GIF_COLORS = 128


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
                 H264)
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
