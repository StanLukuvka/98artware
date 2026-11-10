"""Draw the sample's two BMPs and print their hashes for the state files.

    python artware_experiments/set_state/make_assets.py
"""

import hashlib
import math
import struct
from pathlib import Path

ASSETS = Path(__file__).parent / "assets"
WIDTH, HEIGHT = 160, 120


def write_bmp(path: Path, pixel) -> None:
    """A 24-bit bottom-up BMP, the plainest kind Windows 98 loads."""
    stride = (WIDTH * 3 + 3) // 4 * 4
    rows = []
    for y in reversed(range(HEIGHT)):
        row = b"".join(bytes(reversed(pixel(x, y))) for x in range(WIDTH))  # BGR
        rows.append(row + bytes(stride - len(row)))
    pixels = b"".join(rows)
    path.write_bytes(
        b"BM" + struct.pack("<IHHI", 54 + len(pixels), 0, 0, 54)
        + struct.pack("<IiiHHIIiiII", 40, WIDTH, HEIGHT, 1, 24, 0, len(pixels), 2835, 2835, 0, 0)
        + pixels)


def flower(x, y):
    dx, dy = x - 80, y - 56
    r, angle = math.hypot(dx, dy), math.atan2(dy, dx)
    if r < 12:
        return (255, 200, 0)
    if r < 26 + 14 * math.cos(5 * angle):
        return (220, 40, 120)
    if y > 70 and abs(x - 80) < 3:
        return (0, 128, 0)
    return (255, 255, 255)


def sky(x, y):
    if math.hypot(x - 120, y - 30) < 16:
        return (255, 255, 0)
    if y > 96:
        return (0, 128, 0)
    blue = 255 - y
    return (blue // 3, blue // 2 + 40, 255)


if __name__ == "__main__":
    ASSETS.mkdir(exist_ok=True)
    for name, pixel in (("flower.bmp", flower), ("sky.bmp", sky)):
        path = ASSETS / name
        write_bmp(path, pixel)
        print(name, hashlib.sha256(path.read_bytes()).hexdigest())
