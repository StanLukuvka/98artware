"""Render every gallery scene to docs/assets/gifs, a few VMs at a time.

    uv run python artware_experiments/gallery/render_all.py [name ...]
"""

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "assets" / "gifs"

# file, scene, GIF options
SCENES = {
    "hello": ("Hello", ["--gif-fps", "12", "--gif-colors", "32"]),
    "pointer_clicks": ("PointerClicks", ["--gif-fps", "12", "--gif-colors", "64"]),
    "typing": ("Typing", ["--gif-fps", "12", "--gif-colors", "32"]),
    "window_motion": ("WindowMotion", ["--gif-fps", "15", "--gif-colors", "48"]),
    "drag_window": ("DragWindow", ["--gif-fps", "15", "--gif-colors", "48"]),
    "menus_keys": ("MenusKeys", ["--gif-fps", "12", "--gif-colors", "32"]),
    "hover_dialog": ("HoverDialog", ["--gif-fps", "12", "--gif-colors", "64"]),
    "paint_drawing": ("PaintDrawing", ["--gif-fps", "12", "--gif-colors", "48"]),
    "minesweeper_win": ("MinesweeperWin", ["--gif-fps", "10", "--gif-colors", "48"]),
    "screensaver": ("ScreensaverRun", ["--gif-fps", "12", "--gif-colors", "64"]),
}


def render(name: str) -> str:
    scene, options = SCENES[name]
    output = OUT / f"{name.replace('_', '-')}.gif"
    source = ROOT / "artware_experiments" / "gallery" / f"{name}.py"
    if not source.exists():
        source = ROOT / "artware_experiments" / f"{name}.py"
    subprocess.run(
        [sys.executable, "-m", "art98.cli", "render", str(source), scene, "-o", str(output), "--work", str(ROOT / "work"), *options],
        check=True, cwd=ROOT,
    )
    return f"{output.name}: {output.stat().st_size / 1e6:.2f} MB"


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(3) as pool:
        for line in pool.map(render, sys.argv[1:] or SCENES):
            print(line)
