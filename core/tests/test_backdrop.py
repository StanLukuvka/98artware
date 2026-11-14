"""Backdrop and the guest helpers for colour, wallpaper and the CD, against stand-in guests."""

import struct

import pytest
from art98 import desktop, win32
from art98.anim import Backdrop
from art98.bridge import CallResult
from test_anim import FakeGuest, FakeSession, FakeVideo, Stage
from test_desktop import ICONS, DesktopGuest


def test_resolve_colour():
    assert desktop.resolve_colour("teal") == (0, 128, 128)
    assert desktop.resolve_colour([1, 2, 3]) == (1, 2, 3)
    for bad in (
        "mauve",
        (256, 0, 0),
        (-1, 0, 0),
        (1, 2),
        (1, 2, 3, 4),
        (1.5, 0, 0),
        5,
        None,
    ):
        with pytest.raises(ValueError):
            desktop.resolve_colour(bad)


def test_colourref_puts_red_in_the_low_byte():
    assert desktop.colourref((200, 10, 30)) == 0x1E0AC8


def test_backdrop_sets_the_colour_in_one_frame():
    guest = FakeGuest()
    scene = Stage()
    scene.run(FakeSession(guest), FakeVideo(guest))
    guest.calls.clear()
    assert Backdrop.claims == ()
    scene.play(Backdrop((200, 10, 30)))
    assert guest.named("SetSysColors") == [
        ("SetSysColors", (1, struct.pack("<I", 1), struct.pack("<I", 0x1E0AC8)))
    ]
    with pytest.raises(ValueError):
        Backdrop("mauve")


def test_set_colour_rehides_the_icons_only_when_they_were_hidden():
    guest = DesktopGuest()
    desktop.set_colour(guest, (1, 2, 3))
    assert not guest.named("ShowWindow")  # icons showing before: left alone
    guest.visible.discard(ICONS)
    guest.calls.clear()
    syncs = guest.syncs
    desktop.set_colour(guest, (1, 2, 3))
    assert guest.named("ShowWindow") == [("ShowWindow", (ICONS, win32.SW_HIDE))]
    assert guest.syncs == syncs + 2  # one for the broadcast, one after the repaint


class DiskGuest(FakeGuest):
    """A guest with a registry, drives and a CD that may hold a file."""

    def __init__(self, drives=(("C", 3), ("D", 5)), files=()):
        super().__init__()
        self.drives, self.files = dict(drives), set(files)
        from test_anim import FakeDll

        self.advapi32, self.kernel32 = (
            FakeDll(self, "advapi32"),
            FakeDll(self, "kernel32"),
        )

    def do_RegOpenKeyExA(self, *args):
        return CallResult(0, 0, [struct.pack("<I", 0x77), b""][:1])

    def do_RegSetValueExA(self, *args):
        return CallResult(0, 0, [])

    def do_GetLogicalDrives(self):
        return CallResult(sum(1 << (ord(d) - 65) for d in self.drives), 0, [])

    def do_GetDriveTypeA(self, path):
        return CallResult(self.drives[path[0]], 0, [])

    def do_GetFileAttributesA(self, path):
        return CallResult(
            0x20 if path in self.files else win32.INVALID_FILE_ATTRIBUTES, 0, []
        )


def test_set_wallpaper_call_order():
    guest = DiskGuest()
    desktop.set_wallpaper(guest, "D:\\W.BMP", "tile")
    names = [c[0] for c in guest.calls]
    assert names == [
        "RegOpenKeyExA",
        "RegSetValueExA",
        "RegSetValueExA",
        "RegCloseKey",
        "SystemParametersInfoA",
    ]
    sets = guest.named("RegSetValueExA")
    assert [(c[1][1], c[1][4]) for c in sets] == [
        ("TileWallpaper", b"1\0"),
        ("WallpaperStyle", b"0\0"),
    ]
    assert guest.calls[-1][1] == (0x14, 0, "D:\\W.BMP", 3)
    assert guest.syncs == 1
    with pytest.raises(KeyError):
        desktop.set_wallpaper(guest, "D:\\W.BMP", "bogus")


def test_cd_drive_picks_the_type_5_drive():
    assert desktop.cd_drive(DiskGuest(drives=(("C", 3), ("E", 5), ("F", 5)))) == "E:\\"
    assert desktop.cd_drive(DiskGuest(drives=(("C", 3),))) is None


def test_wait_for_disc(monkeypatch):
    assert desktop.wait_for_disc(DiskGuest(files={"D:\\W.BMP"}), "W.BMP") == "D:\\W.BMP"
    now = [0.0]
    monkeypatch.setattr(desktop.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(desktop.time, "sleep", lambda s: now.__setitem__(0, now[0] + s))
    with pytest.raises(
        desktop.DesktopError,
        match="wallpaper disc failed:\n  the CD with W.BMP did not show up",
    ):
        desktop.wait_for_disc(DiskGuest(), "W.BMP")
    assert 2.0 <= now[0] < 2.2
