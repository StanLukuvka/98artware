"""The tray re-hide spot, and the hidden parts after a persisted display change.

    uv run art98 vm start            (in the checkout that has the work folder)
    ART98_TEST_WORK=/path/to/work uv run python experiments/taskbar/probe_taskbar_3.py OUTDIR

Attaches to the running VM and reverts before every case. Throwaway probe: no source
edits, no savevm. Reuses the helpers in probe_taskbar.py. Writes OUTDIR/results.json and
a PNG per step.
"""

import importlib.util
import json
import os
import struct
import time
from pathlib import Path

from art98.container.service import attach
from art98.desktop import shell_windows, taskbar_windows
from art98.guest.protocol import Out
from art98.guest.win32 import (
    COLOR_DESKTOP,
    colourref,
    repaint_all,
    screen_size,
    set_display_mode,
    work_area,
)
from art98.settings import load

_spec = importlib.util.spec_from_file_location("p1", Path(__file__).with_name("probe_taskbar.py"))
p1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p1)  # sets p1.OUT from sys.argv[1]
rec, shot = p1.rec, p1.shot

SW_HIDE = 0
RUNS = 5
HIDE = ("buttons", "clock", "tray")


def visible(g):
    found = taskbar_windows(g, shell_windows(g)[0])
    return {name: g.user32.IsWindowVisible(hwnd).value for name, hwnd in found.items()}


def hide(g, *names):
    found = taskbar_windows(g, shell_windows(g)[0])
    for name in names:
        g.user32.ShowWindow(found[name], SW_HIDE)


def set_sys_colour(g, rgb):
    g.user32.SetSysColors(1, struct.pack("<I", COLOR_DESKTOP), struct.pack("<I", colourref(rgb)))


def taskbar_rect(g):
    out = g.user32.GetWindowRect(shell_windows(g)[0], Out(16))
    return list(struct.unpack("<4i", out.buffers[0]))


def tray_case(s, when, run):
    g = s.bridge
    s.revert()
    hide(g, "tray")
    g.sync()
    before = visible(g)["tray"]
    set_sys_colour(g, (200, 10, 30))
    if when == "before_sync":
        hide(g, "tray")
    g.sync()
    after_sync = visible(g)["tray"]
    if when == "after_sync":
        hide(g, "tray")
    repaint_all(g)
    now = visible(g)["tray"]
    time.sleep(2)
    later = visible(g)["tray"]
    if run == 0:
        shot(s, f"tray-{when}")
    return {"hidden": before, "after_sync": after_sync, "now": now, "later": later}


def main():
    rec("psi_start", Path("/proc/pressure/cpu").read_text().splitlines()[0])
    with attach(load(os.environ["ART98_TEST_WORK"])) as s:
        g = s.bridge
        for when in ("before_sync", "after_sync"):
            rec(f"tray.{when}", [tray_case(s, when, n) for n in range(RUNS)])

        for size in [(1024, 768), (640, 480)]:
            name = f"display_{size[0]}"
            s.revert()
            hide(g, *HIDE)
            g.sync()
            hidden = visible(g)
            set_display_mode(g, *size, 16, persist=True)
            g.sync()
            straight = visible(g)
            time.sleep(2)
            settled = visible(g)
            row = {"hidden": hidden, "straight_after": straight, "after_2s": settled,
                   "screen": screen_size(g), "taskbar": taskbar_rect(g),
                   "work_area": work_area(g)}  # fmt: skip
            shot(s, f"{name}-after")
            hide(g, *HIDE)
            g.sync()
            row["rehidden"] = visible(g)
            time.sleep(2)
            row["rehidden_after_2s"] = visible(g)
            shot(s, f"{name}-rehidden")
            rec(name, row)

        s.revert()
        rec("revert_restores", {"visible": visible(g), "screen": screen_size(g)})
    rec("psi_end", Path("/proc/pressure/cpu").read_text().splitlines()[0])
    (p1.OUT / "results.json").write_text(json.dumps(p1.RES, indent=2) + "\n")


if __name__ == "__main__":
    main()
