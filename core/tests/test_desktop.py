# FLOW-PRODUCED: written by a LAD worker for .kiro/specs/desktop-taskbar-options/tasks.md (Tasks 4, 7-8). Check the flow before hand-editing.
"""The blank start, against a fake guest that keeps the state apply_desktop() changes."""

import itertools
import json
import struct
import warnings
from dataclasses import replace

import pytest
from art98 import desktop
from art98.anim import Backdrop, Scene
from art98.errors import GuestError
from art98.guest import win32
from art98.guest.bridge import CallResult
from test_anim import FakeGuest, FakeSession, FakeVideo, Stage

TASKBAR, PROGMAN, VIEW, ICONS = 0x50, 0x60, 0x61, 0x62
REBAR, QUICK, BUTTONS, TRAY, CLOCK = 0x70, 0x71, 0x72, 0x73, 0x74
# child -> parent: a child shows only when it and every ancestor does
CHILD_PARENT = {
    REBAR: TASKBAR,
    QUICK: REBAR,
    BUTTONS: REBAR,
    TRAY: TASKBAR,
    CLOCK: TRAY,
}
EMPTY = 0x900
EFFECT_GETS = {get: set_ for _name, get, set_ in desktop.UI_EFFECTS}


class DesktopGuest(FakeGuest):
    """A stock desktop that answers what apply_desktop() sets and reads."""

    def __init__(self, ignore=()):
        super().__init__()
        self.ignore = set(ignore)
        self.visible = {TASKBAR, ICONS}
        self.hidden_parts = set()  # taskbar children hidden on their own
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
        found = {
            (PROGMAN, "SHELLDLL_DefView"): VIEW,
            (VIEW, "SysListView32"): ICONS,
            (TASKBAR, win32.REBAR_CLASS): REBAR,
            (REBAR, win32.QUICK_LAUNCH_CLASS): QUICK,
            (REBAR, win32.BUTTONS_CLASS): BUTTONS,
            (TASKBAR, win32.TRAY_CLASS): TRAY,
            (TRAY, win32.CLOCK_CLASS): CLOCK,
        }
        return CallResult(found.get((parent, class_name), 0), 0, [])

    def do_ShowWindow(self, hwnd, command):
        if "hide" not in self.ignore and command == win32.SW_HIDE:
            self.visible.discard(hwnd)
            if hwnd in CHILD_PARENT:
                self.hidden_parts.add(hwnd)
        return CallResult(1, 0, [])

    def do_EnableWindow(self, hwnd, enable):
        was_disabled = hwnd not in self.enabled
        (self.enabled.add if enable else self.enabled.discard)(hwnd)
        return CallResult(int(was_disabled), 0, [])

    def do_IsWindowEnabled(self, hwnd):
        return CallResult(int(hwnd in self.enabled), 0, [])

    def do_IsWindowVisible(self, hwnd):
        shown = hwnd in self.visible
        if hwnd in CHILD_PARENT:
            shown = (
                hwnd not in self.hidden_parts
                and self.do_IsWindowVisible(CHILD_PARENT[hwnd]).value
            )
        return CallResult(int(shown), 0, [])

    def do_SetSysColors(self, count, indexes, colours):
        if struct.unpack("<I", indexes)[0] == win32.COLOR_DESKTOP:
            self.colour = struct.unpack("<I", colours)[0]
            self.hidden_parts.discard(TRAY)  # a colour change shows the tray again
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


EXPECTED_BLANK_CALLS = [
    ("SetSysColors",),
    ("sync",),
    ("sync",),
    ("ShowWindow", ICONS, win32.SW_HIDE),
    ("ShowWindow", TASKBAR, win32.SW_HIDE),
    ("EnableWindow", TASKBAR, 0),
    ("EnableWindow", PROGMAN, 0),
    ("SystemParametersInfoA", win32.SPI_SETWORKAREA),
    *[("SystemParametersInfoA", set_) for _n, _g, set_ in desktop.UI_EFFECTS],
    ("CreateCursor",),
    *[("CopyIcon",), ("SetSystemCursor",)] * len(desktop.POINTER_SHAPES),
    ("DestroyCursor", EMPTY),
    ("sync",),
]


def changes(guest):
    """The calls that change the guest, in order, as (name, key argument). Reads are left out."""
    seen = []
    for name, args in guest.calls:
        if name in ("SetSysColors", "CreateCursor", "CopyIcon", "SetSystemCursor"):
            seen.append((name,))
        elif name in ("ShowWindow", "EnableWindow", "DestroyCursor"):
            seen.append((name, *args))
        elif name == "SystemParametersInfoA" and args[0] in SET_ACTIONS:
            seen.append((name, args[0]))
        elif name == "sync":
            seen.append((name,))
    return seen


SET_ACTIONS = {win32.SPI_SETWORKAREA} | set(EFFECT_GETS.values())


def traced(guest):
    """Make guest.sync leave a ("sync", ()) entry in guest.calls."""
    real = guest.sync

    def sync(*args, **kwargs):
        guest.calls.append(("sync", ()))
        return real(*args, **kwargs)

    guest.sync = sync
    return guest


def test_blank_makes_the_same_calls_in_the_same_order():
    guest = traced(DesktopGuest())
    desktop.apply_desktop(guest, desktop.BLANK_PARTS)
    assert changes(guest) == EXPECTED_BLANK_CALLS


def test_blank_hides_the_shell_and_turns_everything_off():
    guest = DesktopGuest()
    desktop.apply_desktop(guest, desktop.BLANK_PARTS)
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
    )  # set_colour waits twice (see test_drift.py), then apply_desktop waits once


def test_blank_can_keep_the_pointer():
    guest = DesktopGuest()
    desktop.apply_desktop(guest, replace(desktop.BLANK_PARTS, pointer=True))
    assert guest.named("SetSystemCursor") == []


def test_blank_says_so_when_there_is_no_empty_pointer():
    guest = DesktopGuest()
    guest.do_CreateCursor = lambda *args: CallResult(0, 0, [])
    with pytest.raises(desktop.DesktopError, match="CreateCursor returned no cursor"):
        desktop.apply_desktop(guest, desktop.BLANK_PARTS)
    assert guest.named("SetSystemCursor") == []


def test_blank_says_so_when_a_pointer_shape_will_not_swap():
    guest = DesktopGuest()
    guest.do_SetSystemCursor = lambda handle, shape: CallResult(0, 0, [])
    with pytest.raises(desktop.DesktopError, match="SetSystemCursor failed for"):
        desktop.apply_desktop(guest, desktop.BLANK_PARTS)
    assert guest.named("DestroyCursor") == [("DestroyCursor", (EMPTY,))]


def test_desktop_error_is_a_guest_error():
    assert issubclass(desktop.DesktopError, GuestError)


def test_the_effect_and_pointer_tables_use_the_named_constants():
    assert desktop.POINTER_SHAPES[0] == win32.OCR_NORMAL == 32512
    assert desktop.POINTER_SHAPES[-1] == win32.OCR_APPSTARTING == 32650
    assert desktop.UI_EFFECTS[0] == (
        "menu animation",
        win32.SPI_GETMENUANIMATION,
        win32.SPI_SETMENUANIMATION,
    )


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
        desktop.apply_desktop(guest, desktop.BLANK_PARTS)
    assert any(p.startswith(problem) for p in error.value.problems)


def test_check_parts_reports_a_missing_shell():
    guest = DesktopGuest()
    guest.do_FindWindowA = lambda class_name, title: CallResult(0, 0, [])
    problems = desktop.check_parts(guest, desktop.BLANK_PARTS)
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


def test_an_unknown_desktop_is_refused_where_the_class_is_defined():
    with pytest.raises(ValueError, match="Odd.desktop 'teal'"):

        class Odd(Blank):
            desktop = "teal"


def test_an_unknown_desktop_set_on_an_instance_is_refused_at_run():
    scene = Blank()
    scene.desktop = "teal"
    guest = DesktopGuest()
    with pytest.raises(ValueError, match="desktop 'teal'"):
        scene.run(FakeSession(guest), FakeVideo(guest))


def test_scenes_start_blank_unless_told_otherwise(monkeypatch):
    monkeypatch.undo()
    assert Scene.desktop == "blank"


CHILD_HANDLE = {
    "buttons": BUTTONS,
    "quick_launch": QUICK,
    "tray": TRAY,
    "clock": CLOCK,
}


@pytest.mark.parametrize("part", list(CHILD_HANDLE) + ["icons", "pointer", "taskbar"])
def test_hiding_one_part_on_stock_leaves_the_rest(part):
    if part == "taskbar":
        parts = desktop.resolve_desktop(
            desktop.Desktop("stock", taskbar=False), "T.desktop", None
        )[0]
    else:
        parts = replace(desktop.STOCK_PARTS, **{part: False})
    guest = DesktopGuest()
    desktop.apply_desktop(guest, parts)
    assert desktop.check_parts(guest, parts) == []
    if part in CHILD_HANDLE:
        assert CHILD_HANDLE[part] in guest.hidden_parts
        assert not guest.do_IsWindowVisible(CHILD_HANDLE[part]).value
        for other, handle in CHILD_HANDLE.items():
            if other != part:
                assert handle not in guest.hidden_parts
    elif part == "icons":
        assert ICONS not in guest.visible
    elif part == "pointer":
        assert guest.pointer_hidden()
    else:
        assert TASKBAR not in guest.visible
        assert TASKBAR not in guest.enabled
        assert guest.area == (0, 0, 800, 600)
        assert ICONS in guest.visible
        assert not guest.pointer_hidden()


def test_hiding_buttons_and_the_clock_together():
    parts = replace(desktop.STOCK_PARTS, buttons=False, clock=False)
    guest = DesktopGuest()
    desktop.apply_desktop(guest, parts)
    assert desktop.check_parts(guest, parts) == []
    assert BUTTONS in guest.hidden_parts
    assert CLOCK in guest.hidden_parts
    assert TRAY not in guest.hidden_parts
    assert QUICK not in guest.hidden_parts


def test_the_work_area_stays_put_when_only_children_are_off():
    guest = DesktopGuest()
    before = guest.area
    parts = replace(desktop.STOCK_PARTS, buttons=False, clock=False)
    desktop.apply_desktop(guest, parts)
    assert guest.area == before
    assert all(
        call[1][0] != win32.SPI_SETWORKAREA
        for call in guest.named("SystemParametersInfoA")
    )


def test_stock_with_the_pointer_off_hides_the_pointer_once():
    guest = DesktopGuest()
    desktop.apply_desktop(guest, replace(desktop.STOCK_PARTS, pointer=False))
    assert guest.pointer_hidden()
    assert len(guest.named("CreateCursor")) == 1
    assert len(guest.named("DestroyCursor")) == 1


def test_blank_with_the_taskbar_on_keeps_the_taskbar():
    guest = DesktopGuest()
    parts = desktop.resolve_desktop(
        desktop.Desktop("blank", taskbar=True), "T.desktop", None
    )[0]
    desktop.apply_desktop(guest, parts)
    assert guest.do_IsWindowVisible(TASKBAR).value == 1
    assert TASKBAR in guest.enabled
    assert guest.area == (0, 0, 800, 572)
    assert guest.colour == 0
    assert PROGMAN not in guest.enabled
    assert set(guest.effects.values()) == {0}
    assert ICONS not in guest.visible
    assert desktop.check_parts(guest, parts) == []


def test_the_clock_hides_first_and_the_tray_hides_last():
    def child_sequence(parts):
        guest = DesktopGuest()
        desktop.apply_desktop(guest, parts)
        return [
            (name, args[0])
            for name, args in guest.calls
            if (
                name == "ShowWindow"
                and args[0] in CHILD_PARENT
                and args[1] == win32.SW_HIDE
            )
            or (
                name == "SendMessageA"
                and args[0] == TASKBAR
                and args[1] == win32.WM_SIZE
            )
        ]

    # A clock hide (with WM_SIZE) only runs while its tray is still on, so the
    # clock-first and tray-last orders are checked with two different parts.
    assert child_sequence(
        replace(desktop.STOCK_PARTS, buttons=False, quick_launch=False, clock=False)
    ) == [
        ("ShowWindow", CLOCK),
        ("SendMessageA", TASKBAR),
        ("ShowWindow", BUTTONS),
        ("ShowWindow", QUICK),
    ]
    assert child_sequence(
        replace(desktop.STOCK_PARTS, buttons=False, quick_launch=False, tray=False)
    ) == [
        ("ShowWindow", BUTTONS),
        ("ShowWindow", QUICK),
        ("ShowWindow", TRAY),
    ]


def test_stock_parts_makes_no_guest_call():
    guest = DesktopGuest()
    desktop.apply_desktop(guest, desktop.STOCK_PARTS)
    assert guest.calls == []


def test_check_parts_does_not_look_up_a_child_that_is_on():
    guest = DesktopGuest()
    parts = replace(desktop.STOCK_PARTS, buttons=False)
    desktop.apply_desktop(guest, parts)
    guest.calls.clear()
    assert desktop.check_parts(guest, parts) == []
    looked_up = {args[1] for name, args in guest.calls if name == "FindWindowExA"}
    assert win32.QUICK_LAUNCH_CLASS not in looked_up
    assert win32.TRAY_CLASS not in looked_up
    assert win32.CLOCK_CLASS not in looked_up


def test_a_part_that_will_not_hide_is_named_on_one_line():
    guest = DesktopGuest(ignore=["hide"])
    parts = replace(desktop.STOCK_PARTS, buttons=False)
    with pytest.raises(desktop.DesktopError) as error:
        desktop.apply_desktop(guest, parts)
    assert error.value.problems == ["the taskbar's buttons is showing"]
    assert str(error.value).startswith("the desktop options didn't take:")


def test_a_part_that_cannot_be_found_is_named_on_one_line():
    guest = DesktopGuest()
    real = guest.do_FindWindowExA

    def no_buttons(parent, after, class_name, title):
        if class_name == win32.BUTTONS_CLASS:
            return CallResult(0, 0, [])
        return real(parent, after, class_name, title)

    guest.do_FindWindowExA = no_buttons
    parts = replace(desktop.STOCK_PARTS, buttons=False)
    with pytest.raises(desktop.DesktopError) as error:
        desktop.apply_desktop(guest, parts)
    assert error.value.problems == [
        "the taskbar's buttons (MSTaskSwWClass) wasn't found"
    ]


def test_two_problems_are_listed_in_check_order():
    guest = DesktopGuest(ignore=["hide"])
    parts = replace(desktop.STOCK_PARTS, icons=False, buttons=False)
    with pytest.raises(desktop.DesktopError) as error:
        desktop.apply_desktop(guest, parts)
    assert error.value.problems == [
        "the desktop icons are showing",
        "the taskbar's buttons is showing",
    ]


def test_every_resolved_parts_applies_and_checks_twice():
    options = (
        "icons",
        "pointer",
        "taskbar",
        "buttons",
        "quick_launch",
        "tray",
        "clock",
    )
    distinct = {}
    for preset in ("blank", "stock"):
        for values in itertools.product((None, True, False), repeat=7):
            parts = desktop.resolve_desktop(
                desktop.Desktop(preset, **dict(zip(options, values))), "T.desktop", None
            )[0]
            distinct.setdefault(parts, (preset, values))
    assert len(distinct) > 20
    for parts, case in distinct.items():
        guest = DesktopGuest()
        desktop.apply_desktop(guest, parts)
        assert desktop.check_parts(guest, parts) == [], case
        hidden = {
            args[0]
            for name, args in guest.calls
            if name == "ShowWindow" and args[1] == win32.SW_HIDE
        }
        for child, parent in CHILD_PARENT.items():
            if child in hidden:
                assert parent not in hidden, (case, child, parent)
        before = (frozenset(guest.visible), frozenset(guest.hidden_parts))
        desktop.apply_desktop(guest, parts)
        assert desktop.check_parts(guest, parts) == [], case
        assert (frozenset(guest.visible), frozenset(guest.hidden_parts)) == before, case


def test_a_colour_change_keeps_the_tray_hidden():
    guest = traced(DesktopGuest())
    parts = replace(desktop.STOCK_PARTS, buttons=False, quick_launch=False, tray=False)
    desktop.apply_desktop(guest, parts)
    guest.calls.clear()
    desktop.set_colour(guest, (0, 128, 128))
    assert all(
        not guest.do_IsWindowVisible(handle).value for handle in (BUTTONS, QUICK, TRAY)
    )
    names = [name for name, _args in guest.calls]
    show_tray = guest.calls.index(("ShowWindow", (TRAY, win32.SW_HIDE)))
    first_sync = names.index("sync")
    assert first_sync < show_tray < names.index("sync", first_sync + 1)
    assert desktop.check_parts(guest, parts) == []

    # The clock stays hidden on its own while its tray is still on.
    guest = DesktopGuest()
    clock_parts = replace(desktop.STOCK_PARTS, clock=False)
    desktop.apply_desktop(guest, clock_parts)
    desktop.set_colour(guest, (0, 128, 128))
    assert not guest.do_IsWindowVisible(CLOCK).value
    assert desktop.check_parts(guest, clock_parts) == []


def test_a_colour_change_on_blank_adds_no_show_window():
    guest = DesktopGuest()
    desktop.apply_desktop(guest, desktop.BLANK_PARTS)
    guest.calls.clear()
    desktop.set_colour(guest, (0, 128, 128))
    # The taskbar is already hidden on blank, so set_colour reads only its
    # visibility beyond the icons read it always did; no tray lookup at all.
    assert [args for name, args in guest.calls if name == "IsWindowVisible"] == [
        (TASKBAR,),
        (ICONS,),
    ]
    assert guest.named("ShowWindow") == [("ShowWindow", (ICONS, win32.SW_HIDE))]


def test_a_backdrop_keeps_the_tray_hidden():
    guest = traced(DesktopGuest())
    scene = Stage()
    scene.run(FakeSession(guest), FakeVideo(guest))
    parts = replace(desktop.STOCK_PARTS, buttons=False, quick_launch=False, tray=False)
    desktop.apply_desktop(guest, parts)
    guest.calls.clear()
    scene.play(Backdrop((0, 128, 128)))
    assert all(
        not guest.do_IsWindowVisible(handle).value for handle in (BUTTONS, QUICK, TRAY)
    )
    names = [name for name, _args in guest.calls]
    assert guest.calls.index(("ShowWindow", (TRAY, win32.SW_HIDE))) > names.index(
        "sync"
    )
    assert desktop.check_parts(guest, parts) == []


# ---- the scene wiring: refusals, warnings and the parts a run applies ----

Desktop = desktop.Desktop

CLOCK_TEXT = (
    "{name}.desktop: clock=True has no effect, because tray is off (tray=False). "
    "Remove clock=True, or write tray=True."
)
BUTTONS_TEXT = (
    "{name}.desktop: buttons=False has no effect, because taskbar is off "
    "({source}). Remove buttons=False, or write taskbar=True."
)


def defined_warnings(make):
    """The warnings `make()` raises under the default filter, once per place."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("default")
        make()
    return caught


def test_a_desktop_that_is_not_a_preset_or_desktop_is_refused():
    with pytest.raises(ValueError, match="Odd.desktop 5"):

        class Odd(Blank):
            desktop = 5


@pytest.mark.parametrize("bad", [1, "off"])
def test_a_non_bool_option_is_refused_naming_the_class(bad):
    with pytest.raises(ValueError, match=r"Odd.desktop: tray must be True or False"):

        class Odd(Blank):
            desktop = Desktop("stock", tray=bad)

    scene = Blank()
    scene.desktop = Desktop("stock", tray=bad)
    guest = DesktopGuest()
    with pytest.raises(ValueError, match=r"Blank.desktop: tray must be True or False"):
        scene.run(FakeSession(guest), FakeVideo(guest))


def test_a_clock_under_a_hidden_tray_warns_where_the_class_is_defined():
    with pytest.warns(UserWarning) as caught:

        class NoTray(Blank):
            desktop = Desktop("stock", tray=False, clock=True)

    assert [str(w.message) for w in caught] == [CLOCK_TEXT.format(name="NoTray")]
    assert caught[0].filename == __file__


def test_buttons_under_a_hidden_taskbar_warn_with_the_author_s_option():
    with pytest.warns(UserWarning) as caught:

        class NoBar(Blank):
            desktop = Desktop("stock", taskbar=False, buttons=False)

    text = BUTTONS_TEXT.format(name="NoBar", source="taskbar=False")
    assert [str(w.message) for w in caught] == [text]


def test_buttons_under_the_blank_preset_warn_with_the_preset():
    with pytest.warns(UserWarning) as caught:

        class BlankButtons(Blank):
            desktop = Desktop("blank", buttons=False)

    text = BUTTONS_TEXT.format(name="BlankButtons", source='the "blank" preset')
    assert [str(w.message) for w in caught] == [text]


def test_a_warning_shows_once_per_class_and_a_subclass_does_not_repeat_it():
    def make():
        class Once(Blank):
            desktop = Desktop("stock", tray=False, clock=True)

        class Again(Once):
            pass

        class Third(Once):
            pass

    caught = defined_warnings(make)
    assert [str(w.message) for w in caught] == [CLOCK_TEXT.format(name="Once")]


def test_a_subclass_setting_only_the_pointer_gets_no_override_warning():
    def make():
        class Parent(Blank):
            desktop = Desktop("stock", tray=False, clock=True)

        class Child(Parent):
            pointer_visible = True

    caught = defined_warnings(make)
    assert [str(w.message) for w in caught] == [CLOCK_TEXT.format(name="Parent")]


def test_a_pointer_visible_the_desktop_overrides_warns_at_the_class():
    with pytest.warns(UserWarning, match=r"Hover\.pointer_visible = True") as caught:

        class Hover(Blank):
            desktop = Desktop("blank", pointer=False)
            pointer_visible = True

    assert len(caught) == 1


def test_a_subclass_that_sets_pointer_visible_against_an_inherited_desktop_warns():
    class Parent(Blank):
        desktop = Desktop("blank", pointer=False)

    with pytest.warns(UserWarning, match=r"Child\.pointer_visible = True"):

        class Child(Parent):
            pointer_visible = True


@pytest.mark.parametrize(
    "value",
    [
        "stock",
        "blank",
        Desktop("stock", clock=False),
        Desktop("blank", taskbar=True, buttons=False),
    ],
)
def test_a_preset_alone_or_an_override_that_takes_effect_does_not_warn(value):
    def make():
        class Quiet(Blank):
            desktop = value

    assert defined_warnings(make) == []


def test_pointer_visible_false_on_stock_does_not_warn():
    def make():
        class Quiet(Blank):
            desktop = "stock"
            pointer_visible = False

    assert defined_warnings(make) == []


def test_an_instance_that_sets_a_dead_option_warns_at_run_naming_the_class():
    scene = Blank()
    scene.desktop = Desktop("stock", tray=False, clock=True)
    guest = DesktopGuest()
    with pytest.warns(UserWarning) as caught:
        scene.run(FakeSession(guest), FakeVideo(guest))
    assert [str(w.message) for w in caught] == [CLOCK_TEXT.format(name="Blank")]
    assert caught[0].filename == __file__


def test_an_instance_that_sets_pointer_visible_against_the_desktop_warns_at_run():
    class Hidden(Blank):
        desktop = Desktop("blank", pointer=False)

    scene = Hidden()
    scene.pointer_visible = True
    guest = DesktopGuest()
    with pytest.warns(UserWarning, match=r"Hidden\.pointer_visible = True"):
        scene.run(FakeSession(guest), FakeVideo(guest))


def test_a_class_that_warned_does_not_warn_again_at_run():
    with pytest.warns(UserWarning):

        class Once(Blank):
            desktop = Desktop("stock", tray=False, clock=True)

    guest = DesktopGuest()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        Once().run(FakeSession(guest), FakeVideo(guest))


def test_the_render_goes_on_after_a_warning_with_the_effective_parts():
    with pytest.warns(UserWarning):

        class Goes(Blank):
            desktop = Desktop("stock", tray=False, clock=True)

    guest = DesktopGuest()
    Goes().run(FakeSession(guest), FakeVideo(guest))
    assert TRAY in guest.hidden_parts
    assert CLOCK not in guest.hidden_parts  # the tray's hide covers it
    assert guest.visible == {TASKBAR, ICONS}


def test_pointer_visible_on_stock_changes_nothing():
    class Stock(Blank):
        desktop = "stock"
        pointer_visible = True

    guest = DesktopGuest()
    Stock().run(FakeSession(guest), FakeVideo(guest))
    assert guest.named("SetSystemCursor") == []
    assert guest.visible == {TASKBAR, ICONS}


def test_set_state_applies_the_parts_again_after_a_revert(monkeypatch, tmp_path):
    from art98.anim import setstate

    monkeypatch.setattr(setstate, "apply_state", lambda scene, state: {})
    monkeypatch.setattr(setstate, "check_state", lambda *a: None)
    (tmp_path / "s.json").write_text('{"version": 1}')
    with pytest.warns(UserWarning):

        class Again(Blank):
            desktop = Desktop("stock", icons=False, tray=False, clock=True)

            def construct(self):
                self.set_state(tmp_path / "s.json")

    guest = DesktopGuest()

    class Reverting(FakeSession):
        def revert(self, snapshot="ready"):
            super().revert(snapshot)
            guest.visible = {TASKBAR, ICONS}  # the snapshot is a stock desktop
            guest.hidden_parts = set()

    session = Reverting(guest)
    Again().run(session, FakeVideo(guest))
    assert session.reverts == 1
    # only a second apply after the revert hides the icons again
    assert ICONS not in guest.visible


def test_a_display_change_in_a_state_applies_the_parts_again(monkeypatch):
    from art98 import state as state_module
    from art98.anim import setstate

    modes = [(640, 480, 16)]
    monkeypatch.setattr(setstate, "display_mode", lambda guest: modes[0])
    guest = DesktopGuest()

    def change(_guest, *mode, persist):
        modes.insert(0, mode)
        guest.hidden_parts = set()  # a mode change rebuilds the taskbar

    monkeypatch.setattr(setstate, "set_display_mode", change)
    wanted = state_module.State(
        path=None, display=(800, 600, 16), windows=(), pointer=None
    )
    prepared = []

    class Mode(Blank):
        desktop = Desktop("stock", buttons=False, clock=False)

        def construct(self):
            real = self.prepare_desktop
            self.prepare_desktop = lambda: (prepared.append(1), real())[1]
            setstate.apply_state(self, wanted)

    Mode().run(FakeSession(guest), FakeVideo(guest))
    assert modes[0] == (800, 600, 16)
    assert len(prepared) == 1  # the one in apply_state; setup ran before the patch
    assert BUTTONS in guest.hidden_parts and CLOCK in guest.hidden_parts


def test_the_parts_are_applied_before_setup_runs():
    seen = {}

    with pytest.warns(UserWarning):

        class Early(Blank):
            desktop = Desktop("stock", icons=False, tray=False, clock=True)

            def setup(self):
                seen["icons"] = ICONS in self.guest.visible
                seen["tray"] = TRAY in self.guest.hidden_parts

    guest = DesktopGuest()
    Early().run(FakeSession(guest), FakeVideo(guest))
    assert seen == {"icons": False, "tray": True}


def test_a_state_file_with_a_tray_key_is_still_refused(tmp_path):
    from art98.state import StateError, load_state

    path = tmp_path / "state.json"
    path.write_text(json.dumps({"version": 1, "desktop": {"tray": True}}))
    with pytest.raises(StateError) as caught:
        load_state(path)
    assert caught.value.problems == [
        "desktop.tray: not supported yet: the tray comes after this milestone"
    ]


def test_get_state_writes_no_part_fields_for_a_scene_with_parts_off(tmp_path):
    class PartsOff(Blank):
        desktop = Desktop("stock", icons=False, buttons=False, tray=False)

    guest = DesktopGuest()
    scene = PartsOff()
    scene.run(FakeSession(guest), FakeVideo(guest))
    assert ICONS not in guest.visible and TRAY in guest.hidden_parts

    path = tmp_path / "s.json"
    scene.get_state(path)
    written = json.loads(path.read_text())
    part_fields = {"tray", "clock", "buttons", "quick_launch", "taskbar", "icons"}
    assert not part_fields & set(written)
    assert not part_fields & set(written["desktop"])
