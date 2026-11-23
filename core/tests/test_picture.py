"""Picture windows, Teleport and states against a stand-in guest: no VM."""

import hashlib
import json
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest
from art98.anim import UL, Close, Picture, Scene, Teleport
from art98.anim.setstate import StateMismatch
from art98.errors import MissingFile
from art98.guest import guestfiles
from art98.guest.bridge import CallResult, Window
from art98.state import StateError, load_state
from test_anim import FakeGuest, FakeVideo, FakeVM
from test_state import bmp

INVALID = 0xFFFFFFFF


class GuestWithFiles(FakeGuest):
    """Adds files, VIEW.EXE windows, show states and reverts to the fake guest."""

    def __init__(self):
        super().__init__()
        self.kernel32 = self.user32
        self.files = {}
        self.puts = []
        self.shown = {}
        self.display = (800, 600, 16)
        self.next_hwnd = 0x100
        self.pids = set()

    def do_GetFileAttributesA(self, path):
        return CallResult(0x20 if path in self.files else INVALID, 0, [])

    def put_file(self, path, data):
        self.puts.append(path)
        self.files[path] = data

    def spawn(self, command, cwd=None):
        self.spawned.append(command)
        self.next_pid += 1
        if "VIEW.EXE" in command:
            x, y, width, height = map(int, command.split()[1:5])
            title = command.split('"')[1]
            # The newest window is at the front, as EnumWindows lists them.
            self.rects[self.next_hwnd] = (x, y, x + width, y + height)
            self.rows[0].insert(
                0,
                Window(
                    self.next_hwnd,
                    self.next_pid,
                    True,
                    self.rects[self.next_hwnd],
                    "Art98View",
                    title,
                ),
            )
            self.next_hwnd += 1
        self.pids.add(self.next_pid)
        return self.next_pid

    def windows(self, parent=0):
        # Rows follow the real rects, as the agent's WINDOWS does.
        return [
            Window(
                w.hwnd,
                w.pid,
                w.visible,
                self.rects.get(w.hwnd, w.rect),
                w.class_name,
                w.title,
            )
            for w in self.rows.get(parent, [])
        ]

    def processes(self):
        return [(pid, "VIEW.EXE") for pid in self.pids]

    def revert(self):
        self.rows = {0: []}
        self.rects, self.shown, self.files = {}, {}, {}
        self.cursor = (400, 300)

    def do_PostMessageA(self, hwnd, message, wparam, lparam):
        if message == 0x10:  # WM_CLOSE
            self.rows[0] = [w for w in self.rows[0] if w.hwnd != hwnd]
        return CallResult(1, 0, [])

    def do_ShowWindow(self, hwnd, command):
        self.shown[hwnd] = {7: "minimized", 3: "maximized"}[command]
        return CallResult(1, 0, [])

    def do_IsIconic(self, hwnd):
        return CallResult(self.shown.get(hwnd) == "minimized", 0, [])

    def do_IsZoomed(self, hwnd):
        return CallResult(self.shown.get(hwnd) == "maximized", 0, [])

    def do_GetSystemMetrics(self, index):
        return CallResult({0: self.display[0], 1: self.display[1]}.get(index, 0), 0, [])

    def do_GetDeviceCaps(self, dc, index):
        return CallResult(self.display[2], 0, [])


class Session:
    def __init__(self, guest):
        self.bridge, self.vm = guest, FakeVM()
        self.reverts = 0
        self.fresh = True  # as after `attach`

    def revert(self):
        self.reverts += 1
        self.fresh = True
        self.bridge.revert()


@pytest.fixture(autouse=True)
def fake_viewer(monkeypatch):
    monkeypatch.setattr(guestfiles, "viewer", lambda: b"MZ view")


@pytest.fixture
def guest():
    return GuestWithFiles()


@pytest.fixture
def folder(tmp_path):
    (tmp_path / "flower.bmp").write_bytes(bmp(4, 3))
    return tmp_path


def run(guest, scene_class):
    scene = scene_class()
    session = Session(guest)
    scene.run(session, FakeVideo(guest))
    return scene, session


def state_file(folder, name="state.json", **values):
    data = (folder / "flower.bmp").read_bytes()
    value = {
        "version": 1,
        "windows": [
            {
                "id": "back",
                "app": "picture",
                "title": "Back",
                "at": [10, 20],
                "size": [200, 150],
            },
            {
                "id": "flower",
                "app": "picture",
                "title": "Flower",
                "at": [60, 60],
                "size": [300, 220],
                "open": {
                    "file": "flower.bmp",
                    "sha256": hashlib.sha256(data).hexdigest(),
                },
            },
        ],
        "pointer": [500, 400],
    }
    value.update(values)
    value = {k: v for k, v in value.items() if v is not None}
    path = folder / name
    path.write_text(json.dumps(value))
    return path


# ---- Picture and Teleport ----


def test_a_picture_opens_where_it_should_with_its_image_copied_once(guest, folder):
    image = folder / "flower.bmp"

    class Two(Scene):
        def construct(self):
            self.first = Picture("Flower", image=image, at=(40, 50), size=(300, 200))
            self.second = Picture("Again", image=image)
            self.add(self.first, self.second)

    scene, _ = run(guest, Two)
    viewer = guestfiles.guest_path(b"MZ view", "VIEW.EXE")
    picture = guestfiles.guest_path(image.read_bytes(), "flower.bmp")
    assert guest.spawned == [
        f'{viewer} 40 50 300 200 "Flower" "{picture}"',
        f'{viewer} 100 100 320 240 "Again" "{picture}"',
    ]
    assert guest.puts == [viewer, picture]
    assert scene.first.image_size == (4, 3)
    assert scene.first.rect == (40, 50, 340, 250)


def test_a_picture_remembers_the_file_and_bytes_it_was_built_from(guest, folder):
    image = folder / "flower.bmp"
    picture = Picture(image=image)
    assert picture.source == (image.resolve(), image.read_bytes())
    assert picture.source[1] is picture._image_data


def test_a_picture_given_checked_bytes_does_not_read_the_file(guest, folder):
    image = folder / "flower.bmp"
    data = bmp(4, 3)
    image.unlink()
    picture = Picture(image=image, _data=data)
    assert picture.source == (image.resolve(), data)
    assert picture.source[1] is data
    assert picture.image_size == (4, 3)


def test_a_bad_picture_fails_before_the_guest_is_asked(folder):
    (folder / "cut.bmp").write_bytes(bmp()[:60])
    with pytest.raises(ValueError, match="cut short"):
        Picture(image=folder / "cut.bmp")
    for title, match in (
        ('a "quoted" title', "double quote"),
        ("ends\\", "backslash"),
        ("a\nb", "control"),
        ("\u4e2d", "1252"),
    ):
        with pytest.raises(ValueError, match=match):
            Picture(title)
    Picture("a\\b caf\u00e9")  # accepted: inner backslash, cp1252 accent


def test_a_bad_image_file_name_fails_before_the_guest_is_asked(folder):
    (folder / "x.bmp.").write_bytes(bmp())
    with pytest.raises(ValueError, match="space or a dot"):
        Picture(image=folder / "x.bmp.")
    (folder / "my caf\u00e9.bmp").write_bytes(bmp())
    Picture(image=folder / "my caf\u00e9.bmp")


def test_teleport_moves_and_resizes_in_one_frame(guest):
    class Jump(Scene):
        def construct(self):
            self.pic = Picture(at=(100, 100), size=(320, 240))
            self.add(self.pic)
            self.play(Teleport(self.pic, (40, 40), aligned_edge=UL, size=(200, 100)))

    scene, _ = run(guest, Jump)
    assert guest.rects[scene.pic.hwnd] == (40, 40, 240, 140)
    assert len(scene.recorder.frames) == 1
    with pytest.raises(ValueError, match="somewhere to go"):
        Teleport(scene.pic)


def test_closing_and_opening_a_picture(guest):
    class Blink(Scene):
        def construct(self):
            self.pic = Picture("Blink")
            self.add(self.pic)
            self.play(Close(self.pic))

    scene, _ = run(guest, Blink)
    assert [w for w in guest.windows() if w.class_name == "Art98View"] == []
    assert scene.props == []


# ---- states ----


def test_a_scene_state_is_applied_and_checked_before_setup(guest, folder):
    path = state_file(folder)
    seen = {}

    class Start(Scene):
        state = path

        def setup(self):
            seen["windows"] = [w.title for w in self.guest.windows()]
            seen["flower"] = self.prop("flower")

    scene, session = run(guest, Start)
    assert session.reverts == 0  # attach already reverted
    # Back to front in the state, so front to back on the guest.
    assert seen["windows"] == ["Flower", "Back"]
    assert seen["flower"].rect == (60, 60, 360, 280)
    assert guest.cursor == (500, 400)
    repaints = [args[0] for name, args in guest.calls if name == "RedrawWindow"]
    assert repaints[-2:] == [scene.prop("back").hwnd, scene.prop("flower").hwnd]
    with pytest.raises(KeyError, match="has back, flower"):
        scene.prop("nope")


def test_set_state_jumps_and_old_props_are_forgotten(guest, folder):
    first = state_file(folder, "first.json")
    second = state_file(
        folder,
        "second.json",
        windows=[
            {
                "id": "only",
                "app": "picture",
                "title": "Only",
                "at": [0, 0],
                "size": [100, 100],
                "show": "maximized",
            }
        ],
        pointer=None,
    )

    class Jump(Scene):
        def construct(self):
            self.set_state(first)
            self.old = self.prop("flower")
            self.set_state(second)

    scene, session = run(guest, Jump)
    assert session.reverts == 2
    assert [w.title for w in guest.windows()] == ["Only"]
    assert guest.shown == {scene.prop("only").hwnd: "maximized"}
    assert scene.props == [scene.prop("only")]
    assert scene.old.hwnd is None and scene.old.scene is None
    with pytest.raises(KeyError):
        scene.prop("flower")


def test_a_relative_state_is_found_beside_the_scene_file(guest, folder, monkeypatch):
    here = Path(__file__).parent
    monkeypatch.chdir(folder)
    state_file(folder)

    class Relative(Scene):
        state = "state.json"  # not beside this test file, so the cwd is used

    scene, _ = run(guest, Relative)
    assert not (here / "state.json").exists()
    assert scene.prop("back").title_text == "Back"


def test_a_bad_state_fails_before_the_desktop_is_reverted(guest, folder):
    path = state_file(folder, display=[800, 600, 15])

    class Bad(Scene):
        state = path

    with pytest.raises(StateError, match="colour depth") as caught:
        run(guest, Bad)
    assert not isinstance(caught.value, StateMismatch)
    assert guest.spawned == []


MODES = [(16, 640, 480), (16, 800, 600), (16, 1024, 768)]  # DEVMODE order: depth first


class GuestWithModes(GuestWithFiles):
    """Adds the driver's display modes and a work area that follows the screen."""

    def __init__(self):
        super().__init__()
        self.mode_changes = []

    def revert(self):
        super().revert()
        self.display = (800, 600, 16)

    def do_EnumDisplaySettingsA(self, device, index, blank):
        if index >= len(MODES):
            return CallResult(0, 0, [])
        blob = bytearray(blank)
        struct.pack_into("<III", blob, 104, *MODES[index])
        return CallResult(1, 0, [bytes(blob)])

    def do_ChangeDisplaySettingsA(self, devmode, flags):
        depth, width, height = struct.unpack_from("<III", devmode, 104)
        self.mode_changes.append(((width, height, depth), flags))
        self.display = (width, height, depth)
        return CallResult(0, 0, [])

    def do_SystemParametersInfoA(self, action, value, out, flags):
        width, height = self.display[:2]
        return CallResult(1, 0, [struct.pack("<iiii", 0, 0, width, height - 28)])


@pytest.mark.parametrize("mode", [(640, 480, 16), (1024, 768, 16)])
def test_a_state_display_mode_is_persisted_so_the_taskbar_moves(folder, mode):
    # Explorer moves the taskbar only for a mode written to the registry
    # (CDS_UPDATEREGISTRY, flags 1); the next revert undoes the write.
    guest = GuestWithModes()
    path = state_file(folder, display=list(mode), pointer=[300, 200])

    class Hold(Scene):
        state = path

    scene, _ = run(guest, Hold)
    assert guest.mode_changes == [(mode, 1)]
    width, height = mode[:2]
    assert scene.work_area == (0, 0, width, height - 28)


def test_a_state_in_the_current_mode_leaves_the_display_alone(folder):
    guest = GuestWithModes()
    path = state_file(folder, display=[800, 600, 16])

    class Hold(Scene):
        state = path

    run(guest, Hold)
    assert guest.mode_changes == []


def test_a_guest_that_does_not_match_says_how(guest, folder):
    from art98.anim.setstate import check_state
    from art98.state import load_state

    path = state_file(folder, display=[800, 600, 16])

    class Hold(Scene):
        state = path

    scene, _ = run(guest, Hold)
    back = scene.prop("back")
    guest.rects[back.hwnd] = (11, 20, 211, 160)
    row = guest.rows[0][1]
    guest.rows[0][1] = Window(
        row.hwnd, row.pid, True, row.rect, row.class_name, "Moved"
    )
    guest.shown[scene.prop("flower").hwnd] = "minimized"
    guest.cursor = (1, 2)
    guest.display = (640, 480, 16)
    with pytest.raises(StateMismatch) as caught:
        check_state(
            scene.guest,
            scene.space,
            load_state(path),
            {"back": back, "flower": scene.prop("flower")},
        )
    assert caught.value.problems == [
        "display: [800, 600, 16] wanted, the guest has [640, 480, 16]",
        "windows[0] 'back': title 'Back' wanted, the guest has 'Moved'",
        "windows[0] 'back': at [10, 20] wanted, the guest has [11, 20]",
        "windows[0] 'back': size [200, 150] wanted, the guest has [200, 140]",
        "windows[1] 'flower': normal wanted, the window is minimized",
        "pointer: [500, 400] wanted, the guest has [1, 2]",
    ]
    assert str(path) in str(caught.value)


def test_check_reports_order_and_a_missing_window(guest, folder):
    from art98.anim.setstate import check_state
    from art98.state import load_state

    path = state_file(folder)

    class Hold(Scene):
        state = path

    scene, _ = run(guest, Hold)
    state = load_state(path)
    props = {"back": scene.prop("back"), "flower": scene.prop("flower")}
    guest.rows[0].reverse()
    with pytest.raises(StateMismatch) as caught:
        check_state(scene.guest, scene.space, state, props)
    assert caught.value.problems == [
        "windows: front to back should be ['flower', 'back'], the guest has ['back', 'flower']"
    ]
    guest.rows[0] = guest.rows[0][1:]
    with pytest.raises(StateMismatch) as caught:
        check_state(scene.guest, scene.space, state, props)
    assert caught.value.problems == ["windows[0] 'back': the window isn't there"]


def test_stacking_expects_the_state_stack_when_one_is_given(guest, folder):
    from art98.anim.setstate import stacking_problems
    from art98.state import load_state

    path = state_file(folder, stack=["flower", "back"])
    state = load_state(path)
    guest.add_window(1, "Art98View", (0, 0, 10, 10), "Back")
    guest.add_window(2, "Art98View", (0, 0, 10, 10), "Flower")
    back, flower = guest.rows[0]
    props = {"back": back, "flower": flower}
    found = lambda: {w.hwnd: w for w in guest.windows()}
    # stack is flower, back (back to front), so the guest should be back, flower.
    assert stacking_problems(state, props, found()) == []
    guest.rows[0].reverse()  # the list order is now the wrong z-order
    assert stacking_problems(state, props, found()) == [
        (
            "windows: front to back should be ['back', 'flower'], "
            "the guest has ['flower', 'back']"
        )
    ]


def test_stacking_without_a_stack_uses_the_list_order(guest, folder):
    from art98.anim.setstate import stacking_problems
    from art98.state import load_state

    state = load_state(state_file(folder))
    guest.add_window(2, "Art98View", (0, 0, 10, 10), "Flower")
    guest.add_window(1, "Art98View", (0, 0, 10, 10), "Back")
    flower, back = guest.rows[0]
    props = {"back": back, "flower": flower}
    found = lambda: {w.hwnd: w for w in guest.windows()}
    assert state.stack is None
    assert stacking_problems(state, props, found()) == []
    guest.rows[0].reverse()
    assert stacking_problems(state, props, found()) == [
        (
            "windows: front to back should be ['flower', 'back'], "
            "the guest has ['back', 'flower']"
        )
    ]


def test_apply_state_restacks_in_z_order_and_activates_the_front(
    guest, folder, monkeypatch
):
    from art98.anim import setstate
    from art98.state import load_state

    state = load_state(state_file(folder, stack=["flower", "back"], pointer=None))
    log, hwnds = [], {"back": 1, "flower": 2}

    def prop(id):
        hwnd = hwnds[id]
        return SimpleNamespace(
            hwnd=hwnd,
            bring_to_front=lambda: log.append(("front", hwnd)),
            activate=lambda: log.append(("activate", hwnd)),
        )

    class App:
        @staticmethod
        def from_state(window):
            return prop(window.id)

    monkeypatch.setattr(setstate, "APPS", {"picture": App})
    monkeypatch.setattr(
        setstate, "repaint_window", lambda guest, hwnd: log.append(("repaint", hwnd))
    )
    guest.foreground = 3  # neither window, so the front one must be activated
    props = {}
    scene = SimpleNamespace(
        guest=guest,
        add=lambda prop, id=None: props.__setitem__(id, prop),
        pointer=None,
    )
    setstate.apply_state(scene, state)
    assert log == [
        ("front", 2),  # flower then back: stack order, back to front
        ("front", 1),
        ("activate", 1),  # "back" is last in the stack, so it is frontmost
        ("repaint", 2),  # repaint follows the same z-order
        ("repaint", 1),
    ]


def test_a_missing_image_is_a_missing_file(tmp_path):
    with pytest.raises(MissingFile):
        Picture(image=tmp_path / "flwoer.bmp")


def test_a_picture_without_an_image_has_no_image_size():
    assert Picture().image_size is None


def test_a_file_that_changes_after_the_check_is_not_read_again(guest, folder):
    window = load_state(state_file(folder)).windows[1]
    checked = window.open.data
    (folder / "flower.bmp").write_bytes(bmp(9, 9))
    picture = Picture.from_state(window)
    assert picture.source[1] == checked
    assert picture._image_data == checked
    assert picture.image_size == (4, 3)
    assert hashlib.sha256(picture.source[1]).hexdigest() == window.open.sha256
