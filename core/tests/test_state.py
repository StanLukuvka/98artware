"""Loading state files: every mistake is caught before the guest is touched."""

import hashlib
import json
import struct
import tempfile
from pathlib import Path

import pytest
from art98.state import StateError, dump_state, load_state
from hypothesis import given
from hypothesis import strategies as st


def bmp(width=4, height=3):
    stride = (width * 3 + 3) // 4 * 4
    pixels = bytes(stride * height)
    return (
        b"BM"
        + struct.pack("<IHHI", 54 + len(pixels), 0, 0, 54)
        + struct.pack(
            "<IiiHHIIiiII", 40, width, height, 1, 24, 0, len(pixels), 0, 0, 0, 0
        )
        + pixels
    )


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
        "id": "flower",
        "app": "picture",
        "title": "Flower",
        "at": [60, 60],
        "size": [300, 220],
        "open": {
            "file": "assets/flower.bmp",
            "sha256": hashlib.sha256(
                (folder / "assets" / "flower.bmp").read_bytes()
            ).hexdigest(),
        },
    }
    window.update(changes)
    return window


def problems(folder, value):
    with pytest.raises(StateError) as caught:
        load_state(write(folder, value))
    return caught.value.problems


def test_a_full_state_loads(folder):
    state = load_state(
        write(
            folder,
            {
                "version": 1,
                "display": [800, 600, 16],
                "windows": [
                    flower(folder),
                    {
                        "id": "empty",
                        "app": "picture",
                        "at": [300, 140],
                        "size": [420, 340],
                        "show": "maximized",
                    },
                ],
                "pointer": [400, 500],
            },
        )
    )
    assert state.display == (800, 600, 16)
    assert state.pointer == (400, 500)
    first, second = state.windows
    assert (first.id, first.title, first.at, first.size, first.show) == (
        "flower",
        "Flower",
        (60, 60),
        (300, 220),
        "normal",
    )
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


def test_old_desktop_colour_key_names_the_new_one(folder):
    found = problems(folder, {"version": 1, "desktop": {"colour": [1, 2, 3]}})
    assert found == ["desktop.colour: renamed to fill_colour"]


def test_unknown_and_later_fields_fail(folder):
    found = problems(
        folder,
        {
            "version": 1,
            "desktop": {"icons": []},
            "colour": 1,
            "windows": [flower(folder, focus=True, rect=[0, 0, 1, 1])],
        },
    )
    assert "colour: unknown field" in found
    assert any(p.startswith("desktop.icons: not supported yet") for p in found)
    assert any(p.startswith("windows[0].focus: not supported yet") for p in found)
    assert "windows[0].rect: unknown field" in found


def test_every_problem_is_reported_at_once(folder):
    found = problems(
        folder,
        {
            "version": 2,
            "display": [800, 600, 15],
            "pointer": [-1, 5],
            "windows": [
                flower(folder, app="paint", size=[0, 10], at=[1, True]),
                flower(folder, show="hidden", title='say "hi"'),
                flower(folder),
            ],
        },
    )
    assert found == [
        "version: should be 1",
        "display: colour depth should be one of (8, 16, 24, 32)",
        "windows[0].app: should be one of picture, notepad, not 'paint'",
        "windows[0].at: needs 2 whole numbers",
        "windows[0].size: needs numbers above 0",
        "windows[1].title: 'say \"hi\"' has a double quote",
        "windows[1].show: should be one of normal, minimized, maximized, not 'hidden'",
        "pointer: can't be negative",
    ]


def test_two_windows_cannot_share_an_id(folder):
    found = problems(
        folder, {"version": 1, "windows": [flower(folder), flower(folder)]}
    )
    assert found == ["windows[1].id: 'flower' is used twice"]


def test_a_missing_or_broken_image_is_caught(folder):
    found = problems(
        folder,
        {
            "version": 1,
            "windows": [
                flower(folder, open={"file": "assets/gone.bmp", "sha256": "x"})
            ],
        },
    )
    assert found[0].startswith("windows[0].open.file: ") and found[0].endswith(
        "doesn't exist"
    )
    cut = bmp()[:60]
    (folder / "assets" / "cut.bmp").write_bytes(cut)
    found = problems(
        folder,
        {
            "version": 1,
            "windows": [
                flower(
                    folder,
                    open={
                        "file": "assets/cut.bmp",
                        "sha256": hashlib.sha256(cut).hexdigest(),
                    },
                )
            ],
        },
    )
    assert len(found) == 1 and "is cut short" in found[0]


def note(folder, data=b"hello\n", **changes):
    (folder / "assets" / "note.txt").write_bytes(data)
    window = {
        "id": "note",
        "app": "notepad",
        "title": "Note",
        "at": [10, 10],
        "size": [300, 200],
        "text": {
            "file": "assets/note.txt",
            "sha256": hashlib.sha256(data).hexdigest(),
        },
    }
    window.update(changes)
    return window


def test_a_notepad_text_file_loads(folder):
    state = load_state(write(folder, {"version": 1, "windows": [note(folder)]}))
    assert state.windows[0].text.data == b"hello\n"


def test_a_picture_window_with_text_fails(folder):
    window = flower(folder, text=note(folder)["text"])
    found = problems(folder, {"version": 1, "windows": [window]})
    assert found == ["windows[0].text: picture windows can't have text"]


def test_a_text_file_check_text_rejects_fails_at_text(folder):
    window = note(folder, data=b"a\0b")
    found = problems(folder, {"version": 1, "windows": [window]})
    assert len(found) == 1 and found[0].startswith("windows[0].text: ")
    assert "NUL" in found[0]


def test_dump_state_writes_the_same_bytes_twice_and_loads(folder):
    shuffled = {
        "pointer": [5, 5],
        "windows": [dict(reversed(note(folder).items()))],
        "desktop": {"style": "tile", "wallpaper": flower(folder)["open"]},
        "version": 1,
    }
    (folder / "assets" / "flower.bmp").write_bytes(bmp())
    path = folder / "out.json"
    state = dump_state(shuffled, path)
    first = path.read_bytes()
    dump_state(shuffled, path)
    assert path.read_bytes() == first and first.endswith(b"}\n")
    assert state.windows[0].text.data == b"hello\n"
    assert list(json.loads(first)) == ["version", "desktop", "windows", "pointer"]
    assert list(json.loads(first)["windows"][0])[:3] == ["id", "app", "title"]


def test_files_that_are_not_states(folder):
    with pytest.raises(StateError, match="doesn't exist"):
        load_state(folder / "nothing.json")
    with pytest.raises(StateError, match="not valid JSON"):
        load_state(write(folder, "{version: 1"))
    assert problems(folder, [1, 2]) == ["state: should be an object"]


@pytest.mark.parametrize(
    "title, problem",
    [
        ("ends\\", "ends in a backslash"),
        ("a\tb", "control character"),
        ("\u4e2d", "outside Windows 1252"),
    ],
)
def test_a_title_that_breaks_the_command_line_is_caught(folder, title, problem):
    found = problems(folder, {"version": 1, "windows": [flower(folder, title=title)]})
    assert (
        len(found) == 1
        and found[0].startswith("windows[0].title:")
        and problem in found[0]
    )


def test_a_title_with_an_inner_backslash_and_accent_loads(folder):
    state = load_state(
        write(
            folder, {"version": 1, "windows": [flower(folder, title="a\\b caf\u00e9")]}
        )
    )
    assert state.windows[0].title == "a\\b caf\u00e9"


def named(folder, name):
    """A window whose image is the flower copied to assets/<name>."""
    data = (folder / "assets" / "flower.bmp").read_bytes()
    (folder / "assets" / name).write_bytes(data)
    return flower(
        folder,
        open={"file": f"assets/{name}", "sha256": hashlib.sha256(data).hexdigest()},
    )


@pytest.mark.parametrize(
    "name, problem",
    [
        ("a*.bmp", "one of"),
        ("a\tb.bmp", "control character"),
        ("a.bmp.", "space or a dot"),
        ("a.bmp ", "space or a dot"),
        ("\u4e2d.bmp", "outside Windows 1252"),
    ],
)
def test_a_file_name_the_guest_cannot_take_is_caught(folder, name, problem):
    found = problems(folder, {"version": 1, "windows": [named(folder, name)]})
    assert any(p.startswith("windows[0].open.file:") and problem in p for p in found), (
        found
    )


def test_a_file_name_with_a_space_and_an_accent_loads(folder):
    state = load_state(
        write(folder, {"version": 1, "windows": [named(folder, "my caf\u00e9.bmp")]})
    )
    assert state.windows[0].open.path.name == "my caf\u00e9.bmp"


def test_a_list_where_a_name_is_expected_is_a_problem_not_a_crash(folder):
    found = problems(folder, {"version": 1, "windows": [flower(folder, app=[])]})
    assert found == ["windows[0].app: should be one of picture, notepad, not []"]


def test_display_size_must_be_a_cirrus_mode(folder):
    [found] = problems(folder, {"version": 1, "display": [123, 456, 16]})
    assert found == (
        "display: size should be one of 640x480, 800x600, 1024x768, 1280x1024"
    )
    for size in ([640, 480], [800, 600], [1024, 768], [1280, 1024]):
        assert load_state(write(folder, {"version": 1, "display": [*size, 16]}))


def test_pointer_is_checked_against_the_display_when_given(folder):
    state = {"version": 1, "pointer": [99999, 99999]}
    assert load_state(write(folder, state)).pointer == (99999, 99999)  # screen unknown
    [found] = problems(folder, {**state, "display": [800, 600, 16]})
    assert found == "pointer: should be on the 800x600 screen"
    ok = {**state, "pointer": [799, 599], "display": [800, 600, 16]}
    assert load_state(write(folder, ok)).pointer == (799, 599)


def test_a_capital_sha256_is_the_same_hash(folder):
    window = flower(folder)
    window["open"]["sha256"] = window["open"]["sha256"].upper()
    assert load_state(write(folder, {"version": 1, "windows": [window]}))


def test_a_default_title_comes_from_the_app(folder):
    window = flower(folder)
    del window["title"]
    state = load_state(write(folder, {"version": 1, "windows": [window]}))
    assert state.windows[0].title == "Picture"


def test_a_folder_given_as_the_state_file_is_a_problem(folder):
    with pytest.raises(StateError, match="can't read the file: Is a directory"):
        load_state(folder)


def test_a_file_that_cannot_be_read_is_a_problem(folder):
    picture = folder / "assets" / "flower.bmp"
    window = flower(folder)
    picture.chmod(0)
    try:
        picture.read_bytes()
    except PermissionError:
        pass
    else:
        pytest.skip("running as a user that ignores file permissions")
    [found] = problems(folder, {"version": 1, "windows": [window]})
    assert found.startswith("windows[0].open.file: can't read ")
    assert found.endswith("Permission denied")


def test_a_state_file_is_read_as_utf8(folder):
    path = folder / "u.json"
    path.write_bytes(
        json.dumps({"version": 1, "windows": [flower(folder, title="Café")]}).encode(
            "utf-8"
        )
    )
    assert load_state(path).windows[0].title == "Café"


def test_a_window_id_must_be_letters_digits_underscore_or_dash(folder):
    from art98.state import id_problem

    assert id_problem("note_1-b") is None
    for bad in ("", None, 3, "../x", "a/b", "a b", "é"):
        assert id_problem(bad)
    path = folder / "s.json"
    path.write_text(
        json.dumps({"version": 1, "windows": [{"id": "../x", "app": "notepad"}]})
    )
    with pytest.raises(StateError) as caught:
        load_state(path)
    assert any(p.startswith("windows[0].id:") for p in caught.value.problems)


def test_a_loaded_state_carries_the_sha256_of_its_bytes(folder):
    path = write(folder, {"version": 1, "windows": [flower(folder)]})
    state = load_state(path)
    assert state.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


def test_a_state_lists_its_files_wallpaper_then_windows_open_before_text(folder):
    (folder / "assets" / "wall.bmp").write_bytes(bmp(8, 8))
    (folder / "assets" / "note.txt").write_bytes(b"hello")
    (folder / "assets" / "other.txt").write_bytes(b"other")

    def ref(name):
        data = (folder / "assets" / name).read_bytes()
        return {"file": f"assets/{name}", "sha256": hashlib.sha256(data).hexdigest()}

    note = {
        "id": "note",
        "app": "notepad",
        "at": [100, 80],
        "size": [320, 200],
        "open": ref("note.txt"),
        "text": ref("other.txt"),
    }
    bare = {"id": "bare", "app": "picture", "at": [0, 0], "size": [50, 50]}
    state = load_state(
        write(
            folder,
            {
                "version": 1,
                "desktop": {"wallpaper": ref("wall.bmp")},
                "windows": [note, bare, flower(folder)],
            },
        )
    )
    names = [r.path.name for r in state.files()]
    assert names == ["wall.bmp", "note.txt", "other.txt", "flower.bmp"]
    assert load_state(write(folder, {"version": 1}, "empty.json")).files() == ()


def test_dump_state_returns_a_state_with_its_sha256(folder):
    path = folder / "dumped.json"
    state = dump_state({"version": 1, "windows": [flower(folder)]}, path)
    assert state.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_state_file_format_and_version_are_unchanged(folder):
    from art98.state import VERSION

    path = folder / "dumped.json"
    dump_state({"version": 1, "windows": [flower(folder)]}, path)
    written = json.loads(path.read_text())
    assert VERSION == 1
    assert set(written) == {"version", "windows"}
    assert "sha256" not in written
    assert set(written["windows"][0]["open"]) == {"file", "sha256"}


@given(
    wallpaper=st.booleans(),
    windows=st.lists(
        st.one_of(
            st.tuples(st.just("picture"), st.booleans(), st.just(False)),
            st.tuples(st.just("notepad"), st.booleans(), st.booleans()),
        ),
        max_size=5,
    ),
)
def test_files_lists_every_file_once_in_file_order(wallpaper, windows):
    """**Validates: Requirements 1.2, 1.3, 5.2**"""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        count = 0

        def ref(ext, data):
            nonlocal count
            count += 1
            name = f"f{count}.{ext}"
            (base / name).write_bytes(data)
            return {"file": name, "sha256": hashlib.sha256(data).hexdigest()}, name

        expected = []
        value = {"version": 1, "windows": []}
        if wallpaper:
            wall, name = ref("bmp", bmp(8, 8))
            value["desktop"] = {"wallpaper": wall}
            expected.append(name)
        for index, (app, opens, texts) in enumerate(windows):
            window = {"id": f"w{index}", "app": app, "at": [0, 0], "size": [50, 50]}
            if opens:
                window["open"], name = (
                    ref("bmp", bmp()) if app == "picture" else ref("txt", b"open")
                )
                expected.append(name)
            if texts:
                window["text"], name = ref("txt", b"text")
                expected.append(name)
            value["windows"].append(window)
        state = load_state(write(base, value))
        assert [r.path.name for r in state.files()] == expected
