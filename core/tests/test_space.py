"""The desktop space: one calibration per scene, read through by every prop."""

import struct
import warnings

import pytest
from art98 import win32
from art98.actions import keyboard as keys_module
from art98.actions.programs import Notepad
from art98.actions.window.commands import Teleport
from art98.anim import RIGHT, linear, setstate
from art98.base.space import PlacementError, PlacementWarning
from art98.bridge import CallResult
from test_anim import FakeGuest, FakeSession, FakeVideo, Stage

THICK = win32.WS_THICKFRAME
METRICS = {
    0: 800,
    1: 600,
    4: 18,
    5: 1,
    15: 18,
    33: 3,
    34: 112,
    35: 27,
    59: 800,
    60: 600,
}


class SpaceGuest(FakeGuest):
    """A guest with real-looking metrics, window styles and an app minimum size."""

    def __init__(self):
        super().__init__()
        self.metrics = dict(METRICS)
        self.area = (0, 0, 800, 572)
        self.styles = {}
        self.app_min = {}  # hwnd -> (w, h): an app's own WM_GETMINMAXINFO

    def do_GetSystemMetrics(self, index):
        return CallResult(self.metrics.get(index, 0), 0, [])

    def do_SystemParametersInfoA(self, action, value, out, flags):
        return CallResult(1, 0, [struct.pack("<iiii", *self.area)])

    def do_GetWindowLongA(self, hwnd, index):
        return CallResult(self.styles.get(hwnd, 0), 0, [])

    def do_SetWindowPos(self, hwnd, after, x, y, width, height, flags):
        super().do_SetWindowPos(hwnd, after, x, y, width, height, flags)
        left, top, right, bottom = self.rects[hwnd]
        mw, mh = self.app_min.get(hwnd, (0, 0))
        self.rects[hwnd] = (
            left,
            top,
            left + max(right - left, mw),
            top + max(bottom - top, mh),
        )
        return CallResult(1, 0, [])


@pytest.fixture
def guest():
    return SpaceGuest()


@pytest.fixture
def scene(guest, monkeypatch):
    monkeypatch.setattr(keys_module, "KEY_SETTLE", 0)
    stage = Stage()
    stage.run(FakeSession(guest), FakeVideo(guest))
    guest.calls.clear()
    return stage


def pad(guest, scene, style=THICK, **kwargs):
    guest.styles[0x10] = style
    guest.add_window(0x10, "Notepad", (92, 88, 692, 499), pid=7000)
    guest.add_window(0x11, "Edit", (96, 130, 688, 495), parent=0x10)
    prop = Notepad(**kwargs)
    scene.add(prop)
    guest.calls.clear()
    return prop


def test_calibrate_reads_the_space_in_9_calls(guest):
    space = win32.calibrate(guest)
    assert len(guest.calls) == 9
    assert len(guest.named("GetSystemMetrics")) == 8
    assert space.screen == (800, 600) and space.work_area == (0, 0, 800, 572)
    assert space.metrics.min_track == (112, 27) and space.taskbar == (0, 572, 800, 600)
    assert space.title_bar_offset == 3 + 9


def test_props_hold_a_reference_to_the_scene_space_not_a_copy(guest, scene):
    prop = pad(guest, scene)
    assert prop.space is scene.space
    guest.area = (0, 0, 800, 600)
    scene.calibrate()
    assert prop.space is scene.space and prop.space.work_area == (0, 0, 800, 600)
    prop.center()
    assert prop.get_center().y == 300  # the new area, read through the scene
    assert prop.ghost().space is scene.space


def test_title_bar_makes_no_metric_calls(guest, scene):
    prop = pad(guest, scene)
    spot = prop.title_bar
    guest.calls.clear()
    point = spot.point()
    assert guest.named("GetSystemMetrics") == []
    assert point.y == prop.y + 12


def test_a_size_below_the_minimum_is_clamped_and_warns_once_over_many_frames(
    guest, scene
):
    prop = pad(guest, scene)
    with pytest.warns(PlacementWarning, match="track limits") as caught:
        scene.play(prop.animate.resize(50, 10), run_time=1, rate_func=linear)
    sized = [w for w in caught if "track limits" in str(w.message)]
    assert len(sized) == 1
    assert guest.rects[0x10][2] - guest.rects[0x10][0] == 112  # host == guest
    assert prop.size == (112, 27)


def test_strict_placement_raises_instead_of_clamping(guest, scene):
    scene.strict_placement = True
    scene.calibrate()
    prop = pad(guest, scene)
    prop.resize(50, 10)
    with pytest.raises(PlacementError, match="track limits"):
        prop.apply()


def test_a_fixed_frame_window_is_not_clamped(guest, scene):
    prop = pad(guest, scene, style=0)
    prop.resize(50, 10)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        prop.apply()
    assert guest.rects[0x10][2] - guest.rects[0x10][0] == 50


def test_a_window_off_the_screen_warns_but_a_partly_off_one_does_not(guest, scene):
    prop = pad(guest, scene)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        prop.move_to((10, 10))  # half of it is off the top left
        prop.apply()
    prop.shift((5000, 0))
    with pytest.warns(PlacementWarning, match="off the 800x600 screen"):
        prop.apply()


def test_a_maximised_window_is_not_checked(guest, scene):
    prop = pad(guest, scene)
    prop._maximized = True
    prop.set_rect(-4, -4, 5, 5)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        prop.apply()
        prop.settle()


def test_settle_reads_back_once_per_animation_and_reports_the_guests_clamp(
    guest, scene
):
    prop = pad(guest, scene, style=0)  # fixed frame: only the guest knows the minimum
    guest.app_min[0x10] = (200, 100)
    with pytest.warns(PlacementWarning, match="the guest gave") as caught:
        scene.play(
            prop.animate.shift(30 * RIGHT),
            prop.animate.resize(150, 60),
            run_time=1,
            rate_func=linear,
        )
    assert len([w for w in caught if "guest gave" in str(w.message)]) == 1
    # 30 frames: one refresh per animation at begin, and one read-back at the end
    assert len(guest.named("GetWindowRect")) == 3
    assert prop.size == (200, 100)  # the prop holds what the guest has


def test_apply_consumes_the_pending_read_back_when_a_clamp_sends_nothing(guest, scene):
    prop = pad(guest, scene)
    x, y = prop.rect[:2]
    prop.set_rect(x, y, 112, 27)  # the minimum: sent as it is
    prop.apply()
    prop.set_rect(x, y, 50, 20)  # below it, so `settle` asks for a read-back
    prop.settle()
    assert prop._verify
    with pytest.warns(PlacementWarning):  # the clamp gives the size already sent
        prop.apply()
    assert not prop._verify


def test_teleport_settles_exactly_once(guest, scene):
    prop = pad(guest, scene)
    scene.play(Teleport(prop, (300, 300)))
    assert len(guest.named("GetWindowRect")) == 2  # Teleport.act's refresh, one settle


def test_attach_reads_the_style_once_and_the_rect_back(guest, scene):
    pad(guest, scene)
    guest.calls.clear()
    guest.add_window(0x20, "Notepad", (0, 0, 100, 100), pid=7001)
    guest.add_window(0x21, "Edit", (0, 0, 1, 1), parent=0x20)
    guest.next_pid = 7001
    scene.add(Notepad())
    assert len(guest.named("GetWindowLongA")) == 1


def test_a_display_switch_calibrates_a_new_space(guest, scene):
    old = scene.space
    guest.metrics.update({0: 640, 1: 480})
    guest.area = (0, 0, 640, 452)
    setstate.prepare_desktop(scene)
    assert scene.space is not old
    assert scene.space.screen == (640, 480) and scene.work_area == (0, 0, 640, 452)
    assert scene.screen.rect == (0, 0, 640, 452)


def test_wallpaper_sample_stays_above_the_given_bottom():
    from art98.state import State

    state = State(None, None, (), None)
    assert setstate.wallpaper_sample(state, 640, 480, 452) == (320, 240)
    assert setstate.wallpaper_sample(state, 640, 100, 60)[1] == 48
