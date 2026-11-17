"""B0 probe for the section-state plan: which windows the desktop owns, what appears by itself,
what a window listing costs, and what GetWindowPlacement returns.

Run (VM service up, `art98 vm start`):
    env -u DOCKER_HOST sg docker -c 'uv run python experiments/section-state/probe.py OUTDIR'
Optional: ART98_WORK=<folder> to use a work folder other than art98.toml's.
Writes OUTDIR/b0.json. Nothing is recorded, no snapshot is saved, and each part starts from a
revert. Keep OUTDIR outside the repo.
"""

import json
import os
import struct
import sys
import time
from pathlib import Path

from art98.actions.programs.dialog import Dialog
from art98.actions.programs.notepad import Notepad
from art98.actions.window.menu import Menu
from art98.anim import Scene
from art98.base.vectors import Vec
from art98.container import service
from art98.guest.win32 import show_state, window_rect
from art98.settings import load as load_settings

OUT = Path(sys.argv[1]).resolve()


def psi() -> str:
    return Path("/proc/pressure/cpu").read_text().splitlines()[0]


class NullRecorder:
    """Takes frames without capturing: enough for Scene.play and wait."""

    total = 0

    def frame(self, hold: int = 1) -> None:
        self.total += hold

    def live(self, seconds, stop_condition=None, stacklevel=1) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if stop_condition and stop_condition():
                return
            time.sleep(0.05)
            self.total += 1

    def cut(self, path=None):
        return None


def rows(guest, visible_only=True):
    return [
        {
            "hwnd": w.hwnd,
            "class": w.class_name,
            "title": w.title,
            "visible": w.visible,
            "pid": w.pid,
        }
        for w in guest.windows()
        if w.visible or not visible_only
    ]


def visible_set(guest):
    return {w.hwnd for w in guest.windows() if w.visible}


def describe(guest, hwnds):
    by = {w.hwnd: w for w in guest.windows()}
    return [
        {"hwnd": h, "class": by[h].class_name, "title": by[h].title}
        for h in sorted(hwnds)
        if h in by
    ]


def placement(guest, hwnd):
    # WINDOWPLACEMENT.length must be 44 (an Out buffer is zeroed, and the call then fails)
    result = guest.user32.GetWindowPlacement(hwnd, struct.pack("<I", 44) + bytes(40))
    _length, _flags, show, *_points, l, t, r, b = struct.unpack(
        "<11i", result.buffers[0]
    )
    return {
        "rc": result.value,
        "showCmd": show,
        "rcNormalPosition": [l, t, r, b],
        "GetWindowRect": list(window_rect(guest, hwnd)),
        "show_state": show_state(guest, hwnd),
    }


class Probe(Scene):
    desktop = "blank"
    pointer_visible = True

    def construct(self):
        guest = self.guest
        report = self.report
        base = visible_set(guest)
        report["baseline_visible"] = rows(guest)
        report["baseline_all_count"] = len(guest.windows())
        appeared = {}

        def note(step):
            now = visible_set(guest)
            appeared[step] = {
                "new": describe(guest, now - base),
                "gone": sorted(base - now),
            }

        pad = Notepad(at=(120, 90), size=(360, 240))
        self.add(pad)
        note("notepad open")
        self.play(Menu(pad, "Edit", "Select All"))
        note("after Menu Edit>Select All")
        # Rest the pointer on the title bar, then on the bottom edge (the taskbar on stock).
        self.pointer.place(pad.title_bar)
        self.wait(2.5)
        note("pointer rested on title bar 2.5 s")
        self.pointer.place(Vec(400, self.space.screen[1] - 10))
        self.wait(2.5)
        note("pointer rested at bottom edge 2.5 s")

        # Placement: normal, maximized, minimized.
        place = {"normal": placement(guest, pad.hwnd)}
        pad.maximize()
        place["maximized"] = placement(guest, pad.hwnd)
        pad.restore()
        pad.minimize()
        place["minimized"] = placement(guest, pad.hwnd)
        note("notepad minimized")
        pad.restore()
        report["placement"] = place

        box = Dialog("Probe", "art98", buttons="ok")
        self.add(box)
        note("dialog open")
        self.remove(box)
        note("dialog removed")
        self.remove(pad)
        time.sleep(1.0)
        note("notepad removed")

        # Cost: a full listing and one IsWindow, 100 each.
        def timed(fn, n=100):
            times = []
            for _ in range(n):
                start = time.perf_counter()
                fn()
                times.append((time.perf_counter() - start) * 1000)
            times.sort()
            return {
                "median_ms": round(times[n // 2], 2),
                "p95_ms": round(times[int(n * 0.95)], 2),
            }

        report["cost"] = {
            "psi_before": psi(),
            "windows()": timed(guest.windows),
            "IsWindow": timed(lambda: guest.user32.IsWindow(0x10)),
            "psi_after": psi(),
            "listing_rows": len(guest.windows()),
        }
        report["appeared"] = appeared


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    settings = load_settings(os.environ.get("ART98_WORK"))
    results = {"psi_start": psi()}
    with service.attach(settings) as session:
        for desktop in ("blank", "stock"):
            scene = type(f"Probe_{desktop}", (Probe,), {"desktop": desktop})()
            scene.report = {}
            scene.run(session, NullRecorder())
            results[desktop] = scene.report
        # Do hwnds of the baseline repeat across reverts?
        hw = []
        for _ in range(2):
            session.revert()
            hw.append(sorted(visible_set(session.bridge)))
        results["baseline_same_after_reverts"] = hw[0] == hw[1]
    results["psi_end"] = psi()
    (OUT / "b0.json").write_text(json.dumps(results, indent=1))
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
