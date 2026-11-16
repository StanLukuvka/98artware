"""guestfiles: where the guest programs are."""

import struct

import pytest
from art98.errors import MissingFile, UsageError
from art98.guest import guestfiles


def test_art98_guest_build_overrides_the_checkout_folder(tmp_path, monkeypatch):
    monkeypatch.delenv("ART98_GUEST_BUILD", raising=False)
    assert guestfiles.guest_build().parts[-2:] == ("guest", "build")
    monkeypatch.setenv("ART98_GUEST_BUILD", str(tmp_path))
    assert guestfiles.guest_build() == tmp_path


def test_guest_build_missing_is_a_missing_file():
    assert issubclass(guestfiles.GuestBuildMissing, MissingFile)


def test_text_limit_counts_the_bytes_after_line_ends_are_fixed():
    lines = b"a\n" * 20_000  # 40 000 bytes, 60 000 once every line ends in CRLF
    with pytest.raises(UsageError, match="after line ends are fixed"):
        guestfiles.check_text(lines)
    assert len(guestfiles.check_text(b"a\n" * 10_000)) == 30_000


def bmp_with(compression):
    header = struct.pack("<IiiHHIIiiII", 40, 1, 1, 1, 24, compression, 4, 0, 0, 0, 0)
    return b"BM" + struct.pack("<IHHI", 58, 0, 0, 54) + header + bytes(4)


@pytest.mark.parametrize("compression", [0, 1, 2, 3])
def test_bmp_compression_windows_can_load_is_accepted(compression):
    assert guestfiles.check_bmp(bmp_with(compression)) == (1, 1)


@pytest.mark.parametrize("compression", [4, 5])
def test_jpeg_and_png_inside_a_bmp_are_refused(compression):
    with pytest.raises(UsageError, match=f"compression {compression}"):
        guestfiles.check_bmp(bmp_with(compression))


@pytest.mark.parametrize(
    "name", ["CON", "con", "NUL.txt", "Aux.tar.gz", "COM1", "lpt9.bmp", "PRN"]
)
def test_dos_device_names_are_refused(name):
    assert "DOS device" in guestfiles.name_problem(name)


@pytest.mark.parametrize(
    "name", ["CONSOLE.txt", "COM0", "COM10", "a.con", "flower.bmp"]
)
def test_names_that_only_look_like_devices_are_fine(name):
    assert guestfiles.name_problem(name) is None


def test_a_name_over_max_name_is_refused():
    assert guestfiles.name_problem("a" * guestfiles.MAX_NAME) is None
    assert "characters" in guestfiles.name_problem("a" * (guestfiles.MAX_NAME + 1))
    path = guestfiles.guest_path(b"x", "a" * guestfiles.MAX_NAME)
    assert len(path) < 260


def test_not_cp1252_names_the_characters_windows_cannot_hold():
    assert guestfiles.not_cp1252("caf\u00e9") == ""
    assert guestfiles.not_cp1252("a\u65e5\u672cb") == "\u65e5\u672c"
