"""Scenes rendered one after another in one attach each start from the baseline.

Needs the same prepared image and running service as test_stage.py, and skips
the same way.
"""

from art98.anim import Click, Minesweeper, Paint, Scene, render
from test_stage import (  # noqa: F401  (also brings the skip marks)
    HERE,
    attached,
    pytestmark,
)

STATE = HERE / "examples" / "blank_start" / "states" / "desk.json"
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
        desktop = "stock"
        state = STATE

        def construct(self):
            seen["state_props"] = sorted(self._state_props)
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
