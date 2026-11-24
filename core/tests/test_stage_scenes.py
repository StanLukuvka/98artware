"""Scenes rendered one after another in one attach each start from the baseline.

Needs the same prepared image and running service as test_stage.py, and skips
the same way.
"""

import subprocess

from art98.anim import Click, Desktop, Minesweeper, Paint, Scene, render
from art98.cli import _load_scene
from test_stage import (  # noqa: F401  (also brings the skip marks)
    HERE,
    attached,
    pytestmark,
)

STATE = HERE / "recipes" / "scenes" / "blank_start" / "states" / "desk.json"
APPS = {"MSPaintApp", "Minesweeper", "Notepad"}


def apps_open(guest):
    return sorted(
        w.class_name for w in guest.windows() if w.visible and w.class_name in APPS
    )


def test_each_scene_in_one_attach_starts_clean(tmp_path):
    seen = {}

    class DrawsInPaint(Scene):
        def construct(self):
            seen["paint"] = apps_open(self.guest)
            paint = Paint(at=(100, 40), size=(520, 480))
            self.add(paint)
            self.play(Click(paint.color("red")))
            self.play(Click(paint.tool("fill")))
            self.play(Click(paint.canvas(20, 20)))
            seen["paint_open"] = apps_open(self.guest)
            self.pause(0.2)

    class Sweeps(Scene):
        def construct(self):
            seen["sweep"] = apps_open(self.guest)
            board = Minesweeper(at=(300, 120))
            self.add(board)
            assert board.hwnd
            seen["sweep_open"] = apps_open(self.guest)
            self.pause(0.2)

    class FromState(Scene):
        desktop = Desktop("stock")
        state = STATE

        def construct(self):
            seen["state_props"] = sorted(p.state_id for p in self.props)
            seen["state"] = apps_open(self.guest)
            seen["props"] = len(self.props)
            self.pause(0.2)

    with attached() as session:
        for scene in (DrawsInPaint, Sweeps, FromState):
            render(scene, tmp_path / f"{scene.__name__}.mp4", session=session)
    assert seen["paint"] == [] and seen["paint_open"] == ["MSPaintApp"]
    assert seen["sweep"] == [] and seen["sweep_open"] == ["Minesweeper"]
    assert seen["state_props"] == ["flower", "note"] and seen["props"] == 2
    assert seen["state"] == ["Notepad"]


SECTIONED = """
from art98.anim import *


class Three(Scene):
    desktop = Desktop(pointer=True)

    def construct(self):
        self.section("one", self.one)
        self.section("two", self.two)
        self.section("three", self.three)

    def one(self):
        self.add(Picture("A", at=(40, 40), size=(300, 240)), id="a")
        self.add(Picture("B", at=(380, 120), size=(300, 240)), id="b")
        self.pause(0.5)

    def two(self):
        a = self.prop("a")
        self.play(Drag(a.title_bar, by=(60, 40)), run_time=1)
        self.pause(0.3)

    def three(self):
        b = self.prop("b")
        self.play(Drag(b.title_bar, by=(-80, 60)), run_time=1)
        self.play(Glide(self.prop("a").title_bar), run_time=0.5)
        self.pause(0.3)
"""


def framemd5(path):
    # The guest clock restarts with each revert, so a solo run's clock can show a different
    # minute than the full run's. The owner accepted that as a known limit; everything else
    # must match. Cover the taskbar clock in both clips before hashing (800x600 stock desktop).
    out = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-vf",
            "drawbox=x=740:y=575:w=58:h=22:color=black:t=fill",
            "-f",
            "framemd5",
            "-",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [line.split(", ")[-1] for line in out.splitlines() if line[:1].isdigit()]


def test_a_solo_section_matches_the_full_runs_clip(tmp_path):
    file = tmp_path / "three.py"
    file.write_text(SECTIONED)
    full, solo = tmp_path / "full.mp4", tmp_path / "solo"
    solo.mkdir()
    with attached() as session:
        render(_load_scene(file, "Three"), full, session=session)
        solo_out = render(
            _load_scene(file, "Three"),
            solo / "Three-three.mp4",
            session=session,
            section="three",
        )
    want, got = framemd5(tmp_path / "full-03.mp4"), framemd5(solo_out)
    assert len(got) == len(want), f"{len(got)} solo frames, {len(want)} in the full run"
    first = next((i for i, (a, b) in enumerate(zip(want, got)) if a != b), None)
    assert first is None, f"first differing frame: {first} of {len(want)}"
