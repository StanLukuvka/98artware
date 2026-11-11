"""Dialog as a program (icon, size, disabled, set_message) against a stand-in guest: no VM."""

import struct

import pytest

from art98.actions.programs.dialog import Dialog
from art98.anim import apps
from art98.bridge import CallResult

from test_anim import FakeDll, FakeGuest, FakeSession, FakeVideo, Stage

BOX, ICON, TEXT, YES, NO = 0x70, 0x71, 0x72, 0x73, 0x74


class Call:
    def wait(self):
        return CallResult(6, 0, [])


class DialogGuest(FakeGuest):
    """acall opens a stock box: an icon static, a text static and two buttons."""

    def __init__(self):
        super().__init__()
        self.shell32 = FakeDll(self, "shell32")
        self.icons = {}
        self.styles = {ICON: 0x50000003, TEXT: 0x50022080}

    def acall(self, dll, function, *args):
        self.calls.append(("acall", (dll, function, args)))
        self.add_window(BOX, "#32770", (10, 10, 200, 100), "Quit?")
        self.add_window(ICON, "Static", (20, 30, 52, 62), "", parent=BOX)
        self.add_window(TEXT, "Static", (72, 51, 183, 66), "Really?", parent=BOX)
        self.add_window(YES, "Button", (40, 90, 115, 113), "&Yes", parent=BOX)
        self.add_window(NO, "Button", (121, 90, 196, 113), "&No", parent=BOX)
        return Call()

    def do_ExtractIconA(self, hinst, dll, index):
        return CallResult(self.icons.get((dll, index), 0), 0, [])

    def do_GetWindowLongA(self, hwnd, index):
        return CallResult(self.styles.get(hwnd, 0), 0, [])

    def do_ScreenToClient(self, hwnd, point):
        return CallResult(1, 0, [struct.pack("<ii", -3, -41)])


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
    assert guest.named("acall")[0][1] == ("user32", "MessageBoxA", (0, "Radius?", "Quit?", 0x24))
    assert box.style == 0x24
    assert "ExtractIconA" not in names(guest) and box.answer == "yes"
    with pytest.raises(ValueError, match="unknown icon"):
        Dialog("x", icon="nope")


def test_a_same_title_box_already_open_is_skipped(guest, scene):
    guest.add_window(0x10, "#32770", (0, 0, 50, 50), "Quit?")  # an older box with the same title
    box = Dialog("Hi", "Quit?")
    scene.add(box)
    assert box.hwnd == BOX


def test_custom_icon_is_extracted_set_then_repainted(guest, scene):
    path, index = Dialog.CUSTOM_ICONS["computer"]
    guest.icons[(path, index)] = 0x55
    box = Dialog("Hi", "Quit?", icon="computer")
    scene.add(box)
    assert box.style == 0x40
    order = [c for c in guest.calls if c[0] in ("ExtractIconA", "SendMessageA", "RedrawWindow")]
    assert order[0] == ("ExtractIconA", (0, path, index))
    assert order[1] == ("SendMessageA", (ICON, 0x170, 0x55, 0))
    assert order[2][0] == "RedrawWindow" and order[2][1][0] == ICON
    assert "DestroyIcon" not in names(guest)  # only remove() destroys it
    box.remove()
    assert guest.named("DestroyIcon") == [("DestroyIcon", (0x55,))]


@pytest.mark.parametrize("handle", [0, 1])
def test_custom_icon_rejects_a_bad_file_or_index(guest, scene, handle):
    guest.icons[(r"C:\X.DLL", 3)] = handle
    with pytest.raises(ValueError, match="no icon 3"):
        scene.add(Dialog("Hi", "Quit?", icon=(r"C:\X.DLL", 3)))


def test_disabled_greys_every_button(guest, scene):
    scene.add(Dialog("Hi", "Quit?", buttons="yesno", disabled=True))
    assert guest.named("EnableWindow") == [("EnableWindow", (YES, 0)), ("EnableWindow", (NO, 0))]


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
    guest.rows[0].clear()  # the stand-in reuses one hwnd for every box: forget the first
    with pytest.raises(ValueError, match="smaller than the stock box"):
        scene.add(Dialog("Hi", "Quit?", size=(100, 50)))


def test_set_message_changes_the_text_not_the_title(guest, scene):
    box = Dialog("Hi", "Quit?")
    scene.add(box)
    guest.calls.clear()
    box.set_message("A\nB")
    assert box.message == "A\nB"
    assert guest.named("MoveWindow") == [("MoveWindow", (TEXT, 62, 51 - 41, 111, 30, 1))]
    assert guest.named("SetWindowTextA") == [("SetWindowTextA", (TEXT, "A\nB"))]
    assert box.title_text == "Quit?"
    with pytest.raises(ValueError, match="too tall"):
        box.set_message("1\n2\n3\n4\n5")


def test_dialog_is_exported_and_no_longer_parked():
    from art98 import anim
    assert anim.Dialog is Dialog and apps.Dialog is Dialog
    assert "Dialog" in anim.__all__ and "Dialog" not in apps.PARKED
