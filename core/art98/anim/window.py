"""Window commands: minimize, maximize, restore, close, and a move in one frame."""

from __future__ import annotations

from .animation import Instant
from .vectors import ORIGIN

WM_SYSCOMMAND = 0x0112
SC_MINIMIZE, SC_MAXIMIZE, SC_RESTORE = 0xF020, 0xF030, 0xF120


class _SysCommand(Instant):
    command = 0

    def act(self) -> None:
        self.target.guest.user32.PostMessageA(self.target.hwnd, WM_SYSCOMMAND, self.command, 0)
        self.target.guest.sync(self.target.hwnd)


class Minimize(_SysCommand):
    """Send a window to the taskbar."""

    command = SC_MINIMIZE


class Maximize(_SysCommand):
    """Fill the desktop with a window."""

    command = SC_MAXIMIZE


class RestoreWindow(_SysCommand):
    """Bring a minimized or maximized window back."""

    command = SC_RESTORE


class Close(Instant):
    """Close a window. It leaves the scene too."""

    def act(self) -> None:
        self.scene.remove(self.target)


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
