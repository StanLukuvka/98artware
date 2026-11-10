"""The blank start: a black, empty screen on the restored desktop.

The `ready` snapshot is the stock Windows 98 desktop: a teal background,
icons, the taskbar and the arrow pointer. `blank` turns all of that off in the
running guest. Each step only changes memory, so it holds until the next
revert and the snapshot stays as it is. None of it needs Explorer restarted.

The steps, each tested on the real image (docs/design/blank-start.md):

- the desktop colour goes black, which shows because there's no wallpaper;
- the icons are hidden. Explorer shows them again on a desktop refresh, so
  scenes shouldn't send one (F5 on the desktop, or command 0x7103);
- the taskbar is hidden, along with the tray and Quick Launch, and disabled,
  so the Windows key and Ctrl+Esc no longer open the Start menu. It stays
  hidden through a settings change and the mouse at the bottom edge;
- the desktop window is disabled, so a right-click on the black opens no menu;
- the work area becomes the whole screen, so a maximized window covers it;
- the menu, combo box and list box animations, gradient captions and hot
  tracking are turned off, since their timing comes from the guest's clock;
- every system pointer shape is swapped for an empty one, unless the pointer
  is wanted. ShowCursor(FALSE) doesn't hide the pointer on Windows 98.

The pointer is hidden or not once per desktop, right after a revert. Turning
it on and off later isn't reliable: the first swap of the shapes shows at
once, but after that a new shape only shows once the pointer has moved to a
new place and stayed there. Moving it away and back doesn't help, even with a
pause. Tested on the `ready` image, November 2026.
"""

from __future__ import annotations

import struct

from .protocol import Out
from .win32 import SM_CXSCREEN, SM_CYSCREEN, SPI_GETWORKAREA, SPI_SETWORKAREA, SW_HIDE, screen_size, work_area  # noqa: F401

COLOR_DESKTOP = 1
BLACK = 0x000000

# The interface effects as (name, get action, set action). Each set action
# takes its on/off value in pvParam, so 0 turns it off.
UI_EFFECTS = (
    ("menu animation", 0x1002, 0x1003),
    ("combo box animation", 0x1004, 0x1005),
    ("list box smooth scrolling", 0x1006, 0x1007),
    ("gradient captions", 0x1008, 0x1009),
    ("hot tracking", 0x100E, 0x100F),
)

# Every pointer shape Windows 98 draws by itself: arrow, I-beam, wait, cross,
# up arrow, the four resize arrows, move, no, hand and arrow-with-hourglass.
POINTER_SHAPES = (32512, 32513, 32514, 32515, 32516,
                  32642, 32643, 32644, 32645, 32646, 32648, 32649, 32650)
POINTER_SIZE = 32


class DesktopError(RuntimeError):
    """The guest didn't end up blank."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("the desktop isn't blank:\n" + "\n".join(f"  {p}" for p in problems))


def shell_windows(guest) -> tuple[int, int, int]:
    """The taskbar, the desktop and its icon list, as window handles (0 if missing)."""
    user32 = guest.user32
    taskbar = user32.FindWindowA("Shell_TrayWnd", 0).value
    desktop = user32.FindWindowA("Progman", 0).value
    view = user32.FindWindowExA(desktop, 0, "SHELLDLL_DefView", 0).value if desktop else 0
    icons = user32.FindWindowExA(view, 0, "SysListView32", 0).value if view else 0
    return taskbar, desktop, icons


def blank(guest, pointer: bool = False) -> None:
    """Turn the restored desktop into a black, empty screen, then check it.

    pointer=True keeps the pointer visible. Raises DesktopError listing
    anything that didn't take.
    """
    user32 = guest.user32
    taskbar, desk, icons = shell_windows(guest)
    user32.SetSysColors(1, struct.pack("<I", COLOR_DESKTOP), struct.pack("<I", BLACK))
    if icons:
        user32.ShowWindow(icons, SW_HIDE)
    if taskbar:
        user32.ShowWindow(taskbar, SW_HIDE)
        user32.EnableWindow(taskbar, 0)
    if desk:
        user32.EnableWindow(desk, 0)
    width, height = screen_size(guest)
    user32.SystemParametersInfoA(SPI_SETWORKAREA, 0, struct.pack("<4i", 0, 0, width, height), 0)
    for _name, _get, set_action in UI_EFFECTS:
        user32.SystemParametersInfoA(set_action, 0, 0, 0)
    if not pointer:
        hide_pointer(guest)
    guest.sync()
    problems = check_blank(guest)
    if problems:
        raise DesktopError(problems)


def check_blank(guest) -> list[str]:
    """Every way the guest differs from a blank desktop. The pointer isn't checked."""
    user32 = guest.user32
    problems = []
    taskbar, desk, icons = shell_windows(guest)
    if not icons:
        problems.append("the desktop icon list wasn't found")
    elif user32.IsWindowVisible(icons).value:
        problems.append("the desktop icons are showing")
    if not taskbar:
        problems.append("the taskbar wasn't found")
    elif user32.IsWindowVisible(taskbar).value:
        problems.append("the taskbar is showing")
    elif user32.IsWindowEnabled(taskbar).value:
        problems.append("the taskbar takes input, so the Windows key opens the Start menu")
    if desk and user32.IsWindowEnabled(desk).value:
        problems.append("the desktop takes input, so a right-click opens its menu")
    colour = user32.GetSysColor(COLOR_DESKTOP).value & 0xFFFFFF
    if colour != BLACK:
        problems.append(f"the desktop colour is {colour:06x}, not black")
    width, height = screen_size(guest)
    area = work_area(guest)
    if area != (0, 0, width, height):
        problems.append(f"the work area is {list(area)}, not the whole {width}x{height} screen")
    for name, get_action, _set in UI_EFFECTS:
        result = user32.SystemParametersInfoA(get_action, 0, Out(4), 0)
        if struct.unpack("<I", result.buffers[0])[0]:
            problems.append(f"{name} is on")
    return problems


def hide_pointer(guest) -> None:
    """Swap every system pointer shape for an empty one.

    The pointer still moves and clicks; it just draws nothing. A program that
    sets its own pointer shape (Paint's tools, say) still shows that one. Call
    it once after a revert: see the module notes.
    """
    user32 = guest.user32
    mask = POINTER_SIZE * POINTER_SIZE // 8
    empty = user32.CreateCursor(0, 0, 0, POINTER_SIZE, POINTER_SIZE,
                                b"\xff" * mask, b"\x00" * mask).value
    try:
        for shape in POINTER_SHAPES:
            # SetSystemCursor takes over the handle it's given, so each gets a copy.
            user32.SetSystemCursor(user32.CopyIcon(empty).value, shape)
    finally:
        user32.DestroyCursor(empty)
