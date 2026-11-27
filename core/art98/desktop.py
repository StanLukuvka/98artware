"""The blank start: a black, empty screen on the restored desktop.

The `ready` snapshot is the stock Windows 98 desktop: a teal background,
icons, the taskbar and the arrow pointer. `apply_desktop(guest, BLANK_DESKTOP_PARTS)`
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
    shell_windows_taskbar_hwnd = user32.FindWindowA(TASKBAR_CLASS, 0).value
    shell_windows_progman_hwnd = user32.FindWindowA("Progman", 0).value
    view = (
        user32.FindWindowExA(shell_windows_progman_hwnd, 0, "SHELLDLL_DefView", 0).value
        if shell_windows_progman_hwnd
        else 0
    )
    shell_windows_icons_hwnd = (
        user32.FindWindowExA(view, 0, "SysListView32", 0).value if view else 0
    )
    return (
        shell_windows_taskbar_hwnd,
        shell_windows_progman_hwnd,
        shell_windows_icons_hwnd,
    )


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
    """Set the desktop colour: the plain background behind the icons and around a
    centred wallpaper. It isn't the taskbar or selection colour.

    The change shows the icons and tray again on a blank desktop, so hide them
    again: the icons before the sync (as before), the tray after it, once
    Explorer's thread has handled the broadcast.

    The broadcast makes every window repaint itself on its own thread, in no
    set order, and a frame repainted late can draw over the window in front of
    it (or leave pixels behind). So once every thread has taken the message,
    the whole screen is repainted back to front: the frame comes out as a
    fresh paint would draw it, on every run.
    """
    user32 = guest.user32
    set_colour_taskbar_hwnd, _desk, set_colour_icons_hwnd = shell_windows(guest)
    set_colour_tray_hwnd = (
        user32.FindWindowExA(set_colour_taskbar_hwnd, 0, TRAY_CLASS, 0).value
        if set_colour_taskbar_hwnd
        and user32.IsWindowVisible(set_colour_taskbar_hwnd).value
        else 0
    )
    icons_hidden = (
        bool(set_colour_icons_hwnd)
        and not user32.IsWindowVisible(set_colour_icons_hwnd).value
    )
    tray_hidden = (
        bool(set_colour_tray_hwnd)
        and not user32.IsWindowVisible(set_colour_tray_hwnd).value
    )
    user32.SetSysColors(
        1, struct.pack("<I", COLOR_DESKTOP), struct.pack("<I", colourref(rgb))
    )
    if icons_hidden:
        user32.ShowWindow(set_colour_icons_hwnd, SW_HIDE)  # as today, before the sync
    guest.sync()  # every window's thread has handled WM_SYSCOLORCHANGE
    if tray_hidden:
        user32.ShowWindow(
            set_colour_tray_hwnd, SW_HIDE
        )  # after the sync (Explorer shows it again)
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
# with the name check_desktop_parts gives each in a message.
CHILDREN = (
    ("buttons", "buttons", BUTTONS_CLASS),
    ("quick_launch", "quick launch", QUICK_LAUNCH_CLASS),
    ("tray", "tray", TRAY_CLASS),
    ("clock", "clock", CLOCK_CLASS),
)


def off_children(off_children_desktop_parts: DesktopParts) -> list[str]:
    """The taskbar children to touch: those off, and the clock only under a tray that is on."""
    if not off_children_desktop_parts.taskbar:
        return []
    return [
        name
        for name, _label, _cls in CHILDREN
        if not getattr(off_children_desktop_parts, name)
        and (name != "clock" or off_children_desktop_parts.tray)
    ]


def taskbar_windows(
    guest, taskbar_windows_taskbar_hwnd: int, taskbar_windows_taskbar_children=None
) -> dict[str, int]:
    """The handles of the taskbar's children named in `taskbar_windows_taskbar_children` (all four when None); 0 for a missing one."""
    user32 = guest.user32
    taskbar_windows_taskbar_children = (
        {name for name, _l, _c in CHILDREN}
        if taskbar_windows_taskbar_children is None
        else set(taskbar_windows_taskbar_children)
    )
    taskbar_windows_taskbar_child_hwnds = dict.fromkeys(
        taskbar_windows_taskbar_children, 0
    )
    if taskbar_windows_taskbar_children & {"buttons", "quick_launch"}:
        rebar = user32.FindWindowExA(
            taskbar_windows_taskbar_hwnd, 0, REBAR_CLASS, 0
        ).value
        for name, _label, cls in CHILDREN[:2]:
            if name in taskbar_windows_taskbar_children and rebar:
                taskbar_windows_taskbar_child_hwnds[name] = user32.FindWindowExA(
                    rebar, 0, cls, 0
                ).value
    if taskbar_windows_taskbar_children & {"tray", "clock"}:
        taskbar_windows_tray_hwnd = user32.FindWindowExA(
            taskbar_windows_taskbar_hwnd, 0, TRAY_CLASS, 0
        ).value
        if "tray" in taskbar_windows_taskbar_children:
            taskbar_windows_taskbar_child_hwnds["tray"] = taskbar_windows_tray_hwnd
        if "clock" in taskbar_windows_taskbar_children and taskbar_windows_tray_hwnd:
            taskbar_windows_taskbar_child_hwnds["clock"] = user32.FindWindowExA(
                taskbar_windows_tray_hwnd, 0, CLOCK_CLASS, 0
            ).value
    return taskbar_windows_taskbar_child_hwnds


def apply_desktop(guest, apply_desktop_desktop_parts: DesktopParts) -> None:
    """Put the parts in place on a reverted desktop, then check them.

    Raises DesktopError listing anything that didn't take.
    """
    if apply_desktop_desktop_parts == STOCK_DESKTOP_PARTS:
        return
    user32 = guest.user32
    apply_desktop_taskbar_hwnd, apply_desktop_progman_hwnd, apply_desktop_icons_hwnd = (
        shell_windows(guest)
    )
    apply_desktop_taskbar_children = off_children(apply_desktop_desktop_parts)
    apply_desktop_taskbar_child_hwnds = (
        taskbar_windows(
            guest, apply_desktop_taskbar_hwnd, apply_desktop_taskbar_children
        )
        if apply_desktop_taskbar_hwnd and apply_desktop_taskbar_children
        else {}
    )
    if apply_desktop_desktop_parts.blank_steps:
        set_colour(guest, NAMED_COLOURS["black"])
    if not apply_desktop_desktop_parts.icons and apply_desktop_icons_hwnd:
        user32.ShowWindow(apply_desktop_icons_hwnd, SW_HIDE)
    if not apply_desktop_desktop_parts.taskbar and apply_desktop_taskbar_hwnd:
        user32.ShowWindow(apply_desktop_taskbar_hwnd, SW_HIDE)
        user32.EnableWindow(apply_desktop_taskbar_hwnd, 0)
    if apply_desktop_desktop_parts.blank_steps and apply_desktop_progman_hwnd:
        user32.EnableWindow(apply_desktop_progman_hwnd, 0)
    if not apply_desktop_desktop_parts.taskbar:
        width, height = screen_size(guest)
        user32.SystemParametersInfoA(
            SPI_SETWORKAREA, 0, struct.pack("<4i", 0, 0, width, height), 0
        )
    if apply_desktop_desktop_parts.blank_steps:
        for _name, _get, set_action in UI_EFFECTS:
            user32.SystemParametersInfoA(set_action, 0, 0, 0)
    # The clock first, then WM_SIZE so the tray settles to its icon before
    # anything else is hidden; the tray last.
    if apply_desktop_taskbar_child_hwnds.get("clock"):
        user32.ShowWindow(apply_desktop_taskbar_child_hwnds["clock"], SW_HIDE)
        user32.SendMessageA(apply_desktop_taskbar_hwnd, WM_SIZE, 0, 0)
    for name in ("buttons", "quick_launch", "tray"):
        if apply_desktop_taskbar_child_hwnds.get(name):
            user32.ShowWindow(apply_desktop_taskbar_child_hwnds[name], SW_HIDE)
    if not apply_desktop_desktop_parts.pointer:
        hide_pointer(guest)
    guest.sync()
    apply_desktop_desktop_problems = check_desktop_parts(
        guest, apply_desktop_desktop_parts
    )
    if apply_desktop_desktop_problems:
        raise DesktopError(
            apply_desktop_desktop_problems,
            "the desktop isn't blank:"
            if apply_desktop_desktop_parts.blank_steps
            else "the desktop options didn't take:",
        )


def check_desktop_parts(
    guest, check_desktop_parts_desktop_parts: DesktopParts
) -> list[str]:
    """Every way the guest differs from `check_desktop_parts_desktop_parts`. Reads only what is off, plus the taskbar.

    The pointer isn't checked.
    """
    if check_desktop_parts_desktop_parts == STOCK_DESKTOP_PARTS:
        return []
    user32 = guest.user32
    check_desktop_parts_desktop_problems = []
    (
        check_desktop_parts_taskbar_hwnd,
        check_desktop_parts_progman_hwnd,
        check_desktop_parts_icons_hwnd,
    ) = shell_windows(guest)
    if not check_desktop_parts_desktop_parts.icons:
        if not check_desktop_parts_icons_hwnd:
            check_desktop_parts_desktop_problems.append(
                "the desktop icon list wasn't found"
            )
        elif user32.IsWindowVisible(check_desktop_parts_icons_hwnd).value:
            check_desktop_parts_desktop_problems.append("the desktop icons are showing")
    if not check_desktop_parts_taskbar_hwnd:
        check_desktop_parts_desktop_problems.append("the taskbar wasn't found")
    elif not check_desktop_parts_desktop_parts.taskbar:
        if user32.IsWindowVisible(check_desktop_parts_taskbar_hwnd).value:
            check_desktop_parts_desktop_problems.append("the taskbar is showing")
        elif user32.IsWindowEnabled(check_desktop_parts_taskbar_hwnd).value:
            check_desktop_parts_desktop_problems.append(
                "the taskbar takes input, so the Windows key opens the Start menu"
            )
    elif check_desktop_parts_taskbar_children := off_children(
        check_desktop_parts_desktop_parts
    ):
        check_desktop_parts_taskbar_child_hwnds = taskbar_windows(
            guest,
            check_desktop_parts_taskbar_hwnd,
            check_desktop_parts_taskbar_children,
        )
        for name, label, cls in CHILDREN:
            if name not in check_desktop_parts_taskbar_children:
                continue
            if not check_desktop_parts_taskbar_child_hwnds[name]:
                check_desktop_parts_desktop_problems.append(
                    f"the taskbar's {label} ({cls}) wasn't found"
                )
            elif user32.IsWindowVisible(
                check_desktop_parts_taskbar_child_hwnds[name]
            ).value:
                check_desktop_parts_desktop_problems.append(
                    f"the taskbar's {label} is showing"
                )
    if check_desktop_parts_desktop_parts.blank_steps:
        if (
            check_desktop_parts_progman_hwnd
            and user32.IsWindowEnabled(check_desktop_parts_progman_hwnd).value
        ):
            check_desktop_parts_desktop_problems.append(
                "the desktop takes input, so a right-click opens its menu"
            )
        colour = user32.GetSysColor(COLOR_DESKTOP).value & 0xFFFFFF
        if colour != colourref(NAMED_COLOURS["black"]):
            check_desktop_parts_desktop_problems.append(
                f"the desktop colour is {colour:06x}, not black"
            )
    if not check_desktop_parts_desktop_parts.taskbar:
        width, height = screen_size(guest)
        area = work_area(guest)
        if area != (0, 0, width, height):
            check_desktop_parts_desktop_problems.append(
                f"the work area is {list(area)}, not the whole {width}x{height} screen"
            )
    if check_desktop_parts_desktop_parts.blank_steps:
        for name, get_action, _set in UI_EFFECTS:
            result = user32.SystemParametersInfoA(get_action, 0, Out(4), 0)
            if struct.unpack("<I", result.buffers[0])[0]:
                check_desktop_parts_desktop_problems.append(f"{name} is on")
    return check_desktop_parts_desktop_problems


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
class DesktopParts:
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

STOCK_DESKTOP_PARTS = DesktopParts(*(True,) * 7, blank_steps=False)
BLANK_DESKTOP_PARTS = DesktopParts(
    False, False, False, False, False, False, False, blank_steps=True
)


def resolve_desktop(
    resolve_desktop_desktop: Desktop, resolve_desktop_desktop_owner: str
) -> tuple[DesktopParts, list[str]]:
    """The effective parts and the warning texts. Pure; raises UsageError.

    `resolve_desktop_desktop_owner` is "ClassName.desktop". `resolve_desktop_desktop`
    must be a Desktop: the caller refuses anything else, because it knows what to
    tell the author to write.
    """
    preset = resolve_desktop_desktop.preset
    if not isinstance(preset, str) or preset not in PRESETS:
        raise UsageError(
            f"{resolve_desktop_desktop_owner} {preset!r}: use one of {', '.join(PRESETS)}"
        )
    written = {name: getattr(resolve_desktop_desktop, name) for name in _OPTIONS}
    for name, got in written.items():
        if got is not None and type(got) is not bool:
            raise UsageError(
                f"{resolve_desktop_desktop_owner}: {name} must be True or False, not {got!r}"
            )
    base = {name: preset_value if written[name] is None else written[name]
            for name, preset_value in PRESETS[preset].items()}  # fmt: skip
    resolve_desktop_desktop_notes = []
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
            resolve_desktop_desktop_notes.append(
                f"{resolve_desktop_desktop_owner}: {name}={written[name]} has no effect, because {top} is off "
                f"({source}). Remove {name}={written[name]}, or write {top}=True."
            )
    resolve_desktop_desktop_parts = DesktopParts(
        **effective, blank_steps=preset == "blank"
    )
    return resolve_desktop_desktop_parts, resolve_desktop_desktop_notes
