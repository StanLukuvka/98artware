"""The desktop tree: Desktop options resolved to DesktopParts, with warning texts.

Every case of the pure function is walked (2 presets x 3^7 options = 4,374)
against an oracle written from the level table
as explicit lists, not from the implementation's PARENT.
"""

from __future__ import annotations

import dataclasses
import itertools

import pytest
from art98.desktop import (
    BLANK_DESKTOP_PARTS,
    STOCK_DESKTOP_PARTS,
    Desktop,
    resolve_desktop,
)
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


def cases():
    for preset in PRESET_VALUES:
        for combo in itertools.product(VALUES, repeat=len(OPTIONS)):
            yield preset, dict(zip(OPTIONS, combo))


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
    for preset, written in cases():
        _parts, notes = resolve_desktop(Desktop(preset, **written), OWNER)
        _, hit = oracle(preset, written)
        assert len(notes) == len(hit), (preset, written, notes)
        expected = [
            f"{OWNER}: {o}={written[o]} has no effect, because {top} is off ({src}). "
            f"Remove {o}={written[o]}, or write {top}=True."
            for o, (top, src) in hit.items()  # table order: UNDER is in table order
        ]
        assert notes == expected, (preset, written)


def test_every_case_never_shows_a_child_of_an_off_parent():
    for preset, written in cases():
        parts, _ = resolve_desktop(Desktop(preset, **written), OWNER)
        for child, unders in UNDER.items():
            if getattr(parts, child):
                assert all(getattr(parts, u) for u in unders), (preset, written, child)


def test_every_case_gives_what_was_written_unless_something_above_is_off():
    for preset, written in cases():
        parts, _ = resolve_desktop(Desktop(preset, **written), OWNER)
        base, _ = oracle(preset, written)
        for o in OPTIONS:
            above_off = any(not base[u] for u in UNDER.get(o, ()))
            assert getattr(parts, o) is (False if above_off else base[o]), (
                preset,
                written,
                o,
            )
        assert parts.blank_steps is (preset == "blank")


def test_every_case_a_warned_option_does_nothing():
    for preset, written in cases():
        _, hit = oracle(preset, written)
        if not hit:
            continue
        parts, notes = resolve_desktop(Desktop(preset, **written), OWNER)
        for option in hit:
            others = [n for n in notes if f" {option}=" not in n]
            for value in VALUES:
                again, again_notes = resolve_desktop(
                    Desktop(preset, **{**written, option: value}), OWNER
                )
                assert again == parts, (preset, written, option, value)
                assert [n for n in again_notes if f" {option}=" not in n] == others


@pytest.mark.parametrize(
    "preset,parts", [("stock", STOCK_DESKTOP_PARTS), ("blank", BLANK_DESKTOP_PARTS)]
)
def test_a_preset_alone_never_warns_and_gives_its_parts(preset, parts):
    got, notes = resolve_desktop(Desktop(preset), OWNER)
    assert notes == []
    assert got == parts


def test_the_pointer_comes_from_the_preset_unless_written():
    assert not resolve_desktop(Desktop(), OWNER)[0].pointer
    assert resolve_desktop(Desktop("stock"), OWNER)[0].pointer
    assert resolve_desktop(Desktop(pointer=True), OWNER)[0].pointer
    assert not resolve_desktop(Desktop("stock", pointer=False), OWNER)[0].pointer


def test_resolving_is_pure():
    for preset, written in itertools.islice(cases(), 0, None, 7):
        desktop = Desktop(preset, **written)
        before = dataclasses.astuple(desktop)
        assert resolve_desktop(desktop, OWNER) == resolve_desktop(desktop, OWNER)
        assert dataclasses.astuple(desktop) == before


@pytest.mark.parametrize("bad", [1, 0, "on", []])
@pytest.mark.parametrize("option", OPTIONS)
def test_a_value_that_is_not_true_or_false_is_refused_naming_owner_and_option(
    option, bad
):
    with pytest.raises(UsageError) as caught:
        resolve_desktop(Desktop("stock", **{option: bad}), OWNER)
    assert (
        caught.value.args[0] == f"{OWNER}: {option} must be True or False, not {bad!r}"
    )


def test_the_clock_warning_names_the_tray():
    _, notes = resolve_desktop(
        Desktop("stock", tray=False, clock=True), "NoTray.desktop"
    )
    assert notes == [
        (
            "NoTray.desktop: clock=True has no effect, because tray is off (tray=False). "
            "Remove clock=True, or write tray=True."
        )
    ]


def test_a_child_warning_names_the_taskbar_the_author_turned_off():
    _, notes = resolve_desktop(
        Desktop("stock", taskbar=False, buttons=False), "A.desktop"
    )
    assert notes == [
        (
            "A.desktop: buttons=False has no effect, because taskbar is off (taskbar=False). "
            "Remove buttons=False, or write taskbar=True."
        )
    ]


def test_a_child_warning_names_the_blank_preset_when_it_turns_the_taskbar_off():
    _, notes = resolve_desktop(Desktop("blank", buttons=False), "A.desktop")
    assert notes == [
        (
            'A.desktop: buttons=False has no effect, because taskbar is off (the "blank" preset). '
            "Remove buttons=False, or write taskbar=True."
        )
    ]


def test_the_clock_warning_names_the_highest_off_option():
    _, notes = resolve_desktop(
        Desktop("stock", taskbar=False, tray=False, clock=True), "A.desktop"
    )
    assert notes[-1].startswith(
        "A.desktop: clock=True has no effect, because taskbar is off (taskbar=False)."
    )


def test_blank_with_a_taskbar_shows_every_child():
    parts, notes = resolve_desktop(Desktop("blank", taskbar=True, buttons=False), OWNER)
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
        resolve_desktop(Desktop("foo"), "Scene.desktop")
    assert caught.value.args[0] == "Scene.desktop 'foo': use one of blank, stock"
