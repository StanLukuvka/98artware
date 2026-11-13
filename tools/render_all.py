"""Render every gallery scene to docs/assets/gifs, one at a time on the VM service.

uv run python tools/render_all.py [name ...]

`art98 vm start` must be running. Each render goes into a temporary folder, and only the
final GIF is moved into docs/assets/gifs, so the per-section -NN.mp4 clips never land there.
"""

import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "assets" / "gifs"

# file, scene, GIF options
SCENES = {
    "blank_start": ("BlankStart", ["--gif-fps", "15", "--gif-colors", "64"]),
    "hero": ("Hero", ["--gif-fps", "15", "--gif-colors", "64"]),
    "mvp": ("Mvp", ["--gif-fps", "15", "--gif-colors", "64"]),
    "hello": ("Hello", ["--gif-fps", "12", "--gif-colors", "32"]),
    "pointer_clicks": ("PointerClicks", ["--gif-fps", "12", "--gif-colors", "64"]),
    "typing": ("Typing", ["--gif-fps", "12", "--gif-colors", "32"]),
    "window_motion": ("WindowMotion", ["--gif-fps", "15", "--gif-colors", "48"]),
    "drag_window": ("DragWindow", ["--gif-fps", "15", "--gif-colors", "48"]),
    "menus_keys": ("MenusKeys", ["--gif-fps", "12", "--gif-colors", "32"]),
    "hover_dialog": ("HoverDialog", ["--gif-fps", "12", "--gif-colors", "64"]),
    "paint_drawing": ("PaintDrawing", ["--gif-fps", "12", "--gif-colors", "48"]),
    "minesweeper_win": ("MinesweeperWin", ["--gif-fps", "10", "--gif-colors", "48"]),
    "dialog_storm": ("DialogStorm", ["--gif-fps", "12", "--gif-colors", "64"]),
    "screensaver": ("ScreensaverRun", ["--gif-fps", "12", "--gif-colors", "64"]),
}


def render(name: str) -> str:
    scene, options = SCENES[name]
    final = OUT / f"{name.replace('_', '-')}.gif"
    folders = ("gallery", ".", "mvp", "blank_start", "dialog_storm", "readme")
    source = next(
        path
        for folder in folders
        if (path := ROOT / "recipes" / "scenes" / folder / f"{name}.py").exists()
    )
    # The clips cut() writes beside the output stay in this folder.
    folder = Path(tempfile.mkdtemp(prefix=f"render-{name}-"))
    try:
        made = folder / final.name
        subprocess.run(
            [
                sys.executable,
                "-m",
                "art98.cli",
                "render",
                str(source),
                scene,
                "-o",
                str(made),
                "--work",
                str(ROOT / "work"),
                "--wait",
                "900",
                *options,
            ],
            check=True,
            cwd=ROOT,
        )
        shutil.move(made, final)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    return f"{final.name}: {final.stat().st_size / 1e6:.2f} MB"


def check_service() -> None:
    """Stop with the service's own message unless `art98 vm status` says it is up."""
    done = subprocess.run(  # noqa: PLW1510
        [
            sys.executable,
            "-m",
            "art98.cli",
            "vm",
            "status",
            "--work",
            str(ROOT / "work"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if done.returncode != 0:
        message = (done.stdout + done.stderr).strip()
        raise SystemExit(message or "art98 vm status failed")
    print(done.stdout, end="")


if __name__ == "__main__":
    check_service()
    OUT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(1) as pool:  # one VM service: one render at a time
        for line in pool.map(render, sys.argv[1:] or SCENES):
            print(line)
