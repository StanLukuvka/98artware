"""The art98 picture window, and moving a window in one frame."""

from __future__ import annotations

import time
from pathlib import Path

from .. import guestfiles
from ..bridge import BridgeTimeout, Window
from .animation import Instant
from .props import FIND_WINDOW_TIMEOUT, Win
from .vectors import ORIGIN

DEFAULT_AT = (100, 100)
DEFAULT_SIZE = (320, 240)


class Picture(Win):
    """A plain window that shows one BMP at 1:1, centred, on grey.

    Windows 98 has no small image viewer, so this is art98's own program,
    VIEW.EXE, copied to the guest when it is needed. `image` is a BMP on the
    host, or None for an empty window. The window opens at `at` with the outer
    `size`, so it never has to move off a default position first.
    """

    window_class = "Art98View"

    def __init__(self, title: str = "Picture", *, image: Path | str | None = None,
                 at: tuple[int, int] | None = None, size: tuple[int, int] | None = None):
        if '"' in title:
            raise ValueError("a picture window's title can't contain a double quote")
        super().__init__(title, at=at or DEFAULT_AT, size=size or DEFAULT_SIZE)
        self.image = Path(image) if image is not None else None
        self._image_data = None
        if self.image is not None:
            self._image_data = self.image.read_bytes()
            self.image_size = guestfiles.check_bmp(self._image_data, str(self.image))

    def attach(self, scene) -> None:
        guest = scene.guest
        args = [guestfiles.ensure(guest, guestfiles.viewer(), "VIEW.EXE"),
                *map(str, self._at), *map(str, self._size), f'"{self.title_text}"']
        if self._image_data is not None:
            args.append(f'"{guestfiles.ensure(guest, self._image_data, self.image.name)}"')
        self.command = " ".join(args)
        super().attach(scene)

    def _find(self, pid: int | None) -> Window:
        """Wait for the window, failing at once if VIEW.EXE gave up or crashed."""
        deadline = time.monotonic() + FIND_WINDOW_TIMEOUT
        while True:
            for window in self.guest.windows():
                if window.pid == pid and window.visible and window.class_name == self.class_name:
                    return window
                if window.visible and window.class_name == "#32770" and window.title == "View":
                    raise RuntimeError(
                        f"VIEW.EXE crashed opening {self.image or 'its window'}, and Windows 98's"
                        " crash dialog is on the desktop")
            if pid not in {p for p, _ in self.guest.processes()}:
                what = f"the image {self.image}" if self.image else "its window"
                raise RuntimeError(f"VIEW.EXE closed without a window: Windows 98 couldn't open {what}")
            if time.monotonic() >= deadline:
                raise BridgeTimeout(f"no window for Picture {self.title_text!r}")
            time.sleep(0.05)


class Teleport(Instant):
    """Put a window somewhere else in one frame, with no movement in between.

    `to` and `aligned_edge` work as in `move_to`, so by default the window's
    centre lands on `to`. Give `size` to change its outer size as well.
    """

    def __init__(self, target, to=None, *, aligned_edge=ORIGIN,
                 size: tuple[int, int] | None = None, **kwargs):
        if to is None and size is None:
            raise ValueError("Teleport needs somewhere to go, a size, or both")
        super().__init__(target, **kwargs)
        self.claims = target.claims
        self.to, self.aligned_edge, self.new_size = to, aligned_edge, size

    def act(self) -> None:
        self.target.refresh()
        if self.new_size is not None:
            self.target.resize(*self.new_size)
        if self.to is not None:
            self.target.move_to(self.to, aligned_edge=self.aligned_edge)
        self.target.apply()
