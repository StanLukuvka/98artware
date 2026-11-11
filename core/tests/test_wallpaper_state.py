"""The desktop block of a state: reading it, applying it and checking it, against stand-in guests."""

import hashlib
import json
import struct
from types import SimpleNamespace

import pytest
from art98 import desktop
from art98.anim import setstate
from art98.bridge import CallResult
from art98.state import DesktopState, State, StateError, WindowState, load_state
from test_backdrop import DiskGuest


def bmp(width=4, height=3, rgb=(10, 200, 30)):
    stride = (width * 3 + 3) // 4 * 4
    pixels = (bytes(rgb[::-1]) * width).ljust(stride, b"\0") * height
    return (
        b"BM"
        + struct.pack("<IHHI", 54 + len(pixels), 0, 0, 54)
        + struct.pack(
            "<IiiHHIIiiII", 40, width, height, 1, 24, 0, len(pixels), 0, 0, 0, 0
        )
        + pixels
    )


def ref(folder, name="wall.bmp", data=None):
    data = bmp() if data is None else data
    (folder / name).write_bytes(data)
    return {"file": name, "sha256": hashlib.sha256(data).hexdigest()}


def load(folder, desk, **top):
    path = folder / "state.json"
    path.write_text(json.dumps({"version": 1, "desktop": desk, **top}))
    return load_state(path)


def problems(folder, desk):
    with pytest.raises(StateError) as caught:
        load(folder, desk)
    return caught.value.problems


def test_a_full_desktop_block_loads(tmp_path):
    state = load(
        tmp_path, {"colour": [0, 128, 128], "wallpaper": ref(tmp_path), "style": "tile"}
    )
    assert state.desktop.colour == (0, 128, 128)
    assert state.desktop.style == "tile"
    assert state.desktop.wallpaper.data == bmp()
    assert load(tmp_path, {"colour": [1, 2, 3]}).desktop == DesktopState(
        (1, 2, 3), None, "center"
    )
    assert load(tmp_path, {"wallpaper": ref(tmp_path)}).desktop.style == "center"


def test_a_state_without_desktop_has_none(tmp_path):
    (tmp_path / "s.json").write_text('{"version": 1}')
    assert load_state(tmp_path / "s.json").desktop is None


def test_every_desktop_error_message(tmp_path):
    ok = ref(tmp_path)
    junk = ref(tmp_path, "text.bmp", b"hello world, not a bitmap at all")
    assert problems(tmp_path, {"colour": [1, 2]}) == [
        "desktop.colour: needs 3 whole numbers"
    ]
    assert problems(tmp_path, {"colour": [1, 2, True]}) == [
        "desktop.colour: needs 3 whole numbers"
    ]
    assert problems(tmp_path, {"colour": [1, 2, 256]}) == [
        "desktop.colour: needs numbers from 0 to 255"
    ]
    assert problems(tmp_path, {"colour": [-1, 2, 3]}) == [
        "desktop.colour: needs numbers from 0 to 255"
    ]
    [p] = problems(tmp_path, {"wallpaper": {"file": "nope.bmp", "sha256": "0"}})
    assert p.startswith("desktop.wallpaper.file:") and "doesn't exist" in p
    [p] = problems(tmp_path, {"wallpaper": {**ok, "sha256": "0" * 64}})
    assert p.startswith("desktop.wallpaper.sha256: should be " + ok["sha256"])
    [p] = problems(tmp_path, {"wallpaper": junk})
    assert p.startswith("desktop.wallpaper: ") and "is not a BMP file" in p
    assert problems(tmp_path, {"wallpaper": ok, "style": "wavy"}) == [
        "desktop.style: should be one of center, tile, stretch, not 'wavy'"
    ]
    assert problems(tmp_path, {"style": "tile"}) == ["desktop.style: needs a wallpaper"]
    assert problems(tmp_path, {"icons": [], "tray": 1, "bogus": 2}) == [
        "desktop.bogus: unknown field",
        "desktop.icons: not supported yet: desktop icons come after this milestone",
        "desktop.tray: not supported yet: the tray comes after this milestone",
    ]
    assert problems(tmp_path, [1]) == ["desktop: should be an object"]


class Session:
    def __init__(self, log):
        self.log = log

    def attach_disc(self, files):
        self.log.append(("attach_disc", files))


class Guest(DiskGuest):
    """A CD that holds WALL0001.BMP, an 800x600 screen and one readable pixel colour."""

    def __init__(self, pixel=(10, 200, 30), colour=(0, 128, 128), log=None):
        super().__init__(files={"D:\\WALL0001.BMP"})
        self.pixel, self.colour, self.log = (
            pixel,
            colour,
            log if log is not None else [],
        )
        self.gdi32 = self.user32

    def handle(self, dll, function, args):
        if function in ("SetSysColors", "SystemParametersInfoA"):
            self.log.append(function)
        return super().handle(dll, function, args)

    def do_GetSystemMetrics(self, index):
        return CallResult({0: 800, 1: 600}.get(index, 0), 0, [])

    def do_GetSysColor(self, index):
        return CallResult(desktop.colourref(self.colour), 0, [])

    def do_GetDC(self, hwnd):
        return CallResult(5, 0, [])

    def do_GetPixel(self, dc, x, y):
        self.log.append(("GetPixel", x, y))
        return CallResult(desktop.colourref(self.pixel), 0, [])


def stub_scene(guest, log, monkeypatch):
    class App:
        @staticmethod
        def from_state(window):
            log.append(("from_state", window.id))
            return SimpleNamespace(hwnd=1)

    monkeypatch.setattr(setstate, "APPS", {"picture": App})
    monkeypatch.setattr(setstate, "repaint_window", lambda *a: None)
    return SimpleNamespace(
        guest=guest,
        session=Session(log),
        pointer=None,
        add=lambda prop: log.append("add"),
    )


def window():
    return WindowState("w", "picture", "Picture", (100, 100), (200, 150))


def kinds(log):
    return [e[0] if isinstance(e, tuple) else e for e in log]


def test_apply_attaches_the_disc_before_windows_and_sets_colour_then_wallpaper(
    tmp_path, monkeypatch
):
    log = []
    guest = Guest(log=log)
    scene = stub_scene(guest, log, monkeypatch)
    state = load(
        tmp_path, {"colour": [1, 2, 3], "wallpaper": ref(tmp_path), "style": "stretch"}
    )
    state = State(state.path, None, (window(),), None, state.desktop)
    setstate.apply_state(scene, state)
    k = kinds(log)
    assert (
        k.index("SetSysColors")
        < k.index("attach_disc")
        < k.index("SystemParametersInfoA")
    )
    assert k.index("SystemParametersInfoA") < k.index("from_state") < k.index("add")
    assert log[k.index("attach_disc")] == ("attach_disc", {"WALL0001.BMP": bmp()})
    assert [
        c[1][2] for c in guest.named("SystemParametersInfoA") if c[1][0] == 0x14
    ] == ["D:\\WALL0001.BMP"]


def test_a_state_without_desktop_makes_no_disc_call_and_touches_nothing(
    tmp_path, monkeypatch
):
    log = []
    guest = Guest(log=log)
    scene = stub_scene(guest, log, monkeypatch)
    setstate.apply_state(scene, State(tmp_path / "s.json", None, (window(),), None))
    assert "attach_disc" not in kinds(log)
    assert not guest.named("SetSysColors", "RegSetValueExA", "SystemParametersInfoA")


def checked(tmp_path, guest, desk, windows=()):
    state = load(tmp_path, desk)
    state = State(state.path, None, tuple(windows), None, state.desktop)
    props = {w.id: SimpleNamespace(hwnd=1) for w in windows}
    guest.windows = list
    try:
        setstate.check_state(SimpleNamespace(guest=guest), state, props)
    except setstate.StateMismatch as error:
        # the stand-in has no windows, so only the desktop lines matter here
        error.problems = [p for p in error.problems if p.startswith("desktop.")]
        if error.problems:
            raise


def test_check_state_fails_on_a_wrong_colour(tmp_path):
    with pytest.raises(setstate.StateMismatch) as caught:
        checked(tmp_path, Guest(colour=(1, 2, 3)), {"colour": [4, 5, 6]})
    assert caught.value.problems[0].startswith("desktop.colour:")
    checked(tmp_path, Guest(colour=(4, 5, 6)), {"colour": [4, 5, 6]})


def test_check_state_compares_one_wallpaper_pixel_within_tolerance(tmp_path):
    wall = {
        "wallpaper": ref(tmp_path, data=bmp(800, 600, (10, 200, 30)))
    }  # fills the screen
    checked(tmp_path, Guest(pixel=(18, 192, 24)), wall)  # 16 bpp rounding is inside 12
    with pytest.raises(setstate.StateMismatch) as caught:
        checked(tmp_path, Guest(pixel=(200, 0, 0)), wall)
    assert caught.value.problems[0].startswith("desktop.wallpaper: pixel [")


def test_the_wallpaper_pixel_is_taken_where_no_window_is_and_above_the_taskbar(
    tmp_path,
):
    log = []
    wall = {"wallpaper": ref(tmp_path, data=bmp(800, 600))}
    over = WindowState("w", "picture", "P", (300, 200), (200, 200))  # covers the centre
    checked(tmp_path, Guest(log=log), wall, [over])
    [(_, x, y)] = [e for e in log if isinstance(e, tuple) and e[0] == "GetPixel"]
    assert (x, y) == (200, 150)
    assert y < 572


def test_expected_pixel_for_each_style():
    data = bmp(2, 2, (9, 8, 7))
    desk = lambda style: DesktopState(None, SimpleNamespace(data=data), style)
    bg = (1, 1, 1)
    assert setstate.expected_pixel(desk("center"), (800, 600), bg, 400, 300) == (
        9,
        8,
        7,
    )
    assert setstate.expected_pixel(desk("center"), (800, 600), bg, 10, 10) == bg
    assert setstate.expected_pixel(desk("tile"), (800, 600), bg, 10, 10) == (9, 8, 7)
    assert setstate.expected_pixel(desk("stretch"), (800, 600), bg, 10, 10) == (9, 8, 7)


def odd_bmps():
    rle = bytearray(bmp(4, 3))
    rle[28:30] = struct.pack("<H", 8)  # 8 bpp ...
    rle[30:34] = struct.pack("<I", 1)  # ... BI_RLE8
    rle += b"\0" * 1100
    pixels = b"\x01\x02\x03" * 4  # 12-byte header: 16-bit size, 3-byte palette entries
    os2 = (
        b"BM"
        + struct.pack("<IHHI", 26 + len(pixels), 0, 0, 26)
        + struct.pack("<IHHHH", 12, 4, 1, 1, 24)
        + pixels
    )
    return [bytes(rle), os2]


def test_rle_and_os2_bmps_skip_the_pixel_check_without_raising(tmp_path):
    for data in odd_bmps():
        guest_bmp = setstate.check_bmp(data)  # accepted as a wallpaper
        assert guest_bmp[0] == 4
        assert setstate.bmp_pixel(data, 1, 0) is None
        for style in ("tile", "stretch"):
            assert (
                setstate.expected_pixel(
                    DesktopState(None, SimpleNamespace(data=data), style),
                    (800, 600),
                    (1, 1, 1),
                    10,
                    10,
                )
                is None
            )
        checked(
            tmp_path,
            Guest(pixel=(200, 0, 0)),
            {"wallpaper": ref(tmp_path, data=data), "style": "tile"},
        )
