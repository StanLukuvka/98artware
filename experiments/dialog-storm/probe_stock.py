"""P0: does a stock desktop plus SetSysColors(COLOR_DESKTOP) look right?

Run: . .tools/env.sh; .venv/bin/python experiments/dialog-storm/probe_stock.py OUTDIR
Local backend only, private stage, no snapshot saved. Screenshots go to OUTDIR
(keep it outside the repo). Per colour and per desktop (stock, blank) it saves:
  <desk>-<colour>-a.png  right after SetSysColors + guest.sync()
  <desk>-<colour>-b.png  after RedrawWindow(Progman, REPAINT_ALL) + sync
  blank only: <desk>-<colour>-c.png after ShowWindow(icons, SW_HIDE) again
  <desk>-<colour>-n.png  (stock) with a Notepad on top, after the repaint
and prints pixel samples. A fresh revert() separates desktops, not colours.
"""

import struct
import sys
import time
from pathlib import Path

from art98.desktop import blank, shell_windows
from art98.session import stage
from art98.win32 import RDW_REPAINT_ALL

COLOURS = {
    "teal": (0, 128, 128),
    "darkred": (128, 0, 0),
    "red": (255, 0, 0),
    "white": (255, 255, 255),
}
# probes: desktop gap, first icon label (My Computer text ~ (40,62)), taskbar, Start button
POINTS = {
    "bg": (400, 300),
    "label_bg": (22, 64),
    "taskbar": (400, 590),
    "start": (30, 590),
    "tray": (770, 590),
}


def colourref(r, g, b):
    return r | g << 8 | b << 16


def pressure():
    return Path("/proc/pressure/cpu").read_text().splitlines()[0]


def shot(session, out, name):
    ppm = session.vm.screenshot(out / f"{name}.ppm", format="ppm")
    data = ppm.read_bytes()
    head, rest = data.split(b"\n255\n", 1)
    w = int(head.split()[1])
    px = {
        k: tuple(rest[(y * w + x) * 3 : (y * w + x) * 3 + 3])
        for k, (x, y) in POINTS.items()
    }
    try:
        from PIL import Image

        Image.open(ppm).save(out / f"{name}.png")
        ppm.unlink()
    except Exception:  # noqa: BLE001, S110
        pass
    print(f"  {name}: {px}")
    return px


def run(session, out, desk):
    for cname, rgb in COLOURS.items():
        session.revert()
        guest = session.bridge
        t = time.time()
        if desk == "blank":
            blank(guest)
        guest.user32.SetSysColors(
            1, struct.pack("<I", 1), struct.pack("<I", colourref(*rgb))
        )
        guest.sync()
        got = guest.user32.GetSysColor(1).value
        print(
            f"{desk}/{cname}: want {rgb} GetSysColor={got:06x} (BGR) pressure {pressure()}"
        )
        shot(session, out, f"{desk}-{cname}-a")
        _tb, progman, icons = shell_windows(guest)
        guest.user32.RedrawWindow(progman, 0, 0, RDW_REPAINT_ALL)
        guest.sync()
        shot(session, out, f"{desk}-{cname}-b")
        if desk == "blank":
            icons_on = guest.user32.IsWindowVisible(icons).value
            tb_on = guest.user32.IsWindowVisible(_tb).value
            print(f"  after colour: icons visible={icons_on} taskbar visible={tb_on}")
            guest.user32.ShowWindow(icons, 0)  # the one-line fix: re-hide the icon list
            guest.sync()
            shot(session, out, f"{desk}-{cname}-c")
            print(
                f"  after re-hide: icons visible={guest.user32.IsWindowVisible(icons).value}"
            )
        if desk == "stock":
            guest.spawn("notepad.exe")
            time.sleep(2)
            guest.sync()
            shot(session, out, f"{desk}-{cname}-n")
        print(f"  took {time.time() - t:.1f}s pressure {pressure()}")


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    print("start pressure", pressure())
    with stage("work", backend="local") as session:
        for desk in ("stock", "blank"):
            run(session, out, desk)
