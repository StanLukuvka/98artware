# FLOW-PRODUCED: written by a LAD worker for .kiro/specs/desktop-taskbar-options/tasks.md (Task 1). Check the flow before hand-editing.
"""The desktop tree: Desktop options resolved to Parts, with warning texts.

Every case of the pure function is walked (2 presets x 3^7 options x 3
pointer_visible values = 13,122) against an oracle written from the level table
as explicit lists, not from the implementation's PARENT.
"""

from __future__ import annotations

import dataclasses
import itertools

import pytest
from art98.desktop import BLANK_PARTS, STOCK_PARTS, Desktop, resolve_desktop
from art98.errors import UsageError

OWNER = "Scene.desktop"
OPTIONS = ("icons", "pointer", "taskbar", "buttons", "quick_launch", "tray", "clock")
# Highest first, so the first one that is off is the one to name.
UNDER = {
    "buttons": ("taskbar",),
    "quick_launch": ("taskbar",),
    "tray": ("taskbar",),
    "clock": ("taskbar", "tray"),
}
PRESET_VALUES = {
    "stock": dict.fromkeys(OPTIONS, True),
    "blank": {
        "icons": False,
        "pointer": False,
        "taskbar": False,
        "buttons": True,
        "quick_launch": True,
        "tray": True,
        "clock": True,
    },
}
VALUES = (None, True, False)
POINTERS = (None, True, False)


def cases():
    for preset in PRESET_VALUES:
        for combo in itertools.product(VALUES, repeat=len(OPTIONS)):
            for pv in POINTERS:
                yield preset, dict(zip(OPTIONS, combo)), pv


def oracle(preset, written):
    """(base, expected overridden options -> (top off option, source))."""
    base = {
        o: PRESET_VALUES[preset][o] if written[o] is None else written[o]
        for o in OPTIONS
    }
    hit = {}
    for option, unders in UNDER.items():
        if written[option] is None:
            continue
        off = [u for u in unders if not base[u]]
        if off:
            top = off[0]
            hit[option] = (
                top,
                f"{top}=False"
                if written[top] is not None
                else f'the "{preset}" preset',
            )
    return base, hit


def test_every_case_warns_exactly_for_a_written_option_under_an_off_one():
    for preset, written, pv in cases():
        _parts, notes = resolve_desktop(Desktop(preset, **written), OWNER, pv)
        _, hit = oracle(preset, written)
        overrides = [n for n in notes if "pointer_visible" not in n]
        assert len(overrides) == len(hit), (preset, written, pv, notes)
        expected = [
            f"{OWNER}: {o}={written[o]} has no effect, because {top} is off ({src}). "
            f"Remove {o}={written[o]}, or write {top}=True."
            for o, (top, src) in hit.items()  # table order: UNDER is in table order
        ]
        assert overrides == expected, (preset, written, pv)


def test_every_case_never_shows_a_child_of_an_off_parent():
    for preset, written, pv in cases():
        parts, _ = resolve_desktop(Desktop(preset, **written), OWNER, pv)
        for child, unders in UNDER.items():
            if getattr(parts, child):
                assert all(getattr(parts, u) for u in unders), (preset, written, child)


def test_every_case_gives_what_was_written_unless_something_above_is_off():
    for preset, written, pv in cases():
        parts, _ = resolve_desktop(Desktop(preset, **written), OWNER, pv)
        base, _ = oracle(preset, written)
        for o in OPTIONS:
            if o == "pointer":
                continue  # see the pointer_visible test
            above_off = any(not base[u] for u in UNDER.get(o, ()))
            assert getattr(parts, o) is (False if above_off else base[o]), (
                preset,
                written,
                o,
            )
        assert parts.blank_steps is (preset == "blank")


def test_every_case_a_warned_option_does_nothing():
    for preset, written, pv in cases():
        _, hit = oracle(preset, written)
        if not hit:
            continue
        parts, notes = resolve_desktop(Desktop(preset, **written), OWNER, pv)
        for option in hit:
            others = [n for n in notes if f" {option}=" not in n]
            for value in VALUES:
                again, again_notes = resolve_desktop(
                    Desktop(preset, **{**written, option: value}), OWNER, pv
                )
                assert again == parts, (preset, written, option, value)
                assert [n for n in again_notes if f" {option}=" not in n] == others


@pytest.mark.parametrize(
    "preset,parts", [("stock", STOCK_PARTS), ("blank", BLANK_PARTS)]
)
def test_a_preset_alone_never_warns_and_gives_its_parts(preset, parts):
    for pv in POINTERS:
        for value in (preset, Desktop(preset)):
            got, notes = resolve_desktop(value, OWNER, pv)
            assert notes == []
            on_blank = preset == "blank" and bool(pv)
            assert got == dataclasses.replace(
                parts, pointer=preset == "stock" or on_blank
            )


def test_pointer_visible_touches_only_the_pointer_and_its_warning():
    for preset, written, _ in cases():
        results = {
            pv: resolve_desktop(Desktop(preset, **written), OWNER, pv)
            for pv in POINTERS
        }
        stripped = {
            pv: dataclasses.replace(p, pointer=False) for pv, (p, _) in results.items()
        }
        assert stripped[None] == stripped[True] == stripped[False]
        for pv, (parts, notes) in results.items():
            pointer_notes = [n for n in notes if "pointer_visible" in n]
            wants = (
                written["pointer"] is not None
                and pv is not None
                and pv != written["pointer"]
            )
            assert bool(pointer_notes) is wants, (preset, written, pv)
            if written["pointer"] is not None:
                assert parts.pointer is written["pointer"]
            elif preset == "blank":
                assert parts.pointer is bool(pv)
            else:
                assert parts.pointer is True
            # the override notes do not depend on pointer_visible
            assert [n for n in notes if "pointer_visible" not in n] == [
                n for n in results[None][1] if "pointer_visible" not in n
            ]
            if pointer_notes:
                assert notes[-1] == pointer_notes[0]


def test_resolving_is_pure():
    for preset, written, pv in itertools.islice(cases(), 0, None, 7):
        desktop = Desktop(preset, **written)
        before = dataclasses.astuple(desktop)
        assert resolve_desktop(desktop, OWNER, pv) == resolve_desktop(
            desktop, OWNER, pv
        )
        assert dataclasses.astuple(desktop) == before


@pytest.mark.parametrize("bad", [1, 0, "on", []])
@pytest.mark.parametrize("option", OPTIONS)
def test_a_value_that_is_not_true_or_false_is_refused_naming_owner_and_option(
    option, bad
):
    with pytest.raises(UsageError) as caught:
        resolve_desktop(Desktop("stock", **{option: bad}), OWNER, None)
    assert (
        caught.value.args[0] == f"{OWNER}: {option} must be True or False, not {bad!r}"
    )


def test_the_clock_warning_names_the_tray():
    _, notes = resolve_desktop(
        Desktop("stock", tray=False, clock=True), "NoTray.desktop", None
    )
    assert notes == [
        (
            "NoTray.desktop: clock=True has no effect, because tray is off (tray=False). "
            "Remove clock=True, or write tray=True."
        )
    ]


def test_a_child_warning_names_the_taskbar_the_author_turned_off():
    _, notes = resolve_desktop(
        Desktop("stock", taskbar=False, buttons=False), "A.desktop", None
    )
    assert notes == [
        (
            "A.desktop: buttons=False has no effect, because taskbar is off (taskbar=False). "
            "Remove buttons=False, or write taskbar=True."
        )
    ]


def test_a_child_warning_names_the_blank_preset_when_it_turns_the_taskbar_off():
    _, notes = resolve_desktop(Desktop("blank", buttons=False), "A.desktop", None)
    assert notes == [
        (
            'A.desktop: buttons=False has no effect, because taskbar is off (the "blank" preset). '
            "Remove buttons=False, or write taskbar=True."
        )
    ]


def test_the_clock_warning_names_the_highest_off_option():
    _, notes = resolve_desktop(
        Desktop("stock", taskbar=False, tray=False, clock=True), "A.desktop", None
    )
    assert notes[-1].startswith(
        "A.desktop: clock=True has no effect, because taskbar is off (taskbar=False)."
    )


def test_the_pointer_warning_says_the_tree_wins():
    parts, notes = resolve_desktop(
        Desktop("stock", pointer=False), "Hover.desktop", True
    )
    assert not parts.pointer
    assert notes == [
        (
            "Hover.pointer_visible = True is ignored, because Desktop(pointer=False) sets the pointer. "
            "Remove pointer_visible, or make the two agree."
        )
    ]


def test_the_pointer_note_comes_last():
    _, notes = resolve_desktop(
        Desktop("stock", tray=False, clock=True, pointer=True), "A.desktop", False
    )
    assert len(notes) == 2 and notes[-1].startswith("A.pointer_visible")


def test_the_stock_and_blank_presets_equal_their_constants():
    assert resolve_desktop("stock", OWNER, None)[0] == STOCK_PARTS
    assert resolve_desktop("blank", OWNER, None)[0] == BLANK_PARTS


def test_blank_with_a_taskbar_shows_every_child():
    parts, notes = resolve_desktop(
        Desktop("blank", taskbar=True, buttons=False), OWNER, None
    )
    assert notes == []
    assert (parts.taskbar, parts.buttons, parts.quick_launch, parts.tray, parts.clock) == (
        True, False, True, True, True,
    )  # fmt: skip
    assert parts.blank_steps


def test_options_are_keyword_only_and_misspellings_fail():
    with pytest.raises(TypeError):
        Desktop("stock", False)  # type: ignore[misc]
    with pytest.raises(TypeError):
        Desktop(clok=False)  # type: ignore[call-arg]


def test_a_desktop_cannot_be_changed():
    desktop = Desktop("stock")
    with pytest.raises(dataclasses.FrozenInstanceError):
        desktop.clock = False  # type: ignore[misc]


def test_an_unknown_preset_is_refused_with_the_class_name():
    with pytest.raises(UsageError) as caught:
        resolve_desktop("foo", "Scene.desktop", None)
    assert caught.value.args[0] == "Scene.desktop 'foo': use one of blank, stock"


def test_a_value_that_is_not_a_preset_or_a_desktop_is_refused():
    with pytest.raises(UsageError) as caught:
        resolve_desktop(5, "Scene.desktop", None)
    assert (
        caught.value.args[0]
        == "Scene.desktop 5: use one of blank, stock, or a Desktop(...)"
    )
