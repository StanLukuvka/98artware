"""The blank start, against a fake guest that keeps the state blank() changes."""

import struct

import pytest
from art98 import desktop, win32
from art98.anim import Scene
from art98.bridge import CallResult
from test_anim import FakeGuest, FakeSession, FakeVideo

TASKBAR, PROGMAN, VIEW, ICONS = 0x50, 0x60, 0x61, 0x62
EMPTY = 0x900
EFFECT_GETS = {get: set_ for _name, get, set_ in desktop.UI_EFFECTS}


class DesktopGuest(FakeGuest):
    """A stock desktop that answers what blank() sets and reads."""

    def __init__(self, ignore=()):
        super().__init__()
        self.ignore = set(ignore)
        self.visible = {TASKBAR, ICONS}
        self.enabled = {TASKBAR, PROGMAN}
        self.colour = 0x808000
        self.area = (0, 0, 800, 572)
        self.effects = {set_: 1 for set_ in EFFECT_GETS.values()}
        self.system_cursors = {shape: shape for shape in desktop.POINTER_SHAPES}

    def do_FindWindowA(self, class_name, title):
        return CallResult(
            {"Shell_TrayWnd": TASKBAR, "Progman": PROGMAN}.get(class_name, 0), 0, []
        )

    def do_FindWindowExA(self, parent, after, class_name, title):
        found = {(PROGMAN, "SHELLDLL_DefView"): VIEW, (VIEW, "SysListView32"): ICONS}
        return CallResult(found.get((parent, class_name), 0), 0, [])

    def do_ShowWindow(self, hwnd, command):
        if "hide" not in self.ignore and command == win32.SW_HIDE:
            self.visible.discard(hwnd)
        return CallResult(1, 0, [])

    def do_EnableWindow(self, hwnd, enable):
        was_disabled = hwnd not in self.enabled
        (self.enabled.add if enable else self.enabled.discard)(hwnd)
        return CallResult(int(was_disabled), 0, [])

    def do_IsWindowEnabled(self, hwnd):
        return CallResult(int(hwnd in self.enabled), 0, [])

    def do_IsWindowVisible(self, hwnd):
        return CallResult(int(hwnd in self.visible), 0, [])

    def do_SetSysColors(self, count, indexes, colours):
        if struct.unpack("<I", indexes)[0] == win32.COLOR_DESKTOP:
            self.colour = struct.unpack("<I", colours)[0]
        return CallResult(1, 0, [])

    def do_GetSysColor(self, index):
        return CallResult(self.colour, 0, [])

    def do_GetSystemMetrics(self, index):
        return CallResult(
            {win32.SM_CXSCREEN: 800, win32.SM_CYSCREEN: 600}.get(index, 0), 0, []
        )

    def do_SystemParametersInfoA(self, action, value, param, flags):
        if action == win32.SPI_SETWORKAREA and "area" not in self.ignore:
            self.area = struct.unpack("<4i", param)
        elif action == win32.SPI_GETWORKAREA:
            return CallResult(1, 0, [struct.pack("<4i", *self.area)])
        elif action in EFFECT_GETS:
            return CallResult(
                1, 0, [struct.pack("<I", self.effects[EFFECT_GETS[action]])]
            )
        elif action in self.effects:
            self.effects[action] = param
        return CallResult(1, 0, [])

    def do_CreateCursor(self, *args):
        return CallResult(EMPTY, 0, [])

    def do_CopyIcon(self, handle):
        return CallResult(handle, 0, [])

    def do_SetSystemCursor(self, handle, shape):
        self.system_cursors[shape] = handle
        return CallResult(1, 0, [])

    def pointer_hidden(self):
        return set(self.system_cursors.values()) == {EMPTY}


def test_blank_hides_the_shell_and_turns_everything_off():
    guest = DesktopGuest()
    desktop.blank(guest)
    assert guest.visible == set()
    assert guest.enabled == set()
    assert guest.colour == 0
    assert guest.area == (0, 0, 800, 600)
    assert set(guest.effects.values()) == {0}
    assert guest.pointer_hidden()
    assert len(guest.named("CopyIcon")) == len(desktop.POINTER_SHAPES)
    assert guest.named("DestroyCursor") == [("DestroyCursor", (EMPTY,))]
    assert (
        guest.syncs == 3
    )  # set_colour waits twice (see test_drift.py), then blank waits once


def test_blank_can_keep_the_pointer():
    guest = DesktopGuest()
    desktop.blank(guest, pointer=True)
    assert guest.named("SetSystemCursor") == []


@pytest.mark.parametrize(
    "ignore, problem",
    [
        ("hide", "the taskbar is showing"),
        ("area", "the work area is [0, 0, 800, 572]"),
    ],
)
def test_blank_says_what_did_not_take(ignore, problem):
    guest = DesktopGuest(ignore=[ignore])
    with pytest.raises(desktop.DesktopError) as error:
        desktop.blank(guest)
    assert any(p.startswith(problem) for p in error.value.problems)


def test_check_blank_reports_a_missing_shell():
    guest = DesktopGuest()
    guest.do_FindWindowA = lambda class_name, title: CallResult(0, 0, [])
    problems = desktop.check_blank(guest)
    assert "the taskbar wasn't found" in problems
    assert "the desktop icon list wasn't found" in problems


class Blank(Scene):
    desktop = "blank"

    def construct(self):
        self.seen = (self.work_area, self.screen.rect)


def test_a_scene_starts_blank_and_measures_the_whole_screen():
    guest = DesktopGuest()
    scene = Blank()
    session = FakeSession(guest)
    scene.run(session, FakeVideo(guest))
    assert session.reverts == 0
    assert guest.visible == set()
    assert scene.seen == ((0, 0, 800, 600), (0, 0, 800, 600))


def test_a_scene_hides_the_pointer_unless_it_wants_it():
    class Pointed(Blank):
        pointer_visible = True

    hidden, shown = DesktopGuest(), DesktopGuest()
    Blank().run(FakeSession(hidden), FakeVideo(hidden))
    Pointed().run(FakeSession(shown), FakeVideo(shown))
    assert hidden.pointer_hidden()
    assert shown.named("SetSystemCursor") == []
    assert shown.visible == set()


def test_a_stock_scene_leaves_the_desktop_alone():
    class Stock(Blank):
        desktop = "stock"

    guest = DesktopGuest()
    Stock().run(FakeSession(guest), FakeVideo(guest))
    assert guest.visible == {TASKBAR, ICONS}
    assert guest.enabled == {TASKBAR, PROGMAN}
    assert guest.named("SetSysColors") == []


def test_an_unknown_desktop_is_refused():
    class Odd(Blank):
        desktop = "teal"

    guest = DesktopGuest()
    with pytest.raises(ValueError, match="desktop 'teal'"):
        Odd().run(FakeSession(guest), FakeVideo(guest))


def test_scenes_start_blank_unless_told_otherwise(monkeypatch):
    monkeypatch.undo()
    assert Scene.desktop == "blank"
