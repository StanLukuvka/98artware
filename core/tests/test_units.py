"""base/units.py: pixel, frame and progress math, and the rule that it lives only there."""

import ast
from pathlib import Path

import pytest
from art98.anim import Scene
from art98.base.animation import AnimationGroup, Instant, path_function
from art98.base.units import clamp, count, distance, frames, lerp, pixel
from art98.base.vectors import Vec

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0.4, 0), (0.5, 1), (1.5, 2), (2.5, 3), (-0.5, 0), (-1.5, -1), (-2.5, -2)],
)
def test_pixel_rounds_half_up(value, expected):
    assert pixel(value) == expected


def test_half_a_pixel_per_frame_steps_evenly():
    assert [pixel(i * 0.5) for i in range(8)] == [0, 1, 1, 2, 2, 3, 3, 4]


def test_frames_round_half_up():
    assert frames(0.5, 5) == 3
    assert frames(1, 30) == 30


def test_count_is_half_up_and_stays_within_zero_and_n():
    assert [count(a, 4) for a in (0, 0.125, 0.5, 1)] == [0, 1, 2, 4]
    assert count(-1, 4) == 0
    assert count(2, 4) == 4


def test_distance_is_a_straight_line():
    assert distance((0, 0), (3, 4)) == 5
    assert distance(Vec(1, 1), (4, 5)) == 5


def test_clamp_limits_both_ends():
    assert (clamp(5, 0, 3), clamp(-1, 0, 3), clamp(2, 0, 3)) == (3, 0, 2)


def test_lerp_blends_numbers_and_points():
    assert lerp(10, 20, 0.25) == 12.5
    point = lerp((0, 0), (10, 20), 0.5)
    assert point == Vec(5, 10)
    assert isinstance(point, Vec)


def test_a_path_is_paced_by_straight_line_length():
    along = path_function([(0, 0), (30, 40), (30, 90)])
    # 50 px diagonal then 50 px straight: halfway is the corner.
    assert along(0.5) == pytest.approx((30, 40))
    assert along(0.75) == pytest.approx((30, 65))


def test_sum_of_points_works():
    assert sum([Vec(1, 2), Vec(3, 4)]) == Vec(4, 6)
    assert sum([Vec(1, 2)]) == Vec(1, 2)


def test_an_instant_acts_again_when_played_again():
    acted = []

    class Poke(Instant):
        def act(self):
            acted.append(1)

    poke = Poke()
    for _ in range(2):
        poke.begin(Scene())
        poke.update(1.0)
    assert len(acted) == 2


def test_a_negative_lag_ratio_is_refused():
    with pytest.raises(ValueError, match="lag_ratio"):
        AnimationGroup(lag_ratio=-0.5)


SCANNED = [
    *(ROOT / "core/art98/base").rglob("*.py"),
    *(ROOT / "core/art98/anim").rglob("*.py"),
    *(ROOT / "core/art98/actions").rglob("*.py"),
    ROOT / "core/art98/desktop.py",
    ROOT / "core/art98/output/recorder.py",
]


def stray_math(path):
    for node in ast.walk(ast.parse(path.read_text())):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Name) and fn.id == "round":
            yield node.lineno, "round"
        if (
            isinstance(fn, ast.Attribute)
            and fn.attr in ("hypot", "dist")
            and isinstance(fn.value, ast.Name)
            and fn.value.id == "math"
        ):
            yield node.lineno, f"math.{fn.attr}"


def test_rounding_and_distance_live_only_in_units_py():
    home = ROOT / "core/art98/base/units.py"
    strays = sorted(
        f"{path.relative_to(ROOT)}:{line}: {what}"
        for path in SCANNED
        if path != home
        for line, what in stray_math(path)
    )
    assert strays == [], "use pixel, frames, count or distance from art98.base.units"
