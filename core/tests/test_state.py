"""Loading state files: every mistake is caught before the guest is touched."""

import hashlib
import json
import struct

import pytest

from art98.state import StateError, load_state


def bmp(width=4, height=3):
    stride = (width * 3 + 3) // 4 * 4
    pixels = bytes(stride * height)
    return (b"BM" + struct.pack("<IHHI", 54 + len(pixels), 0, 0, 54)
            + struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0, len(pixels), 0, 0, 0, 0)
            + pixels)


@pytest.fixture
def folder(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "flower.bmp").write_bytes(bmp())
    return tmp_path


def write(folder, value, name="state.json"):
    path = folder / name
    path.write_text(json.dumps(value) if not isinstance(value, str) else value)
    return path


def flower(folder, **changes):
    window = {
        "id": "flower", "app": "picture", "title": "Flower", "at": [60, 60], "size": [300, 220],
        "open": {"file": "assets/flower.bmp",
                 "sha256": hashlib.sha256((folder / "assets" / "flower.bmp").read_bytes()).hexdigest()},
    }
    window.update(changes)
    return window


def problems(folder, value):
    with pytest.raises(StateError) as caught:
        load_state(write(folder, value))
    return caught.value.problems


def test_a_full_state_loads(folder):
    state = load_state(write(folder, {
        "version": 1, "display": [800, 600, 16],
        "windows": [flower(folder), {"id": "empty", "app": "picture", "at": [300, 140],
                                     "size": [420, 340], "show": "maximized"}],
        "pointer": [400, 500],
    }))
    assert state.display == (800, 600, 16)
    assert state.pointer == (400, 500)
    first, second = state.windows
    assert (first.id, first.title, first.at, first.size, first.show) == (
        "flower", "Flower", (60, 60), (300, 220), "normal")
    assert first.open.path == (folder / "assets" / "flower.bmp").resolve()
    assert first.open.data == bmp()
    assert (second.title, second.open, second.show) == ("Picture", None, "maximized")
    assert state.window("empty") is second


def test_only_the_version_is_needed(folder):
    state = load_state(write(folder, {"version": 1}))
    assert (state.display, state.windows, state.pointer) == (None, (), None)


def test_a_wrong_hash_says_what_it_should_be(folder):
    window = flower(folder)
    actual = window["open"]["sha256"]
    window["open"]["sha256"] = "0" * 64
    [problem] = problems(folder, {"version": 1, "windows": [window]})
    assert problem.startswith("windows[0].open.sha256: should be " + actual)


def test_unknown_and_later_fields_fail(folder):
    found = problems(folder, {"version": 1, "desktop": {"icons": []}, "colour": 1,
                              "windows": [flower(folder, focus=True, rect=[0, 0, 1, 1])]})
    assert "colour: unknown field" in found
    assert any(p.startswith("desktop.icons: not supported yet") for p in found)
    assert any(p.startswith("windows[0].focus: not supported yet") for p in found)
    assert "windows[0].rect: unknown field" in found


def test_every_problem_is_reported_at_once(folder):
    found = problems(folder, {"version": 2, "display": [800, 600, 15], "pointer": [-1, 5],
                              "windows": [
                                  flower(folder, app="paint", size=[0, 10], at=[1, True]),
                                  flower(folder, show="hidden", title='say "hi"'),
                                  flower(folder),
                              ]})
    assert found == [
        "version: should be 1",
        "display: colour depth should be one of (8, 16, 24, 32)",
        "windows[0].app: should be one of picture, notepad, not 'paint'",
        "windows[0].at: needs 2 whole numbers",
        "windows[0].size: needs numbers above 0",
        "windows[1].title: 'say \"hi\"' has a double quote",
        "windows[1].show: should be one of normal, minimized, maximized, not 'hidden'",
        "pointer: should be on the screen",
    ]


def test_two_windows_cannot_share_an_id(folder):
    found = problems(folder, {"version": 1, "windows": [flower(folder), flower(folder)]})
    assert found == ["windows[1].id: 'flower' is used twice"]


def test_a_missing_or_broken_image_is_caught(folder):
    found = problems(folder, {"version": 1, "windows": [
        flower(folder, open={"file": "assets/gone.bmp", "sha256": "x"})]})
    assert found[0].startswith("windows[0].open.file: ") and found[0].endswith("doesn't exist")
    cut = bmp()[:60]
    (folder / "assets" / "cut.bmp").write_bytes(cut)
    found = problems(folder, {"version": 1, "windows": [
        flower(folder, open={"file": "assets/cut.bmp", "sha256": hashlib.sha256(cut).hexdigest()})]})
    assert len(found) == 1 and "is cut short" in found[0]


def test_files_that_are_not_states(folder):
    with pytest.raises(StateError, match="doesn't exist"):
        load_state(folder / "nothing.json")
    with pytest.raises(StateError, match="not valid JSON"):
        load_state(write(folder, "{version: 1"))
    assert problems(folder, [1, 2]) == ["state: should be an object"]


@pytest.mark.parametrize("title, problem", [
    ("ends\\", "ends in a backslash"),
    ("a\tb", "control character"),
    ("\u4e2d", "outside Windows 1252"),
])
def test_a_title_that_breaks_the_command_line_is_caught(folder, title, problem):
    found = problems(folder, {"version": 1, "windows": [flower(folder, title=title)]})
    assert len(found) == 1 and found[0].startswith("windows[0].title:") and problem in found[0]


def test_a_title_with_an_inner_backslash_and_accent_loads(folder):
    state = load_state(write(folder, {"version": 1, "windows": [flower(folder, title="a\\b caf\u00e9")]}))
    assert state.windows[0].title == "a\\b caf\u00e9"


def named(folder, name):
    """A window whose image is the flower copied to assets/<name>."""
    data = (folder / "assets" / "flower.bmp").read_bytes()
    (folder / "assets" / name).write_bytes(data)
    return flower(folder, open={"file": f"assets/{name}", "sha256": hashlib.sha256(data).hexdigest()})


@pytest.mark.parametrize("name, problem", [
    ("a*.bmp", "one of"), ("a\tb.bmp", "control character"), ("a.bmp.", "space or a dot"),
    ("a.bmp ", "space or a dot"), ("\u4e2d.bmp", "outside Windows 1252"),
])
def test_a_file_name_the_guest_cannot_take_is_caught(folder, name, problem):
    found = problems(folder, {"version": 1, "windows": [named(folder, name)]})
    assert any(p.startswith("windows[0].open.file:") and problem in p for p in found), found


def test_a_file_name_with_a_space_and_an_accent_loads(folder):
    state = load_state(write(folder, {"version": 1, "windows": [named(folder, "my caf\u00e9.bmp")]}))
    assert state.windows[0].open.path.name == "my caf\u00e9.bmp"
