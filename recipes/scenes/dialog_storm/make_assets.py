"""Draw the wallpaper tile and print its hash for states/wall.json.

python recipes/scenes/dialog_storm/make_assets.py
"""

import hashlib
import struct
from pathlib import Path

ASSETS = Path(__file__).parent / "assets"
WIDTH, HEIGHT = (
    64,
    48,
)  # a tile: the state's "tile" style repeats it over the 800x600 screen


def pixel(x, y):
    """A dark red diamond lattice on a lighter red."""
    if (x + y) % 32 < 3 or (x - y) % 32 < 3:
        return (96, 0, 0)
    return (176, 24, 24)


def write_bmp(path: Path) -> None:
    """A 24-bit bottom-up BMP, the plainest kind Windows 98 loads."""
    stride = (WIDTH * 3 + 3) // 4 * 4
    rows = []
    for y in reversed(range(HEIGHT)):
        row = b"".join(bytes(reversed(pixel(x, y))) for x in range(WIDTH))  # BGR
        rows.append(row + bytes(stride - len(row)))
    pixels = b"".join(rows)
    path.write_bytes(
        b"BM"
        + struct.pack("<IHHI", 54 + len(pixels), 0, 0, 54)
        + struct.pack(
            "<IiiHHIIiiII", 40, WIDTH, HEIGHT, 1, 24, 0, len(pixels), 2835, 2835, 0, 0
        )
        + pixels
    )


if __name__ == "__main__":
    ASSETS.mkdir(exist_ok=True)
    path = ASSETS / "wall.bmp"
    write_bmp(path)
    print(path.name, hashlib.sha256(path.read_bytes()).hexdigest())
