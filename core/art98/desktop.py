"""The blank start: a black, empty screen on the restored desktop.

The `ready` snapshot is the stock Windows 98 desktop: a teal background,
icons, the taskbar and the arrow pointer. `apply_desktop(guest, BLANK_PARTS)`
turns all of that off in the running guest. Each step only changes memory, so it holds until the next
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
from dataclasses import KW_ONLY, dataclass

from .errors import GuestError, UsageError
from .guest.protocol import Out
from .guest.win32 import (
    BUTTONS_CLASS,
    CLOCK_CLASS,
    COLOR_DESKTOP,
    HKCU,
    KEY_SET_VALUE,
    OCR_APPSTARTING,
    OCR_CROSS,
    OCR_HAND,
    OCR_IBEAM,
    OCR_NO,
    OCR_NORMAL,
    OCR_SIZEALL,
    OCR_SIZENESW,
    OCR_SIZENS,
    OCR_SIZENWSE,
    OCR_SIZEWE,
    OCR_UP,
    OCR_WAIT,
    QUICK_LAUNCH_CLASS,
    REBAR_CLASS,
    REG_SZ,
    SPI_GETCOMBOBOXANIMATION,
    SPI_GETGRADIENTCAPTIONS,
    SPI_GETHOTTRACKING,
    SPI_GETLISTBOXSMOOTHSCROLLING,
    SPI_GETMENUANIMATION,
    SPI_SETCOMBOBOXANIMATION,
    SPI_SETDESKWALLPAPER,
    SPI_SETGRADIENTCAPTIONS,
    SPI_SETHOTTRACKING,
    SPI_SETLISTBOXSMOOTHSCROLLING,
    SPI_SETMENUANIMATION,
    SPI_SETWORKAREA,
    SPIF_SENDWININICHANGE,
    SPIF_UPDATEINIFILE,
    SW_HIDE,
    TASKBAR_CLASS,
    TRAY_CLASS,
    WM_SIZE,
    colourref,
    repaint_all,
    screen_size,
    work_area,
)

NAMED_COLOURS = {
    "teal": (0, 128, 128),
    "dark_red": (128, 0, 0),
    "red": (255, 0, 0),
    "white": (255, 255, 255),
    "black": (0, 0, 0),
}

# (TileWallpaper, WallpaperStyle). The one place the styles are defined.
STYLES = {"center": ("0", "0"), "tile": ("1", "0"), "stretch": ("0", "2")}

# The interface effects as (name, get action, set action). Each set action
# takes its on/off value in pvParam, so 0 turns it off.
UI_EFFECTS = (
    ("menu animation", SPI_GETMENUANIMATION, SPI_SETMENUANIMATION),
    ("combo box animation", SPI_GETCOMBOBOXANIMATION, SPI_SETCOMBOBOXANIMATION),
    (
        "list box smooth scrolling",
        SPI_GETLISTBOXSMOOTHSCROLLING,
        SPI_SETLISTBOXSMOOTHSCROLLING,
    ),
    ("gradient captions", SPI_GETGRADIENTCAPTIONS, SPI_SETGRADIENTCAPTIONS),
    ("hot tracking", SPI_GETHOTTRACKING, SPI_SETHOTTRACKING),
)

# Every pointer shape Windows 98 draws by itself: arrow, I-beam, wait, cross,
# up arrow, the four resize arrows, move, no, hand and arrow-with-hourglass.
POINTER_SHAPES = (
    OCR_NORMAL,
    OCR_IBEAM,
    OCR_WAIT,
    OCR_CROSS,
    OCR_UP,
    OCR_SIZENWSE,
    OCR_SIZENESW,
    OCR_SIZEWE,
    OCR_SIZENS,
    OCR_SIZEALL,
    OCR_NO,
    OCR_HAND,
    OCR_APPSTARTING,
)
POINTER_SIZE = 32


class DesktopError(GuestError):
    """The guest didn't end up blank, or refused the wallpaper or pointer change."""

    def __init__(self, problems: list[str], lead: str = "the desktop isn't blank:"):
        self.problems = problems
        super().__init__(lead + "\n" + "\n".join(f"  {p}" for p in problems))


def shell_windows(guest) -> tuple[int, int, int]:
    """The taskbar, the desktop and its icon list, as window handles (0 if missing)."""
    user32 = guest.user32
    taskbar = user32.FindWindowA(TASKBAR_CLASS, 0).value
    desktop = user32.FindWindowA("Progman", 0).value
    view = (
        user32.FindWindowExA(desktop, 0, "SHELLDLL_DefView", 0).value if desktop else 0
    )
    icons = user32.FindWindowExA(view, 0, "SysListView32", 0).value if view else 0
    return taskbar, desktop, icons


def resolve_colour(colour) -> tuple[int, int, int]:
    """A colour name from NAMED_COLOURS or an (r, g, b) of ints 0..255, as a tuple. Raises UsageError."""
    if isinstance(colour, str):
        if colour not in NAMED_COLOURS:
            raise UsageError(
                f"unknown colour {colour!r}; use one of {sorted(NAMED_COLOURS)} or (r, g, b)"
            )
        return NAMED_COLOURS[colour]
    try:
        rgb = tuple(colour)
    except TypeError:
        raise UsageError(
            f"colour must be a name or (r, g, b), not {colour!r}"
        ) from None
    if len(rgb) != 3 or not all(type(c) is int and 0 <= c <= 255 for c in rgb):
        raise UsageError(f"colour must be three ints from 0 to 255, not {colour!r}")
    return rgb


def set_colour(guest, rgb) -> None:
    """Set the desktop colour. The change shows the icons and tray again on a
    blank desktop, so hide them again: the icons before the sync (as before),
    the tray after it, once Explorer's thread has handled the broadcast.

    The broadcast makes every window repaint itself on its own thread, in no
    set order, and a frame repainted late can draw over the window in front of
    it (or leave pixels behind). So once every thread has taken the message,
    the whole screen is repainted back to front: the frame comes out as a
    fresh paint would draw it, on every run.
    """
    user32 = guest.user32
    taskbar, _desk, icons = shell_windows(guest)
    tray = (
        user32.FindWindowExA(taskbar, 0, TRAY_CLASS, 0).value
        if taskbar and user32.IsWindowVisible(taskbar).value
        else 0
    )
    icons_hidden = bool(icons) and not user32.IsWindowVisible(icons).value
    tray_hidden = bool(tray) and not user32.IsWindowVisible(tray).value
    user32.SetSysColors(
        1, struct.pack("<I", COLOR_DESKTOP), struct.pack("<I", colourref(rgb))
    )
    if icons_hidden:
        user32.ShowWindow(icons, SW_HIDE)  # as today, before the sync
    guest.sync()  # every window's thread has handled WM_SYSCOLORCHANGE
    if tray_hidden:
        user32.ShowWindow(tray, SW_HIDE)  # after the sync (Explorer shows it again)
    repaint_all(guest)


def set_wallpaper(guest, path: str, style: str) -> None:
    """Show the BMP at `path` on the desktop. Icons are not re-hidden: the call doesn't bring them back."""
    tile, mode = STYLES[style]
    key = guest.advapi32.RegOpenKeyExA(
        HKCU, r"Control Panel\Desktop", 0, KEY_SET_VALUE, Out(4)
    )
    if key.value != 0:
        raise DesktopError(
            [r"could not open Control Panel\Desktop in the registry"],
            "the wallpaper failed:",
        )
    hkey = struct.unpack("<I", key.buffers[0])[0]
    try:
        for name, value in (("TileWallpaper", tile), ("WallpaperStyle", mode)):
            data = value.encode() + b"\0"
            if (
                guest.advapi32.RegSetValueExA(
                    hkey, name, 0, REG_SZ, data, len(data)
                ).value
                != 0
            ):
                raise DesktopError(
                    [f"could not set {name} in the registry"], "the wallpaper failed:"
                )
    finally:
        guest.advapi32.RegCloseKey(hkey)
    guest.user32.SystemParametersInfoA(
        SPI_SETDESKWALLPAPER, 0, path, SPIF_UPDATEINIFILE | SPIF_SENDWININICHANGE
    )
    guest.sync()


# The taskbar's children, in the order apply_desktop hides them after the clock,
# with the name check_parts gives each in a message.
CHILDREN = (
    ("buttons", "buttons", BUTTONS_CLASS),
    ("quick_launch", "quick launch", QUICK_LAUNCH_CLASS),
    ("tray", "tray", TRAY_CLASS),
    ("clock", "clock", CLOCK_CLASS),
)


def off_children(parts: Parts) -> list[str]:
    """The taskbar children to touch: those off, and the clock only under a tray that is on."""
    if not parts.taskbar:
        return []
    return [
        name
        for name, _label, _cls in CHILDREN
        if not getattr(parts, name) and (name != "clock" or parts.tray)
    ]


def taskbar_windows(guest, taskbar: int, names=None) -> dict[str, int]:
    """The handles of the taskbar's children named in `names` (all four when None); 0 for a missing one."""
    user32 = guest.user32
    names = {name for name, _l, _c in CHILDREN} if names is None else set(names)
    found = dict.fromkeys(names, 0)
    if names & {"buttons", "quick_launch"}:
        rebar = user32.FindWindowExA(taskbar, 0, REBAR_CLASS, 0).value
        for name, _label, cls in CHILDREN[:2]:
            if name in names and rebar:
                found[name] = user32.FindWindowExA(rebar, 0, cls, 0).value
    if names & {"tray", "clock"}:
        tray = user32.FindWindowExA(taskbar, 0, TRAY_CLASS, 0).value
        if "tray" in names:
            found["tray"] = tray
        if "clock" in names and tray:
            found["clock"] = user32.FindWindowExA(tray, 0, CLOCK_CLASS, 0).value
    return found


def apply_desktop(guest, parts: Parts) -> None:
    """Put the parts in place on a reverted desktop, then check them.

    Raises DesktopError listing anything that didn't take.
    """
    if parts == STOCK_PARTS:
        return
    user32 = guest.user32
    taskbar, desk, icons = shell_windows(guest)
    children = off_children(parts)
    handles = taskbar_windows(guest, taskbar, children) if taskbar and children else {}
    if parts.blank_steps:
        set_colour(guest, NAMED_COLOURS["black"])
    if not parts.icons and icons:
        user32.ShowWindow(icons, SW_HIDE)
    if not parts.taskbar and taskbar:
        user32.ShowWindow(taskbar, SW_HIDE)
        user32.EnableWindow(taskbar, 0)
    if parts.blank_steps and desk:
        user32.EnableWindow(desk, 0)
    if not parts.taskbar:
        width, height = screen_size(guest)
        user32.SystemParametersInfoA(
            SPI_SETWORKAREA, 0, struct.pack("<4i", 0, 0, width, height), 0
        )
    if parts.blank_steps:
        for _name, _get, set_action in UI_EFFECTS:
            user32.SystemParametersInfoA(set_action, 0, 0, 0)
    # The clock first, then WM_SIZE so the tray settles to its icon before
    # anything else is hidden; the tray last.
    if handles.get("clock"):
        user32.ShowWindow(handles["clock"], SW_HIDE)
        user32.SendMessageA(taskbar, WM_SIZE, 0, 0)
    for name in ("buttons", "quick_launch", "tray"):
        if handles.get(name):
            user32.ShowWindow(handles[name], SW_HIDE)
    if not parts.pointer:
        hide_pointer(guest)
    guest.sync()
    problems = check_parts(guest, parts)
    if problems:
        raise DesktopError(
            problems,
            "the desktop isn't blank:"
            if parts.blank_steps
            else "the desktop options didn't take:",
        )


def check_parts(guest, parts: Parts) -> list[str]:
    """Every way the guest differs from `parts`. Reads only what is off, plus the taskbar.

    The pointer isn't checked.
    """
    if parts == STOCK_PARTS:
        return []
    user32 = guest.user32
    problems = []
    taskbar, desk, icons = shell_windows(guest)
    if not parts.icons:
        if not icons:
            problems.append("the desktop icon list wasn't found")
        elif user32.IsWindowVisible(icons).value:
            problems.append("the desktop icons are showing")
    if not taskbar:
        problems.append("the taskbar wasn't found")
    elif not parts.taskbar:
        if user32.IsWindowVisible(taskbar).value:
            problems.append("the taskbar is showing")
        elif user32.IsWindowEnabled(taskbar).value:
            problems.append(
                "the taskbar takes input, so the Windows key opens the Start menu"
            )
    elif children := off_children(parts):
        handles = taskbar_windows(guest, taskbar, children)
        for name, label, cls in CHILDREN:
            if name not in children:
                continue
            if not handles[name]:
                problems.append(f"the taskbar's {label} ({cls}) wasn't found")
            elif user32.IsWindowVisible(handles[name]).value:
                problems.append(f"the taskbar's {label} is showing")
    if parts.blank_steps:
        if desk and user32.IsWindowEnabled(desk).value:
            problems.append("the desktop takes input, so a right-click opens its menu")
        colour = user32.GetSysColor(COLOR_DESKTOP).value & 0xFFFFFF
        if colour != colourref(NAMED_COLOURS["black"]):
            problems.append(f"the desktop colour is {colour:06x}, not black")
    if not parts.taskbar:
        width, height = screen_size(guest)
        area = work_area(guest)
        if area != (0, 0, width, height):
            problems.append(
                f"the work area is {list(area)}, not the whole {width}x{height} screen"
            )
    if parts.blank_steps:
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
    empty = user32.CreateCursor(
        0, 0, 0, POINTER_SIZE, POINTER_SIZE, b"\xff" * mask, b"\x00" * mask
    ).value
    if not empty:
        raise DesktopError(
            ["CreateCursor returned no cursor, so the pointer can't be hidden"],
            "the pointer failed:",
        )
    try:
        for shape in POINTER_SHAPES:
            # SetSystemCursor takes over the handle it's given, so each gets a copy.
            if not user32.SetSystemCursor(user32.CopyIcon(empty).value, shape).value:
                raise DesktopError(
                    [f"SetSystemCursor failed for pointer shape {shape}"],
                    "the pointer failed:",
                )
    finally:
        user32.DestroyCursor(empty)


@dataclass(frozen=True)
class Desktop:
    """What a scene's desktop shows: a preset, then parts written over it.

    Each option is True, False or left out (the preset's value). A part under an
    option that is off is hidden whatever it says; `resolve_desktop` warns.
    """

    preset: str = "blank"
    _: KW_ONLY
    icons: bool | None = None
    pointer: bool | None = None
    taskbar: bool | None = None
    buttons: bool | None = None
    quick_launch: bool | None = None
    tray: bool | None = None
    clock: bool | None = None


@dataclass(frozen=True)
class Parts:
    """What the guest will show. A child of an off part is always False."""

    icons: bool
    pointer: bool
    taskbar: bool
    buttons: bool
    quick_launch: bool
    tray: bool
    clock: bool
    # The steps that belong to no part: black colour, disabled Progman,
    # animations, gradient captions and hot tracking off. True for "blank" only.
    blank_steps: bool


# Each option and the option it sits directly under. The one place the levels live.
PARENT = {
    "buttons": "taskbar",
    "quick_launch": "taskbar",
    "tray": "taskbar",
    "clock": "tray",
}

_OPTIONS = ("icons", "pointer", "taskbar", "buttons", "quick_launch", "tray", "clock")

PRESETS = {
    "blank": {
        **dict.fromkeys(_OPTIONS, True),
        "icons": False,
        "pointer": False,
        "taskbar": False,
    },
    "stock": dict.fromkeys(_OPTIONS, True),
}

STOCK_PARTS = Parts(*(True,) * 7, blank_steps=False)
BLANK_PARTS = Parts(False, False, False, False, False, False, False, blank_steps=True)


def resolve_desktop(
    value, owner: str, pointer_visible: bool | None
) -> tuple[Parts, list[str]]:
    """The effective parts and the warning texts. Pure; raises UsageError.

    `owner` is "ClassName.desktop". `pointer_visible` is None when never declared.
    """
    if isinstance(value, str):
        value = Desktop(value)
    elif not isinstance(value, Desktop):
        raise UsageError(
            f"{owner} {value!r}: use one of {', '.join(PRESETS)}, or a Desktop(...)"
        )
    preset = value.preset
    if not isinstance(preset, str) or preset not in PRESETS:
        raise UsageError(f"{owner} {preset!r}: use one of {', '.join(PRESETS)}")
    written = {name: getattr(value, name) for name in _OPTIONS}
    for name, got in written.items():
        if got is not None and type(got) is not bool:
            raise UsageError(f"{owner}: {name} must be True or False, not {got!r}")
    base = {name: preset_value if written[name] is None else written[name]
            for name, preset_value in PRESETS[preset].items()}  # fmt: skip
    notes = []
    effective = {}
    for name in _OPTIONS:
        off = []  # the options this one sits under that are off, lowest first
        up = PARENT.get(name)
        while up is not None:
            if not base[up]:
                off.append(up)
            up = PARENT.get(up)
        effective[name] = base[name] and not off
        if written[name] is not None and off:
            top = off[-1]
            source = (
                f"{top}=False" if written[top] is not None else f'the "{preset}" preset'
            )
            notes.append(
                f"{owner}: {name}={written[name]} has no effect, because {top} is off "
                f"({source}). Remove {name}={written[name]}, or write {top}=True."
            )
    if written["pointer"] is not None:
        if pointer_visible is not None and bool(pointer_visible) != written["pointer"]:
            notes.append(
                f"{owner.removesuffix('.desktop')}.pointer_visible = {bool(pointer_visible)} "
                f"is ignored, because Desktop(pointer={written['pointer']}) sets the pointer. "
                "Remove pointer_visible, or make the two agree."
            )
    elif preset == "blank":
        effective["pointer"] = bool(pointer_visible)
    return Parts(**effective, blank_steps=preset == "blank"), notes
