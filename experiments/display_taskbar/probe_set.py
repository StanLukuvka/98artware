"""A Set to a state at 640x480 and 1024x768 through Scene.set_state, with a screenshot of each.

.venv/bin/python experiments/display_taskbar/probe_set.py OUTDIR [WORK]
"""

import json
from pathlib import Path

import probe_display as p
from art98.anim import Scene
from art98.container.service import attach


def main():
    p.rec("psi_start", Path("/proc/pressure/cpu").read_text().splitlines()[0])
    with attach(p.SETTINGS) as s:
        scene = Scene()
        scene.desktop = "stock"
        scene.session, scene.guest, scene.vm = s, s.bridge, s.vm
        for mode in [(640, 480, 16), (1024, 768, 16)]:
            path = p.OUT / f"state-{mode[0]}.json"
            path.write_text(
                json.dumps({"version": 1, "display": mode, "pointer": [200, 150]})
            )
            scene.set_state(path)
            p.rec(f"set{mode[0]}", {"space_work": scene.work_area, **p.read(s.bridge)})
            p.shot(s, f"set-{mode[0]}")
        s.revert()
    p.rec("psi_end", Path("/proc/pressure/cpu").read_text().splitlines()[0])


if __name__ == "__main__":
    main()
