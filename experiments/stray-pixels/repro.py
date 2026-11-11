"""Stray pixels after Backdrop: does the screen differ from a full repaint?

Run: . .tools/env.sh; .venv/bin/python experiments/stray-pixels/repro.py OUTDIR N [local|service]
local: a fresh boot on local QEMU (art98.session.stage). service: the running VM service
(`art98 vm start` must be running; art98.service.attach, reverts first).
(service on Docker: env -u DOCKER_HOST sg docker -c '... service')
Per run: revert, blank, open the DialogStorm boxes (8 cascade, 2 pair, 1 typing), set the colour
with art98.desktop.set_colour (or a pre-fix sequence with PRE=1), screendump (A), force a full
repaint (back to front) of every top-level window, sync, screendump (B), count differing pixels. Prints the
rate of runs where A != B. The local mode uses a private stage, no snapshot saved; keep OUTDIR outside the repo.
"""

import os
import sys
import time
from pathlib import Path

import art98.desktop
from art98.desktop import blank, set_colour
from art98.service import attach
from art98.session import stage
from art98.win32 import RDW_REPAINT_ALL, place_window

OUT = Path(sys.argv[1]).resolve()
N = int(sys.argv[2])
BACKEND = sys.argv[3] if len(sys.argv) > 3 else "local"
if BACKEND not in ("local", "service", "container"):
    raise SystemExit(f"backend must be local or service, not {BACKEND}")
# "container" is the old name for service
LABEL = "local" if BACKEND == "local" else "service"
OUT.mkdir(parents=True, exist_ok=True)
if os.environ.get("PRE"):  # the pre-fix set_colour: no back-to-front repaint at the end
    art98.desktop.repaint_all = lambda guest: guest.sync()
SIZE = (300, 130)
BOXES = [(60 + 24 * i, 330 - 18 * i, 0x30, False) for i in range(8)] + [
    (397, 383, 0x40, True),
    (404, 377, 0x40, True),
    (120, 60, 0x00, False),
]


def psi():
    return Path("/proc/pressure/cpu").read_text().splitlines()[0]


def pixels(session, name):
    ppm = session.vm.screenshot(OUT / f"{name}.ppm", format="ppm")
    data = ppm.read_bytes()
    head, rest = data.split(b"\n255\n", 1)
    return int(head.split()[1]), rest


def open_boxes(guest):
    seen = {w.hwnd for w in guest.windows() if w.class_name.lower() == "#32770"}
    for i, (x, y, style, disabled) in enumerate(BOXES):
        guest.acall("user32", "MessageBoxA", 0, "???", f"box{i}", style)
        deadline = time.monotonic() + 10
        while True:
            new = [
                w
                for w in guest.windows()
                if w.visible
                and w.class_name.lower() == "#32770"
                and w.hwnd not in seen
                and f"box{i}" in w.title
            ]
            if new:
                break
            if time.monotonic() > deadline:
                raise RuntimeError(f"box{i} never appeared")
            time.sleep(0.02)
        hwnd = new[0].hwnd
        seen.add(hwnd)
        place_window(guest, hwnd, x, y, *SIZE, 0x4)
        if disabled:
            for b in guest.windows(hwnd):
                if b.class_name.lower() == "button":
                    guest.user32.EnableWindow(b.hwnd, 0)
        time.sleep(2 / 24)


def run(session, k):
    session.revert()
    guest = session.bridge
    blank(guest)
    set_colour(guest, (0, 128, 128))
    open_boxes(guest)
    guest.sync()
    time.sleep(0.5)
    set_colour(guest, (128, 0, 0))
    if os.environ.get(
        "WAIT"
    ):  # cause check: is it a race (a later sync fixes it) or a gap (it doesn't)?
        time.sleep(float(os.environ["WAIT"]))
    guest.sync()
    w, a = pixels(session, f"{k}-a")
    for win in reversed(guest.windows()):  # back to front, as win32.repaint_all does
        if win.visible:
            guest.user32.RedrawWindow(win.hwnd, 0, 0, RDW_REPAINT_ALL)
    guest.sync()
    _, b = pixels(session, f"{k}-b")
    bad = [i // 3 for i in range(0, len(a), 3) if a[i : i + 3] != b[i : i + 3]]
    box = (
        (
            min(p % w for p in bad),
            min(p // w for p in bad),
            max(p % w for p in bad),
            max(p // w for p in bad),
        )
        if bad
        else None
    )
    for s in "ab":
        if not bad:
            (OUT / f"{k}-{s}.ppm").unlink()
    return len(bad), box


if __name__ == "__main__":
    print(f"backend {LABEL} start pressure {psi()}", flush=True)
    diffs = 0
    session_cm = stage("work") if LABEL == "local" else attach()
    with session_cm as session:
        for k in range(N):
            n, box = run(session, k)
            diffs += bool(n)
            print(f"run {k}: {n} differing px bbox {box} pressure {psi()}", flush=True)
    print(f"RESULT {LABEL}: {diffs}/{N} runs differ")
