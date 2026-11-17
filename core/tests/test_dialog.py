"""Dialog as a program (icon, size, disabled, set_message, remove) against a stand-in guest: no VM."""

import struct

import pytest
from art98.actions.programs import dialog as dialog_module
from art98.actions.programs.dialog import Dialog
from art98.actions.window import Close
from art98.errors import GuestError, UsageError
from art98.guest import win32
from art98.guest.bridge import CallResult
from test_anim import FakeDll, FakeGuest, FakeSession, FakeVideo, Stage

BOX, ICON, TEXT, YES, NO, ABORT = 0x70, 0x71, 0x72, 0x73, 0x74, 0x75
WM_CLOSE, BM_CLICK = win32.WM_CLOSE, win32.BM_CLICK


class Call:
    """What MessageBoxA's thread returns once the box has been answered."""

    def __init__(self, code):
        self.code = code

    def wait(self):
        return CallResult(self.code, 0, [])


class DialogGuest(FakeGuest):
    """acall opens a stock box: an icon static, a text static and two buttons.

    A box stays in `alive` until WM_CLOSE (unless `ignores_close`) or a
    BM_CLICK on one of its buttons closes it, as on Windows.
    """

    def __init__(self):
        super().__init__()
        self.shell32 = FakeDll(self, "shell32")
        self.icons = {}
        self.styles = {ICON: 0x50000003, TEXT: 0x50022080}
        self.alive = set()
        self.button_ids = {6: YES, 7: NO}  # IDYES, IDNO
        self.ignores_close = False  # a box with no Cancel button
        self.answer_code = 6
        self.posted, self.clicks = [], []

    def acall(self, dll, function, *args):
        self.calls.append(("acall", (dll, function, args)))
        self.add_window(BOX, "#32770", (10, 10, 200, 100), "Quit?")
        self.add_window(ICON, "Static", (20, 30, 52, 62), "", parent=BOX)
        self.add_window(TEXT, "Static", (72, 51, 183, 66), "Really?", parent=BOX)
        self.add_window(YES, "Button", (40, 90, 115, 113), "&Yes", parent=BOX)
        self.add_window(NO, "Button", (121, 90, 196, 113), "&No", parent=BOX)
        self.alive.add(BOX)
        return Call(self.answer_code)

    def do_ExtractIconA(self, hinst, dll, index):
        return CallResult(self.icons.get((dll, index), 0), 0, [])

    def do_GetWindowLongA(self, hwnd, index):
        return CallResult(self.styles.get(hwnd, 0), 0, [])

    def do_ScreenToClient(self, hwnd, point):
        return CallResult(1, 0, [struct.pack("<ii", -3, -41)])

    def do_IsWindow(self, hwnd):
        return CallResult(int(hwnd in self.alive), 0, [])

    def do_PostMessageA(self, hwnd, message, wparam, lparam):
        self.posted.append((hwnd, message))
        if message == WM_CLOSE and not self.ignores_close:
            self.alive.discard(hwnd)
            self.close_window(hwnd)
        return CallResult(1, 0, [])

    def do_GetDlgItem(self, parent, control_id):
        return CallResult(self.button_ids.get(control_id, 0), 0, [])

    def do_SendMessageA(self, hwnd, message, wparam, lparam):
        if message == BM_CLICK:
            self.clicks.append(hwnd)
            if hwnd in self.button_ids.values():
                self.alive.discard(BOX)
                self.close_window(BOX)
                self.answer_code = {YES: 6, NO: 7}.get(hwnd, self.answer_code)
        return CallResult(1, 0, [])


@pytest.fixture
def guest():
    return DialogGuest()


@pytest.fixture
def scene(guest):
    stage = Stage()
    stage.run(FakeSession(guest), FakeVideo(guest))
    guest.calls.clear()
    return stage


def names(guest):
    return [name for name, _ in guest.calls]


def test_stock_icon_style_bits_are_unchanged(guest, scene):
    box = Dialog("Radius?", "Quit?", icon="question", buttons="yesno")
    scene.add(box)
    assert guest.named("acall")[0][1] == (
        "user32",
        "MessageBoxA",
        (0, "Radius?", "Quit?", 0x24),
    )
    assert box.style == 0x24
    assert "ExtractIconA" not in names(guest) and box.answer == "yes"
    with pytest.raises(ValueError, match="unknown icon"):
        Dialog("x", icon="nope")


def test_a_same_title_box_already_open_is_skipped(guest, scene):
    guest.add_window(
        0x10, "#32770", (0, 0, 50, 50), "Quit?"
    )  # an older box with the same title
    box = Dialog("Hi", "Quit?")
    scene.add(box)
    assert box.hwnd == BOX


def test_custom_icon_is_extracted_set_then_repainted(guest, scene):
    path, index = Dialog.CUSTOM_ICONS["computer"]
    guest.icons[(path, index)] = 0x55
    box = Dialog("Hi", "Quit?", icon="computer")
    scene.add(box)
    assert box.style == 0x40
    order = [
        c
        for c in guest.calls
        if c[0] in ("ExtractIconA", "SendMessageA", "RedrawWindow")
    ]
    assert order[0] == ("ExtractIconA", (0, path, index))
    assert order[1] == ("SendMessageA", (ICON, 0x170, 0x55, 0))
    assert order[2][0] == "RedrawWindow" and order[2][1][0] == ICON
    assert "DestroyIcon" not in names(guest)  # only remove() destroys it
    box.remove()
    assert guest.named("DestroyIcon") == [("DestroyIcon", (0x55,))]


@pytest.mark.parametrize("handle", [0, 1])
def test_custom_icon_rejects_a_bad_file_or_index_and_closes_the_box(
    guest, scene, handle
):
    guest.icons[(r"C:\X.DLL", 3)] = handle
    with pytest.raises(ValueError, match="no icon 3"):
        scene.add(Dialog("Hi", "Quit?", icon=(r"C:\X.DLL", 3)))
    assert BOX not in guest.alive


def test_disabled_greys_every_button(guest, scene):
    scene.add(Dialog("Hi", "Quit?", buttons="yesno", disabled=True))
    assert guest.named("EnableWindow") == [
        ("EnableWindow", (YES, 0)),
        ("EnableWindow", (NO, 0)),
    ]


def test_size_goes_to_win_and_the_box_is_laid_out_again(guest, scene):
    box = Dialog("Hi", "Quit?", buttons="yesno", at=(5, 6), size=(300, 150))
    scene.add(box)
    assert box.size == (300, 150) and guest.rects[BOX] == (5, 6, 305, 156)
    # client 148x191 in the stand-in: two buttons centred, bottom margin 11
    assert guest.named("MoveWindow") == [
        ("MoveWindow", (YES, -4, 157, 75, 23, 1)),
        ("MoveWindow", (NO, 77, 157, 75, 23, 1)),
        ("MoveWindow", (TEXT, 62, 10, 70, 15, 1)),
    ]
    guest.rows[
        0
    ].clear()  # the stand-in reuses one hwnd for every box: forget the first
    scene.props.remove(box)
    with pytest.raises(UsageError, match="smaller than the least"):
        scene.add(Dialog("Hi", "Quit?", size=(100, 50)))


def test_set_message_changes_the_text_not_the_title(guest, scene):
    box = Dialog("Hi", "Quit?")
    scene.add(box)
    guest.calls.clear()
    box.set_message("A\nB")
    assert box.message == "A\nB"
    assert guest.named("MoveWindow") == [
        ("MoveWindow", (TEXT, 62, 51 - 41, 111, 30, 1))
    ]
    assert guest.named("SetWindowTextA") == [("SetWindowTextA", (TEXT, "A\nB"))]
    assert box.title_text == "Quit?"
    with pytest.raises(ValueError, match="too tall"):
        box.set_message("1\n2\n3\n4\n5")


def test_yes_no_box_is_closed_by_its_no_button(guest, scene):
    box = Dialog("Hi", "Quit?", buttons="yesno")
    scene.add(box)
    guest.calls.clear()
    box.remove()
    assert guest.clicks == [NO]  # WM_CLOSE does nothing to a box with no Cancel
    assert "PostMessageA" not in names(guest)
    assert BOX not in guest.alive


def test_abort_retry_ignore_box_is_closed_by_its_abort_button(guest, scene):
    guest.button_ids[3] = ABORT
    box = Dialog("Hi", "Quit?", buttons="abortretryignore")
    scene.add(box)
    guest.calls.clear()
    box.remove()
    assert guest.clicks == [ABORT]
    assert BOX not in guest.alive


def test_box_with_a_cancel_button_is_closed_by_wm_close(guest, scene):
    box = Dialog("Hi", "Quit?")
    scene.add(box)
    guest.calls.clear()
    box.remove()
    assert guest.named("PostMessageA") == [("PostMessageA", (BOX, WM_CLOSE, 0, 0))]
    assert guest.clicks == [] and BOX not in guest.alive


def test_icon_is_destroyed_only_after_the_box_has_gone(guest, scene):
    path, index = Dialog.CUSTOM_ICONS["computer"]
    guest.icons[(path, index)] = 0x55
    box = Dialog("Hi", "Quit?", icon="computer", buttons="yesno")
    scene.add(box)
    guest.calls.clear()
    box.remove()
    order = names(guest)
    last_look = max(i for i, name in enumerate(order) if name == "IsWindow")
    assert order.index("SendMessageA") < last_look < order.index("DestroyIcon")
    assert guest.named("DestroyIcon") == [("DestroyIcon", (0x55,))]


def test_a_box_that_stays_open_is_an_error_and_keeps_its_icon(
    guest, scene, monkeypatch
):
    monkeypatch.setattr(dialog_module, "CLOSE_TIMEOUT", 0.01)
    path, index = Dialog.CUSTOM_ICONS["computer"]
    guest.icons[(path, index)] = 0x55
    box = Dialog("Hi", "Quit?", icon="computer")
    scene.add(box)
    guest.ignores_close = True
    guest.calls.clear()
    with pytest.raises(GuestError, match="did not close"):
        box.remove()
    assert "DestroyIcon" not in names(guest)


def test_a_bad_button_set_is_a_usage_error_naming_the_choices():
    with pytest.raises(UsageError, match="no button set 'yes_no'"):
        Dialog("x", buttons="yes_no")


@pytest.mark.parametrize("icon", [("shell32.dll",), ["a.dll", 1, 2], ("a.dll", "3")])
def test_a_custom_icon_must_be_a_dll_and_an_index(icon):
    with pytest.raises(UsageError, match="dll, index"):
        Dialog("x", icon=icon)


def test_text_and_title_must_fit_in_windows_1252(guest, scene):
    with pytest.raises(UsageError, match="1252"):
        Dialog("日本")
    with pytest.raises(UsageError, match="1252"):
        Dialog("x", "ł")
    box = Dialog("x", "Quit?")
    scene.add(box)
    with pytest.raises(UsageError, match="1252"):
        box.set_message("日")


def test_answer_and_set_message_say_when_the_box_is_not_on_stage():
    box = Dialog("x")
    with pytest.raises(UsageError, match="not on stage"):
        _ = box.answer
    with pytest.raises(UsageError, match="not on stage"):
        box.set_message("y")


def test_set_message_on_a_closed_box_is_a_guest_error(guest, scene):
    box = Dialog("Hi", "Quit?")
    scene.add(box)
    del guest.rects[TEXT]  # the box has gone: its text has no place any more
    with pytest.raises(GuestError, match="has closed"):
        box.set_message("again")


def test_an_answer_that_is_not_a_button_is_a_guest_error(guest, scene):
    guest.answer_code = 99  # the code the box's thread returns when it closes
    box = Dialog("Hi", "Quit?")
    scene.add(box)
    with pytest.raises(GuestError, match="99"):
        _ = box.answer


def test_dialog_is_an_exported_program():
    from art98 import anim

    assert anim.Dialog is Dialog
    assert "Dialog" in anim.__all__


@pytest.mark.parametrize("ignores_close", [False, True])
def test_close_via_a_button_presses_it_and_the_box_answers_for_real(
    guest, scene, ignores_close
):
    guest.ignores_close = ignores_close
    box = Dialog("Really?", "Quit?", icon="question", buttons="yesno")
    scene.add(box)
    scene.wait(0.1)
    guest.calls.clear()
    scene.play(Close(box, via=box.button("Yes")))
    scene.wait(0.1)
    assert guest.clicks == [YES] and guest.named("mouse_event") == []
    pressed = [a[2] for f, a in guest.named("SendMessageA") if a[1] == 0x00F3]
    assert pressed == [1, 0] and box not in scene.props
    assert box.answer == "yes"


def test_a_box_that_stays_after_close_via_a_button_resets_the_button(
    guest, scene, monkeypatch
):
    monkeypatch.setattr(dialog_module, "CLOSE_TIMEOUT", 0.01)
    box = Dialog("Really?", "Quit?", buttons="yesno")
    scene.add(box)
    yes = box.button("Yes")
    guest.do_SendMessageA = lambda *args: CallResult(1, 0, [])  # the click does nothing
    guest.calls.clear()
    with pytest.raises(GuestError, match="did not close"):
        scene.play(Close(box, via=yes))
    pressed = [a[2] for f, a in guest.named("SendMessageA") if a[1] == 0x00F3]
    assert pressed == [1, 0] and box.closing is False
