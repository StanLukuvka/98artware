"""M7b scratch scene: stock desktop, a Picture and a Notepad moved across the icon area.

    . .tools/env.sh
    STRAY_OUT=DIR [STRAY_NO_REPAINT=1] .venv/bin/art98 render experiments/host-checks/stray_labels.py \
        --work work -o DIR/stray.mp4
`art98 vm start` must be running (the render attaches to the VM service).

After every move a `Snap` shoots the screen three ways: A0 right away, A1 after
`guest.sync()`, R after a full RedrawWindow of the desktop and every top-level
window plus sync. Pixels where A0 or A1 differs from R are stale (a label or
frame left behind). STRAY_NO_REPAINT=1 turns `win32.repaint_window` into a no-op
to show what the repaint in `place_window` is worth. Results go to DIR/snaps.json.
"""

import json
import os
import time
from pathlib import Path

from art98 import win32
from art98.anim import *
from art98.base.animation import Instant

OUT = Path(os.environ.get("STRAY_OUT", "."))
LOG = []
if os.environ.get("STRAY_NO_REPAINT"):
    win32.repaint_window = lambda guest, hwnd: None


def read(path):
    data = Path(path).read_bytes()
    w, h = map(int, data.split(None, 4)[1:3])
    return w, h, data[len(data) - w * h * 3 :]


def diff(a, b):
    """Differing pixels and their bounding box, row by row."""
    w, h, pa = a
    pb = b[2]
    n, box = 0, None
    for y in range(h):
        ra, rb = pa[y * w * 3 : (y + 1) * w * 3], pb[y * w * 3 : (y + 1) * w * 3]
        if ra == rb:
            continue
        xs = [x for x in range(w) if ra[x * 3 : x * 3 + 3] != rb[x * 3 : x * 3 + 3]]
        n += len(xs)
        b2 = [xs[0], y, xs[-1], y]
        box = (
            b2
            if box is None
            else [
                min(box[0], b2[0]),
                min(box[1], y),
                max(box[2], b2[2]),
                max(box[3], y),
            ]
        )
    return n, box


class Snap(Instant):
    def __init__(self, name, prop=None):
        super().__init__(None)
        self.name, self.prop = name, prop

    def act(self):
        g, vm = self.scene.guest, self.scene.vm
        shot = lambda tag: (
            vm.screenshot(OUT / f"{self.name}_{tag}.ppm", format="ppm"),
            read(OUT / f"{self.name}_{tag}.ppm"),
        )[1]
        a0 = shot("A0")
        t = time.monotonic()
        g.sync()
        t_sync = time.monotonic() - t
        a1 = shot("A1")
        own = None
        if (
            self.prop is not None
        ):  # R1: repaint only the moved window, as repaint_window does
            t = time.monotonic()
            win32.repaint_window(g, self.prop.hwnd)
            t_own = time.monotonic() - t
            g.sync()
            own = [
                diff(shot("R1"), read(OUT / f"{self.name}_A1.ppm"))[0],
                round(t_own, 4),
            ]
        t = time.monotonic()
        desk = g.find_window(class_name="Progman").hwnd
        for hwnd in [desk] + [
            p.hwnd for p in self.scene.props if getattr(p, "hwnd", None)
        ]:
            g.user32.RedrawWindow(hwnd, 0, 0, win32.RDW_REPAINT_ALL)
        g.sync()
        t_redraw = time.monotonic() - t
        r = shot("R")
        n0, b0 = diff(a0, r)
        n1, b1 = diff(a1, r)
        LOG.append(
            {
                "snap": self.name,
                "A0_vs_R": [n0, b0],
                "A1_vs_R": [n1, b1],
                "own_repaint_changed_px_and_s": own,
                "sync_s": round(t_sync, 4),
                "redraw_all_s": round(t_redraw, 4),
                "psi": Path("/proc/pressure/cpu").read_text().split()[1],
            }
        )
        (OUT / "snaps.json").write_text(json.dumps(LOG, indent=1))


class StrayLabels(Scene):
    desktop = "stock"
    pointer_visible = True

    def construct(self):
        flower = Picture(
            "Flower",
            image="examples/mvp/assets/flower.bmp",
            at=(200, 120),
            size=(240, 200),
        )
        note = Notepad(open=None, at=(420, 300), size=(300, 200))
        self.add(flower, note)
        self.pause(1)
        self.play(Snap("s0_open"))
        self.play(
            Teleport(flower, to=(20, 20), aligned_edge=UL)
        )  # onto the icon column
        self.play(Snap("s1_teleport_onto_icons", flower))
        self.play(Teleport(flower, to=(400, 80), aligned_edge=UL))  # off the icons
        self.play(Snap("s2_teleport_off_icons", flower))
        self.play(Teleport(note, to=(10, 300), aligned_edge=UL))
        self.play(Snap("s3_note_teleport_icons", note))
        self.play(
            Drag(note.title_bar, by=(300, -150)), run_time=1.5
        )  # drag off the icons
        self.play(Snap("s4_note_drag_off", note))
        self.play(
            Drag(flower.title_bar, by=(-380, 60)), run_time=1.5
        )  # drag across the icons
        self.play(Snap("s5_flower_drag_on", flower))
        self.play(Drag(flower.title_bar, by=(400, 100)), run_time=1.5)
        self.play(Snap("s6_flower_drag_off", flower))
        self.pause(0.5)
