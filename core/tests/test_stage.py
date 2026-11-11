"""The prepared image itself, booted on each backend.

These need a finished work folder: ART98_TEST_WORK, else work/ in the checkout.
The local backend needs QEMU on PATH, the container backend the art98 image
(`art98 up` builds it). Each test runs on a throwaway copy of the disk.
"""

import os
import shutil
import time
from pathlib import Path

import pytest

from art98.qemu import QEMU_BINARY
from art98.session import stage
from art98.container import host as container

HERE = Path(__file__).resolve().parents[2]
WORK = Path(os.environ.get("ART98_TEST_WORK") or HERE / "work")
MVP = HERE / "examples" / "mvp" / "mvp.py"
BLANK_START = HERE / "examples" / "blank_start" / "blank_start.py"


def _container_ready() -> bool:
    try:
        return container.Engine().has_image(container.image_name())
    except container.ContainerError:
        return False


BACKENDS = [
    pytest.param("local", marks=[
        pytest.mark.qemu,
        pytest.mark.skipif(shutil.which(QEMU_BINARY) is None, reason="needs QEMU")]),
    pytest.param("container", marks=[
        pytest.mark.container,
        pytest.mark.skipif(not _container_ready(), reason="needs the art98 container image")]),
]
pytestmark = [
    pytest.mark.stage,
    pytest.mark.skipif(not (WORK / "image.json").exists(), reason=f"no prepared image in {WORK}"),
]


@pytest.fixture(params=BACKENDS)
def booted(request):
    with stage(WORK, backend=request.param) as session:
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


@pytest.mark.parametrize("backend", BACKENDS)
def test_a_scene_renders(backend, tmp_path):
    from art98.anim import render
    from art98.cli import _load_scene

    out = render(_load_scene(MVP, "Mvp"), tmp_path / "mvp.mp4", work=WORK, backend=backend)
    assert out.stat().st_size > 10_000


@pytest.mark.qemu
@pytest.mark.skipif(shutil.which(QEMU_BINARY) is None, reason="needs QEMU")
def test_the_proof_scene_renders(tmp_path):
    from art98.anim import render
    from art98.cli import _load_scene

    out = render(_load_scene(BLANK_START, "BlankStart"), tmp_path / "blank_start.mp4", work=WORK, backend="local")
    assert out.stat().st_size > 10_000
    assert [(tmp_path / f"blank_start-0{n}.mp4").exists() for n in (1, 2, 3)] == [True] * 3


def test_disc_insert_revert_insert(tmp_path):
    from art98 import desktop

    data = bytes(range(256)) * 100

    def attrs(session):
        drive = desktop.cd_drive(session.bridge)
        return session.bridge.kernel32.GetFileAttributesA(drive + "WALL0001.BMP").value

    with stage(WORK, backend="local") as session:
        session.attach_disc({"WALL0001.BMP": data})
        path = desktop.wait_for_disc(session.bridge, "WALL0001.BMP")
        assert session.bridge.get_file(path) == data
        session.revert()
        assert attrs(session) == desktop.INVALID_FILE_ATTRIBUTES
        session.attach_disc({"WALL0001.BMP": data})
        path = desktop.wait_for_disc(session.bridge, "WALL0001.BMP")
        assert session.bridge.get_file(path) == data


def _pixel(session, tmp_path, x, y):
    data = session.vm.screenshot(tmp_path / "px.ppm", format="ppm").read_bytes()
    head, rest = data.split(b"\n255\n", 1)
    width = int(head.split()[1])
    return tuple(rest[(y * width + x) * 3:(y * width + x) * 3 + 3])


@pytest.mark.qemu
@pytest.mark.skipif(shutil.which(QEMU_BINARY) is None, reason="needs QEMU")
def test_backdrop_colour_reads_back(tmp_path):
    from art98 import desktop

    rgb = (200, 10, 30)
    with stage(WORK, backend="local") as session:
        guest = session.bridge
        desktop.blank(guest)
        desktop.set_colour(guest, rgb)
        guest.sync()
        assert guest.user32.GetSysColor(1).value & 0xFFFFFF == desktop.colourref(rgb)
        assert not guest.user32.IsWindowVisible(desktop.shell_windows(guest)[2]).value  # P0: icons stay hidden
        got = _pixel(session, tmp_path, 790, 590)
        assert all(abs(g - w) <= 8 for g, w in zip(got, rgb)), got


def _wall_bmp(width, height):
    """Left half red, right half blue, 24 bpp (stdlib only)."""
    import struct

    stride = (width * 3 + 3) // 4 * 4
    row = (b"\x00\x00\xff" * (width // 2) + b"\xff\x00\x00" * (width - width // 2)).ljust(stride, b"\0")
    pixels = row * height
    return (b"BM" + struct.pack("<IHHI", 54 + len(pixels), 0, 0, 54)
            + struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0, len(pixels), 0, 0, 0, 0) + pixels)


@pytest.mark.qemu
@pytest.mark.skipif(shutil.which(QEMU_BINARY) is None, reason="needs QEMU")
def test_state_with_wallpaper(tmp_path):
    import hashlib
    import json

    from art98.anim import Scene

    data = _wall_bmp(640, 480)
    (tmp_path / "wall.bmp").write_bytes(data)
    (tmp_path / "s.json").write_text(json.dumps({"version": 1, "desktop": {
        "colour": [0, 128, 128], "wallpaper": {"file": "wall.bmp", "sha256": hashlib.sha256(data).hexdigest()}}}))

    def near(got, want):
        return all(abs(g - w) <= 12 for g, w in zip(got, want))

    with stage(WORK, backend="local") as session:
        scene = Scene()
        scene.desktop = "stock"
        scene.session, scene.guest, scene.vm = session, session.bridge, session.vm
        for _ in range(2):  # the second Set reverts (and ejects) first, then does it all again
            scene.set_state(tmp_path / "s.json")  # check_state already compared one pixel
            assert near(_pixel(session, tmp_path, 300, 300), (255, 0, 0))
            assert near(_pixel(session, tmp_path, 500, 300), (0, 0, 255))
            assert near(_pixel(session, tmp_path, 5, 5), (0, 128, 128))


@pytest.mark.qemu
@pytest.mark.skipif(shutil.which(QEMU_BINARY) is None, reason="needs QEMU")
def test_same_title_dialogs(tmp_path):
    from art98 import win32
    from art98.anim import Dialog, Scene

    with stage(WORK, backend="local") as session:
        scene = Scene()
        scene.desktop = "stock"
        scene.session, scene.guest, scene.vm = session, session.bridge, session.vm
        boxes = [Dialog("???", "???", icon=icon, at=at, size=size) for icon, at, size in (
            ("warning", (60, 300), (300, 130)), ("computer", (200, 200), (320, 150)),
            ("info", (340, 100), (340, 170)))]
        for box in boxes:
            scene.add(box)
        assert len({box.hwnd for box in boxes}) == 3
        for box in boxes:
            left, top, right, bottom = win32.window_rect(session.bridge, box.hwnd)
            assert (left, top, right - left, bottom - top) == (*box._at, *box._size)
