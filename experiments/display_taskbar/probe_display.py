"""Why the taskbar stays put after a display mode change, and what moves it.

    uv run art98 vm start
    .venv/bin/python experiments/display_taskbar/probe_display.py OUTDIR [WORK]

Attaches to the running VM and reverts before every case. Throwaway probe: no source
edits, no savevm. Writes OUTDIR/results.json and a PNG per case.
"""

import json
import struct
import sys
import time
from pathlib import Path

from art98.container.service import attach
from art98.desktop import shell_windows
from art98.guest.protocol import Out
from art98.guest.win32 import (
    DEVMODE_SIZE,
    DM_BITSPERPEL,
    DM_PELSHEIGHT,
    DM_PELSWIDTH,
    screen_size,
    window_rect,
    work_area,
)
from art98.settings import load

OUT = Path(sys.argv[1]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
SETTINGS = load(sys.argv[2] if len(sys.argv) > 2 else None)
RES: dict = {}
T0 = time.perf_counter()

WM_SIZE, WM_SETTINGCHANGE, WM_DISPLAYCHANGE = 0x0005, 0x001A, 0x007E
SPI_SETWORKAREA = 0x2F
HWND_BROADCAST = 0xFFFF
SMTO_ABORTIFHUNG = 2


def rec(key, value):
    RES[key] = value
    print(f"[{time.perf_counter() - T0:6.1f}s] {key} = {value}", flush=True)


def shot(session, name):
    ppm = session.vm.screenshot(OUT / f"{name}.ppm", format="ppm")
    try:
        from PIL import Image

        Image.open(ppm).save(OUT / f"{name}.png")
        ppm.unlink()
    except Exception:  # noqa: BLE001, S110
        pass


def change(g, w, h, bpp, flags):
    mode = 0
    while True:
        blank = bytearray(DEVMODE_SIZE)
        struct.pack_into("<H", blank, 36, DEVMODE_SIZE)
        result = g.user32.EnumDisplaySettingsA(None, mode, blank)
        if result.value == 0:
            raise RuntimeError("no mode")
        devmode = bytearray(result.buffers[0])
        if struct.unpack_from("<III", devmode, 104) == (bpp, w, h):
            break
        mode += 1
    struct.pack_into("<I", devmode, 40, DM_BITSPERPEL | DM_PELSWIDTH | DM_PELSHEIGHT)
    return g.user32.ChangeDisplaySettingsA(devmode, flags).signed


def read(g):
    taskbar, desktop, icons = shell_windows(g)
    return {
        "screen": screen_size(g),
        "work": work_area(g),
        "taskbar": window_rect(g, taskbar),
        "progman": window_rect(g, desktop),
        "icons": window_rect(g, icons),
    }


def main():
    rec("psi_start", Path("/proc/pressure/cpu").read_text().splitlines()[0])
    w, h, bpp = 1024, 768, 16
    lp = h << 16 | w

    def tray():
        return shell_windows(g)[0]

    nudges = {
        "none": lambda: None,
        "displaychange_tray": lambda: g.user32.SendMessageA(
            tray(), WM_DISPLAYCHANGE, bpp, lp
        ),
        "displaychange_broadcast": lambda: g.user32.SendMessageTimeoutA(
            HWND_BROADCAST, WM_DISPLAYCHANGE, bpp, lp, SMTO_ABORTIFHUNG, 3000, Out(4)
        ),
        "size_tray": lambda: g.user32.SendMessageA(tray(), WM_SIZE, 0, 0),
        "settingchange_workarea_tray": lambda: g.user32.SendMessageA(
            tray(), WM_SETTINGCHANGE, SPI_SETWORKAREA, 0
        ),
    }
    with attach(SETTINGS) as s:
        g = s.bridge
        s.revert()
        rec("stock", read(g))
        for flags in (0, 1):
            for name, nudge in nudges.items():
                if flags == 1 and name != "none":
                    continue
                key = f"flags{flags}.{name}"
                s.revert()
                result = change(g, w, h, bpp, flags)
                after = read(g)
                nudge()
                g.sync()
                now = read(g)
                time.sleep(3)
                g.sync()
                later = read(g)
                rec(key, {"cds": result, "after_change": after, "after_nudge": now,
                          "after_3s": later})  # fmt: skip
                shot(s, key)
        s.revert()
    rec("psi_end", Path("/proc/pressure/cpu").read_text().splitlines()[0])
    (OUT / "results.json").write_text(json.dumps(RES, indent=2) + "\n")


if __name__ == "__main__":
    main()
