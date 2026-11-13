"""Shared helpers for the three VM-service probes: scenes, CPU pressure, run-copy size."""

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(HERE / "recipes" / "scenes"))

from art98.anim import Close, Notepad, Scene, TypeWithCursor
from art98.settings import load

SETTINGS = load(HERE / "work")


class Short(Scene):
    """About 1 s of video: for the disk-growth loop."""

    desktop = "stock"

    def construct(self):
        pad = Notepad()
        self.add(pad)
        self.pause(0.3)
        self.play(TypeWithCursor(pad, "probe"))
        self.pause(0.3)
        self.play(Close(pad))


class Longer(Scene):
    """About 6 s of video (the Hello scene): something to kill in the middle of."""

    desktop = "stock"

    def construct(self):
        pad = Notepad()
        self.add(pad)
        self.pause(0.5)
        self.play(TypeWithCursor(pad, "hello from 1998"))
        self.wait(1)
        self.pause(2)
        self.play(Close(pad))
        self.pause(1)


def cpu():
    """The 'some avg10' value of /proc/pressure/cpu."""
    text = Path("/proc/pressure/cpu").read_text()
    return float(re.search(r"some avg10=([\d.]+)", text).group(1))


def run_copy():
    """The service's run-copy qcow2 (runs/vm-*/golden.qcow2)."""
    found = sorted((SETTINGS.work_dir / "runs").glob("vm-*/golden.qcow2"))
    return found[-1] if found else None


def sizes(path):
    """(allocated MiB, apparent MiB) of a file."""
    st = path.stat()
    return round(st.st_blocks * 512 / 2**20, 2), round(st.st_size / 2**20, 2)
