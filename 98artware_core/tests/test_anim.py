"""The scene layer against a stand-in guest: nothing here needs a VM."""

import struct

import pytest

from art98 import anim, session as session_module
from art98.anim import *
from art98.anim.apps import PARKED, Dialog, Minesweeper, Notepad, Paint, Screensaver
from art98.anim import actions
from art98.anim.actions import BUTTONS, char_chord, key_chord
from art98.bridge import CallResult, Window

WM_CHAR, WM_CLOSE, WM_SYSCOMMAND = 0x0102, 0x0010, 0x0112
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE = 1, 2, 4, 0x10
LDOWN, LUP = BUTTONS["left"]
RDOWN, RUP = BUTTONS["right"]


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
        self.rows = {0: []}
        self.cursor = (400, 300)
        self.foreground = 0
        self.spawned = []
        self.syncs = 0
        self.next_pid = 7000
        self.user32 = FakeDll(self, "user32")
        self.gdi32 = FakeDll(self, "gdi32")

    def add_window(self, hwnd, class_name, rect, title="", parent=0, pid=0):
        self.rects[hwnd] = rect
        self.rows.setdefault(parent, []).append(
            Window(hwnd, pid, True, rect, class_name, title))

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
        return CallResult({4: 18, 33: 3}.get(index, 0), 0, [])

    def do_ClientToScreen(self, hwnd, point):
        x, y = struct.unpack("<ii", point)
        left, top = self.rects[hwnd][:2]
        return CallResult(1, 0, [struct.pack("<ii", left + 3 + x, top + 41 + y)])

    def do_GetClientRect(self, hwnd, out):
        return CallResult(1, 0, [struct.pack("<iiii", 0, 0, 148, 191)])

    def do_GetDlgCtrlID(self, hwnd):
        return CallResult(hwnd, 0, [])

    def do_GetForegroundWindow(self):
        return CallResult(self.foreground, 0, [])

    def windows(self, parent=0):
        return list(self.rows.get(parent, []))

    def find_window(self, title=None, class_name=None, parent=0, timeout=10.0):
        return next(w for w in self.windows(parent)
                    if class_name is None or w.class_name == class_name)

    def spawn(self, command, cwd=None):
        self.spawned.append(command)
        return self.next_pid

    def sync(self, hwnd=0, timeout_ms=500):
        self.syncs += 1
        return 0


class FakeVM:
    def __init__(self):
        self.keys = []

    def send_keys(self, *codes, hold_ms=80):
        self.keys.append(codes)


class FakeVideo:
    def __init__(self, guest):
        self.guest = guest
        self.count = 0
        self.frames = []
        self.live_calls = []

    def frame(self, hold=1):
        self.frames.append((hold, len(self.guest.calls), self.guest.cursor))
        self.count += hold

    def live(self, seconds, stop_condition=None):
        self.live_calls.append(seconds)
        for _ in range(round(seconds * 30)):
            if stop_condition is not None and stop_condition():
                return
            self.count += 1


class FakeSession:
    def __init__(self, guest):
        self.bridge, self.vm = guest, FakeVM()


class Stage(Scene):
    pass


@pytest.fixture
def guest():
    return FakeGuest()


@pytest.fixture
def scene(guest, monkeypatch):
    monkeypatch.setattr(actions, "KEY_SETTLE", 0)
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


# ---- the frame loop ----


def test_play_writes_run_time_times_fps_frames_and_ends_at_exactly_1(scene):
    probe = Probe(run_time=0.5, rate_func=linear)
    scene.play(probe)
    assert scene.video.count == 15
    assert scene.time == pytest.approx(0.5)
    assert probe.log[0] == "begin" and probe.log[-1] == "finish"
    assert probe.log[-2] == 1.0
    assert len(probe.log) == 17


def test_one_play_runs_animations_together_and_short_ones_hold(scene):
    long, short = Probe(run_time=1, rate_func=linear), Probe(run_time=0.5, rate_func=linear)
    scene.play(long, short)
    assert scene.video.count == 30
    assert short.log.count("finish") == 1
    assert short.log.index(1.0) == 15
    assert long.log[-2] == 1.0


def test_play_overrides_run_time_and_rate_func(scene):
    probe = Probe()
    scene.play(probe, run_time=0.1, rate_func=lambda t: 0.25)
    assert scene.video.count == 3
    assert set(probe.log[1:-1]) == {0.25}


def test_an_instant_animation_takes_one_frame(guest, scene):
    pad = notepad(guest, scene)
    scene.play(Minimize(pad))
    assert scene.video.count == 1
    assert ("PostMessageA", (0x10, WM_SYSCOMMAND, 0xF020, 0)) in guest.calls


def test_two_pointer_animations_in_one_play_are_refused(scene):
    with pytest.raises(ValueError, match="pointer"):
        scene.play(Click((1, 1)), Glide((2, 2)))


def test_play_needs_an_animation(scene):
    with pytest.raises(ValueError):
        scene.play()


def test_pause_holds_one_capture(scene):
    scene.pause(2)
    assert scene.video.frames == [(60, 0, (400, 300))]
    assert scene.time == 2


def test_wait_records_live_unless_frozen(scene):
    scene.wait(1)
    assert scene.video.live_calls == [1]
    scene.wait(1, frozen_frame=True)
    assert scene.video.live_calls == [1] and scene.time == 2


def test_wait_stops_on_its_condition(scene):
    answers = iter([False, False, True])
    scene.wait(10, stop_condition=lambda: next(answers))
    assert scene.video.count == 2


def test_wait_until_warns_when_it_gives_up(scene):
    with pytest.warns(UserWarning, match="gave up"):
        scene.wait_until(lambda: False, max_time=0.1)


def test_only_the_free_clock_exists(guest):
    class Stepped(Scene):
        clock = "stepped"

    with pytest.raises(NotImplementedError):
        Stepped().run(FakeSession(guest), FakeVideo(guest))


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
    assert scene.video.count == 30
    assert second.start == (100, 100)
    assert guest.cursor == (200, 100)


def test_a_group_with_lag_starts_late(scene):
    first, second = Probe(run_time=1, rate_func=linear), Probe(run_time=1, rate_func=linear)
    scene.play(LaggedStart(first, second, lag_ratio=0.5))
    assert scene.video.count == 45
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


def test_a_prop_not_on_stage_says_so():
    with pytest.raises(RuntimeError, match="add it"):
        Notepad().guest


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
    assert all(args[-1] == SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE for _, args in moves)


def test_a_move_and_a_resize_become_one_call_per_frame(guest, scene):
    pad = notepad(guest, scene)
    scene.play(pad.animate.shift(30 * RIGHT), pad.animate.resize(300, 200),
               run_time=0.1, rate_func=linear)
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
        pad.animate.close


def test_move_along_path_carries_the_centre(guest, scene):
    pad = notepad(guest, scene)
    scene.play(MoveAlongPath(pad, [(300, 200), (400, 200), (400, 300)]), run_time=0.5,
               rate_func=linear)
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


# ---- pointer ----


def test_pointer_follows_real_position_at_begin(guest, scene):
    guest.cursor = (10, 10)
    glide = Glide((20, 10), run_time=0.1, rate_func=linear)
    scene.play(glide)
    assert glide.start == (10, 10)
    assert [args for _, args in guest.named("SetCursorPos")][-1] == (20, 10)


def test_pointer_animate_goes_through_the_frame_loop(guest, scene):
    scene.play(scene.pointer.animate.shift(10 * RIGHT), run_time=0.1, rate_func=linear)
    assert guest.cursor == (410, 300)


def events(guest):
    return [(name, args[0] if name == "mouse_event" else args)
            for name, args in guest.named("SetCursorPos", "mouse_event")]


def test_click_arrives_then_presses_then_releases(guest, scene):
    scene.play(Click((500, 400)))
    log = events(guest)
    press = log.index(("mouse_event", LDOWN))
    release = log.index(("mouse_event", LUP))
    assert press < release
    assert log[press - 1] == ("SetCursorPos", (500, 400))
    assert guest.cursor == (500, 400)
    assert scene.video.count == round(Click.run_time * 30)


def test_press_and_release_land_on_different_frames(guest, scene):
    scene.play(Click((500, 400)))
    press = guest.calls.index(("mouse_event", (LDOWN, 0, 0, 0, 0)))
    release = guest.calls.index(("mouse_event", (LUP, 0, 0, 0, 0)))
    assert any(press < index <= release for _, index, _ in scene.video.frames)


def test_right_click_uses_the_right_button(guest, scene):
    scene.play(RightClick((1, 2)))
    assert [e for e in events(guest) if e[0] == "mouse_event"] == [
        ("mouse_event", RDOWN), ("mouse_event", RUP)]


def test_double_click_is_two_clicks_inside_one_stretch(guest, scene):
    scene.play(DoubleClick((1, 2)))
    assert [e[1] for e in events(guest) if e[0] == "mouse_event"] == [LDOWN, LUP, LDOWN, LUP]
    held = [i for i, (_, index, _) in enumerate(scene.video.frames)
            if index >= guest.calls.index(("mouse_event", (LDOWN, 0, 0, 0, 0)))]
    last = len(guest.calls) - 1 - guest.calls[::-1].index(("mouse_event", (LUP, 0, 0, 0, 0)))
    span = [i for i in held if scene.video.frames[i][1] <= last]
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


def menu_guest(guest):
    labels = {(0x50, 0): "&File", (0x50, 1): "&Help", (0x51, 0): "&New\tCtrl+N",
              (0x51, 1): "E&xit"}
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


# ---- keyboard ----


def test_typing_sends_each_letter_to_the_edit_control(guest, scene):
    pad = notepad(guest, scene)
    scene.play(TypeWithCursor(pad, "a\nb"))
    assert guest.named("SendMessageA") == [
        ("SendMessageA", (0x11, WM_CHAR, code, 1)) for code in (97, 13, 98)]
    assert scene.video.count == 9


def test_typing_spreads_letters_over_the_frames(guest, scene):
    pad = notepad(guest, scene)
    scene.play(TypeWithCursor(pad, "abcdef", run_time=0.2))
    assert [hold for hold, _, _ in scene.video.frames] == [1] * 6
    indices = [index for _, index, _ in scene.video.frames]
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


@pytest.mark.parametrize("char, chord", [
    ("a", ("a",)), ("A", ("shift", "a")), ("7", ("7",)), ("&", ("shift", "7")),
    (" ", ("spc",)), ("\n", ("ret",)), (".", ("dot",)), ("?", ("shift", "slash")),
    ("|", ("shift", "backslash")), ("\\", ("backslash",)),
])
def test_characters_become_keys(char, chord):
    assert char_chord(char) == chord


def test_a_character_with_no_key_is_refused():
    with pytest.raises(ValueError):
        char_chord("é")


def test_keys_press_in_order_on_the_real_keyboard(scene):
    scene.play(Keys("ctrl+a", "delete"))
    assert scene.vm.keys == [("ctrl", "a"), ("delete",)]
    assert scene.video.count == 15


def test_type_keys_presses_every_character(scene):
    scene.play(TypeKeys("Hi\n"))
    assert scene.vm.keys == [("shift", "h"), ("i",), ("ret",)]


# ---- apps ----


def paint(guest, scene, left=20, top=10):
    def at(rect):
        return tuple(v + (left if i % 2 == 0 else top) for i, v in enumerate(rect))

    guest.add_window(0x40, "MSPaintApp", at((0, 0, 580, 510)), "untitled - Paint", pid=7000)
    guest.add_window(0x41, "Afx:1000000:8", at((63, 44, 574, 432)), parent=0x40)
    guest.add_window(0x42, "AfxWnd42", at((2, 432, 261, 483)), "Colors", parent=0x40)
    for number in Paint.TOOLS.values():
        offset = 42 + (number % 16) * 25
        guest.add_window(number, "ToolChild", at((8, offset, 33, offset + 25)), parent=0x40)
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
        return CallResult(0xFFFFFF if x < x0 + 400 and y < y0 + 300 else 0x808080, 0, [])

    guest.do_GetPixel = pixel
    assert prop.canvas_size == (400, 300)


def test_resizing_the_canvas_drags_the_handle_and_remembers(guest, scene):
    prop = paint(guest, scene)
    prop._canvas_size = (400, 300)
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


def test_screensaver_needs_a_real_name():
    assert '"C:\\WINDOWS\\SYSTEM\\3D Pipes.scr" /s' == Screensaver("3D Pipes").command
    with pytest.raises(ValueError):
        Screensaver("Starfield")


def test_screensaver_stops_by_moving_the_pointer(guest, scene):
    guest.add_window(0x60, "WindowsScreenSaverClass", (0, 0, 800, 600), pid=7000)
    saver = Screensaver("Mystify Your Mind")
    scene.add(saver)
    alive = iter([1, 0])
    guest.do_IsWindow = lambda hwnd: CallResult(next(alive), 0, [])
    saver.stop()
    assert guest.cursor == (440, 340)


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
    (tmp_path / "image.json").write_text(
        '{"disk": "%s"}' % (tmp_path / "golden.qcow2"))
    with session_module.private_stage(tmp_path) as stage:
        assert (stage / "golden.qcow2").read_bytes() == b"disk"
        assert str(stage) in (stage / "image.json").read_text()
        (stage / "golden.qcow2").write_bytes(b"dirty")
    assert (tmp_path / "golden.qcow2").read_bytes() == b"disk"
    assert not stage.exists()


def test_recorder_picks_a_lossless_codec_for_gif_sources(monkeypatch):
    commands = []

    class FakePopen:
        def __init__(self, command, stdin=None):
            commands.append(command)

    monkeypatch.setattr(session_module.subprocess, "Popen", FakePopen)
    session_module.FrameRecorder(None, "a.mkv", lossless=True)
    session_module.FrameRecorder(None, "b.mp4")
    assert "ffv1" in commands[0] and "libx264" in commands[1]


def test_recorder_live_stops_on_its_condition(monkeypatch):
    recorder = session_module.FrameRecorder.__new__(session_module.FrameRecorder)
    recorder._fps, recorder.count = 1000, 0

    def capture(hold):
        recorder.count += hold

    recorder._capture = capture
    recorder.live(1, stop_condition=lambda: recorder.count >= 3)
    assert recorder.count == 3


def test_render_turns_a_class_into_a_scene_and_routes_a_gif(tmp_path, monkeypatch, guest):
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

        def record(self, path, fps=30, lossless=False):
            options.update(path=path, fps=fps, lossless=lossless)
            return Recorder(guest)

    options, gifs = {}, []
    monkeypatch.setattr(render_module, "stage",
                        lambda work, display, backend: Booted(guest))
    monkeypatch.setattr(render_module, "write_gif", lambda *a: gifs.append(a))
    written = render_module.render(Tiny, tmp_path / "out.gif")
    assert written == tmp_path / "out.gif"
    assert options["lossless"] is True and gifs[0][1] == tmp_path / "out.gif"


def test_cli_finds_the_scene_in_a_file(tmp_path):
    from art98.cli import _load_scene

    file = tmp_path / "one_scene.py"
    file.write_text("from art98.anim import *\nclass Only(Scene):\n    pass\n")
    assert _load_scene(file, None).__name__ == "Only"
    file = tmp_path / "two_scenes.py"
    file.write_text("from art98.anim import *\nclass A(Scene):\n    pass\n"
                    "class B(Scene):\n    pass\n")
    assert _load_scene(file, "B").__name__ == "B"
    with pytest.raises(SystemExit, match="A, B"):
        _load_scene(file, None)


def test_star_import_gives_the_scene_api():
    namespace = {}
    exec("from art98.anim import *", namespace)
    for name in ("Scene", "Click", "Picture", "RIGHT", "smooth", "Teleport", "Stroke"):
        assert name in namespace
    # Parked program classes come from art98.anim.apps, not the star import.
    assert not set(PARKED) & set(namespace)
    assert set(anim.__all__) <= set(dir(anim))
