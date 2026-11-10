"""The prepared image itself, booted on each backend.

These need a finished work folder: ART98_TEST_WORK, else work/ in the checkout.
The local backend needs QEMU on PATH, the container backend the art98 image
(`art98 up` builds it). Each test runs on a throwaway copy of the disk.
"""

import os
import shutil
from pathlib import Path

import pytest

from art98.qemu import QEMU_BINARY
from art98.session import stage
from art98.container import host as container

HERE = Path(__file__).resolve().parents[2]
WORK = Path(os.environ.get("ART98_TEST_WORK") or HERE / "work")
MVP = HERE / "artware_experiments" / "set_state" / "mvp.py"


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
