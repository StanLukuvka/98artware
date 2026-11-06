"""The pointer and the keyboard as actors.

Pointer moves go through SetCursorPos and buttons through mouse_event, which
is real input: Windows routes it, so menus open and windows drag themselves.
Text goes one of two ways. TypeWithCursor sends WM_CHAR to a known control and
needs no focus. Keys and TypeKeys press real keys on the guest's keyboard, so
they go to whatever has the focus.
"""

from __future__ import annotations

import struct
import time

from ..protocol import Out
from .animation import Animation, Instant, Succession, path_function
from .props import Prop, Spot, Win, point_of
from .rate_functions import linear, smooth
from .vectors import Vec, lerp

BUTTONS = {
    "left": (0x0002, 0x0004),
    "right": (0x0008, 0x0010),
    "middle": (0x0020, 0x0040),
}
WM_CHAR = 0x0102
WM_SYSCOMMAND = 0x0112
SC_MINIMIZE, SC_MAXIMIZE, SC_RESTORE = 0xF020, 0xF030, 0xF120
VK_BACK = 8
MF_BYPOSITION = 0x0400
KEY_HOLD_MS = 40
KEY_SETTLE = 0.1  # time for a key press to reach the guest and be handled

QCODES = {
    "enter": "ret", "return": "ret", "escape": "esc", "space": "spc", "del": "delete",
    "win": "meta_l", "pageup": "pgup", "pagedown": "pgdn", "-": "minus", "=": "equal",
    ",": "comma", ".": "dot", "/": "slash", ";": "semicolon", "'": "apostrophe",
    "[": "bracket_left", "]": "bracket_right", "\\": "backslash", "`": "grave_accent",
}
UNSHIFTED = r"`1234567890-=[]\;',./"
SHIFTED = '~!@#$%^&*()_+{}|:"<>?'


def key_chord(combo: str) -> tuple[str, ...]:
    """Turn "ctrl+s" into the QEMU key names ("ctrl", "s")."""
    if combo == "+":
        return ("shift", "equal")
    return tuple(QCODES.get(name, name) for name in combo.lower().split("+"))


def char_chord(char: str) -> tuple[str, ...]:
    """The keys that type one character on the guest's US keyboard."""
    if char == "\n":
        return ("ret",)
    if char == "\t":
        return ("tab",)
    if char == " ":
        return ("spc",)
    if char in SHIFTED:
        return ("shift", QCODES.get(plain := UNSHIFTED[SHIFTED.index(char)], plain))
    if char.isascii() and char.isalpha() and char.isupper():
        return ("shift", char.lower())
    if char.isascii() and char.isalnum():
        return (char,)
    if char in UNSHIFTED:
        return (QCODES[char],)
    raise ValueError(f"no key types {char!r}")


class Pointer(Prop):
    """The guest's mouse pointer. Every scene has one, as `self.pointer`."""

    claims = ("pointer",)

    def attach(self, scene) -> None:
        super().attach(scene)
        self.refresh()
        self._sent = self.get_center().rounded()

    def refresh(self) -> None:
        self.x, self.y = struct.unpack("<ii", self.guest.user32.GetCursorPos(Out(8)).buffers[0])

    def apply(self) -> None:
        wanted = self.get_center().rounded()
        if wanted != self._sent:
            self.guest.user32.SetCursorPos(*wanted)
            self._sent = wanted

    def place(self, point) -> None:
        """Jump there now, with no frames in between."""
        self.x, self.y = point_of(point)
        self.apply()

    def press(self, button: str = "left") -> None:
        self.guest.user32.mouse_event(BUTTONS[button][0], 0, 0, 0, 0)

    def release(self, button: str = "left") -> None:
        self.guest.user32.mouse_event(BUTTONS[button][1], 0, 0, 0, 0)


def _span(progress: float, start: float, end: float) -> float:
    """How far progress is through the stretch from start to end."""
    return 0.0 if progress <= start else 1.0 if progress >= end else (progress - start) / (end - start)


class PointerAction(Animation):
    """Pointer travel, then button events at set points in the run time."""

    claims = ("pointer",)
    travel = 1.0

    def __init__(self, target, **kwargs):
        super().__init__(target, **kwargs)
        self.pointer = None
        self.start = self.end = Vec(0, 0)
        self.events: list = []

    def begin(self, scene) -> None:
        super().begin(scene)
        self.pointer = scene.pointer
        self.pointer.refresh()
        self.start = self.pointer.get_center()
        self.end = point_of(self.target)
        self.events = self.schedule()

    def schedule(self) -> list:
        return []

    def update(self, progress: float) -> None:
        self.pointer.place(lerp(self.start, self.end, self.rate_func(_span(progress, 0, self.travel))))
        self.fire(progress)

    def fire(self, progress: float) -> None:
        while self.events and progress >= self.events[0][0]:
            self.events.pop(0)[1]()


class Glide(PointerAction):
    """Move the pointer to a target with no buttons held."""

    run_time = 0.5


class Hover(PointerAction):
    """Move to a target and stay, in real time, so a tooltip can come up.

    `hold` is seconds at the target. Tooltips are timed by the guest, so the
    frames of this animation follow the host clock.
    """

    live = True

    def __init__(self, target, *, hold: float = 1.0, travel_time: float = 0.5, **kwargs):
        super().__init__(target, **kwargs)
        self.run_time = travel_time + hold
        self.travel = travel_time / self.run_time


class Click(PointerAction):
    """Travel to a target, press and release a button."""

    run_time = 0.65
    travel = 0.74
    button = "left"

    def __init__(self, target, *, button: str | None = None, **kwargs):
        super().__init__(target, **kwargs)
        if button is not None:
            self.button = button

    def schedule(self) -> list:
        return [(self.travel, self._press), (0.84, self._release)]

    def _press(self) -> None:
        self.pointer.press(self.button)

    def _release(self) -> None:
        self.pointer.release(self.button)


class RightClick(Click):
    """Click with the right button. A context menu opens on the release."""

    button = "right"


class DoubleClick(Click):
    """Two clicks, a few frames apart.

    Windows counts a double click by its own clock (500 ms), so both clicks
    fall inside the same short stretch of the run time.
    """

    run_time = 0.75
    travel = 0.66

    def schedule(self) -> list:
        return [(0.66, self._press), (0.72, self._release),
                (0.78, self._press), (0.84, self._release)]


class Drag(PointerAction):
    """Press on one target, carry the pointer to another, and let go.

    `to` is a target, or use `by` for an offset from where the drag starts.
    Windows moves whatever was grabbed, so a title bar drags its window.
    """

    run_time = 1.2
    travel = 0.3
    drop = 0.9

    def __init__(self, source, to=None, *, by=None, button: str = "left", **kwargs):
        if (to is None) == (by is None):
            raise ValueError("Drag needs either to= or by=")
        super().__init__(source, **kwargs)
        self.to, self.by, self.button = to, by, button
        self.grab = self.goal = Vec(0, 0)

    def schedule(self) -> list:
        self.grab = self.end
        self.goal = self.grab + self.by if self.by is not None else point_of(self.to)
        return [(self.travel, self._take_hold),
                (self.drop, lambda: self.pointer.release(self.button))]

    def _take_hold(self) -> None:
        self.pointer.place(self.grab)
        self.pointer.press(self.button)

    def update(self, progress: float) -> None:
        if progress < self.travel:
            self.pointer.place(lerp(self.start, self.grab, self.rate_func(_span(progress, 0, self.travel))))
            return
        self.fire(self.travel)
        carried = self.rate_func(_span(progress, self.travel, self.drop))
        self.pointer.place(lerp(self.grab, self.goal, carried))
        self.fire(progress)

    def finish(self, scene) -> None:
        scene.refresh_props()


class Stroke(PointerAction):
    """Hold a button down along a path, as a pen does.

    The path is a list of points, or a function from 0..1 to a point. The
    pointer first travels to the start of the path. Each frame moves it
    `steps_per_frame` times and waits for the guest after each move: Windows
    keeps only the latest pointer position, so without the wait an app sees a
    few corners instead of a curve.
    """

    run_time = 2.0
    travel_time = 0.4

    def __init__(self, path, *, button: str = "left", steps_per_frame: int = 4, **kwargs):
        super().__init__(None, **kwargs)
        self.path = path_function(path)
        self.button = button
        self.steps = steps_per_frame
        self._done = 0.0

    def begin(self, scene) -> None:
        self.target = Spot(lambda: self.path(0))
        self.travel = min(0.5, self.travel_time / self.run_time) if self.run_time else 0.0
        self._done = 0.0
        super().begin(scene)

    def schedule(self) -> list:
        return [(self.travel, self._pen_down)]

    def _pen_down(self) -> None:
        self.pointer.place(self.end)
        self.pointer.press(self.button)

    def update(self, progress: float) -> None:
        if progress < self.travel:
            self.pointer.place(lerp(self.start, self.end, smooth(_span(progress, 0, self.travel))))
            return
        self.fire(self.travel)
        drawn = self.rate_func(_span(progress, self.travel, 1.0))
        for step in range(1, self.steps + 1):
            self.pointer.place(self.path(self._done + (drawn - self._done) * step / self.steps))
            self.scene.guest.sync()
        self._done = drawn
        if progress >= 1:
            self.pointer.release(self.button)


class Menu(Succession):
    """Open a window's menu with real clicks, and pick an item.

    `Menu(pad, "File", "Save As...")` clicks each label in turn. Labels are
    found in the live menu, and `&` shortcut marks and case are ignored. Each
    click is aimed when its turn comes, because Windows only knows where a
    menu item is once its menu is open.
    """

    def __init__(self, window: Win, *labels: str, step: float = 0.45):
        if not labels:
            raise ValueError("Menu needs at least one label")
        clicks = [Click(Spot(_item_finder(window, labels[: depth + 1])), run_time=step)
                  for depth in range(len(labels))]
        super().__init__(*clicks)
        self.target = window


def _item_finder(window: Win, labels: tuple[str, ...]):
    def label_of(menu: int, position: int) -> str:
        result = window.guest.user32.GetMenuStringA(menu, position, Out(64), 64, MF_BYPOSITION)
        return result.buffers[0][:result.value].decode("cp1252").split("\t")[0].replace("&", "")

    def position_of(menu: int, label: str) -> int:
        count = window.guest.user32.GetMenuItemCount(menu).value
        names = [label_of(menu, position) for position in range(count)]
        for position, name in enumerate(names):
            if name.lower() == label.lower():
                return position
        raise LookupError(f"no menu item {label!r}: found {[n for n in names if n]}")

    def locate():
        user32 = window.guest.user32
        menu = user32.GetMenu(window.hwnd).value
        for label in labels[:-1]:
            menu = user32.GetSubMenu(menu, position_of(menu, label)).value
        result = user32.GetMenuItemRect(window.hwnd, menu, position_of(menu, labels[-1]), Out(16))
        if not result:
            raise LookupError(f"menu {' > '.join(labels)} is not open")
        left, top, right, bottom = struct.unpack("<iiii", result.buffers[0])
        return (left + right) / 2, (top + bottom) / 2

    return locate


class TypeWithCursor(Animation):
    """Type into a Notepad or Edit control, letter by letter.

    Each letter is a WM_CHAR, so the real caret moves and no focus is needed.
    The default run time gives ten letters a second.
    """

    rate_func = staticmethod(linear)
    seconds_per_letter = 0.1

    def __init__(self, target: Win, text: str, **kwargs):
        super().__init__(target, **kwargs)
        self.codes = text.replace("\n", "\r").encode("cp1252", errors="replace")
        if "run_time" not in kwargs or kwargs["run_time"] is None:
            self.run_time = len(self.codes) * self.seconds_per_letter
        self._typed = 0

    def begin(self, scene) -> None:
        super().begin(scene)
        self._typed = 0

    def interpolate(self, alpha: float) -> None:
        hwnd = self.target.edit_hwnd
        wanted = min(len(self.codes), round(alpha * len(self.codes)))
        while self._typed < wanted:
            self.scene.guest.user32.SendMessageA(hwnd, WM_CHAR, self.codes[self._typed], 1)
            self._typed += 1


class UntypeWithCursor(TypeWithCursor):
    """Delete letters with Backspace, from the caret."""

    def __init__(self, target: Win, count: int, **kwargs):
        super().__init__(target, chr(VK_BACK) * count, **kwargs)


class Keys(Animation):
    """Press keys or chords on the guest's real keyboard, evenly over run_time.

    Each argument is one press, such as "ctrl+s", "alt+tab" or "enter". The
    keys go to whatever has the focus.
    """

    rate_func = staticmethod(linear)
    claims = ("keyboard",)
    seconds_per_key = 0.25

    def __init__(self, *combos: str, **kwargs):
        super().__init__(None, **kwargs)
        self.chords = [key_chord(combo) for combo in combos]
        if kwargs.get("run_time") is None:
            self.run_time = len(self.chords) * self.seconds_per_key
        self._pressed = 0

    def begin(self, scene) -> None:
        super().begin(scene)
        self._pressed = 0

    def interpolate(self, alpha: float) -> None:
        wanted = min(len(self.chords), int(alpha * len(self.chords) + 1e-9))
        while self._pressed < wanted:
            self.scene.vm.send_keys(*self.chords[self._pressed], hold_ms=KEY_HOLD_MS)
            self._pressed += 1
            time.sleep(KEY_SETTLE)


class TypeKeys(Keys):
    """Type text on the real keyboard, for windows that need real key presses.

    This covers what WM_CHAR can't: dialogs without a known Edit control,
    the MS-DOS Prompt and games. US layout, printable ASCII, \\n and \\t.
    """

    seconds_per_key = 0.15

    def __init__(self, text: str, **kwargs):
        super().__init__(**kwargs)
        self.chords = [char_chord(char) for char in text]
        if kwargs.get("run_time") is None:
            self.run_time = len(self.chords) * self.seconds_per_key


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
