"""Rendering a scene: VM, recorder, output file."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from ..recorder import GIF_COLORS, GIF_FPS, H264
from ..session import stage


def write_gif(source: Path | str, output: Path | str, fps: int = GIF_FPS, colors: int = GIF_COLORS,
              scale: float = 1.0, dither: str = "none") -> Path:
    """Convert a video to a GIF with its own palette, keeping pixels sharp."""
    size = "" if scale == 1 else f"scale=iw*{scale}:ih*{scale}:flags=neighbor,"
    graph = (
        f"fps={fps},{size}split[a][b];"
        f"[a]palettegen=max_colors={colors}:stats_mode=diff[palette];"
        f"[b][palette]paletteuse=dither={dither}:diff_mode=rectangle"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(source), "-filter_complex", graph,
         "-loop", "0", str(output)],
        check=True,
    )
    return Path(output)


def render(scene, output: Path | str | None = None, *, gif: Path | str | None = None,
           work: Path | str = "work", gif_fps: int = GIF_FPS, gif_colors: int = GIF_COLORS,
           gif_scale: float = 1.0, gif_dither: str = "none", display: str = "none",
           backend: str | None = None) -> Path:
    """Play a scene on a private copy of the prepared image and write the video.

    `output` ends in .mp4 or .gif. `gif` asks for a GIF as well. A GIF is made
    from a lossless recording, because 4:2:0 video smears 1-pixel coloured
    text. The prepared image itself is only copied, never written. backend is
    "local" or "container", as for `boot`.
    """
    scene = scene() if isinstance(scene, type) else scene
    output = Path(output or f"{type(scene).__name__}.mp4")
    if output.suffix == ".gif":
        gif, output = output, None
    temp = Path(tempfile.mkdtemp(prefix="art98-render-")) if gif else None
    master = temp / "master.mkv" if temp else output
    try:
        with stage(work, display=display, backend=backend) as session:
            with session.record(master, fps=scene.fps, lossless=bool(gif)) as video:
                scene.run(session, video)
        if gif:
            write_gif(master, gif, gif_fps, gif_colors, gif_scale, gif_dither)
            if output:
                subprocess.run(
                    ["ffmpeg", "-y", "-loglevel", "error", "-i", str(master), *H264, str(output)],
                    check=True,
                )
    finally:
        if temp:
            shutil.rmtree(temp, ignore_errors=True)
    return output or Path(gif)
