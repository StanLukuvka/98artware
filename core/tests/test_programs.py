"""Minesweeper, Paint and Screensaver against a stand-in guest: no VM.

The fakes are the ones in test_anim.py; `paint` there builds a Paint window.
"""

import struct

import pytest
from art98 import UsageError
from art98.actions.programs import minesweeper as minesweeper_module
from art98.actions.programs.minesweeper import Minesweeper
from art98.actions.programs.paint import Paint
from art98.actions.programs.screensaver import Screensaver
from art98.errors import GuestError, NotFound
from art98.guest import win32
from art98.guest.bridge import BridgeTimeout, CallResult
from test_anim import FakeGuest, FakeSession, FakeVideo, Stage, paint


@pytest.fixture
def guest():
    return FakeGuest()


@pytest.fixture
def scene(guest):
    stage = Stage()
    stage.run(FakeSession(guest), FakeVideo(guest))
    guest.calls.clear()
    return stage


@pytest.fixture
def sweeper(guest, scene):
    guest.add_window(0x30, "Minesweeper", (100, 100, 270, 300), pid=7000)
    board = Minesweeper()
    scene.add(board)
    guest.calls.clear()
    return board


@pytest.fixture
def no_waits(monkeypatch):
    monkeypatch.setattr(minesweeper_module.time, "sleep", lambda seconds: None)


# ---- Minesweeper ----


def test_neighbours_are_the_cells_next_to_a_cell_on_the_board(sweeper):
    assert sweeper.neighbours((0, 0)) == [(0, 1), (1, 0), (1, 1)]
    assert len(sweeper.neighbours((4, 4))) == 8


def test_flood_fill_reads_the_board_size_once(guest, sweeper):
    sweeper.mines = frozenset({(0, 0)})
    sweeper.opened_by((7, 7))
    sweeper.opened_by((3, 3))
    assert len(guest.named("GetClientRect")) == 1


def test_flood_fill_needs_the_mines_read_first(sweeper):
    with pytest.raises(UsageError, match="find_mines"):
        sweeper.opened_by((1, 1))


def test_forget_drops_the_mines_and_the_board_size(sweeper):
    sweeper.mines = frozenset({(0, 0)})
    sweeper.forget()
    assert sweeper.mines is None


def test_find_mines_puts_the_desktop_and_the_pointer_back_after_an_error(
    guest, scene, sweeper, no_waits
):
    guest.foreground = 0x30
    guest.add_window(0x01, "Progman", (0, 0, 800, 600))
    seen = []

    def pixel(dc, x, y):
        seen.append(x)
        if len(seen) == 3:
            raise BridgeTimeout("the guest stopped answering")
        return CallResult(0, 0, [])

    guest.do_GetPixel = pixel
    with pytest.raises(BridgeTimeout):
        sweeper.find_mines()
    assert guest.named("ShowWindow")[-1][1] == (0x01, win32.SW_SHOWNA)
    assert guest.cursor == (400, 300)  # where the pointer was before the read


def test_find_mines_refuses_a_board_too_small_to_play(guest, sweeper):
    guest.do_GetClientRect = lambda hwnd, out: CallResult(
        1, 0, [struct.pack("<iiii", 0, 0, 10, 20)]
    )
    with pytest.raises(GuestError, match="make the window bigger"):
        sweeper.find_mines()
    assert guest.named("GetDC") == []  # refused before anything was sent to the guest


def test_minesweeper_not_on_stage_says_so():
    with pytest.raises(UsageError, match="not on stage"):
        Minesweeper().find_mines()


# ---- Paint ----


def test_a_tool_or_colour_that_is_not_there_is_not_found(guest, scene):
    prop = paint(guest, scene)
    with pytest.raises(NotFound, match="no tool 'spray'"):
        prop.tool("spray")
    with pytest.raises(NotFound, match="mauve"):
        prop.color("mauve")


def test_paint_targets_used_before_paint_is_on_stage_say_so():
    with pytest.raises(UsageError, match="not on stage"):
        Paint().tool("pencil").point()
    with pytest.raises(UsageError, match="not on stage"):
        Paint().canvas(1, 1).point()


def test_a_canvas_bigger_than_the_window_is_an_error(guest, scene):
    prop = paint(guest, scene)
    guest.do_GetPixel = lambda dc, x, y: CallResult(0xFFFFFF, 0, [])
    with pytest.raises(GuestError, match="does not fit the window"):
        _ = prop.canvas_size


def test_no_canvas_under_the_first_probe_is_an_error(guest, scene):
    prop = paint(guest, scene)
    guest.do_GetPixel = lambda dc, x, y: CallResult(0x808080, 0, [])
    with pytest.raises(GuestError, match="does not fit the window"):
        _ = prop.canvas_size


def test_a_revert_forgets_the_canvas_size_and_the_parts(guest, scene):
    prop = paint(guest, scene)
    prop.canvas_size = (400, 300)
    prop.forget()
    with pytest.raises(UsageError, match="not on stage"):
        _ = prop.canvas_size


# ---- Screensaver ----


def test_stop_near_the_right_and_bottom_edges_moves_towards_the_middle(guest, scene):
    guest.add_window(0x60, "WindowsScreenSaverClass", (0, 0, 800, 600), pid=7000)
    saver = Screensaver("Mystify Your Mind")
    scene.add(saver)
    guest.cursor = (790, 590)
    alive = iter([1, 0])
    guest.do_IsWindow = lambda hwnd: CallResult(next(alive), 0, [])
    saver.stop()
    moves = [args for _, args in guest.named("SetCursorPos")]
    assert moves[0] == (750, 550)
    assert all(0 <= x < 800 and 0 <= y < 600 for x, y in moves)
    assert guest.cursor == (790, 590)


def test_stop_times_out_when_the_screensaver_keeps_running(guest, scene):
    guest.add_window(0x60, "WindowsScreenSaverClass", (0, 0, 800, 600), pid=7000)
    saver = Screensaver("Mystify Your Mind")
    scene.add(saver)
    guest.do_IsWindow = lambda hwnd: CallResult(1, 0, [])
    with pytest.raises(BridgeTimeout, match="did not stop"):
        saver.stop(timeout=0.01)


def test_a_screensaver_name_that_is_not_there_is_not_found():
    with pytest.raises(NotFound, match="Starfield"):
        Screensaver("Starfield")


def test_screensaver_stop_before_it_is_on_stage_says_so():
    with pytest.raises(UsageError, match="not on stage"):
        Screensaver().stop()
