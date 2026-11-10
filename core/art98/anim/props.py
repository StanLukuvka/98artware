"""Props: host-side handles on things that exist inside the guest."""

from __future__ import annotations

import struct
import time
from typing import Callable

from ..bridge import RDW_REPAINT_ALL, BridgeTimeout, Window
from ..protocol import Out
from .vectors import DL, DR, LEFT, ORIGIN, RIGHT, Vec

DESKTOP_AREA = (0, 0, 800, 572)  # used until a prop is added to a scene
DEFAULT_BUFF = 8

WM_SETTEXT, WM_GETTEXT, WM_GETTEXTLENGTH, WM_CLOSE = 0x000C, 0x000D, 0x000E, 0x0010
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0004, 0x0010
SM_CYCAPTION, SM_CYSIZEFRAME = 4, 33
FIND_WINDOW_TIMEOUT = 15.0


def window_rect(guest, hwnd: int) -> tuple[int, int, int, int] | None:
    """A window's (left, top, right, bottom) on the screen, or None if it has gone."""
    result = guest.user32.GetWindowRect(hwnd, Out(16))
    if not result:
        return None
    return struct.unpack("<iiii", result.buffers[0])


class Spot:
    """A place on screen that is worked out when it is needed.

    Controls move with their windows, so a target such as a Paint tool is
    located when an animation begins, not when the scene names it.
    """

    def __init__(self, locate: Callable[[], tuple[float, float]]):
        self._locate = locate

    def point(self) -> Vec:
        return Vec(*self._locate())


def point_of(target) -> Vec:
    """Where a target is: a point, a Spot, or a prop's centre."""
    locate = getattr(target, "point", None)
    return Vec(*locate()) if locate else Vec(target[0], target[1])


class Box:
    """A rectangle in screen pixels, with Manim's layout methods.

    These only change numbers on the host. A prop's values reach the guest on
    the next frame, or at once with `apply()`.
    """

    claims: tuple[str, ...] = ()
    LAYOUT = frozenset(("shift", "move_to", "center", "to_edge", "to_corner", "next_to",
                        "resize", "set_rect", "scale"))

    def __init__(self, x: float = 0, y: float = 0, width: float = 0, height: float = 0):
        self.x, self.y, self.width, self.height = x, y, width, height
        self.area = DESKTOP_AREA

    @property
    def rect(self) -> tuple[int, int, int, int]:
        """(left, top, right, bottom), the same order as a Win32 RECT."""
        x, y = round(self.x), round(self.y)
        return x, y, x + round(self.width), y + round(self.height)

    @property
    def size(self) -> tuple[int, int]:
        return round(self.width), round(self.height)

    def get_center(self) -> Vec:
        return Vec(self.x + self.width / 2, self.y + self.height / 2)

    def point(self) -> Vec:
        return self.get_center()

    def get_corner(self, direction) -> Vec:
        return self.get_center() + Vec(direction[0] * self.width / 2, direction[1] * self.height / 2)

    def refresh(self) -> None:
        """Read the real position back. A plain Box has nothing to read."""

    def ghost(self) -> "Box":
        """A copy to try layout calls on, without touching the prop."""
        ghost = Box(self.x, self.y, self.width, self.height)
        ghost.area = self.area
        return ghost

    def shift(self, *vectors) -> "Box":
        for vector in vectors:
            self.x += vector[0]
            self.y += vector[1]
        return self

    def move_to(self, target, aligned_edge=ORIGIN) -> "Box":
        """Put this box's centre on the target, or the given edge or corner."""
        return self.shift(point_of(target) - self.get_corner(aligned_edge))

    def center(self) -> "Box":
        """Centre in the work area: the whole screen, or above the taskbar."""
        left, top, right, bottom = self.area
        return self.move_to(((left + right) / 2, (top + bottom) / 2))

    def to_edge(self, edge=LEFT, buff: float = 0) -> "Box":
        left, top, right, bottom = self.area
        if edge[0]:
            self.x = left + buff if edge[0] < 0 else right - buff - self.width
        if edge[1]:
            self.y = top + buff if edge[1] < 0 else bottom - buff - self.height
        return self

    def to_corner(self, corner=DL, buff: float = 0) -> "Box":
        return self.to_edge(corner, buff)

    def next_to(self, other, direction=RIGHT, buff: float = DEFAULT_BUFF) -> "Box":
        """Sit beside another box, centred on it along the other axis."""
        other.refresh()
        gap = Vec(direction[0] * (other.width + self.width) / 2 + direction[0] * buff,
                  direction[1] * (other.height + self.height) / 2 + direction[1] * buff)
        return self.move_to(other.get_center() + gap)

    def resize(self, width: float, height: float) -> "Box":
        """Change size, keeping the top left corner where it is."""
        self.width, self.height = width, height
        return self

    def set_rect(self, x: float, y: float, width: float, height: float) -> "Box":
        self.x, self.y, self.width, self.height = x, y, width, height
        return self

    def scale(self, factor: float) -> "Box":
        """Grow or shrink about the centre. A real app keeps its font size."""
        centre = self.get_center()
        self.width *= factor
        self.height *= factor
        return self.move_to(centre)


class Prop(Box):
    """Something on stage. Adding it to a scene is what brings it to life."""

    def __init__(self, x: float = 0, y: float = 0, width: float = 0, height: float = 0):
        super().__init__(x, y, width, height)
        self.scene = None

    @property
    def animate(self):
        from .animation import Animate

        return Animate(self)

    @property
    def guest(self):
        if self.scene is None:
            raise RuntimeError(f"{type(self).__name__} is not on stage: add it to the scene first")
        return self.scene.guest

    def attach(self, scene) -> None:
        self.scene = scene
        self.area = scene.work_area

    def apply(self) -> None:
        """Send any changed values to the guest."""

    def remove(self) -> None:
        """Leave the stage."""

    def forget(self) -> None:
        """Leave the stage without touching the guest, after a revert."""
        self.scene = None


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
        self.guest.user32.SetWindowPos(self.hwnd, 0, x, y, width, height, flags)
        # Moves leave stale pixels on the frame, so it is repainted (Bridge.move_window).
        self.guest.user32.RedrawWindow(self.hwnd, 0, 0, RDW_REPAINT_ALL)
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
        self.guest.user32.PostMessageA(self.hwnd, WM_CLOSE, 0, 0)

    def remove(self) -> None:
        self.close()

    def forget(self) -> None:
        # The window went with the revert. Adding the prop again opens a new one.
        super().forget()
        self.hwnd, self._sent = None, None
