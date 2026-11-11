"""Applying a state to the guest, and checking the guest matches it.

Set is revert, apply, check. Revert is `Session.revert`. Apply opens the
state's windows back to front, so each new one lands on top, and places the
pointer last. Check reads back what the state describes and fails on any
difference. Anything the state leaves out isn't checked.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from ..desktop import blank
from ..state import State, StateError, load_state
from ..win32 import (  # noqa: F401  (SW_*, cursor_pos, screen_size stay importable from here)
    SW_MAXIMIZE, SW_SHOWMINNOACTIVE, cursor_pos, repaint_window, screen_size, show_window, work_area,
)
from ..actions.pointer import Pointer
from ..actions.programs.notepad import Notepad
from ..actions.window.picture import Picture

BITSPIXEL = 12
APPS = {"picture": Picture, "notepad": Notepad}


class StateMismatch(StateError):
    """The guest doesn't look like the state after applying it."""


def display_mode(guest) -> tuple[int, int, int]:
    width, height = screen_size(guest)
    dc = guest.user32.GetDC(0).value
    try:
        depth = guest.gdi32.GetDeviceCaps(dc, BITSPIXEL).value
    finally:
        guest.user32.ReleaseDC(0, dc)
    return width, height, depth


def apply_state(scene, state: State) -> dict:
    """Make the reverted desktop match the state. Returns its props by window id."""
    guest = scene.guest
    if state.display and display_mode(guest) != state.display:
        guest.set_display_mode(*state.display, persist=False)
        scene.prepare_desktop()
    props = {}
    for window in state.windows:
        prop = APPS[window.app].from_state(window)
        scene.add(prop)
        props[window.id] = prop
        # Maximizing activates the window, so it's done before the next one
        # opens on top of it, and the order stays back to front.
        if window.show != "normal":
            command = SW_SHOWMINNOACTIVE if window.show == "minimized" else SW_MAXIMIZE
            show_window(guest, prop.hwnd, command)
            prop.refresh()
    # A window moving off another can leave desktop pixels on its frame, so
    # every window is repainted, back to front (design doc: "Stray pixels").
    for window in state.windows:
        repaint_window(guest, props[window.id].hwnd)
    if state.pointer:
        scene.pointer.place(state.pointer)
    guest.sync()
    return props


def check_state(scene, state: State, props: dict) -> None:
    """Raise StateMismatch listing every way the guest differs from the state."""
    guest = scene.guest
    problems = []
    if state.display:
        actual = display_mode(guest)
        if actual != state.display:
            problems.append(f"display: {list(state.display)} wanted, the guest has {list(actual)}")
    found = {w.hwnd: w for w in guest.windows()}
    for index, window in enumerate(state.windows):
        where = f"windows[{index}] {window.id!r}"
        real = found.get(props[window.id].hwnd)
        if real is None or not real.visible:
            problems.append(f"{where}: the window isn't there")
            continue
        if real.title != window.title:
            problems.append(f"{where}: title {window.title!r} wanted, the guest has {real.title!r}")
        hwnd = real.hwnd
        show = ("minimized" if guest.user32.IsIconic(hwnd).value
                else "maximized" if guest.user32.IsZoomed(hwnd).value else "normal")
        if show != window.show:
            problems.append(f"{where}: {window.show} wanted, the window is {show}")
        elif show == "normal":
            left, top, right, bottom = real.rect
            if (left, top) != window.at:
                problems.append(f"{where}: at {list(window.at)} wanted, the guest has {[left, top]}")
            if (right - left, bottom - top) != window.size:
                problems.append(f"{where}: size {list(window.size)} wanted, the guest has "
                                f"{[right - left, bottom - top]}")
    # Top-level windows come back front to back, and the state lists them
    # back to front. Windows 98 sends a minimized window to the bottom, so only
    # the others are compared.
    stacked = [w for w in reversed(state.windows) if w.show != "minimized"]
    wanted = [props[w.id].hwnd for w in stacked]
    order = [hwnd for hwnd in found if hwnd in wanted]
    if len(order) == len(wanted) and order != wanted:
        ids = {props[w.id].hwnd: w.id for w in stacked}
        problems.append(f"windows: front to back should be {[ids[h] for h in wanted]}, "
                        f"the guest has {[ids[h] for h in order]}")
    if state.pointer:
        actual = cursor_pos(guest)
        if actual != state.pointer:
            problems.append(f"pointer: {list(state.pointer)} wanted, the guest has {list(actual)}")
    if problems:
        raise StateMismatch(state.path, problems)


def set_state(scene, path) -> None:
    state = load_state(scene._find_state(Path(path)))
    scene.session.revert()
    for prop in scene.props:
        prop.forget()
    scene.props.clear()
    scene._state_props = {}
    scene._start_desktop()
    props = apply_state(scene, state)
    check_state(scene, state, props)
    scene._state_props = props


def find_state(scene, path: Path) -> Path:
    if path.is_absolute():
        return path
    try:
        beside = Path(inspect.getfile(type(scene))).resolve().parent / path
    except (TypeError, OSError):
        beside = None
    if beside is not None and beside.exists():
        return beside
    return Path.cwd() / path


def start_desktop(scene) -> None:
    scene.prepare_desktop()
    scene.pointer = Pointer()
    scene.pointer.attach(scene)


def prepare_desktop(scene) -> None:
    if scene.desktop == "blank":
        blank(scene.guest, pointer=scene.pointer_visible)
    scene.read_work_area()


def read_work_area(scene) -> None:
    scene.work_area = work_area(scene.guest)
