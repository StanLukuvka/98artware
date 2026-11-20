"""Every driver mode with CDS_UPDATEREGISTRY: the result, the taskbar and the work area.

    .venv/bin/python experiments/display_taskbar/probe_modes.py OUTDIR [WORK]

Reverts before each mode, and checks that a revert brings back 800x600x16.
"""

import json
import time
from pathlib import Path

import probe_display as p
from art98.anim.setstate import display_mode
from art98.container.service import attach

MODES = [(640, 480, 16), (1024, 768, 16), (800, 600, 8), (1024, 768, 8), (640, 480, 24),
         (640, 480, 8), (1280, 1024, 8), (640, 480, 4)]  # fmt: skip


def main():
    p.rec("psi_start", Path("/proc/pressure/cpu").read_text().splitlines()[0])
    with attach(p.SETTINGS) as s:
        g = s.bridge
        for mode in MODES:
            s.revert()
            t = time.perf_counter()
            result = p.change(g, *mode, 1)
            took = time.perf_counter() - t
            g.sync()
            p.rec(f"{mode}", {"cds": result, "took": round(took, 2), "mode": display_mode(g),
                              **p.read(g)})  # fmt: skip
            p.shot(s, "x".join(map(str, mode)))
        s.revert()
        p.rec("after_revert", {"mode": display_mode(g), **p.read(g)})
    p.rec("psi_end", Path("/proc/pressure/cpu").read_text().splitlines()[0])
    (p.OUT / "modes.json").write_text(json.dumps(p.RES, indent=2) + "\n")


if __name__ == "__main__":
    main()
