"""The host-side drift fixes (experiments/drift/README.md), against stand-in guests."""

from art98 import desktop, win32
from art98.anim import DR, Drag, Maximize, Minimize, RestoreWindow
from art98.bridge import CallResult, Window
from test_anim import FakeGuest, guest, notepad, scene  # noqa: F401  (fixtures)
from test_desktop import ICONS, DesktopGuest


def stack(guest, *rows):  # noqa: F811
    """Top-level windows front to back, as the guest lists them: (hwnd, visible)."""
    guest.rows[0] = [
        Window(hwnd, 0, visible, (0, 0, 10, 10), "#32770", "") for hwnd, visible in rows
    ]


def test_repaint_all_goes_back_to_front_and_then_waits():
    guest = FakeGuest()  # noqa: F811
    stack(guest, (1, True), (2, True), (3, False), (4, True))
    guest.sync = lambda *a: guest.calls.append(("sync", a))
    win32.repaint_all(guest)
    assert [(name, args[0] if args else None) for name, args in guest.calls] == [
        ("RedrawWindow", 4),
        ("RedrawWindow", 2),
        ("RedrawWindow", 1),
        ("sync", None),
    ]
    assert all(
        args[3] == win32.RDW_REPAINT_ALL
        for name, args in guest.calls
        if name == "RedrawWindow"
    )


def test_set_colour_waits_for_every_window_then_repaints_the_screen():
    guest = DesktopGuest()  # noqa: F811
    stack(guest, (1, True), (2, True))
    guest.sync = lambda *a: guest.calls.append(("sync", a))
    desktop.set_colour(guest, (128, 0, 0))
    names = [
        name
        for name, _ in guest.calls
        if name in ("SetSysColors", "sync", "RedrawWindow")
    ]
    # the broadcast, a sync so each window's thread has taken it, the repaint back to front, a sync
    assert names == ["SetSysColors", "sync", "RedrawWindow", "RedrawWindow", "sync"]
    assert [args[0] for name, args in guest.calls if name == "RedrawWindow"] == [2, 1]


def test_set_colour_still_rehides_the_icons_before_the_repaint():
    guest = DesktopGuest()  # noqa: F811
    guest.visible.discard(ICONS)
    guest.calls.clear()
    desktop.set_colour(guest, (1, 2, 3))
    names = [name for name, _ in guest.calls]
    assert names.index("SetSysColors") < names.index("ShowWindow")
    assert guest.syncs >= 2


def test_a_window_command_reads_the_new_place_back(guest, scene):  # noqa: F811
    pad = notepad(guest, scene)
    pad_hwnd = pad.hwnd

    def command(hwnd, message, wparam, lparam):
        if wparam == 0xF030:  # SC_MAXIMIZE
            guest.rects[hwnd] = (-4, -4, 804, 604)
        elif wparam == 0xF020:  # SC_MINIMIZE
            guest.rects[hwnd] = (3000, 3000, 3160, 3024)
        else:
            guest.rects[hwnd] = (92, 88, 692, 499)
        return CallResult(1, 0, [])

    guest.do_PostMessageA = command
    scene.play(Maximize(pad))
    assert pad.rect == (-4, -4, 804, 604)
    scene.play(Minimize(pad))
    assert pad.rect == (3000, 3000, 3160, 3024)
    scene.play(RestoreWindow(pad))
    assert pad.rect == (92, 88, 692, 499) and pad.hwnd == pad_hwnd


def test_a_corner_drag_follows_the_window_while_windows_resizes_it(guest, scene):  # noqa: F811
    pad = notepad(guest, scene)
    seen = []

    def resize(*args):
        guest.rects[0x10] = (92, 88, 640, 450)
        return CallResult(1, 0, [])

    guest.do_mouse_event = resize
    original = scene.recorder.frame
    scene.recorder.frame = lambda hold=1: (seen.append(pad.rect), original(hold))[1]
    scene.play(Drag(pad.corner(DR), by=(-50, -50), run_time=0.5))
    assert seen[-1] == (92, 88, 640, 450)
    # read back and repainted by the frame, not only when the drag ended
    assert any(rect == (92, 88, 640, 450) for rect in seen[:-1])
    assert 0x10 in [args[0] for _, args in guest.named("RedrawWindow")]
