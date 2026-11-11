"""Notepad as an action class, and in state files, against a stand-in guest: no VM."""

import hashlib
import json

import pytest
from art98 import guestfiles
from art98.actions.programs.notepad import notepad_title
from art98.anim import Notepad, Scene
from art98.bridge import Window
from art98.state import StateError, load_state
from test_picture import (  # noqa: F401  (fake_viewer is an autouse fixture)
    GuestWithFiles,
    fake_viewer,
    run,
)


class NotepadGuest(GuestWithFiles):
    """Also starts notepad.exe: a window titled from its argument, with an Edit child."""

    def spawn(self, command, cwd=None):
        if not command.startswith("notepad.exe"):
            return super().spawn(command, cwd)
        self.spawned.append(command)
        self.next_pid += 1
        name = command.split('"')[1].rsplit("\\", 1)[1] if '"' in command else ""
        hwnd, self.next_hwnd = self.next_hwnd, self.next_hwnd + 2
        self.rects[hwnd] = (92, 88, 692, 499)
        self.rects[hwnd + 1] = (96, 130, 688, 495)
        self.rows[0].insert(
            0,
            Window(
                hwnd,
                self.next_pid,
                True,
                self.rects[hwnd],
                "Notepad",
                notepad_title(name),
            ),
        )
        self.rows[hwnd] = [
            Window(hwnd + 1, self.next_pid, True, self.rects[hwnd + 1], "Edit", "")
        ]
        self.pids.add(self.next_pid)
        return self.next_pid


@pytest.fixture
def guest():
    return NotepadGuest()


@pytest.fixture
def folder(tmp_path):
    (tmp_path / "note.txt").write_bytes(b"one\ntwo\r\nthree")
    (tmp_path / "flower.bmp").write_bytes(__import__("test_state").bmp())
    return tmp_path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def state_file(folder, windows):
    path = folder / "state.json"
    path.write_text(json.dumps({"version": 1, "windows": windows}))
    return path


def note_window(folder, **changes):
    window = {
        "id": "note",
        "app": "notepad",
        "at": [320, 140],
        "size": [420, 260],
        "open": {"file": "note.txt", "sha256": sha(folder / "note.txt")},
    }
    window.update(changes)
    return window


def test_notepad_is_an_exported_program():
    from art98 import anim
    from art98.actions.programs import Notepad as program

    assert program is Notepad
    assert "Notepad" in anim.__all__


def test_titles_a_bare_notepad_takes_any_title():
    assert Notepad().title_text == ""
    assert Notepad(open=None).title_text == ""


def test_a_file_notepad_copies_the_file_with_crlf_and_opens_it(guest, folder):
    note = folder / "note.txt"

    class One(Scene):
        def construct(self):
            self.pad = Notepad(open=note, at=(40, 50), size=(300, 200))
            self.add(self.pad)

    scene, _ = run(guest, One)
    path = guestfiles.guest_path(b"one\r\ntwo\r\nthree", "note.txt")
    assert guest.spawned == [f'notepad.exe "{path}"']
    assert guest.files[path] == b"one\r\ntwo\r\nthree"
    assert scene.pad.title_text == "note - Notepad"
    assert scene.pad.rect == (40, 50, 340, 250)
    assert scene.pad.edit_hwnd == scene.pad.hwnd + 1


def test_a_bad_text_file_fails_before_the_guest_is_asked(folder):
    (folder / "bin.txt").write_bytes(b"a\0b")
    (folder / "big.txt").write_bytes(b"x" * 50_001)
    (folder / "wide.txt").write_bytes(b"a\x81b")  # 0x81 is undefined in cp1252
    for name, message in (
        ("bin.txt", "NUL"),
        ("big.txt", "at most"),
        ("wide.txt", "1252"),
    ):
        with pytest.raises(ValueError, match=message):
            Notepad(open=folder / name)


def test_check_text_normalises_line_ends_once():
    assert guestfiles.check_text(b"a\nb\r\nc\n") == b"a\r\nb\r\nc\r\n"
    assert guestfiles.check_text(b"caf\xe9") == b"caf\xe9"


def test_a_notepad_state_loads_with_default_titles(folder):
    state = load_state(
        state_file(
            folder,
            [
                note_window(folder),
                {"id": "blank", "app": "notepad", "at": [1, 2], "size": [3, 4]},
                note_window(folder, id="named", title="My note"),
            ],
        )
    )
    assert [w.title for w in state.windows] == [
        "note - Notepad",
        "Untitled - Notepad",
        "My note",
    ]
    assert (
        state.window("note").open.data == b"one\ntwo\r\nthree"
    )  # the hash stays the host file's


def test_the_state_errors_name_notepad_and_check_the_text(folder):
    (folder / "bin.txt").write_bytes(b"a\0b")
    bad = note_window(folder, app="paint")
    bin_ = note_window(
        folder, id="bin", open={"file": "bin.txt", "sha256": sha(folder / "bin.txt")}
    )
    with pytest.raises(StateError) as caught:
        load_state(state_file(folder, [bad, bin_]))
    text = "\n".join(caught.value.problems)
    assert "picture, notepad" in text and "NUL" in text


def test_a_picture_state_keeps_the_picture_default_title(folder):
    window = {"id": "p", "app": "picture", "at": [1, 2], "size": [3, 4]}
    assert load_state(state_file(folder, [window])).windows[0].title == "Picture"


def test_from_state_builds_a_notepad(folder):
    window = load_state(state_file(folder, [note_window(folder)])).windows[0]
    pad = Notepad.from_state(window)
    assert (pad.title_text, pad.open_file, pad._at, pad._size) == (
        "note - Notepad",
        window.open.path,
        (320, 140),
        (420, 260),
    )


def test_a_state_with_a_picture_and_a_notepad_is_applied_back_to_front(guest, folder):
    path = state_file(
        folder,
        [
            {
                "id": "pic",
                "app": "picture",
                "title": "Flower",
                "at": [10, 20],
                "size": [200, 150],
                "open": {"file": "flower.bmp", "sha256": sha(folder / "flower.bmp")},
            },
            note_window(folder),
        ],
    )
    seen = {}

    class Start(Scene):
        state = path

        def setup(self):
            seen["titles"] = [
                w.title for w in self.guest.windows() if w.class_name != "Edit"
            ]
            seen["note"] = self.prop("note")

    run(guest, Start)
    assert seen["titles"] == ["note - Notepad", "Flower"]
    assert seen["note"].rect == (320, 140, 740, 400)


@pytest.mark.parametrize(
    "name, title",
    [
        ("note.txt", "note - Notepad"),
        ("Note.TXT", "Note - Notepad"),
        ("a.b.txt", "a.b - Notepad"),
        ("x.log", "x.log - Notepad"),
        ("plain", "plain - Notepad"),
    ],
)
def test_notepad_title_drops_only_a_trailing_txt(name, title):
    assert notepad_title(name) == title


def test_a_file_name_the_guest_cannot_take_fails_before_the_guest_is_asked(folder):
    for name, message in (
        ("a*.txt", "one of"),
        ("a\tb.txt", "control"),
        ("a.txt.", "space or a dot"),
        ("a.txt ", "space or a dot"),
        ("\u4e2d.txt", "1252"),
    ):
        (folder / name).write_bytes(b"x")
        with pytest.raises(ValueError, match=message):
            Notepad(open=folder / name)
    (folder / "my caf\u00e9.txt").write_bytes(b"x")
    Notepad(open=folder / "my caf\u00e9.txt")  # accepted: inner space, cp1252 accent
    with pytest.raises(ValueError, match="control"):
        guestfiles.guest_path(b"x", "a\x01")
