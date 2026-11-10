"""Files the host copies to the guest, named by their content.

A revert throws away everything copied since the baseline, so anything a
scene needs on the guest is copied again when it is missing. Each file goes in
a folder named after its hash, so a file that is there is the right one, and
checking for it costs one call instead of a copy.
"""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path

GUEST_DIR = r"C:\ART98"
INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF
BAD_NAME_CHARS = set('\\/:*?"<>|')
BMP_HEADER_SIZES = {12, 40, 52, 56, 108, 124}
BMP_DEPTHS = {1, 4, 8, 16, 24, 32}
BI_RGB, BI_BITFIELDS = 0, 3


def guest_build() -> Path:
    """Where `make` in windows_handlers/ leaves the programs that run on the guest."""
    return Path(__file__).resolve().parents[2] / "windows_handlers" / "build"


def guest_path(data: bytes, name: str) -> str:
    """The guest path for these bytes: C:\\ART98\\F<7 hex digits>\\<name>."""
    if not name or set(name) & BAD_NAME_CHARS:
        raise ValueError(f"{name!r} can't be a file name on the guest")
    return rf"{GUEST_DIR}\F{hashlib.sha256(data).hexdigest()[:7]}\{name}"


def ensure(guest, data: bytes, name: str) -> str:
    """Copy data to the guest unless it is there already, and return its path."""
    path = guest_path(data, name)
    if guest.kernel32.GetFileAttributesA(path).value == INVALID_FILE_ATTRIBUTES:
        guest.kernel32.CreateDirectoryA(path.rsplit("\\", 1)[0], 0)
        guest.put_file(path, data)
    return path


def viewer() -> bytes:
    """VIEW.EXE, the picture window, as built in windows_handlers/build."""
    path = guest_build() / "view.exe"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing; run make in windows_handlers/")
    return path.read_bytes()


def check_bmp(data: bytes, source: str = "image") -> tuple[int, int]:
    """Return a BMP's (width, height), or raise ValueError if it isn't one Windows 98 can load."""
    if len(data) < 26 or data[:2] != b"BM":
        raise ValueError(f"{source} is not a BMP file")
    header = struct.unpack_from("<I", data, 14)[0]
    if header not in BMP_HEADER_SIZES or len(data) < 14 + header:
        raise ValueError(f"{source} has a BMP header Windows 98 can't read (size {header})")
    compression = 0
    if header == 12:
        width, height, _, depth = struct.unpack_from("<HHHH", data, 18)
    else:
        width, height, _, depth, compression = struct.unpack_from("<iiHHI", data, 18)
    if width <= 0 or height == 0:
        raise ValueError(f"{source} has no pixels ({width}x{height})")
    if depth not in BMP_DEPTHS:
        raise ValueError(f"{source} uses {depth} bits per pixel, which Windows 98 can't load")
    # LoadImage on Windows 98 can crash reading past the end, so the pixels must all be there.
    pixels = struct.unpack_from("<I", data, 10)[0]
    needed = pixels + (width * depth + 31) // 32 * 4 * abs(height)
    if compression in (BI_RGB, BI_BITFIELDS) and len(data) < needed:
        raise ValueError(f"{source} is cut short: {len(data)} bytes, its header needs {needed}")
    if pixels >= len(data):
        raise ValueError(f"{source} is cut short: its pixels would start past the end")
    return width, abs(height)
