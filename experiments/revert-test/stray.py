"""Throwaway: reproduce the stray pixels at Notepad's left edge, from `ready` and a warm baseline.

REDRAW=1 repaints both windows, back to front, after placing them. Set N for fewer Sets.
"""

import faulthandler
import json
import os
import struct
import sys
import time
from pathlib import Path

faulthandler.dump_traceback_later(int(os.environ.get("WATCHDOG", "400")), exit=True)
from art98.session import boot_local as boot
from art98.session import private_stage

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
N = int(os.environ.get("N", "10"))
PAINT = r'"C:\Program Files\Accessories\MSPAINT.EXE"'
GUEST = r"C:\ART98\P.BMP"
RDW_REPAINT_ALL = 1 | 4 | 0x80 | 0x100 | 0x400


def bmp(w=160, h=120):
    pad = (4 - (w * 3) % 4) % 4
    rows = b"".join(
        bytes(v for x in range(w) for v in (x * 255 // w, y * 255 // h, 128))
        + b"\0" * pad
        for y in range(h)
    )
    return (
        b"BM"
        + struct.pack("<IHHI", 54 + len(rows), 0, 0, 54)
        + struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, len(rows), 2835, 2835, 0, 0)
        + rows
    )


IMG = bmp()


def pressure():
    return open("/proc/pressure/cpu").readline().strip()


def read(path):
    data = Path(path).read_bytes()
    parts, pos = [], 0
    while len(parts) < 4:
        tok = data[pos:].split(None, 1)[0]
        parts.append(tok)
        pos = data.index(tok, pos) + len(tok)
    return int(parts[1]), int(parts[2]), data[pos + 1 :]


def diff(a, b):
    wa, ha, pa = read(a)
    wb, hb, pb = read(b)
    if (wa, ha) != (wb, hb):
        return [("size", wa, ha, wb, hb)]
    if pa == pb:
        return []
    out = []
    for i in range(0, len(pa), 3):
        if pa[i : i + 3] != pb[i : i + 3]:
            out.append(
                (i // 3 % wa, i // 3 // wa, tuple(pa[i : i + 3]), tuple(pb[i : i + 3]))
            )
    return out


def place(g, hwnd, x, y, w, h):
    g.user32.SetWindowPos(hwnd, 0, x, y, w, h, 0x14)
    g.move_window(hwnd, x, y)


def close(g, hwnd):
    g.user32.PostMessageA(hwnd, 0x10, 0, 0)
    for _ in range(100):
        if not g.user32.IsWindow(hwnd).value:
            return
        time.sleep(0.05)
    raise SystemExit("window did not close")


def set_a(vm, g, base, tag, log):
    t0 = time.perf_counter()
    vm.load_snapshot(base)
    g.ping()
    g.put_file(GUEST, IMG)
    g.spawn("notepad.exe")
    n = g.find_window(class_name="Notepad")
    n_spawn = n.rect
    g.spawn(f"{PAINT} {GUEST}")
    p = g.find_window(class_name="MSPaintApp")
    p_spawn = p.rect
    place(g, n.hwnd, 60, 60, 300, 200)
    place(g, p.hwnd, 300, 140, 420, 340)
    if os.environ.get("REDRAW"):
        for h in (n.hwnd, p.hwnd):
            g.user32.RedrawWindow(h, 0, 0, RDW_REPAINT_ALL)
    g.user32.SetCursorPos(400, 500)
    g.sync()
    total = (time.perf_counter() - t0) * 1000
    vm.screenshot(OUT / f"{tag}_0.ppm", format="ppm")
    time.sleep(1.0)
    g.sync()
    vm.screenshot(OUT / f"{tag}_1.ppm", format="ppm")
    log.append(
        {
            "tag": tag,
            "ms": round(total),
            "n_spawn": n_spawn,
            "p_spawn": p_spawn,
            "psi": pressure(),
        }
    )


def summarise(px):
    if not px:
        return "identical"
    if px[0][0] == "size":
        return str(px[0])
    xs = [p[0] for p in px]
    ys = [p[1] for p in px]
    return f"{len(px)} px, x {min(xs)}-{max(xs)}, y {min(ys)}-{max(ys)}"


log = []
print("start", pressure(), flush=True)
with private_stage("work") as stage, boot(stage) as s:
    g, vm = s.bridge, s.vm
    # One revert first, so every shot is in the post-revert colour form.
    vm.load_snapshot("ready")
    g.ping()
    vm.screenshot(OUT / "ready.ppm", format="ppm")
    for i in range(N):
        set_a(vm, g, "ready", f"c{i:02}", log)
        print(log[-1], flush=True)
    vm.load_snapshot("ready")
    g.ping()
    g.spawn("notepad.exe")
    close(g, g.find_window(class_name="Notepad").hwnd)
    g.put_file(GUEST, IMG)
    g.spawn(f"{PAINT} {GUEST}")
    close(g, g.find_window(class_name="MSPaintApp").hwnd)
    time.sleep(2)
    g.sync()
    vm.save_snapshot("warm")
    g.ping()
    for i in range(N):
        set_a(vm, g, "warm", f"w{i:02}", log)
        print(log[-1], flush=True)

ref = OUT / "c00_1.ppm"
report = {}
for e in log:
    t = e["tag"]
    d0 = diff(ref, OUT / f"{t}_0.ppm")
    d1 = diff(ref, OUT / f"{t}_1.ppm")
    dt = diff(OUT / f"{t}_0.ppm", OUT / f"{t}_1.ppm")
    print(
        t,
        e["ms"],
        "ms | vs ref now:",
        summarise(d0),
        "| vs ref +1s:",
        summarise(d1),
        "| now vs +1s:",
        summarise(dt),
    )
    report[t] = dict(e, d0=d0[:40], d1=d1[:40], dt=dt[:40])
(OUT / "report.json").write_text(json.dumps(report, indent=1))
print("end", pressure())
