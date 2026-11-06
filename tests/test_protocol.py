import pytest

from art98.protocol import (
    FrameError, Out, crc16, encode_request, frame, parse_values, unframe,
)


def test_crc_matches_ccitt_false_check_value():
    assert crc16(b"123456789") == 0x29B1


def test_frame_round_trip():
    assert unframe(frame(b"7 OK 1")[:-1]) == b"7 OK 1"


@pytest.mark.parametrize("line", [b"", b"7 OK 1", b"7 OK 2 *0000", b"7 OK 1 *zzzz"])
def test_bad_frames_are_rejected(line):
    with pytest.raises(FrameError):
        unframe(line)


def test_encode_request_covers_every_argument_kind():
    line = encode_request(3, "CALL", ("user32", -1, None, True, b"\xab\x01", Out(16)))
    assert unframe(line[:-1]) == b'3 CALL "user32" 4294967295 0 1 #ab01 &16'


def test_strings_escape_quotes_backslashes_and_controls():
    line = encode_request(1, "SPAWN", ('say "hi"\\\n',))
    assert unframe(line[:-1]) == b'1 SPAWN "say \\"hi\\"\\\\\\x0a"'


def test_parse_values():
    assert parse_values(b'12 0x10 "a \\"b\\" \\x41" #00ff') == [12, 16, 'a "b" A', b"\x00\xff"]


def test_strings_use_the_windows_code_page():
    assert parse_values('"caf\u00e9"'.encode("cp1252")) == ["caf\u00e9"]
