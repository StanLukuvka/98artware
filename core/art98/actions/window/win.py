"""Win: a real top-level window, or a real control inside one, as a prop."""

from __future__ import annotations

import struct
import time

from ...base.props import Prop, Spot
from ...base.vectors import DR, Vec
from ...bridge import BridgeTimeout, Window
from ...protocol import Out
from ... import win32
from ...win32 import (
    SM_CYCAPTION, SM_CYSIZEFRAME, SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE, SWP_NOZORDER,
    WM_GETTEXT, WM_GETTEXTLENGTH, WM_SETTEXT, window_rect,
)

FIND_WINDOW_TIMEOUT = 15.0


class Win(Prop):
    """A real top-level window, or a real control inside one.

    Give it a `command` to start a program, or `title`, `class_name` or `hwnd`
    to take hold of a window that exists. `at` is the top left corner and
    `size` the outer size. Both are applied when the prop is added.
    """

    command: str | None = None
    window_class: str | None = None

    def __init__(self, title: str | None = None, *, class_name: str | None = None,
                 hwnd: int | None = None, command: str | None = None,
                 at: tuple[int, int] | None = None, size: tuple[int, int] | None = None):
        super().__init__()
        self.title_text = title
        self.class_name = class_name or self.window_class
        self.hwnd = hwnd
        if command is not None:
            self.command = command
        self._at, self._size = at, size
        self._sent: tuple[int, int, int, int] | None = None

    def attach(self, scene) -> None:
        super().attach(scene)
        if self.hwnd is None:
            pid = self.guest.spawn(self.command) if self.command else None
            self.hwnd = self._find(pid).hwnd
        self.refresh()
        if self._size:
            self.width, self.height = self._size
        if self._at:
            self.x, self.y = self._at
        self.apply()
        self.ready()

    def _find(self, pid: int | None) -> Window:
        deadline = time.monotonic() + FIND_WINDOW_TIMEOUT
        while True:
            window = self._look(pid)
            if window is not None:
                return window
            if time.monotonic() >= deadline:
                raise BridgeTimeout(self._not_found(pid))
            time.sleep(0.05)

    def _look(self, pid: int | None) -> Window | None:
        """One look at the guest's windows: the one wanted, or None. A subclass
        can raise here to fail early."""
        for window in self.guest.windows():
            if (
                window.visible
                and (pid is None or window.pid == pid)
                and (self.title_text is None
                     or self.title_text.lower() in window.title.lower())
                and (self.class_name is None
                     or self.class_name.lower() == window.class_name.lower())
            ):
                return window
        return None

    def _not_found(self, pid: int | None) -> str:
        return (f"no window for {type(self).__name__}: "
                f"title={self.title_text!r} class={self.class_name!r} pid={pid}")

    def ready(self) -> None:
        """Called once the window exists and has been placed."""
        self.guest.sync(self.hwnd)

    def refresh(self) -> None:
        """Read the real place back, after sending any change still waiting."""
        if self.hwnd is None or self.scene is None:
            return
        if self._sent is not None:
            self.apply()
        rect = window_rect(self.guest, self.hwnd)
        if rect is None:
            return  # the window has gone, so the last known place stands
        left, top, right, bottom = rect
        self.set_rect(left, top, right - left, bottom - top)
        self._sent = self.rect[0], self.rect[1], *self.size

    def point(self) -> Vec:
        self.refresh()
        return self.get_center()

    def apply(self) -> None:
        wanted = (*self.rect[:2], *self.size)
        if wanted == self._sent or self.hwnd is None:
            return
        x, y, width, height = wanted
        flags = SWP_NOZORDER | SWP_NOACTIVATE
        if self._sent and (width, height) == self._sent[2:]:
            flags |= SWP_NOSIZE
        if self._sent and (x, y) == self._sent[:2]:
            flags |= SWP_NOMOVE
        # Moves leave stale pixels on the frame, so it is repainted (Bridge.move_window).
        win32.place_window(self.guest, self.hwnd, x, y, width, height, flags)
        self._sent = wanted

    # ---- places to aim at ----

    @property
    def title_bar(self) -> Spot:
        """The middle of the title bar, which is where a window is dragged from."""

        def locate():
            self.refresh()
            frame = self.guest.user32.GetSystemMetrics(SM_CYSIZEFRAME).value
            caption = self.guest.user32.GetSystemMetrics(SM_CYCAPTION).value
            return self.x + self.width / 2, self.y + frame + caption / 2

        return Spot(locate)

    def corner(self, direction=DR, inset: int = 2) -> Spot:
        """A corner or edge of the frame, which is where a window is resized from."""

        def locate():
            self.refresh()
            return self.get_corner(direction) - Vec(direction[0], direction[1]) * inset

        return Spot(locate)

    def client(self, x: int, y: int) -> Spot:
        """A point given in the window's client coordinates."""

        def locate():
            point = struct.pack("<ii", x, y)
            return struct.unpack(
                "<ii", self.guest.user32.ClientToScreen(self.hwnd, point).buffers[0])

        return Spot(locate)

    # ---- the live window ----

    def client_size(self) -> tuple[int, int]:
        rect = self.guest.user32.GetClientRect(self.hwnd, Out(16)).buffers[0]
        return struct.unpack("<iiii", rect)[2:]

    def children(self, class_name: str | None = None, title: str | None = None) -> list[Window]:
        """Every descendant window, optionally by class and title."""
        return [
            window for window in self.guest.windows(self.hwnd)
            if (class_name is None or class_name.lower() == window.class_name.lower())
            and (title is None or title.lower() in window.title.lower())
        ]

    def control(self, class_name: str | None = None, title: str | None = None) -> "Win":
        """A child window as a prop, for clicking or moving."""
        found = self.children(class_name, title)
        if not found:
            raise LookupError(f"no {class_name or 'child'} {title or ''} in window {self.hwnd:#x}")
        child = Win(hwnd=found[0].hwnd)
        child.attach(self.scene)
        return child

    @property
    def text(self) -> str:
        """The window's text: a title bar, or an Edit control's contents."""
        return self._read_text(self.hwnd)

    def _read_text(self, hwnd: int) -> str:
        length = self.guest.user32.SendMessageA(hwnd, WM_GETTEXTLENGTH, 0, 0).value
        result = self.guest.user32.SendMessageA(hwnd, WM_GETTEXT, length + 1, Out(length + 1))
        return result.buffers[0][:result.value].decode("cp1252", errors="replace")

    def set_text(self, text: str) -> None:
        self.guest.user32.SendMessageA(self.hwnd, WM_SETTEXT, 0, text)

    @property
    def edit_hwnd(self) -> int:
        """Where typing goes. Apps with an inner editor override this."""
        return self.hwnd

    def activate(self) -> None:
        """Make this the foreground window, so the real keyboard reaches it.

        SetForegroundWindow fails when the agent calls it, so this clicks the
        title bar, between frames, and puts the pointer back.
        """
        user32 = self.guest.user32
        if user32.GetForegroundWindow().value == self.hwnd:
            return
        pointer = self.scene.pointer
        pointer.refresh()
        home = pointer.get_center()
        pointer.place(self.title_bar)
        pointer.press()
        pointer.release()
        self.guest.sync()
        pointer.place(home)
        if user32.GetForegroundWindow().value != self.hwnd:
            raise RuntimeError(f"could not activate window {self.hwnd:#x}: is it covered?")

    def bring_to_front(self) -> None:
        """Raise the window without activating it."""
        self.guest.user32.SetWindowPos(
            self.hwnd, 0, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def close(self) -> None:
        """Ask the window to close, as its X button does."""
        win32.close_window(self.guest, self.hwnd)

    def remove(self) -> None:
        self.close()

    def forget(self) -> None:
        # The window went with the revert. Adding the prop again opens a new one.
        super().forget()
        self.hwnd, self._sent = None, None
