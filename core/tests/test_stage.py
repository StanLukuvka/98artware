"""The prepared image itself, on the long-lived VM service.

These need a finished work folder (ART98_TEST_WORK, else work/ in the checkout)
and a running service: `art98 vm start`. Without one they skip. The service
serves one render at a time, so every test releases its session when it ends
(a `with attach()` or the `booted` fixture); a failure never holds the lock.
"""

import os
from contextlib import ExitStack, contextmanager
from pathlib import Path

import pytest
from art98 import service
from art98.settings import load

HERE = Path(__file__).resolve().parents[2]
WORK = Path(os.environ.get("ART98_TEST_WORK") or HERE / "work")
MVP = HERE / "recipes" / "scenes" / "mvp" / "mvp.py"
BLANK_START = HERE / "recipes" / "scenes" / "blank_start" / "blank_start.py"
SETTINGS = load(WORK)

pytestmark = [
    pytest.mark.stage,
    pytest.mark.skipif(
        not (WORK / "image.json").exists(), reason=f"no prepared image in {WORK}"
    ),
]


@contextmanager
def attached(**options):
    """service.attach, but a service that is not running skips the test."""
    with ExitStack() as stack:
        try:
            session = stack.enter_context(service.attach(SETTINGS, **options))
        except service.NotRunning as error:
            pytest.skip(str(error))
        yield session


@pytest.fixture
def booted():
    with attached() as session:
        yield session


def test_the_desktop_answers_shows_and_reverts(booted, tmp_path):
    bridge, vm = booted.bridge, booted.vm
    assert bridge.ping() > 0
    assert any(name.endswith("EXPLORER.EXE") for _, name in bridge.processes())
    shot = vm.screenshot(tmp_path / "shot.ppm", format="ppm").read_bytes()
    assert shot.startswith(b"P6\n800 600\n255\n") and len(shot) == 800 * 600 * 3 + 15
    vm.send_keys("ctrl", "esc")
    bridge.sync()
    booted.revert()
    assert bridge.ping() > 0


def test_frames_record_to_a_video(booted, tmp_path):
    with booted.record(tmp_path / "clip.mp4") as video:
        for _ in range(5):
            video.frame()
    assert video.count == 5 and (tmp_path / "clip.mp4").stat().st_size > 0


def test_a_scene_renders(booted, tmp_path):
    from art98.anim import render
    from art98.cli import _load_scene

    out = render(_load_scene(MVP, "Mvp"), tmp_path / "mvp.mp4", session=booted)
    assert out.stat().st_size > 10_000


def test_the_proof_scene_renders(booted, tmp_path):
    from art98.anim import render
    from art98.cli import _load_scene

    out = render(
        _load_scene(BLANK_START, "BlankStart"),
        tmp_path / "blank_start.mp4",
        session=booted,
    )
    assert out.stat().st_size > 10_000
    assert [(tmp_path / f"blank_start-0{n}.mp4").exists() for n in (1, 2, 3)] == [
        True
    ] * 3


def test_disc_insert_revert_insert(booted):
    from art98 import desktop, win32

    data = bytes(range(256)) * 100

    def attrs(session):
        drive = desktop.cd_drive(session.bridge)
        return session.bridge.kernel32.GetFileAttributesA(drive + "WALL0001.BMP").value

    session = booted
    session.attach_disc({"WALL0001.BMP": data})
    path = desktop.wait_for_disc(session.bridge, "WALL0001.BMP")
    assert session.bridge.get_file(path) == data
    session.revert()
    assert attrs(session) == win32.INVALID_FILE_ATTRIBUTES
    session.attach_disc({"WALL0001.BMP": data})
    path = desktop.wait_for_disc(session.bridge, "WALL0001.BMP")
    assert session.bridge.get_file(path) == data


def _pixel(session, tmp_path, x, y):
    data = session.vm.screenshot(tmp_path / "px.ppm", format="ppm").read_bytes()
    head, rest = data.split(b"\n255\n", 1)
    width = int(head.split()[1])
    return tuple(rest[(y * width + x) * 3 : (y * width + x) * 3 + 3])


def test_backdrop_colour_reads_back(booted, tmp_path):
    from art98 import desktop

    rgb = (200, 10, 30)
    session = booted
    guest = session.bridge
    desktop.blank(guest)
    desktop.set_colour(guest, rgb)
    guest.sync()
    assert guest.user32.GetSysColor(1).value & 0xFFFFFF == desktop.colourref(rgb)
    assert not guest.user32.IsWindowVisible(
        desktop.shell_windows(guest)[2]
    ).value  # P0: icons stay hidden
    got = _pixel(session, tmp_path, 790, 590)
    assert all(abs(g - w) <= 8 for g, w in zip(got, rgb)), got


def _wall_bmp(width, height):
    """Left half red, right half blue, 24 bpp (stdlib only)."""
    import struct

    stride = (width * 3 + 3) // 4 * 4
    row = (
        b"\x00\x00\xff" * (width // 2) + b"\xff\x00\x00" * (width - width // 2)
    ).ljust(stride, b"\0")
    pixels = row * height
    return (
        b"BM"
        + struct.pack("<IHHI", 54 + len(pixels), 0, 0, 54)
        + struct.pack(
            "<IiiHHIIiiII", 40, width, height, 1, 24, 0, len(pixels), 0, 0, 0, 0
        )
        + pixels
    )


def test_state_with_wallpaper(booted, tmp_path):
    import hashlib
    import json

    from art98.anim import Scene

    data = _wall_bmp(640, 480)
    (tmp_path / "wall.bmp").write_bytes(data)
    (tmp_path / "s.json").write_text(
        json.dumps(
            {
                "version": 1,
                "desktop": {
                    "colour": [0, 128, 128],
                    "wallpaper": {
                        "file": "wall.bmp",
                        "sha256": hashlib.sha256(data).hexdigest(),
                    },
                },
            }
        )
    )

    def near(got, want):
        return all(abs(g - w) <= 12 for g, w in zip(got, want))

    session = booted
    scene = Scene()
    scene.desktop = "stock"
    scene.session, scene.guest, scene.vm = session, session.bridge, session.vm
    for _ in range(
        2
    ):  # the second Set reverts (and ejects) first, then does it all again
        scene.set_state(tmp_path / "s.json")  # check_state already compared one pixel
        assert near(_pixel(session, tmp_path, 300, 300), (255, 0, 0))
        assert near(_pixel(session, tmp_path, 500, 300), (0, 0, 255))
        assert near(_pixel(session, tmp_path, 5, 5), (0, 128, 128))


def test_same_title_dialogs(booted):
    from art98 import win32
    from art98.anim import Dialog, Scene

    session = booted
    scene = Scene()
    scene.desktop = "stock"
    scene.session, scene.guest, scene.vm = session, session.bridge, session.vm
    boxes = [
        Dialog("???", "???", icon=icon, at=at, size=size)
        for icon, at, size in (
            ("warning", (60, 300), (300, 130)),
            ("computer", (200, 200), (320, 150)),
            ("info", (340, 100), (340, 170)),
        )
    ]
    for box in boxes:
        scene.add(box)
    assert len({box.hwnd for box in boxes}) == 3
    for box in boxes:
        left, top, right, bottom = win32.window_rect(session.bridge, box.hwnd)
        assert (left, top, right - left, bottom - top) == (*box._at, *box._size)


def test_attach_twice_is_busy(booted):
    # `booted` holds the one owner slot; a second attach must be refused at once.
    with pytest.raises(service.Busy), service.attach(SETTINGS):
        pass
    assert booted.bridge.ping() > 0  # the refused attach left the holder alone


def test_revert_between_attaches():
    from art98 import desktop, win32

    def disc_attrs(guest):
        drive = desktop.cd_drive(guest)
        if drive is None:
            return win32.INVALID_FILE_ATTRIBUTES
        return guest.kernel32.GetFileAttributesA(drive + "WALL0001.BMP").value

    with attached() as first:
        guest = first.bridge
        guest.spawn("notepad.exe")
        guest.find_window(class_name="Notepad")
        first.attach_disc({"WALL0001.BMP": b"x" * 512})
        desktop.wait_for_disc(guest, "WALL0001.BMP")
        assert any(w.class_name == "Notepad" for w in guest.windows())
    with attached() as second:  # revert=True is the default: back to the snapshot
        assert not any(w.class_name == "Notepad" for w in second.bridge.windows())
        assert disc_attrs(second.bridge) == win32.INVALID_FILE_ATTRIBUTES


def test_render_leaves_the_vm_running_and_paused(tmp_path):
    from art98.anim import render
    from art98.cli import _load_scene

    with attached() as session:
        # attached to the VM: running and held, so not paused, and busy
        held = service.status(SETTINGS)
        assert held["running"] and held["busy"] and not held["paused"]
        render(_load_scene(MVP, "Mvp"), tmp_path / "mvp.mp4", session=session)
    after = service.status(SETTINGS)
    assert after["running"] and after["paused"] and not after["busy"]


# ---- drift: does the host's model of the screen match the guest? (experiments/drift/README.md, dev branch) ----


def _drift_short_scenes():
    from art98.anim import DOWN, LEFT, Click, Minesweeper, Paint, Picture, Scene, Stroke

    class PaintShort(Scene):
        desktop = "stock"

        def construct(self):
            paint = Paint(at=(150, 40), size=(520, 480))
            self.add(paint)
            self.play(paint.animate.shift(60 * LEFT + 30 * DOWN), run_time=0.4)
            self.play(Click(paint.tool("brush"), run_time=0.3))
            self.play(Stroke(lambda t: paint.canvas(40 + 120 * t, 40 + 60 * t).point()))

    class MinesweeperShort(Scene):
        desktop = "stock"

        def construct(self):
            board = Minesweeper(at=(300, 120))
            self.add(board)
            self.play(board.animate.shift(80 * DOWN), run_time=0.4)
            self.play(Click(board.client(60, 90), run_time=0.3))

    class PictureShort(Scene):
        desktop = "stock"

        def construct(self):
            pic = Picture(
                "Sky",
                image=HERE / "recipes" / "scenes" / "mvp" / "assets" / "sky.bmp",
                at=(100, 100),
                size=(240, 200),
            )
            self.add(pic)
            self.play(pic.animate.shift(200 * DOWN), run_time=0.4)
            self.play(pic.animate.resize(300, 220), run_time=0.4)

    return PaintShort, MinesweeperShort, PictureShort


# name -> (file, class or scene factory index, check B too?)
DRIFT_SCENES = {
    "motion": ("recipes/scenes/gallery/window_motion.py", "WindowMotion", False),
    "drag": ("recipes/scenes/gallery/drag_window.py", "DragWindow", False),
    "typing": (
        "recipes/scenes/gallery/typing.py",
        "Typing",
        True,
    ),  # Notepad, with a caret
    "menus": ("recipes/scenes/gallery/menus_keys.py", "MenusKeys", False),
    "storm": (
        "recipes/scenes/dialog_storm/dialog_storm.py",
        "DialogStorm",
        True,
    ),  # Dialog
    "cmds": (None, "Commands", False),
    "paint": (None, "PaintShort", True),
    "minesweeper": (None, "MinesweeperShort", True),
    "picture": (None, "PictureShort", True),
}


@pytest.mark.parametrize("name", list(DRIFT_SCENES))
def test_no_drift(booted, tmp_path, name):
    from art98.cli import _load_scene
    from drift_check import Commands, audit

    file, cls, pixels = DRIFT_SCENES[name]
    if file:
        scene = _load_scene(HERE / file, cls)
        scene = scene() if isinstance(scene, type) else scene
    elif cls == "Commands":
        scene = Commands()
    else:
        scene = {c.__name__: c for c in _drift_short_scenes()}[cls]()
    if name != "storm":  # the storm keeps its own 24 fps
        scene.fps = 10
    rec = audit(
        booted, scene, name, pixels=pixels, keep=tmp_path, taskbar=name != "storm"
    )
    assert rec.index > 5, f"{name}: only {rec.index} frames were audited"
    assert not rec.failures, "\n".join(rec.failures[:10])
