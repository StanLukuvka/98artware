"""The scene layer against a stand-in guest: nothing here needs a VM."""

import hashlib
import importlib.util
import inspect
import json
import re
import shutil
import struct
from pathlib import Path

import pytest
from art98 import UsageError, anim
from art98 import session as session_module
from art98.actions import keyboard as keys_module
from art98.actions import programs
from art98.actions.keyboard import char_chord, key_chord
from art98.anim import *
from art98.anim import scene as scene_module
from art98.anim.setstate import window_problems
from art98.base.animation import path_function
from art98.base.props import Spot
from art98.errors import GuestError, MissingFile, NotFound
from art98.guest import guestfiles, win32
from art98.guest.bridge import CallResult, Window
from art98.guest.win32 import MOUSE_BUTTONS
from art98.output import recorder as recorder_module
from art98.state import load_state

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")

WM_CHAR, WM_CLOSE, WM_SYSCOMMAND = 0x0102, 0x0010, 0x0112
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE = 1, 2, 4, 0x10
LDOWN, LUP = MOUSE_BUTTONS["left"]
RDOWN, RUP = MOUSE_BUTTONS["right"]


class FakeDll:
    def __init__(self, guest, name):
        self._guest, self._name = guest, name

    def __getattr__(self, function):
        def call(*args, timeout=None):
            return self._guest.handle(self._name, function, args)

        return call


class FakeGuest:
    """Keeps just enough state to answer what props ask."""

    def __init__(self):
        self.calls = []
        self.rects = {}
        self.edit_text = {}
        self.edit_sel = {}  # hwnd -> (start, end) the Edit control reports
        self.rows = {0: []}
        self.iconic, self.zoomed = (
            set(),
            set(),
        )  # hwnds the guest shows minimized / maximized
        self.normal = {}  # hwnd -> the rect Windows keeps for a maximized window
        self.cursor = (400, 300)
        self.foreground = 0
        self.spawned = []
        self.syncs = 0
        self.next_pid = 7000
        self.user32 = FakeDll(self, "user32")
        self.gdi32 = FakeDll(self, "gdi32")
        # GetFileAttributesA gives 1: a file is there
        self.kernel32 = FakeDll(self, "kernel32")

    def add_window(self, hwnd, class_name, rect, title="", parent=0, pid=0):
        self.rects[hwnd] = rect
        self.rows.setdefault(parent, []).append(
            Window(hwnd, pid, True, rect, class_name, title)
        )

    def handle(self, dll, function, args):
        self.calls.append((function, args))
        handler = getattr(self, f"do_{function}", None)
        return handler(*args) if handler else CallResult(1, 0, [])

    def named(self, *functions):
        return [call for call in self.calls if call[0] in functions]

    def do_GetCursorPos(self, out):
        return CallResult(1, 0, [struct.pack("<ii", *self.cursor)])

    def do_SetCursorPos(self, x, y):
        self.cursor = (x, y)
        return CallResult(1, 0, [])

    def do_GetWindowRect(self, hwnd, out):
        if hwnd not in self.rects:  # Windows: FALSE for a window that has gone
            return CallResult(0, 0, [])
        return CallResult(1, 0, [struct.pack("<iiii", *self.rects[hwnd])])

    def do_SetWindowPos(self, hwnd, after, x, y, width, height, flags):
        left, top, right, bottom = self.rects[hwnd]
        if flags & SWP_NOMOVE:
            x, y = left, top
        if flags & SWP_NOSIZE:
            width, height = right - left, bottom - top
        self.rects[hwnd] = (x, y, x + width, y + height)
        return CallResult(1, 0, [])

    def do_SystemParametersInfoA(self, action, value, out, flags):
        return CallResult(1, 0, [struct.pack("<iiii", 0, 0, 800, 572)])

    def do_GetSystemMetrics(self, index):
        return CallResult({0: 800, 1: 600, 4: 18, 33: 3}.get(index, 0), 0, [])

    def do_ClientToScreen(self, hwnd, point):
        x, y = struct.unpack("<ii", point)
        left, top = self.rects[hwnd][:2]
        return CallResult(1, 0, [struct.pack("<ii", left + 3 + x, top + 41 + y)])

    def do_IsIconic(self, hwnd):
        return CallResult(int(hwnd in self.iconic), 0, [])

    def do_IsZoomed(self, hwnd):
        return CallResult(int(hwnd in self.zoomed), 0, [])

    def do_GetWindowPlacement(self, hwnd, buffer):
        # WINDOWPLACEMENT: 44 bytes; rcNormalPosition is the last four ints.
        assert struct.unpack("<I", buffer[:4]) == (44,)
        placement = (44, 0, 1, 0, 0, 0, 0, *self.normal.get(hwnd, self.rects[hwnd]))
        return CallResult(1, 0, [struct.pack("<11i", *placement)])

    def do_GetDeviceCaps(self, dc, index):
        return CallResult(16, 0, [])

    def do_GetSysColor(self, index):
        return CallResult(0x808000, 0, [])  # teal, as a COLORREF

    def do_SendMessageA(self, hwnd, message, wparam, lparam):
        # Edit controls keep the text WM_SETTEXT gave them.
        text = self.edit_text.get(hwnd, b"")
        if message == 0x000C:  # WM_SETTEXT
            self.edit_text[hwnd] = lparam.encode("cp1252")
        elif message == 0x000E:  # WM_GETTEXTLENGTH
            return CallResult(len(text), 0, [])
        elif message == 0x000D:  # WM_GETTEXT
            return CallResult(len(text), 0, [text])
        elif message == win32.EM_GETSEL:
            start, end = self.edit_sel.get(hwnd, (0, 0))
            return CallResult(start | end << 16, 0, [])
        elif message == win32.EM_SETSEL:
            self.edit_sel[hwnd] = (wparam, lparam)
        return CallResult(1, 0, [])

    def do_GetClientRect(self, hwnd, out):
        return CallResult(1, 0, [struct.pack("<iiii", 0, 0, 148, 191)])

    def do_PostMessageA(self, hwnd, message, wparam, lparam):
        if message == WM_CLOSE:  # Windows: the window and its children go
            self.close_window(hwnd)
        return CallResult(1, 0, [])

    def close_window(self, hwnd):
        self.rects.pop(hwnd, None)
        for rows in self.rows.values():
            rows[:] = [w for w in rows if w.hwnd != hwnd]
        self.rows.pop(hwnd, None)

    def do_GetDlgCtrlID(self, hwnd):
        return CallResult(hwnd, 0, [])

    def do_GetForegroundWindow(self):
        return CallResult(self.foreground, 0, [])

    def do_mouse_event(self, flags, *_):
        # A real press on a window gives it the foreground. Captures written with
        # a `stack` activate the front window through a title-bar click on set.
        if flags == LDOWN:
            for w in self.windows():
                left, top, right, bottom = self.rects.get(w.hwnd, (0, 0, 0, 0))
                if left <= self.cursor[0] <= right and top <= self.cursor[1] <= bottom:
                    self.foreground = w.hwnd
                    break
        return CallResult(1, 0, [])

    def windows(self, parent=0):
        return list(self.rows.get(parent, []))

    def find_window(self, title=None, class_name=None, parent=0, timeout=10.0):
        return next(
            w
            for w in self.windows(parent)
            if class_name is None or w.class_name == class_name
        )

    def spawn(self, command, cwd=None):
        self.spawned.append(command)
        return self.next_pid

    def sync(self, hwnd=0, timeout_ms=500):
        self.syncs += 1
        return 0


class FakeVM:
    def __init__(self):
        self.keys = []
        self.calls = []

    def insert_disc(self, iso):
        self.calls.append("insert_disc")

    def eject_disc(self):
        self.calls.append("eject_disc")

    def load_snapshot(self, name):
        self.calls.append("load_snapshot")

    def send_keys(self, *codes, hold_ms=80):
        self.keys.append(codes)


class FakeVideo:
    def __init__(self, guest):
        self.guest = guest
        self.count = 0
        self.frames = []
        self.cuts = []
        self.live_calls = []
        self.clips = self.parts = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    @property
    def total(self):
        return self.count

    def frame(self, hold=1):
        self.frames.append((hold, len(self.guest.calls), self.guest.cursor))
        self.count += hold

    def cut(self, path=None):
        self.cuts.append((self.count, path))
        return Path(f"clip{len(self.cuts)}.mp4")

    def live(self, seconds, stop_condition=None, stacklevel=1):
        self.live_calls.append(seconds)
        for _ in range(round(seconds * 30)):
            if stop_condition is not None and stop_condition():
                return
            self.count += 1


class FakeSession:
    def __init__(self, guest):
        self.bridge, self.vm = guest, FakeVM()
        self.reverts = 0
        self.fresh = True  # as after `attach`
        self.videos = []  # what `record` handed out

    def revert(self, snapshot="ready"):
        self.reverts += 1
        self.fresh = True

    def record(self, path, output_fps, lossless=False, defer=False):
        """What `render` asks for: one video that is already its own single clip."""
        path = Path(path)
        path.write_bytes(b"video")
        video = FakeVideo(self.bridge)
        video.clips = video.parts = [path]
        self.videos.append(video)
        return video


class QuietBridge:
    def abandon(self, reason):
        pass

    def ping(self):
        return 1


def test_revert_ejects_the_disc_before_loadvm_only_when_one_was_inserted():
    vm = FakeVM()
    session = session_module.Session(vm, QuietBridge())
    session.revert()
    assert vm.calls == [
        "load_snapshot"
    ]  # no disc: an old container image never sees eject_disc
    session.attach_disc({"WALL0001.BMP": b"x" * 10})
    assert vm.calls[-1] == "insert_disc"
    session.revert()
    assert vm.calls[1:] == ["insert_disc", "eject_disc", "load_snapshot"]
    session.revert()
    assert vm.calls[4:] == ["load_snapshot"]


def test_a_failed_insert_still_gets_ejected_by_revert():
    class Refusing(FakeVM):
        def insert_disc(self, iso):
            raise OSError("reply lost")

    vm = Refusing()
    session = session_module.Session(vm, QuietBridge())
    with pytest.raises(OSError):
        session.attach_disc({"WALL0001.BMP": b"x" * 10})
    session.revert()
    assert vm.calls == ["eject_disc", "load_snapshot"]


def test_a_failed_revert_leaves_the_guest_not_fresh():
    class Broken(FakeVM):
        def load_snapshot(self, name):
            raise OSError("no such snapshot")

    session = session_module.Session(Broken(), QuietBridge())
    session.fresh = True
    with pytest.raises(OSError):
        session.revert()
    assert session.fresh is False


def test_close_closes_the_vm_even_if_the_bridge_will_not():
    class BadBridge(QuietBridge):
        def close(self):
            raise OSError("broken pipe")

    class ClosingVM(FakeVM):
        def close(self):
            self.calls.append("close")

    vm = ClosingVM()
    with pytest.raises(OSError):
        session_module.Session(vm, BadBridge()).close()
    assert vm.calls == ["close"]


def test_stage_without_an_image_says_to_run_setup(tmp_path):
    with (
        pytest.raises(session_module.ImageMissing, match="art98 setup"),
        session_module.stage(tmp_path),
    ):
        pass
    with pytest.raises(session_module.ImageMissing, match="art98 setup"):
        session_module.boot_local(tmp_path)
    assert issubclass(session_module.ImageMissing, MissingFile)


class Stage(Scene):
    pass


@pytest.fixture
def guest():
    return FakeGuest()


@pytest.fixture
def scene(guest, monkeypatch):
    monkeypatch.setattr(keys_module, "KEY_SETTLE", 0)
    stage = Stage()
    stage.run(FakeSession(guest), FakeVideo(guest))
    guest.calls.clear()
    return stage


def notepad(guest, scene, pid=7000):
    guest.add_window(0x10, "Notepad", (92, 88, 692, 499), pid=pid)
    guest.add_window(0x11, "Edit", (96, 130, 688, 495), parent=0x10)
    pad = Notepad()
    scene.add(pad)
    guest.calls.clear()
    return pad


class Probe(Animation):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.log = []

    def begin(self, scene):
        super().begin(scene)
        self.log.append("begin")

    def interpolate(self, alpha):
        self.log.append(alpha)

    def finish(self, scene):
        self.log.append("finish")


# ---- vectors and rate functions ----


def test_vectors_read_like_manim_with_y_down():
    assert 280 * RIGHT + 120 * DOWN == (280, 120)
    assert (10, 10) + 5 * UP == (10, 5)
    assert UL == (-1, -1) and DR == (1, 1)
    assert isinstance((1, 2) + RIGHT, Vec)


@pytest.mark.parametrize("function", [linear, smooth, smoothstep, rush_into, rush_from])
def test_rate_functions_run_from_0_to_1(function):
    assert function(0) == pytest.approx(0)
    assert function(1) == pytest.approx(1)
    values = [function(i / 50) for i in range(51)]
    assert values == sorted(values)


def test_there_and_back_returns():
    assert there_and_back(0) == pytest.approx(0)
    assert there_and_back(0.5) == pytest.approx(1)
    assert there_and_back(1) == pytest.approx(0)


# ---- retired settings ----


def test_a_scene_defining_a_retired_setting_fails_at_class_definition(monkeypatch):
    monkeypatch.setattr(scene_module, "RETIRED", {"old": "removed"})
    with pytest.raises(UsageError, match="Old.old"):
        type("Old", (Scene,), {"old": 30})


def test_a_scene_defining_output_fps_is_fine():
    assert type("New", (Scene,), {"output_fps": 24}).output_fps == 24


def test_a_live_play_that_runs_late_warns_once(scene, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(recorder_module.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(recorder_module.time, "sleep", lambda s: None)
    video_frame = scene.recorder.frame

    def slow(hold=1):
        now[0] += 0.1  # capturing takes 0.1 s against 1/30 s
        video_frame(hold)

    scene.recorder.frame = slow
    with pytest.warns(UserWarning, match="took 1.50 s") as record:
        scene.play(Probe(run_time=0.5, rate_func=linear), live=True)
    assert len(record) == 1 and "slower" in str(record[0].message)


# ---- the frame loop ----


def test_play_writes_run_time_times_fps_frames_and_ends_at_exactly_1(scene):
    probe = Probe(run_time=0.5, rate_func=linear)
    scene.play(probe)
    assert scene.recorder.count == 15
    assert scene.time == pytest.approx(0.5)
    assert probe.log[0] == "begin" and probe.log[-1] == "finish"
    assert probe.log[-2] == 1.0
    assert len(probe.log) == 17


def test_one_play_runs_animations_together_and_short_ones_hold(scene):
    long, short = (
        Probe(run_time=1, rate_func=linear),
        Probe(run_time=0.5, rate_func=linear),
    )
    scene.play(long, short)
    assert scene.recorder.count == 30
    assert short.log.count("finish") == 1
    assert short.log.index(1.0) == 15
    assert long.log[-2] == 1.0


def test_play_overrides_run_time_and_rate_func(scene):
    probe = Probe()
    scene.play(probe, run_time=0.1, rate_func=lambda t: 0.25)
    assert scene.recorder.count == 3
    assert set(probe.log[1:-1]) == {0.25}


def test_an_instant_animation_takes_one_frame(guest, scene):
    pad = notepad(guest, scene)
    scene.play(Minimize(pad))
    assert scene.recorder.count == 1
    assert ("PostMessageA", (0x10, WM_SYSCOMMAND, 0xF020, 0)) in guest.calls


def test_two_pointer_animations_in_one_play_are_refused(scene):
    with pytest.raises(ValueError, match="pointer"):
        scene.play(Click((1, 1)), Glide((2, 2)))


def test_play_needs_an_animation(scene):
    with pytest.raises(ValueError):
        scene.play()


@pytest.mark.parametrize("how", ["play", "wait", "wait_until"])
def test_a_late_warning_points_at_the_scene_script(scene, monkeypatch, how):
    now = [100.0]
    monkeypatch.setattr(recorder_module.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(recorder_module.time, "sleep", lambda s: None)

    class SlowVideo(FakeVideo):
        live = recorder_module.Recorder.live  # the real one, on a fake
        _output_fps = 10

        def _capture(self, hold):
            now[0] += 0.5  # half a second a frame against 0.1 s planned
            self.count += hold

        def frame(self, hold=1):
            now[0] += 0.5
            super().frame(hold)

    scene.recorder.__class__ = SlowVideo
    scene.output_fps = 10
    calls = {
        "play": lambda: scene.play(Probe(run_time=1, rate_func=linear), live=True),
        "wait": lambda: scene.wait(1),
        "wait_until": lambda: scene.wait_until(
            iter([False, False, True, True]).__next__, max_time=1
        ),
    }
    with pytest.warns(UserWarning, match="slower") as record:
        calls[how]()
    assert [w.filename for w in record] == [__file__]


def test_pause_holds_one_capture(scene):
    scene.pause(2)
    assert scene.recorder.frames == [(60, 0, (400, 300))]
    assert scene.time == 2


def test_wait_records_live_and_pause_holds_one_capture(scene):
    scene.wait(1)
    assert scene.recorder.live_calls == [1]
    scene.pause(1)
    assert scene.recorder.live_calls == [1] and scene.time == 2


def test_wait_has_no_frozen_frame_and_scene_has_no_live_or_video(scene):
    with pytest.raises(TypeError):
        scene.wait(1, frozen_frame=True)
    assert not hasattr(scene, "live") and not hasattr(scene, "video")


def test_wait_stops_on_its_condition(scene):
    answers = iter([False, False, True])
    scene.wait(10, stop_condition=lambda: next(answers))
    assert scene.recorder.count == 2


def test_wait_until_warns_when_it_gives_up(scene):
    with pytest.warns(UserWarning, match="gave up"):
        scene.wait_until(lambda: False, max_time=0.1)


def test_wait_until_warning_points_at_the_caller(scene):
    with pytest.warns(UserWarning, match="gave up") as record:
        scene.wait_until(lambda: False, max_time=0.1)
    assert record[0].filename == __file__


def test_run_calls_the_hooks_in_order_and_exposes_the_guest(guest):
    order = []

    class Hooks(Scene):
        def setup(self):
            order.append("setup")

        def construct(self):
            order.append("construct")
            assert self.guest is guest and self.pointer.get_center() == (400, 300)

        def tear_down(self):
            order.append("tear_down")

    Hooks().run(FakeSession(guest), FakeVideo(guest))
    assert order == ["setup", "construct", "tear_down"]


def test_succession_starts_each_child_where_the_last_left_off(guest, scene):
    first, second = Glide((100, 100), run_time=0.5), Glide((200, 100), run_time=0.5)
    scene.play(Succession(first, second))
    assert scene.recorder.count == 30
    assert second.start == (100, 100)
    assert guest.cursor == (200, 100)


def test_a_group_with_lag_starts_late(scene):
    first, second = (
        Probe(run_time=1, rate_func=linear),
        Probe(run_time=1, rate_func=linear),
    )
    scene.play(LaggedStart(first, second, lag_ratio=0.5))
    assert scene.recorder.count == 45
    assert first.log[-2] == 1.0 and second.log[-2] == 1.0


def test_overlapping_children_may_not_share_the_pointer():
    with pytest.raises(ValueError):
        AnimationGroup(Glide((0, 0)), Glide((1, 1)))
    Succession(Glide((0, 0)), Glide((1, 1)))


# ---- layout ----


def test_layout_matches_manim_meanings():
    box = Box(0, 0, 100, 50)
    assert box.move_to((200, 200)).rect == (150, 175, 250, 225)
    assert box.move_to((10, 20), aligned_edge=UL).rect == (10, 20, 110, 70)
    assert box.to_corner(DR).rect == (700, 522, 800, 572)
    assert box.to_edge(LEFT, buff=5).rect[0] == 5
    assert box.center().get_center() == (400, 286)
    assert box.scale(2).size == (200, 100)
    assert box.get_center() == (400, 286)
    other = Box(100, 100, 40, 40)
    assert box.resize(10, 10).next_to(other, RIGHT, buff=2).rect == (142, 115, 152, 125)
    assert box.shift(UP, 2 * LEFT).rect == (140, 114, 150, 124)


# ---- windows ----


def test_reading_a_window_back_keeps_a_change_not_yet_sent(guest, scene):
    pad = notepad(guest, scene)
    pad.to_corner(UL, buff=90)
    beside = Box(width=50, height=50).next_to(pad, RIGHT, buff=10)
    assert pad.rect[:2] == (90, 90)
    assert guest.rects[pad.hwnd][:2] == (90, 90)
    assert beside.x == pad.rect[2] + 10


def test_a_win_starts_its_program_and_finds_its_own_window(guest, scene):
    guest.add_window(0x20, "Notepad", (0, 0, 100, 100), pid=1)
    guest.add_window(0x10, "Notepad", (92, 88, 692, 499), pid=7000)
    guest.add_window(0x11, "Edit", (0, 0, 1, 1), parent=0x10)
    pad = Notepad(at=(10, 20), size=(300, 200))
    scene.add(pad)
    assert guest.spawned == ["notepad.exe"] and pad.hwnd == 0x10
    assert guest.rects[0x10] == (10, 20, 310, 220)


def test_normal_rect_unpacks_the_placement_the_guest_returns(guest):
    guest.add_window(0x10, "Notepad", (10, 20, 310, 220))
    assert win32.normal_rect(guest, 0x10) == (10, 20, 310, 220)
    guest.calls.clear()
    guest.do_GetWindowPlacement = lambda hwnd, buffer: CallResult(0, 0, [bytes(44)])
    with pytest.raises(GuestError, match="GetWindowPlacement"):
        win32.normal_rect(guest, 0x10)


def state_with_text(tmp_path, data=b"one\ntwo\n"):
    (tmp_path / "note.txt").write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    return load_state(
        dump_json(
            tmp_path,
            {
                "version": 1,
                "windows": [
                    {
                        "id": "note",
                        "app": "notepad",
                        "title": "Note",
                        "at": [10, 20],
                        "size": [300, 200],
                        "text": {"file": "note.txt", "sha256": digest},
                    }
                ],
            },
        )
    )


def dump_json(tmp_path, value):
    path = tmp_path / "state.json"
    path.write_text(json.dumps(value))
    return path


def test_a_state_text_is_set_in_the_edit_box_and_checked(guest, scene, tmp_path):
    state = state_with_text(tmp_path)
    guest.add_window(0x10, "Notepad", (10, 20, 310, 220), "Note", pid=7000)
    guest.add_window(0x11, "Edit", (96, 130, 688, 495), parent=0x10)
    pad = Notepad.from_state(state.window("note"))
    scene.add(pad)
    assert guest.edit_text[0x11] == b"one\r\ntwo\r\n"
    found = {0x10: Window(0x10, 7000, True, (10, 20, 310, 220), "Notepad", "Note")}
    assert window_problems(guest, state, {"note": pad}, found) == []
    guest.edit_text[0x11] = b"changed"
    assert window_problems(guest, state, {"note": pad}, found) == [
        "windows[0] 'note': text differs from note.txt"
    ]


def test_a_prop_not_on_stage_says_so():
    with pytest.raises(UsageError, match="add it"):
        Notepad().guest  # noqa: B018


def test_playing_a_prop_adds_it(guest, scene):
    guest.add_window(0x10, "Notepad", (0, 0, 100, 100), pid=7000)
    guest.add_window(0x11, "Edit", (0, 0, 1, 1), parent=0x10)
    pad = Notepad()
    scene.play(TypeWithCursor(pad, "a"))
    assert pad in scene.props


def test_a_move_keeps_size_and_order_and_repaints_each_frame(guest, scene):
    pad = notepad(guest, scene)
    scene.play(pad.animate.shift(30 * RIGHT), run_time=0.1, rate_func=linear)
    moves = guest.named("SetWindowPos")
    assert len(moves) == 3 and len(guest.named("RedrawWindow")) == 3
    assert moves[-1][1][2:4] == (122, 88)
    assert all(
        args[-1] == SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE for _, args in moves
    )


def test_a_move_and_a_resize_become_one_call_per_frame(guest, scene):
    pad = notepad(guest, scene)
    scene.play(
        pad.animate.shift(30 * RIGHT),
        pad.animate.resize(300, 200),
        run_time=0.1,
        rate_func=linear,
    )
    assert len(guest.named("SetWindowPos")) == 3
    assert guest.rects[0x10] == (122, 88, 422, 288)


def test_movement_under_a_pixel_sends_nothing(guest, scene):
    pad = notepad(guest, scene)
    scene.play(pad.animate.shift(0.4 * RIGHT), run_time=0.5)
    assert guest.named("SetWindowPos") == []


def test_animate_starts_from_the_real_window(guest, scene):
    pad = notepad(guest, scene)
    guest.rects[0x10] = (0, 0, 600, 411)
    scene.play(pad.animate.shift(10 * DOWN), run_time=0.1)
    assert guest.rects[0x10] == (0, 10, 600, 421)


def test_animate_refuses_what_is_not_layout(guest, scene):
    pad = notepad(guest, scene)
    with pytest.raises(AttributeError):
        pad.animate.close  # noqa: B018


def test_move_along_path_carries_the_centre(guest, scene):
    pad = notepad(guest, scene)
    scene.play(
        MoveAlongPath(pad, [(300, 200), (400, 200), (400, 300)]),
        run_time=0.5,
        rate_func=linear,
    )
    left, top, right, bottom = guest.rects[0x10]
    assert (left + right) / 2 == pytest.approx(400, abs=1)
    assert (top + bottom) / 2 == pytest.approx(300, abs=1)


def test_title_bar_and_client_points_use_the_live_window(guest, scene):
    pad = notepad(guest, scene)
    spot = pad.title_bar
    guest.rects[0x10] = (100, 100, 300, 300)
    assert spot.point() == (200, 112)
    assert pad.client(5, 6).point() == (108, 147)


def test_activate_clicks_the_title_bar_when_needed(guest, scene):
    pad = notepad(guest, scene)
    guest.foreground = 0x10
    pad.activate()
    assert guest.named("mouse_event") == []
    guest.foreground = 0

    def click_takes_focus(*args):
        guest.foreground = 0x10
        return CallResult(1, 0, [])

    guest.do_mouse_event = click_takes_focus
    pad.activate()
    assert guest.cursor == (400, 300)
    assert len(guest.named("mouse_event")) == 2


def test_close_marks_notepad_saved_and_leaves_the_scene(guest, scene):
    pad = notepad(guest, scene)
    scene.play(Close(pad))
    assert ("SendMessageA", (0x11, 0x00B9, 0, 0)) in guest.calls
    assert ("PostMessageA", (0x10, WM_CLOSE, 0, 0)) in guest.calls
    assert pad not in scene.props


# ---- tracking ----


def test_a_window_the_scene_did_not_add_fails_the_next_wait_naming_it(guest, scene):
    guest.add_window(0x99, "#32768", (0, 0, 50, 50), "Stray menu")
    with pytest.raises(scene_module.UntrackedWindow, match="Stray menu.*0x99"):
        scene.wait(0.1)
    assert issubclass(scene_module.UntrackedWindow, GuestError)


def test_a_window_the_scene_did_not_add_fails_play_and_the_end_of_run(guest, scene):
    guest.add_window(0x99, "Foo", (0, 0, 50, 50), "Stray")
    with pytest.raises(scene_module.UntrackedWindow):
        scene.play(Wait(0.1))

    class Leaks(Stage):
        def construct(self):
            self.guest.add_window(0x98, "Foo", (0, 0, 50, 50), "Leak")

    with pytest.raises(scene_module.UntrackedWindow, match="Leak"):
        Leaks().run(FakeSession(FakeGuest()), FakeVideo(guest))


def test_pause_does_not_look_at_the_guest(guest, scene):
    guest.add_window(0x99, "Foo", (0, 0, 50, 50), "Stray")
    scene.pause(0.1)


def test_windows_the_desktop_started_with_are_not_untracked(guest):
    guest.add_window(0x5, "Progman", (0, 0, 800, 600))
    stage = Stage()
    stage.run(FakeSession(guest), FakeVideo(guest))
    stage.wait(0.1)
    guest.add_window(0x99, "Foo", (0, 0, 50, 50), "Stray")
    with pytest.raises(scene_module.UntrackedWindow):
        stage.wait(0.1)


def test_a_hidden_window_is_not_untracked_and_a_hidden_prop_is_not_gone(guest, scene):
    pad = notepad(guest, scene)
    guest.rows[0][0] = Window(0x10, 7000, False, (92, 88, 692, 499), "Notepad", "")
    guest.rows[0].append(Window(0x99, 1, False, (0, 0, 5, 5), "Foo", "Hidden"))
    scene.wait(0.1)
    assert pad in scene.props


def test_a_control_of_a_prop_is_not_untracked(guest, scene):
    pad = notepad(guest, scene)
    pad.control("Edit")
    scene.wait(0.1)


def test_a_window_gone_without_close_raises_implicit_close_naming_the_prop(
    guest, scene
):
    pad = notepad(guest, scene)
    guest.close_window(0x10)  # the X button, a menu's Exit
    with pytest.raises(scene_module.ImplicitClose, match=r"Notepad.*Close\(window"):
        scene.wait(0.1)
    assert issubclass(scene_module.ImplicitClose, GuestError) and pad in scene.props


def test_a_reused_handle_with_another_pid_counts_as_gone(guest, scene):
    notepad(guest, scene)
    guest.close_window(0x10)
    guest.add_window(0x10, "Notepad", (92, 88, 692, 499), pid=8123)
    with pytest.raises(scene_module.ImplicitClose):
        scene.wait(0.1)


def test_a_reused_handle_with_another_class_counts_as_gone(guest, scene):
    notepad(guest, scene)
    guest.close_window(0x10)
    guest.add_window(0x10, "OtherClass", (92, 88, 692, 499), pid=7000)
    with pytest.raises(scene_module.ImplicitClose):
        scene.wait(0.1)


def prompt_of(guest, pid=7000):
    guest.add_window(0x60, "#32770", (150, 150, 300, 250), "Congratulations", pid=pid)


def test_a_prompt_claimed_by_minesweeper_does_not_raise_during_a_play(guest, scene):
    board = sweeper(guest, scene)
    prompt_of(guest)

    typed = scene.vm.send_keys

    def answer_prompt(*codes, hold_ms=80):
        typed(*codes, hold_ms=hold_ms)
        guest.close_window(0x60)  # the prompt goes when a key is pressed

    scene.vm.send_keys = answer_prompt
    board.sign_scoreboard()
    assert scene._claims == []


def test_a_prompt_nobody_claimed_still_raises_in_a_play(guest, scene):
    sweeper(guest, scene)
    prompt_of(guest)
    with pytest.raises(scene_module.UntrackedWindow, match="Congratulations"):
        scene.play(Wait(0.1))


def test_a_claim_does_not_cover_another_process_and_the_error_names_the_owner(
    guest, scene
):
    sweeper(guest, scene)
    prompt_of(guest, pid=9999)
    guest.add_window(0x61, "#32770", (0, 0, 5, 5), "Mine", pid=7000)
    board_claim = lambda w: w.class_name == "#32770" and w.pid == 7000
    with scene.claim("Minesweeper's prompt", board_claim):
        with pytest.raises(scene_module.UntrackedWindow, match="0x60") as caught:
            scene.wait(0.1)
        guest.close_window(0x60)
        guest.close_window(0x61)
    assert "Claimed now: Minesweeper's prompt" in str(caught.value)


def test_a_claim_whose_window_is_still_up_after_release_raises_naming_the_owner(
    guest, scene, monkeypatch
):
    from art98.guest import win32

    monkeypatch.setattr(win32, "CLOSE_TIMEOUT", 0.01)
    guest.add_window(0x62, "#32770", (0, 0, 5, 5), "Left behind")
    with (
        pytest.raises(scene_module.UntrackedWindow, match="Owner X left.*Left behind"),
        scene.claim("Owner X", lambda w: w.class_name == "#32770"),
    ):
        scene.wait(0.1)
    assert scene._claims == []


def test_a_claim_is_released_when_its_block_raises(guest, scene):
    with pytest.raises(RuntimeError), scene.claim("Owner X", lambda w: True):
        raise RuntimeError("boom")
    assert scene._claims == []


def test_the_right_click_menu_claim_lasts_across_a_wait_and_ends_when_the_menu_goes(
    guest, scene
):
    guest.add_window(0x70, "#32768", (640, 300, 740, 400), "")
    scene.play(RightClick((640, 300)))
    scene.wait(0.1)
    scene.wait(0.1)
    assert len(scene._claims) == 1
    guest.close_window(0x70)
    scene.wait(0.1)
    assert scene._claims == []
    guest.add_window(0x71, "#32768", (640, 300, 740, 400), "")
    with pytest.raises(scene_module.UntrackedWindow):
        scene.wait(0.1)


def test_a_right_click_that_opens_no_menu_drops_its_claim_after_the_grace_period(
    guest, scene, monkeypatch
):
    now = [100.0]
    monkeypatch.setattr(scene_module, "monotonic", lambda: now[0])
    scene.play(RightClick((640, 300)))
    scene.check_tracking()
    assert len(scene._claims) == 1  # still waiting for a menu
    now[0] += 6.0  # past win32.CLOSE_TIMEOUT
    scene.check_tracking()
    assert scene._claims == []
    guest.add_window(0x72, "#32768", (640, 300, 740, 400), "")
    with pytest.raises(scene_module.UntrackedWindow):
        scene.wait(0.1)


def test_a_menu_that_appears_after_the_first_check_is_still_claimed(
    guest, scene, monkeypatch
):
    now = [100.0]
    monkeypatch.setattr(scene_module, "monotonic", lambda: now[0])
    scene.play(RightClick((640, 300)))
    scene.check_tracking()
    guest.add_window(0x73, "#32768", (640, 300, 740, 400), "")
    scene.wait(0.1)
    assert len(scene._claims) == 1
    guest.close_window(0x73)
    scene.wait(0.1)
    assert scene._claims == []


def test_a_tooltip_up_when_a_hover_returns_does_not_raise(guest, scene):
    guest.add_window(0x80, "tooltips_class32", (700, 560, 780, 580), "")
    scene.play(Hover((768, 587), hold=0.1, travel_time=0.1))
    assert len(scene._claims) == 1
    guest.close_window(0x80)
    scene.wait(0.1)
    assert scene._claims == []


def test_a_tooltip_that_appears_after_its_hover_claim_ended_still_raises(
    guest, scene, monkeypatch
):
    now = [100.0]
    monkeypatch.setattr(scene_module, "monotonic", lambda: now[0])
    scene.play(Hover((768, 587), hold=0.1, travel_time=0.1))
    assert len(scene._claims) == 1  # still waiting for a tooltip
    now[0] += 6.0  # past win32.CLOSE_TIMEOUT
    scene.check_tracking()
    assert scene._claims == []
    guest.add_window(0x81, "tooltips_class32", (700, 560, 780, 580), "")
    with pytest.raises(scene_module.UntrackedWindow):
        scene.check_tracking()


def test_a_tooltip_with_no_hover_still_raises(guest, scene):
    guest.add_window(0x82, "tooltips_class32", (700, 560, 780, 580), "")
    with pytest.raises(scene_module.UntrackedWindow):
        scene.wait(0.1)


def test_a_claim_release_waits_for_a_window_that_is_still_closing(
    guest, scene, monkeypatch
):
    from art98.guest import win32

    monkeypatch.setattr(win32, "CLOSE_POLL", 0)
    guest.add_window(0x63, "#32770", (0, 0, 5, 5), "Closing")
    real, calls = guest.windows, [0]

    def windows():
        calls[0] += 1
        if calls[0] == 3:
            guest.close_window(0x63)
        return real()

    monkeypatch.setattr(guest, "windows", windows)
    with scene.claim("Owner X", lambda w: w.class_name == "#32770"):
        pass
    assert scene._claims == []


def test_close_ends_the_window_with_a_clean_check_and_leaves_the_pointer(guest, scene):
    pad = notepad(guest, scene)
    guest.cursor = (10, 10)
    close = Close(pad)
    assert close.claims == () and close.run_time == 0
    scene.play(close)
    scene.wait(0.1)
    assert pad not in scene.props and pad.closing is False
    assert guest.cursor == (10, 10) and guest.named("SetCursorPos") == []


def test_close_with_explicit_none_run_time_uses_the_default(guest, scene):
    pad = notepad(guest, scene)
    assert Close(pad, run_time=None).run_time == 0.0


def test_close_via_a_spot_glides_there_and_sends_no_mouse_button_events(guest, scene):
    pad = notepad(guest, scene)
    close = Close(pad, via=Spot(lambda: (300, 200)))
    assert close.claims == ("pointer",)
    scene.play(close)
    assert guest.cursor == (300, 200)
    assert guest.named("mouse_event") == []
    assert ("PostMessageA", (0x10, WM_CLOSE, 0, 0)) in guest.calls
    assert pad not in scene.props
    scene.wait(0.1)


def test_close_marks_the_window_as_closing_from_the_first_frame(guest, scene):
    pad = notepad(guest, scene)
    marks = []
    close = Close(pad)
    close.begin(scene)
    marks.append(pad.closing)
    guest.close_window(0x10)
    scene.check_tracking()  # a window on its way out is not gone
    close.finish(scene)
    assert marks == [True] and pad.closing is False


def test_a_close_whose_window_stays_times_out_naming_what_appeared(
    guest, scene, monkeypatch
):
    from art98.guest import win32

    monkeypatch.setattr(win32, "CLOSE_TIMEOUT", 0.01)
    pad = notepad(guest, scene)

    def save_prompt(hwnd, message, wparam, lparam):
        guest.add_window(0x77, "#32770", (0, 0, 90, 50), "Notepad save")
        return CallResult(1, 0, [])

    guest.do_PostMessageA = save_prompt
    with pytest.raises(GuestError, match=r"didn't close.*untracked.*Notepad save"):
        scene.play(Close(pad))
    assert pad.closing is False


def test_two_closes_via_the_pointer_in_one_play_are_refused(guest, scene):
    first = notepad(guest, scene)
    guest.add_window(0x20, "Notepad", (92, 88, 692, 499), pid=7001)
    guest.add_window(0x21, "Edit", (96, 130, 688, 495), parent=0x20)
    second = Win(hwnd=0x20)
    scene.add(second)
    with pytest.raises(UsageError, match="pointer"):
        scene.play(Close(first, via=(5, 5)), Close(second, via=(9, 9)))


def test_a_screensaver_close_claims_the_pointer():
    assert Close(Screensaver()).claims == ("pointer",)


def test_scene_remove_ends_a_window_as_close_does(guest, scene):
    pad = notepad(guest, scene)
    scene.remove(pad)
    scene.wait(0.1)
    assert pad not in scene.props
    assert ("PostMessageA", (0x10, WM_CLOSE, 0, 0)) in guest.calls


def test_a_play_that_raises_clears_closing_and_the_pressed_button(guest, scene):
    pad = notepad(guest, scene)

    class Boom(Animation):
        run_time = 0.5

        def update(self, progress):
            raise GuestError("frame failed")

    with pytest.raises(GuestError, match="frame failed"):
        scene.play(Close(pad, via=Spot(lambda: (300, 200))), Boom())
    assert pad.closing is False and pad in scene.props


def test_close_of_a_prop_not_on_stage_raises_without_starting_it(guest, scene):
    pad = Notepad()
    for close in (Close(pad), Close(pad, via=(5, 5))):
        with pytest.raises(UsageError, match="not on stage"):
            scene.play(close)
    with pytest.raises(UsageError, match="not on stage"):
        scene.remove(pad)
    assert pad.scene is None and guest.named("spawn") == []


def test_close_of_a_prop_that_is_not_a_window_raises_usage_error(guest, scene):
    with pytest.raises(UsageError, match="needs a window"):
        scene.remove(scene.pointer)


def test_a_second_prop_on_a_window_another_prop_owns_is_refused(guest, scene):
    pad = notepad(guest, scene)
    with pytest.raises(UsageError, match="one prop per window"):
        scene.add(Win(hwnd=pad.hwnd))
    assert pad in scene.props


def test_add_takes_an_id_for_one_prop_and_prop_finds_it(guest, scene):
    pad = notepad(guest, scene)
    scene.add(pad, id="pad")
    assert scene.prop("pad") is pad and pad.state_id == "pad"
    with pytest.raises(UsageError, match="exactly one"):
        scene.add(Notepad(), Notepad(), id="two")
    with pytest.raises(NotFound, match="'nope'.*pad"):
        scene.prop("nope")


# ---- pointer ----


def test_pointer_follows_real_position_at_begin(guest, scene):
    guest.cursor = (10, 10)
    glide = Glide((20, 10), run_time=0.1, rate_func=linear)
    scene.play(glide)
    assert glide.start == (10, 10)
    assert [args for _, args in guest.named("SetCursorPos")][-1] == (20, 10)


def test_attach_sends_one_set_cursor_pos_to_the_read_position(guest, scene):
    guest.cursor = (33, 44)
    Pointer().attach(scene)
    assert guest.named("SetCursorPos") == [("SetCursorPos", (33, 44))]


def test_pointer_animate_goes_through_the_frame_loop(guest, scene):
    scene.play(scene.pointer.animate.shift(10 * RIGHT), run_time=0.1, rate_func=linear)
    assert guest.cursor == (410, 300)


def events(guest):
    return [
        (name, args[0] if name == "mouse_event" else args)
        for name, args in guest.named("SetCursorPos", "mouse_event")
    ]


def test_click_arrives_then_presses_then_releases(guest, scene):
    scene.play(Click((500, 400)))
    log = events(guest)
    press = log.index(("mouse_event", LDOWN))
    release = log.index(("mouse_event", LUP))
    assert press < release
    assert log[press - 1] == ("SetCursorPos", (500, 400))
    assert guest.cursor == (500, 400)
    assert scene.recorder.count == round(Click.run_time * 30)


def test_press_and_release_land_on_different_frames(guest, scene):
    scene.play(Click((500, 400)))
    press = guest.calls.index(("mouse_event", (LDOWN, 0, 0, 0, 0)))
    release = guest.calls.index(("mouse_event", (LUP, 0, 0, 0, 0)))
    assert any(press < index <= release for _, index, _ in scene.recorder.frames)


def test_right_click_uses_the_right_button(guest, scene):
    scene.play(RightClick((1, 2)))
    assert [e for e in events(guest) if e[0] == "mouse_event"] == [
        ("mouse_event", RDOWN),
        ("mouse_event", RUP),
    ]


def test_double_click_is_two_clicks_inside_one_stretch(guest, scene):
    scene.play(DoubleClick((1, 2)))
    assert [e[1] for e in events(guest) if e[0] == "mouse_event"] == [
        LDOWN,
        LUP,
        LDOWN,
        LUP,
    ]
    held = [
        i
        for i, (_, index, _) in enumerate(scene.recorder.frames)
        if index >= guest.calls.index(("mouse_event", (LDOWN, 0, 0, 0, 0)))
    ]
    last = (
        len(guest.calls)
        - 1
        - guest.calls[::-1].index(("mouse_event", (LUP, 0, 0, 0, 0)))
    )
    span = [i for i in held if scene.recorder.frames[i][1] <= last]
    assert len(span) <= 5  # under 170 ms of video, well inside 500 ms


def test_drag_presses_at_the_source_and_releases_at_the_goal(guest, scene):
    scene.play(Drag((100, 100), (300, 200), run_time=1))
    log = events(guest)
    press, release = log.index(("mouse_event", LDOWN)), log.index(("mouse_event", LUP))
    assert log[press - 1] == ("SetCursorPos", (100, 100))
    assert log[release - 1] == ("SetCursorPos", (300, 200))
    assert release - press > 5


def test_drag_by_an_offset(guest, scene):
    scene.play(Drag((100, 100), by=(10, 20), run_time=0.5))
    assert guest.cursor == (110, 120)


def test_drag_needs_one_destination():
    with pytest.raises(ValueError):
        Drag((0, 0))


def test_drag_reads_windows_back_when_it_ends(guest, scene):
    pad = notepad(guest, scene)

    def moved(*args):
        guest.rects[0x10] = (5, 5, 605, 416)
        return CallResult(1, 0, [])

    guest.do_mouse_event = moved
    scene.play(Drag(pad.title_bar, by=(1, 1), run_time=0.5))
    assert pad.rect == (5, 5, 605, 416)


def test_stroke_waits_for_the_guest_on_every_step(guest, scene):
    path = [(100, 100), (200, 100)]
    before = guest.syncs
    scene.play(Stroke(path, run_time=1, steps_per_frame=3))
    assert guest.syncs - before >= 3 * 15
    log = events(guest)
    press, release = log.index(("mouse_event", LDOWN)), log.index(("mouse_event", LUP))
    assert log[press - 1] == ("SetCursorPos", (100, 100))
    assert log[release - 1] == ("SetCursorPos", (200, 100))


def test_stroke_takes_a_function_as_its_path(guest, scene):
    scene.play(Stroke(lambda t: (t * 100, 50), run_time=0.8))
    assert guest.cursor == (100, 50)


def test_hover_records_in_real_time(guest, scene):
    hover = Hover((10, 10), hold=0.2, travel_time=0.1)
    assert hover.live and hover.run_time == pytest.approx(0.3)
    scene.play(hover)
    assert guest.cursor == (10, 10)


def test_hover_refuses_run_time_and_takes_no_time_without_a_division_error():
    with pytest.raises(UsageError, match="travel_time"):
        Hover((1, 2), run_time=3)
    assert Hover((1, 2), hold=0, travel_time=0).run_time == 0


@pytest.mark.parametrize(
    "make",
    [
        lambda: Click((1, 2), button="rigth"),
        lambda: Drag((1, 2), (3, 4), button="rigth"),
        lambda: Stroke([(1, 2), (3, 4)], button="rigth"),
    ],
)
def test_a_misspelled_mouse_button_is_refused_when_the_action_is_built(make):
    with pytest.raises(UsageError, match="rigth"):
        make()


@pytest.mark.parametrize("run_time", [0.75, 5.0])
def test_a_double_click_keeps_its_presses_0_09_seconds_apart(run_time):
    double = DoubleClick((1, 2), run_time=run_time)
    presses = [at for at, event in double.schedule() if event == double._press]
    assert (presses[1] - presses[0]) * run_time == pytest.approx(0.09)


def test_a_click_holds_the_button_for_the_same_time_at_any_run_time():
    click = Click((1, 2), run_time=5.0)
    (press_at, _), (release_at, _) = click.schedule()
    assert (release_at - press_at) * 5.0 == pytest.approx(0.065)


def test_a_stroke_needs_at_least_one_step_per_frame():
    with pytest.raises(UsageError, match="steps_per_frame"):
        Stroke([(1, 2), (3, 4)], steps_per_frame=0)


def test_a_path_with_a_spot_is_located_when_the_animation_begins():
    where = [(10, 10)]
    path = path_function([Spot(lambda: where[0]), (50, 10)])
    where[0] = (30, 10)  # the window moved after the path was made
    point = path(0)
    assert (point[0], point[1]) == (30, 10)


def menu_guest(guest):
    labels = {
        (0x50, 0): "&File",
        (0x50, 1): "&Help",
        (0x51, 0): "&New\tCtrl+N",
        (0x51, 1): "E&xit",
    }
    guest.do_GetMenu = lambda hwnd: CallResult(0x50, 0, [])
    guest.do_GetMenuItemCount = lambda menu: CallResult(2, 0, [])
    guest.do_GetSubMenu = lambda menu, position: CallResult(0x51, 0, [])

    def text(menu, position, out, size, flags):
        label = labels[(menu, position)].encode()
        return CallResult(len(label), 0, [label + b"\0"])

    def rect(hwnd, menu, position, out):
        top = 40 if menu == 0x50 else 60 + 20 * position
        return CallResult(1, 0, [struct.pack("<iiii", 10, top, 50, top + 20)])

    guest.do_GetMenuStringA = text
    guest.do_GetMenuItemRect = rect


def test_menu_clicks_each_label_when_its_turn_comes(guest, scene):
    pad = notepad(guest, scene)
    menu_guest(guest)
    scene.play(Menu(pad, "File", "Exit"))
    assert guest.cursor == (30, 90)
    assert len(guest.named("mouse_event")) == 4


def test_menu_reports_a_missing_label(guest, scene):
    pad = notepad(guest, scene)
    menu_guest(guest)
    with pytest.raises(LookupError, match="Paste"):
        scene.play(Menu(pad, "Paste"))


def test_a_window_with_no_menu_or_a_label_with_no_submenu_is_not_found(guest, scene):
    pad = notepad(guest, scene)
    menu_guest(guest)
    guest.do_GetMenu = lambda hwnd: CallResult(0, 0, [])
    with pytest.raises(NotFound, match="has no menu"):
        scene.play(Menu(pad, "File", "Exit"))
    menu_guest(guest)
    guest.do_GetSubMenu = lambda menu, position: CallResult(0, 0, [])
    with pytest.raises(NotFound, match="has no submenu"):
        scene.play(Menu(pad, "File", "Exit"))


# ---- keyboard ----


def test_typing_sends_each_letter_to_the_edit_control(guest, scene):
    pad = notepad(guest, scene)
    scene.play(TypeWithCursor(pad, "a\nb"))
    assert guest.named("SendMessageA") == [
        ("SendMessageA", (0x11, WM_CHAR, code, 1)) for code in (97, 13, 98)
    ]
    assert scene.recorder.count == 9


def test_typing_invalidates_the_edit_so_the_frame_shows_the_text(guest, scene):
    pad = notepad(guest, scene)
    scene.play(TypeWithCursor(pad, "ab", run_time=0.2))
    redraws = guest.named("RedrawWindow")
    assert redraws and all(args == (0x11, 0, 0, 0x585) for _, args in redraws)
    calls = [
        name for name, _ in guest.calls if name in ("SendMessageA", "RedrawWindow")
    ]
    assert calls[-1] == "RedrawWindow" and calls[0] == "SendMessageA"


def test_typing_spreads_letters_over_the_frames(guest, scene):
    pad = notepad(guest, scene)
    scene.play(TypeWithCursor(pad, "abcdef", run_time=0.2))
    assert [hold for hold, _, _ in scene.recorder.frames] == [1] * 6
    indices = [index for _, index, _ in scene.recorder.frames]
    assert indices == sorted(set(indices))


def test_untype_sends_backspaces(guest, scene):
    pad = notepad(guest, scene)
    scene.play(UntypeWithCursor(pad, 2))
    assert [args[2] for _, args in guest.named("SendMessageA")] == [8, 8]


def test_key_names_become_qemu_names():
    assert key_chord("ctrl+s") == ("ctrl", "s")
    assert key_chord("Alt+F4") == ("alt", "f4")
    assert key_chord("enter") == ("ret",)
    assert key_chord("win") == ("meta_l",)


def test_a_key_chord_with_an_unknown_or_empty_name_is_refused():
    with pytest.raises(UsageError, match="'sx'"):
        key_chord("ctrl+sx")
    with pytest.raises(UsageError, match="no key called ''"):
        key_chord("ctrl++")


@pytest.mark.parametrize(
    "char, chord",
    [
        ("a", ("a",)),
        ("A", ("shift", "a")),
        ("7", ("7",)),
        ("&", ("shift", "7")),
        (" ", ("spc",)),
        ("\n", ("ret",)),
        (".", ("dot",)),
        ("?", ("shift", "slash")),
        ("|", ("shift", "backslash")),
        ("\\", ("backslash",)),
    ],
)
def test_characters_become_keys(char, chord):
    assert char_chord(char) == chord


def test_a_character_with_no_key_is_refused():
    with pytest.raises(ValueError):
        char_chord("é")


def test_typing_takes_windows_line_ends_and_refuses_what_cp1252_cannot_hold(
    guest, scene
):
    pad = notepad(guest, scene)
    assert TypeWithCursor(pad, "a\r\nb").items == b"a\rb"
    with pytest.raises(UsageError, match="日本"):
        TypeWithCursor(pad, "日本")


def test_untyping_needs_at_least_one_letter(guest, scene):
    pad = notepad(guest, scene)
    with pytest.raises(UsageError, match="count is 0"):
        UntypeWithCursor(pad, 0)


def test_keys_press_in_order_on_the_real_keyboard(scene):
    scene.play(Keys("ctrl+a", "delete"))
    assert scene.vm.keys == [("ctrl", "a"), ("delete",)]
    assert scene.recorder.count == 15


def test_type_keys_presses_every_character(scene):
    scene.play(TypeKeys("Hi\n"))
    assert scene.vm.keys == [("shift", "h"), ("i",), ("ret",)]


# ---- programs ----


def paint(guest, scene, left=20, top=10):
    def at(rect):
        return tuple(v + (left if i % 2 == 0 else top) for i, v in enumerate(rect))

    guest.add_window(
        0x40, "MSPaintApp", at((0, 0, 580, 510)), "untitled - Paint", pid=7000
    )
    guest.add_window(0x41, "Afx:1000000:8", at((63, 44, 574, 432)), parent=0x40)
    guest.add_window(0x42, "AfxWnd42", at((2, 432, 261, 483)), "Colors", parent=0x40)
    for number in Paint.TOOLS.values():
        offset = 42 + (number % 16) * 25
        guest.add_window(
            number, "ToolChild", at((8, offset, 33, offset + 25)), parent=0x40
        )
    prop = Paint()
    scene.add(prop)
    guest.calls.clear()
    return prop


def test_paint_tools_come_from_control_ids(guest, scene):
    prop = paint(guest, scene)
    number = Paint.TOOLS["brush"]
    left, top, right, bottom = guest.rects[number]
    assert prop.tool("brush").point() == ((left + right) // 2, (top + bottom) // 2)


def test_paint_targets_follow_the_window(guest, scene):
    prop = paint(guest, scene)
    tool, swatch, pixel = prop.tool("fill"), prop.color("red"), prop.canvas(5, 5)
    before = tool.point(), swatch.point(), pixel.point()
    for hwnd, (left, top, right, bottom) in list(guest.rects.items()):
        guest.rects[hwnd] = (left + 100, top + 50, right + 100, bottom + 50)
    after = tool.point(), swatch.point(), pixel.point()
    assert [a - b for a, b in zip(after, before)] == [(100, 50)] * 3


def test_paint_palette_positions(guest, scene):
    prop = paint(guest, scene)
    assert prop.color("black").point() == (22 + 40, 442 + 16)
    assert prop.color("navy").point() == (22 + 40 + 6 * 16, 442 + 16)
    assert prop.color("red").point() == (22 + 40 + 2 * 16, 442 + 32)


def test_paint_refuses_unknown_names(guest, scene):
    prop = paint(guest, scene)
    with pytest.raises(ValueError):
        prop.tool("spray")
    with pytest.raises(ValueError):
        prop.color("mauve")


def test_paint_measures_the_canvas_between_white_and_grey(guest, scene):
    prop = paint(guest, scene)
    x0, y0 = prop.canvas(0, 0).point()

    def pixel(dc, x, y):
        return CallResult(
            0xFFFFFF if x < x0 + 400 and y < y0 + 300 else 0x808080, 0, []
        )

    guest.do_GetPixel = pixel
    assert prop.canvas_size == (400, 300)


def test_resizing_the_canvas_drags_the_handle_and_remembers(guest, scene):
    prop = paint(guest, scene)
    prop.canvas_size = (400, 300)
    origin = prop.canvas(0, 0).point()
    scene.play(prop.resize_canvas(500, 350, run_time=0.5))
    log = events(guest)
    press = log.index(("mouse_event", LDOWN))
    assert log[press - 1] == ("SetCursorPos", (origin + (401, 300)).rounded())
    assert guest.cursor == (origin + (501, 350)).rounded()
    assert prop.canvas_size == (500, 350)


def sweeper(guest, scene):
    guest.add_window(0x30, "Minesweeper", (100, 100, 270, 300), pid=7000)
    board = Minesweeper()
    scene.add(board)
    guest.calls.clear()
    return board


def test_minesweeper_reads_board_size_from_the_client_area(guest, scene):
    board = sweeper(guest, scene)
    assert board.board_size == (8, 8)
    assert board.cell(0, 0).point() == (100 + 3 + 12 + 8, 100 + 41 + 55 + 8)


def test_minesweeper_flood_fill_stops_at_numbers(guest, scene):
    board = sweeper(guest, scene)
    board.mines = {(0, 0)}
    assert board.opened_by((1, 1)) == {(1, 1)}
    assert len(board.opened_by((7, 7))) == 63


def test_minesweeper_clear_never_opens_a_mine(guest, scene):
    board = sweeper(guest, scene)
    board.mines = {(0, 0), (7, 7), (3, 4)}
    opened = []

    def press(flags, *args):
        if flags == LDOWN:
            opened.append(guest.cursor)
        return CallResult(1, 0, [])

    guest.do_mouse_event = press
    board.clear()
    bad = {board.cell(*mine).point().rounded() for mine in board.mines}
    assert not bad & set(opened)
    assert len(guest.named("mouse_event")) >= 2 * len(board.mines)


def won_on_the_first_click(guest, scene):
    """A board with one mine: the first click opens the other 63 cells, and wins."""
    board = sweeper(guest, scene)
    board.mines = frozenset({(0, 0)})

    def press(flags, *args):
        if flags == LDOWN:
            prompt_of(guest)  # the best-time prompt comes up with the winning click
        return CallResult(1, 0, [])

    guest.do_mouse_event = press
    return board


def test_a_prompt_that_comes_up_during_clears_winning_click_is_claimed(guest, scene):
    board = won_on_the_first_click(guest, scene)
    board.clear()  # the flags and the check after the play run with the prompt up
    owners = [c.owner for c in scene._claims]
    assert owners == ["Minesweeper's best-time prompt and table"]


def test_sign_scoreboard_after_clear_releases_the_prompt_claim(guest, scene):
    board = won_on_the_first_click(guest, scene)
    board.clear()
    typed = scene.vm.send_keys

    def answer_prompt(*codes, hold_ms=80):
        typed(*codes, hold_ms=hold_ms)
        guest.close_window(0x60)

    scene.vm.send_keys = answer_prompt
    board.sign_scoreboard()
    assert scene._claims == [] and board._prompt is None


def test_a_won_game_never_signed_raises_at_the_end_of_run_naming_sign_scoreboard(
    guest, scene
):
    board = won_on_the_first_click(guest, scene)
    board.clear()
    with pytest.raises(scene_module.UntrackedWindow, match=r"call sign_scoreboard\(\)"):
        scene._finish()
    assert scene._claims == []


def test_flagging_leaves_no_menu_claims(guest, scene):
    scene.play(RightClick((640, 300), menu=False))
    assert scene._claims == []
    board = sweeper(guest, scene)
    board.mines = frozenset({(0, 0), (7, 7)})
    board.clear()
    assert not [c for c in scene._claims if "RightClick" in c.owner]


def test_the_untracked_window_message_lists_each_claim_owner_once(guest, scene):
    guest.add_window(0x63, "Stray", (0, 0, 5, 5), "Stray")
    for _ in range(3):
        scene.claim("Owner A", lambda w: w.class_name == "Nothing")
    scene.claim("Owner B", lambda w: w.class_name == "Nothing")
    with pytest.raises(scene_module.UntrackedWindow) as caught:
        scene.check_tracking()
    assert str(caught.value).endswith("Claimed now: Owner A, Owner B.")


def test_screensaver_needs_a_real_name():
    assert '"C:\\WINDOWS\\SYSTEM\\3D Pipes.scr" /s' == Screensaver("3D Pipes").command
    assert "Scrolling Marquee" in Screensaver("Scrolling Marquee").command
    with pytest.raises(ValueError):
        Screensaver("Starfield")


def test_screensaver_stops_by_moving_the_pointer(guest, scene):
    guest.add_window(0x60, "WindowsScreenSaverClass", (0, 0, 800, 600), pid=7000)
    saver = Screensaver("Mystify Your Mind")
    scene.add(saver)
    alive = iter([1, 0])
    guest.do_IsWindow = lambda hwnd: CallResult(next(alive), 0, [])
    saver.stop()
    assert guest.named("SetCursorPos")[0][1] == (
        440,
        340,
    )  # one step towards the middle
    assert guest.cursor == (400, 300)  # then back where it started


def test_dialog_opens_on_a_guest_thread_and_reports_its_answer(guest, scene):
    class Call:
        def wait(self):
            return CallResult(6, 0, [])

    seen = []

    def acall(dll, function, *args):
        seen.append((dll, function, args))
        guest.add_window(0x70, "#32770", (10, 10, 200, 100), "Quit?")
        guest.add_window(0x71, "Button", (20, 60, 90, 90), "&Yes", parent=0x70)
        return Call()

    guest.acall = acall
    box = Dialog("Really?", "Quit?", icon="question", buttons="yesno")
    scene.add(box)
    assert seen == [("user32", "MessageBoxA", (0, "Really?", "Quit?", 0x24))]
    assert box.button("Yes").point() == (55, 75)
    assert box.answer == "yes"


# ---- rendering ----


def test_private_stage_copies_and_cleans_up(tmp_path):
    (tmp_path / "golden.qcow2").write_bytes(b"disk")
    (tmp_path / "image.json").write_text('{"disk": "%s"}' % (tmp_path / "golden.qcow2"))
    with session_module.private_stage(tmp_path) as stage:
        assert (stage / "golden.qcow2").read_bytes() == b"disk"
        assert str(stage) in (stage / "image.json").read_text()
        (stage / "golden.qcow2").write_bytes(b"dirty")
    assert (tmp_path / "golden.qcow2").read_bytes() == b"disk"
    assert not stage.exists()


@needs_ffmpeg
def test_render_turns_a_class_into_a_scene_and_routes_a_gif(
    tmp_path, monkeypatch, guest
):
    from art98.anim import renderer as render_module

    class Tiny(Scene):
        def construct(self):
            self.pause(0.1)

    class Recorder(FakeVideo):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

    class Booted(FakeSession):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

        def record(self, path, output_fps, lossless=False, defer=False):
            options.update(path=path, output_fps=output_fps, lossless=lossless)
            recorder = Recorder(guest)
            recorder.clips = recorder.parts = [path]
            return recorder

    options, gifs = {}, []
    monkeypatch.setattr(
        render_module,
        "write_gif",
        lambda *a, **k: (gifs.append(a), (tmp_path / "out.part.gif").write_bytes(b"")),
    )
    written = render_module.render(Tiny, tmp_path / "out.gif", session=Booted(guest))
    assert written == tmp_path / "out.gif"
    assert options["lossless"] is True and gifs[0][1] == tmp_path / "out.gif"


def test_cli_scene_named_like_a_stdlib_module_finds_its_own_file(tmp_path):
    from art98.cli import _load_scene

    file = tmp_path / "typing.py"
    file.write_text("from art98.anim import *\nclass T(Scene):\n    pass\n")
    (tmp_path / "x.json").write_text("{}")
    scene = _load_scene(file, None)
    assert Path(inspect.getfile(scene)) == file
    assert scene()._find_state(Path("x.json")) == tmp_path / "x.json"
    import typing

    assert typing.__file__ != str(file)  # stdlib untouched


def test_cli_finds_the_scene_in_a_file(tmp_path):
    from art98.cli import _load_scene

    file = tmp_path / "one_scene.py"
    file.write_text("from art98.anim import *\nclass Only(Scene):\n    pass\n")
    assert _load_scene(file, None).__name__ == "Only"
    file = tmp_path / "two_scenes.py"
    file.write_text(
        "from art98.anim import *\nclass A(Scene):\n    pass\n"
        "class B(Scene):\n    pass\n"
    )
    assert _load_scene(file, "B").__name__ == "B"
    with pytest.raises(SystemExit, match="A, B"):
        _load_scene(file, None)


def test_star_import_gives_the_scene_api():
    namespace = {}
    exec("from art98.anim import *", namespace)  # noqa: S102
    for name in ("Scene", "Click", "Picture", "RIGHT", "smooth", "Teleport", "Stroke"):
        assert name in namespace
    # Every program is an action class, and the star import gives each one.
    for name in ("Dialog", "Minesweeper", "Notepad", "Paint", "Screensaver"):
        assert namespace[name] is getattr(programs, name)
        assert name in anim.__all__
    assert importlib.util.find_spec("art98.anim.apps") is None
    assert set(anim.__all__) <= set(dir(anim))


# ---- sections and no revert after boot ----


def three_sections(guest, tmp_path, monkeypatch, calls):
    """A scene of three sections around one Picture (id flower); `calls` says what ran."""
    from test_state import bmp

    monkeypatch.setattr(guestfiles, "viewer", lambda: b"MZ view")
    (tmp_path / "flower.bmp").write_bytes(bmp(4, 3))
    guest.add_window(0x30, "Art98View", (60, 60, 360, 280), "Flower", pid=7000)

    class Three(Scene):
        def setup(self):
            calls.append("setup")
            picture = Picture(
                "Flower", image=tmp_path / "flower.bmp", at=(60, 60), size=(300, 220)
            )
            self.add(picture, id="flower")

        def construct(self):
            self.section("one", self.one)
            self.section("two", self.two)
            self.section("three", self.three)

        def one(self):
            calls.append("one")
            self.pause(1)

        def two(self):
            calls.append("two")
            self.pause(2)

        def three(self):
            calls.append(("three", self.time, self.prop("flower").state_id))
            self.pause(1)

        def tear_down(self):
            calls.append("tear_down")

    return Three


def run_sections(scene_class, caps, guest, only=None):
    scene = scene_class()
    scene.only_section, scene.captures = only, caps
    session, video = FakeSession(guest), FakeVideo(guest)
    scene.run(session, video)
    return scene, session, video


def full_run(guest, tmp_path, monkeypatch, calls):
    """A full run, its captures swapped in as render does."""
    from art98.anim import renderer as render_module

    caps = tmp_path / "caps"
    scene_class = three_sections(guest, tmp_path, monkeypatch, calls)
    scene, _, video = run_sections(scene_class, caps, guest)
    render_module.swap_captures(caps)
    return scene_class, scene, video, caps


def test_a_full_run_cuts_and_captures_at_each_later_boundary(
    guest, tmp_path, monkeypatch
):
    calls = []
    _, scene, video, caps = full_run(guest, tmp_path, monkeypatch, calls)
    assert calls == ["setup", "one", "two", ("three", 3.0, "flower"), "tear_down"]
    assert scene.sections == [("one", 0.0), ("two", 1.0), ("three", 3.0)]
    assert [cut for cut, _ in video.cuts] == [30, 90]
    names = sorted(p.name for p in caps.iterdir())
    assert names == [
        "02-two.meta.json",
        "02-two.state.files",
        "02-two.state.json",
        "03-three.meta.json",
        "03-three.state.files",
        "03-three.state.json",
    ]
    meta = json.loads((caps / "03-three.meta.json").read_text())
    assert meta["time"] == 3.0
    assert sorted(meta["hashes"]) == ["section one", "section two", "setup", "state"]
    assert load_state(caps / "03-three.state.json").window("flower")
    assert not (tmp_path / "caps.part").exists()


def test_a_solo_run_of_a_later_section_calls_only_its_method(
    guest, tmp_path, monkeypatch
):
    calls = []
    scene_class, full, _, caps = full_run(guest, tmp_path, monkeypatch, calls)
    calls.clear()
    scene, _, video = run_sections(scene_class, caps, guest, only="three")
    # no setup, no earlier method; tear_down still runs; time starts where the full run's did
    assert calls == [("three", 3.0, "flower"), "tear_down"]
    assert scene.sections == [("three", 3.0)] == full.sections[2:]
    assert scene.time == 3.0 + 30 / 30
    assert video.cuts == [] and video.count == 30


def test_a_solo_run_of_a_middle_section_never_calls_the_others(
    guest, tmp_path, monkeypatch
):
    calls = []
    scene_class, _, _, caps = full_run(guest, tmp_path, monkeypatch, calls)
    calls.clear()
    scene, _, video = run_sections(scene_class, caps, guest, only="two")
    assert calls == ["two", "tear_down"]
    assert video.count == 60 and scene.sections == [("two", 1.0)]


def test_a_solo_run_of_the_first_section_is_a_full_start_that_stops_after_it(
    guest, tmp_path, monkeypatch
):
    calls = []
    scene_class = three_sections(guest, tmp_path, monkeypatch, calls)
    scene, _, video = run_sections(scene_class, tmp_path / "none", guest, only="one")
    assert calls == ["setup", "one", "tear_down"]
    assert video.count == 30 and not (tmp_path / "none").exists()
    assert scene.sections == [("one", 0.0)]


@pytest.mark.parametrize(
    ("key", "value", "changed"),
    [
        ("section one", "0" * 64, "one()"),
        ("section two", "0" * 64, "two()"),
        ("setup", "0" * 64, "setup()"),
        ("state", "0" * 64, "the state file"),
        ("section gone", "0" * 64, "section 'gone'"),
    ],
)
def test_a_capture_made_before_a_method_changed_is_refused_naming_it(
    guest, tmp_path, monkeypatch, key, value, changed
):
    calls = []
    scene_class, _, _, caps = full_run(guest, tmp_path, monkeypatch, calls)
    calls.clear()
    meta_path = caps / "03-three.meta.json"
    meta = json.loads(meta_path.read_text())
    meta["hashes"][key] = value
    meta_path.write_text(json.dumps(meta))
    with pytest.raises(
        UsageError, match=rf"'three'.*before {re.escape(changed)} changed"
    ):
        run_sections(scene_class, caps, guest, only="three")
    assert calls == []


def test_a_section_unknown_to_the_scene_lists_the_names_it_has(
    guest, tmp_path, monkeypatch
):
    calls = []
    scene_class, _, _, caps = full_run(guest, tmp_path, monkeypatch, calls)
    calls.clear()
    with pytest.raises(scene_module.SectionNotFound, match="'nope'.*one, two, three"):
        run_sections(scene_class, caps, guest, only="nope")
    assert calls == []


def test_a_later_section_with_no_capture_says_to_render_the_whole_scene_first(
    guest, tmp_path, monkeypatch
):
    calls = []
    scene_class, _, _, caps = full_run(guest, tmp_path, monkeypatch, calls)
    (caps / "03-three.state.json").unlink()
    with pytest.raises(MissingFile, match="render the whole scene once first"):
        run_sections(scene_class, caps, guest, only="three")
    with pytest.raises(MissingFile, match="render the whole scene once first"):
        run_sections(scene_class, tmp_path / "nowhere", guest, only="two")


def test_a_solo_run_ignores_leftovers_beside_the_captures(guest, tmp_path, monkeypatch):
    calls = []
    scene_class, _, _, caps = full_run(guest, tmp_path, monkeypatch, calls)
    (caps / ".03-three.state.json.part").mkdir()
    (caps / "03-three.state.json.bak").write_text("x")
    calls.clear()
    run_sections(scene_class, caps, guest, only="three")
    assert calls[0][0] == "three"


def test_an_attribute_an_earlier_section_set_is_missing_in_a_solo_run(
    guest, tmp_path, monkeypatch
):
    scene_class = three_sections(guest, tmp_path, monkeypatch, [])

    class Sloppy(scene_class):
        def one(self):
            self.flower = self.prop("flower")

        def three(self):
            self.flower.hwnd  # noqa: B018

    caps = tmp_path / "caps"
    run_sections(Sloppy, caps, guest)
    from art98.anim import renderer as render_module

    render_module.swap_captures(caps)
    with pytest.raises(AttributeError, match="flower"):
        run_sections(Sloppy, caps, guest, only="three")


@pytest.mark.parametrize(
    "work", ["pause", "play", "add", "get_state", "set_state", "pointer"]
)
def test_work_before_any_section_in_a_solo_run_is_a_clean_error(guest, tmp_path, work):
    class Early(Scene):
        def construct(self):
            if work == "pause":
                self.pause(1)
            elif work == "play":
                self.play(Wait(0.1))
            elif work == "add":
                self.add(Win(hwnd=0x40))
            elif work == "get_state":
                self.get_state(tmp_path / "s.json")
            elif work == "set_state":
                self.set_state(tmp_path / "s.json")
            elif work == "pointer":
                self.pointer.place((10, 10))
            self.section("x", lambda: None)

    with pytest.raises(scene_module.SectionNotFound, match=r"'x'.*self\.section\("):
        run_sections(Early, tmp_path / "caps", guest, only="x")


def test_code_between_section_calls_is_refused_in_a_full_run(
    guest, tmp_path, monkeypatch
):
    scene_class = three_sections(guest, tmp_path, monkeypatch, [])

    class Between(scene_class):
        def construct(self):
            self.section("one", self.one)
            self.pause(1)
            self.section("two", self.two)

    with pytest.raises(UsageError, match=r"code between section\(\) calls"):
        run_sections(Between, tmp_path / "caps", guest)

    guest.add_window(0x41, "Other", (0, 0, 300, 300), "Other", pid=7000)

    class After(scene_class):  # after the last section: nothing later would catch it
        def construct(self):
            self.section("one", self.one)
            self.add(Win(hwnd=0x41))

    with pytest.raises(UsageError, match=r"code between section\(\) calls"):
        run_sections(After, tmp_path / "caps", guest)


def test_a_capture_the_state_cant_hold_stops_the_full_run_with_nothing_swapped_in(
    guest, tmp_path, monkeypatch
):
    scene_class = three_sections(guest, tmp_path, monkeypatch, [])
    guest.add_window(0x40, "Other", (0, 0, 300, 300), "Other", pid=7000)

    class Holding(scene_class):
        def one(self):
            self.add(Win(hwnd=0x40), id="other")

    with pytest.raises(UsageError, match="Win can't be captured yet"):
        run_sections(Holding, tmp_path / "caps", guest)
    assert not (tmp_path / "caps").exists()


@pytest.mark.parametrize("name", ["", "  ", None, 3, "a b", "../x"])
def test_a_section_needs_a_plain_name(scene, tmp_path, name):
    scene.captures = tmp_path / "caps"
    with pytest.raises(UsageError, match="section name"):
        scene.section(name, lambda: None)
    assert scene.recorder.cuts == []


def test_a_section_needs_a_callable_a_unique_name_and_a_scene_file(scene, tmp_path):
    scene.captures = tmp_path / "caps"
    with pytest.raises(UsageError, match="needs a method"):
        scene.section("a", None)
    scene.section("a", lambda: None)
    with pytest.raises(UsageError, match="two sections are called 'a'"):
        scene.section("a", lambda: None)
    scene.captures = None
    with pytest.raises(UsageError, match="needs to live in a file"):
        scene.section("b", lambda: None)


def test_a_scene_with_no_sections_is_unchanged_by_only_section_being_unset(scene):
    assert scene.only_section is None and scene.sections == []
    assert scene.time == 0.0


def test_time_counts_from_the_offset_a_solo_run_starts_at(scene):
    scene._time_offset = 2.5
    scene.recorder.count = 45
    assert scene.time == 4.0


def test_a_render_with_sections_defaults_the_solo_output_and_keeps_one_clip(
    guest, tmp_path, monkeypatch
):
    from art98.anim import renderer as render_module

    caps = tmp_path / "caps"
    monkeypatch.setattr(render_module, "captures_folder", lambda scene: caps)
    monkeypatch.setattr(render_module, "require_ffmpeg", lambda: None)
    monkeypatch.chdir(tmp_path)
    calls = []
    scene_class = three_sections(guest, tmp_path, monkeypatch, calls)
    session = FakeSession(guest)
    assert scene_class().render(session=session) == Path("Three.mp4")
    assert len(list(caps.iterdir())) == 6
    calls.clear()
    written = scene_class().render(section="three", session=session)
    assert written == Path("Three-three.mp4")
    assert session.videos[-1].clips == [written] and session.videos[-1].cuts == []
    assert calls[0][0] == "three"
    assert len(list(caps.iterdir())) == 6  # a solo run writes no captures


def test_a_render_that_fails_leaves_the_earlier_captures_alone(
    guest, tmp_path, monkeypatch
):
    from art98.anim import renderer as render_module

    caps = tmp_path / "caps"
    monkeypatch.setattr(render_module, "captures_folder", lambda scene: caps)
    monkeypatch.setattr(render_module, "require_ffmpeg", lambda: None)
    scene_class = three_sections(guest, tmp_path, monkeypatch, [])
    session = FakeSession(guest)
    scene_class().render(tmp_path / "out.mp4", session=session)
    before = snapshot(caps)
    assert before

    class Failing(scene_class):
        def three(self):
            raise KeyError("boom")

    with pytest.raises(KeyError):
        Failing().render(tmp_path / "out.mp4", session=session)
    assert snapshot(caps) == before
    assert not (tmp_path / "caps.part").exists()
    assert not (tmp_path / "caps.old").exists()


def test_a_successful_render_replaces_stale_captures_and_clears_a_crashed_swap(
    guest, tmp_path, monkeypatch
):
    from art98.anim import renderer as render_module

    caps = tmp_path / "caps"
    monkeypatch.setattr(render_module, "captures_folder", lambda scene: caps)
    monkeypatch.setattr(render_module, "require_ffmpeg", lambda: None)
    caps.mkdir()
    (caps / "09-stale.state.json").write_text("{}")
    (tmp_path / "caps.old").mkdir()
    (tmp_path / "caps.part").mkdir()
    (tmp_path / "caps.part" / "junk").write_text("x")
    scene_class = three_sections(guest, tmp_path, monkeypatch, [])
    scene_class().render(tmp_path / "out.mp4", session=FakeSession(guest))
    assert sorted(p.name for p in tmp_path.iterdir() if "caps" in p.name) == ["caps"]
    assert not (caps / "09-stale.state.json").exists()
    assert (caps / "02-two.state.json").exists()


def test_a_render_asking_for_a_section_needs_the_scene_file(guest, monkeypatch):
    from art98.anim import renderer as render_module

    monkeypatch.setattr(render_module, "captures_folder", lambda scene: None)
    monkeypatch.setattr(render_module, "require_ffmpeg", lambda: None)
    with pytest.raises(UsageError, match="needs the scene to live in a file"):
        Stage().render(section="x", session=FakeSession(guest))
    with pytest.raises(UsageError, match="--section"):
        Stage().render(section="../x", session=FakeSession(guest))


def test_captures_live_beside_the_scene_file_and_not_beside_the_output():
    from art98.anim import renderer as render_module

    folder = render_module.captures_folder(Stage())
    assert folder == Path(__file__).resolve().with_name("test_anim.Stage.sections")


def test_a_scene_without_a_state_is_not_reverted(guest):
    seen = []

    class Probing(Stage):
        def setup(self):
            seen.append(session.reverts)

    session = FakeSession(guest)
    Probing().run(session, FakeVideo(guest))
    assert session.reverts == 0 and seen == [0]


def test_a_second_scene_on_one_session_reverts_and_starts_with_no_props(guest):
    session, seen = FakeSession(guest), []

    class Opens(Stage):
        def construct(self):
            self.add(Notepad())

    class Probing(Stage):
        def setup(self):
            seen.append((session.reverts, list(self.props)))

    guest.add_window(0x10, "Notepad", (92, 88, 692, 499), pid=7000)
    guest.add_window(0x11, "Edit", (96, 130, 688, 495), parent=0x10)
    first = Opens()
    first.run(session, FakeVideo(guest))
    assert session.reverts == 0 and first.props and not session.fresh
    probe = Probing()
    probe.props.append(first.props[0])  # a reused scene object's leftovers
    probe.run(session, FakeVideo(guest))
    assert seen == [(1, [])]


def test_a_desktop_start_that_raises_leaves_the_session_not_fresh(guest, monkeypatch):
    session = FakeSession(guest)

    def boom(scene):
        raise RuntimeError("calibrate failed")

    monkeypatch.setattr(Stage, "prepare_desktop", boom)
    with pytest.raises(RuntimeError):
        Stage().run(session, FakeVideo(guest))
    assert not session.fresh


def test_a_state_scene_right_after_attach_reverts_once(guest, monkeypatch, tmp_path):
    from art98.anim import setstate

    monkeypatch.setattr(setstate, "apply_state", lambda scene, state: {})
    monkeypatch.setattr(setstate, "check_state", lambda *a: None)
    (tmp_path / "s.json").write_text('{"version": 1}')
    session = FakeSession(guest)

    class WithState(Stage):
        state = tmp_path / "s.json"

    WithState().run(session, FakeVideo(guest))
    assert session.reverts == 0 and not session.fresh  # attach's revert was the one
    WithState().run(session, FakeVideo(guest))
    assert session.reverts == 1  # the second scene: one revert, not two
    session.fresh = False  # a session attached with revert=False
    WithState().run(session, FakeVideo(guest))
    assert session.reverts == 2


def test_a_set_state_in_the_middle_of_a_scene_still_reverts(
    guest, monkeypatch, tmp_path
):
    from art98.anim import setstate

    monkeypatch.setattr(setstate, "apply_state", lambda scene, state: {})
    monkeypatch.setattr(setstate, "check_state", lambda *a: None)
    (tmp_path / "s.json").write_text('{"version": 1}')
    session = FakeSession(guest)

    class Mid(Stage):
        state = tmp_path / "s.json"

        def construct(self):
            self.set_state(tmp_path / "s.json")

    Mid().run(session, FakeVideo(guest))
    assert session.reverts == 1


def test_a_title_bar_drag_repaints_the_window_only_when_it_moved(guest, scene):
    pad = notepad(guest, scene)
    guest.do_mouse_event = lambda *a: (
        guest.rects.__setitem__(0x10, (10, 10, 610, 421)) or CallResult(1, 0, [])
    )
    scene.play(Drag(pad.title_bar, by=(1, 1), run_time=0.5))
    redraws = [args[0] for _, args in guest.named("RedrawWindow")]
    assert redraws and set(redraws) == {0x10}
    guest.calls.clear()
    scene.play(Drag(pad.title_bar, by=(1, 1), run_time=0.5))  # the window stays put now
    assert guest.named("RedrawWindow") == []


@needs_ffmpeg
def test_render_uses_a_given_session_and_never_closes_it(tmp_path, monkeypatch, guest):
    from art98.anim import renderer as render_module

    class Tiny(Scene):
        def construct(self):
            self.pause(0.1)

    class Recorder(FakeVideo):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

    class Given(FakeSession):
        closed = False

        def __exit__(self, *exc):
            self.closed = True

        def close(self):
            self.closed = True

        def record(self, path, output_fps, lossless=False, defer=False):
            recorder = Recorder(guest)
            recorder.clips = recorder.parts = [path]
            return recorder

    monkeypatch.setattr(
        render_module,
        "write_gif",
        lambda *a, **k: (tmp_path / "out.part.gif").write_bytes(b""),
    )
    session = Given(guest)
    written = Tiny().render(tmp_path / "out.gif", session=session)
    assert written == tmp_path / "out.gif" and not session.closed


def test_a_state_file_missing_everywhere_names_both_places(
    scene, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(MissingFile) as caught:
        scene._find_state(Path("nope.json"))
    message = str(caught.value)
    assert str(Path(__file__).resolve().parent / "nope.json") in message
    assert str(tmp_path / "nope.json") in message


def test_play_overrides_do_not_stick_to_the_animation(scene):
    plain = Probe()  # run_time and rate_func come from the class
    own = Probe(run_time=0.5, rate_func=linear)
    scene.play(plain, own, run_time=2, rate_func=smooth)
    assert scene.time == 2
    assert "run_time" not in vars(plain) or plain.run_time == 1.0
    assert "rate_func" not in vars(plain)
    assert own.run_time == 0.5 and own.rate_func is linear
    scene.play(plain)
    assert scene.time == 3


def test_time_before_run_is_a_usage_error():
    with pytest.raises(UsageError, match="isn't running"):
        _ = Stage().time


# ---- get_state ----


def captured_scene(guest, scene, tmp_path, monkeypatch):
    """A Picture (id flower) in front of a Notepad (id note), as the guest would have them."""
    from test_state import bmp

    monkeypatch.setattr(guestfiles, "viewer", lambda: b"MZ view")
    (tmp_path / "flower.bmp").write_bytes(bmp(4, 3))
    (tmp_path / "note.txt").write_bytes(b"one\ntwo\n")
    guest.add_window(0x30, "Art98View", (60, 60, 360, 280), "Flower", pid=7000)
    guest.add_window(0x10, "Notepad", (92, 88, 692, 499), "note - Notepad", pid=7000)
    guest.add_window(0x11, "Edit", (96, 130, 688, 495), parent=0x10)
    guest.edit_text[0x11] = b"one\r\ntwo\r\n"
    picture = Picture(
        "Flower", image=tmp_path / "flower.bmp", at=(60, 60), size=(300, 220)
    )
    pad = Notepad(open=tmp_path / "note.txt")
    scene.add(picture, id="flower")
    scene.add(pad, id="note")
    return picture, pad


def test_a_captured_scene_loads_and_sets_back_to_the_same_state(
    guest, scene, tmp_path, monkeypatch
):
    captured_scene(guest, scene, tmp_path, monkeypatch)
    first = tmp_path / "a" / "state.json"
    state = scene.get_state(first)
    assert [w.id for w in state.windows] == ["flower", "note"]  # creation order
    assert state.stack == ("note", "flower")  # back to front
    assert state.display == (800, 600, 16) and state.pointer == (400, 300)
    assert state.desktop.fill_colour == (0, 128, 128)
    assert (first.parent / "state.files/windows/flower/flower.bmp").exists()
    scene.set_state(first)
    second = tmp_path / "b" / "state.json"
    scene.get_state(second)
    assert first.read_text() == second.read_text()


def test_capture_writes_windows_in_creation_order_and_stack_in_z_order(
    guest, scene, tmp_path, monkeypatch
):
    # Props are added flower then note; on the guest flower is in front of note,
    # so the back-to-front stack is the reverse of the creation order.
    captured_scene(guest, scene, tmp_path, monkeypatch)
    path = tmp_path / "s.json"
    state = scene.get_state(path)
    assert [w.id for w in state.windows] == ["flower", "note"]
    assert state.stack == ("note", "flower")
    data = json.loads(path.read_text())
    assert [w["id"] for w in data["windows"]] == ["flower", "note"]
    assert data["stack"] == ["note", "flower"]


def test_a_notepad_whose_text_changed_after_opening_writes_text(
    guest, scene, tmp_path, monkeypatch
):
    captured_scene(guest, scene, tmp_path, monkeypatch)
    unchanged = scene.get_state(tmp_path / "s.json")
    assert unchanged.window("note").text is None
    guest.edit_text[0x11] = b"changed\r\nlines"
    state = scene.get_state(tmp_path / "s.json")
    assert state.window("note").open is not None
    assert state.window("note").text.data == b"changed\r\nlines"
    assert (
        tmp_path / "s.files/windows/note/text.txt"
    ).read_bytes() == b"changed\r\nlines"


def test_a_capture_writes_the_notepad_selection(guest, scene, tmp_path, monkeypatch):
    captured_scene(guest, scene, tmp_path, monkeypatch)
    guest.edit_sel[0x11] = (2, 5)
    state = scene.get_state(tmp_path / "s.json")
    assert state.window("note").selection == (2, 5)
    windows = json.loads((tmp_path / "s.json").read_text())["windows"]
    assert next(w for w in windows if w["id"] == "note")["selection"] == [2, 5]


def test_a_state_selection_is_restored_after_the_notepad_text(guest, scene, tmp_path):
    data = b"one\ntwo\n"
    (tmp_path / "note.txt").write_bytes(data)
    state = load_state(
        dump_json(
            tmp_path,
            {
                "version": 1,
                "windows": [
                    {
                        "id": "note",
                        "app": "notepad",
                        "title": "Note",
                        "at": [10, 20],
                        "size": [300, 200],
                        "text": {
                            "file": "note.txt",
                            "sha256": hashlib.sha256(data).hexdigest(),
                        },
                        "selection": [2, 5],
                    }
                ],
            },
        )
    )
    guest.add_window(0x10, "Notepad", (10, 20, 310, 220), "Note", pid=7000)
    guest.add_window(0x11, "Edit", (96, 130, 688, 495), parent=0x10)
    pad = Notepad.from_state(state.window("note"))
    scene.add(pad)
    messages = [a[1] for _, a in guest.named("SendMessageA")]
    assert messages.index(0x000C) < messages.index(win32.EM_SETSEL)  # text, then caret
    assert ("SendMessageA", (0x11, win32.EM_SETSEL, 2, 5)) in guest.calls
    assert guest.edit_sel[0x11] == (2, 5)


def test_a_notepad_state_without_selection_sends_no_em_setsel(guest, scene, tmp_path):
    state = state_with_text(tmp_path)
    guest.add_window(0x10, "Notepad", (10, 20, 310, 220), "Note", pid=7000)
    guest.add_window(0x11, "Edit", (96, 130, 688, 495), parent=0x10)
    pad = Notepad.from_state(state.window("note"))
    assert state.window("note").selection is None
    scene.add(pad)
    assert not [a for _, a in guest.named("SendMessageA") if a[1] == win32.EM_SETSEL]


def test_a_maximized_window_keeps_its_normal_place_in_a_capture(
    guest, scene, tmp_path, monkeypatch
):
    captured_scene(guest, scene, tmp_path, monkeypatch)
    guest.zoomed.add(0x30)
    guest.rects[0x30] = (-4, -4, 804, 576)
    guest.normal[0x30] = (60, 60, 360, 280)
    window = scene.get_state(tmp_path / "s.json").window("flower")
    assert (window.show, window.at, window.size) == ("maximized", (60, 60), (300, 220))


def test_a_window_the_state_cant_open_fails_the_capture(
    guest, scene, tmp_path, monkeypatch
):
    captured_scene(guest, scene, tmp_path, monkeypatch)
    guest.add_window(0x40, "Other", (0, 0, 300, 300), "Other", pid=7000)
    scene.add(Win(hwnd=0x40), id="other")
    with pytest.raises(UsageError, match="Win can't be captured yet"):
        scene.get_state(tmp_path / "s.json")
    assert not (tmp_path / "s.files").exists()


def test_a_live_claim_over_a_visible_window_fails_the_capture(
    guest, scene, tmp_path, monkeypatch
):
    captured_scene(guest, scene, tmp_path, monkeypatch)
    guest.add_window(0x60, "#32770", (150, 150, 300, 250), "Menu", pid=7000)
    with scene.claim("RightClick menu", lambda w: w.hwnd == 0x60, hint="menu is open"):
        with pytest.raises(UsageError, match="RightClick menu.*before the section"):
            scene.get_state(tmp_path / "s.json")
        guest.close_window(0x60)
        scene.get_state(tmp_path / "s.json")  # claim still live, window gone: fine


def test_a_claim_covering_a_props_own_window_does_not_fail_the_capture(
    guest, scene, tmp_path, monkeypatch
):
    captured_scene(guest, scene, tmp_path, monkeypatch)
    with scene.claim("Everything", lambda w: True):
        scene.get_state(tmp_path / "s.json")


def test_a_window_prop_without_an_id_fails_the_capture(
    guest, scene, tmp_path, monkeypatch
):
    picture, _ = captured_scene(guest, scene, tmp_path, monkeypatch)
    picture.state_id = None
    with pytest.raises(UsageError, match=r"self\.add\(prop, id=\.\.\.\)"):
        scene.get_state(tmp_path / "s.json")


def test_an_untracked_window_fails_the_capture_before_anything_is_written(
    guest, scene, tmp_path, monkeypatch
):
    captured_scene(guest, scene, tmp_path, monkeypatch)
    guest.add_window(0x50, "Stray", (0, 0, 10, 10), "Stray")
    with pytest.raises(scene_module.UntrackedWindow):
        scene.get_state(tmp_path / "s.json")
    assert list(tmp_path.glob("s.*")) == []


def test_two_captures_of_the_same_scene_are_byte_identical(
    guest, scene, tmp_path, monkeypatch
):
    captured_scene(guest, scene, tmp_path, monkeypatch)
    scene.get_state(tmp_path / "s.json")
    first = (tmp_path / "s.json").read_bytes()
    scene.get_state(tmp_path / "s.json")
    assert (tmp_path / "s.json").read_bytes() == first


def snapshot(folder):
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def test_a_capture_the_reader_rejects_leaves_the_earlier_capture_untouched(
    guest, scene, tmp_path, monkeypatch
):
    from art98 import state as state_module

    captured_scene(guest, scene, tmp_path, monkeypatch)
    out = tmp_path / "out"
    scene.get_state(out / "s.json")
    before = snapshot(out)

    def reject(path):
        raise state_module.StateError(path, ["no"])

    monkeypatch.setattr(state_module, "load_state", reject)
    with pytest.raises(state_module.StateError):
        scene.get_state(out / "s.json")
    assert snapshot(out) == before
    assert not (out / ".s.json.part").exists()


def test_a_leftover_temp_folder_from_a_crash_is_cleared_by_the_next_capture(
    guest, scene, tmp_path, monkeypatch
):
    captured_scene(guest, scene, tmp_path, monkeypatch)
    (tmp_path / ".s.json.part" / "s.files").mkdir(parents=True)
    (tmp_path / ".s.json.part" / "s.files" / "stale").write_bytes(b"x")
    scene.get_state(tmp_path / "s.json")
    assert not (tmp_path / ".s.json.part").exists()
    assert not (tmp_path / "s.files" / "stale").exists()


def test_a_plain_file_named_like_the_files_folder_is_replaced(
    guest, scene, tmp_path, monkeypatch
):
    captured_scene(guest, scene, tmp_path, monkeypatch)
    (tmp_path / "s.files").write_bytes(b"in the way")
    scene.get_state(tmp_path / "s.json")
    assert (tmp_path / "s.files/windows/flower/flower.bmp").exists()


def test_a_window_id_that_is_empty_or_leaves_the_folder_is_a_usage_error(scene):
    for bad in ("", "../x", "a/b", "desk top"):
        with pytest.raises(UsageError, match=r"add\(id="):
            scene.add(Win(hwnd=0x40), id=bad)
    assert scene.props == []


def test_a_captured_id_the_reader_would_refuse_fails_before_anything_is_written(
    guest, scene, tmp_path, monkeypatch
):
    picture, _ = captured_scene(guest, scene, tmp_path, monkeypatch)
    picture.state_id = "../x"
    with pytest.raises(UsageError, match="letters, digits"):
        scene.get_state(tmp_path / "s.json")
    assert list(tmp_path.glob("*s.*")) == []


def test_a_minimized_window_keeps_its_order_and_normal_place_in_a_capture(
    guest, scene, tmp_path, monkeypatch
):
    captured_scene(guest, scene, tmp_path, monkeypatch)
    guest.iconic.add(0x30)
    guest.rects[0x30] = (-32000, -32000, -31840, -31972)
    guest.normal[0x30] = (60, 60, 360, 280)
    state = scene.get_state(tmp_path / "s.json")
    assert [w.id for w in state.windows] == ["flower", "note"]
    window = state.window("flower")
    assert (window.show, window.at, window.size) == ("minimized", (60, 60), (300, 220))


def test_a_wallpaper_set_by_a_state_is_captured_and_a_later_set_without_one_clears_it(
    guest, scene, tmp_path, monkeypatch
):
    from art98.anim import setstate
    from art98.state import dump_state
    from test_state import bmp

    monkeypatch.setattr(setstate, "wait_for_disc", lambda *a: "D:\\WALL0001.BMP")
    monkeypatch.setattr(setstate, "set_wallpaper", lambda *a: None)
    monkeypatch.setattr(setstate, "check_state", lambda *a: None)
    scene.session.attach_disc = lambda files: None
    data = bmp(4, 3)
    (tmp_path / "wall.bmp").write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    dump_state(
        {
            "version": 1,
            "desktop": {
                "fill_colour": [0, 128, 128],
                "wallpaper": {"file": "wall.bmp", "sha256": digest},
                "style": "tile",
            },
            "windows": [],
        },
        tmp_path / "in.json",
    )
    scene.set_state(tmp_path / "in.json")
    state = scene.get_state(tmp_path / "out.json")
    assert state.desktop.wallpaper.data == data and state.desktop.style == "tile"
    assert (tmp_path / "out.files/desktop/wall.bmp").read_bytes() == data
    dump_state({"version": 1, "windows": []}, tmp_path / "bare.json")
    scene.set_state(tmp_path / "bare.json")
    assert scene.get_state(tmp_path / "again.json").desktop.wallpaper is None


def test_an_empty_notepad_text_after_an_opened_file_round_trips(
    guest, scene, tmp_path, monkeypatch
):
    captured_scene(guest, scene, tmp_path, monkeypatch)
    guest.edit_text[0x11] = b""
    state = scene.get_state(tmp_path / "s.json")
    assert state.window("note").text.data == b""
    again = scene.get_state(tmp_path / "s.json")
    assert again.window("note").text.data == b""
