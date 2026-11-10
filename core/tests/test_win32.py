"""The win32 helpers send the guest calls they always did."""

import struct

from art98 import win32
from art98.bridge import RDW_REPAINT_ALL as bridge_repaint
from art98.protocol import Out


class Result:
    def __init__(self, value=1, buffers=()):
        self.value, self.buffers = value, list(buffers)

    def __bool__(self):
        return self.value != 0


class Guest:
    """Records every user32 call; `result` is what each call returns."""

    def __init__(self, result=None):
        self.calls, self.result = [], Result() if result is None else result
        guest = self

        class User32:
            def __getattr__(self, name):
                def call(*args):
                    guest.calls.append((name, args))
                    return guest.result
                return call

        self.user32 = User32()


def test_window_rect_is_none_when_the_window_is_gone():
    assert win32.window_rect(Guest(Result(0)), 5) is None
    rect = struct.pack("<iiii", 1, 2, 3, 4)
    assert win32.window_rect(Guest(Result(1, [rect])), 5) == (1, 2, 3, 4)


def test_place_window_moves_then_repaints():
    guest = Guest()
    win32.place_window(guest, 7, 1, 2, 3, 4, 0x14)
    assert guest.calls == [("SetWindowPos", (7, 0, 1, 2, 3, 4, 0x14)),
                           ("RedrawWindow", (7, 0, 0, 0x585))]


def test_repaint_flags_are_shared():
    assert bridge_repaint == win32.RDW_REPAINT_ALL == 0x585


def test_mouse_button_sends_down_or_up():
    guest = Guest()
    win32.mouse_button(guest, "right", True)
    win32.mouse_button(guest, "right", False)
    assert [c[1][0] for c in guest.calls] == [0x0008, 0x0010]


def test_menu_item_rect_is_none_when_the_menu_is_closed():
    assert win32.menu_item_rect(Guest(Result(0)), 1, 2, 3) is None
    rect = struct.pack("<iiii", 5, 6, 7, 8)
    guest = Guest(Result(1, [rect]))
    assert win32.menu_item_rect(guest, 1, 2, 3) == (5, 6, 7, 8)
    assert isinstance(guest.calls[0][1][3], Out)
