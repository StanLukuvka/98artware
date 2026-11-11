"""Throwaway: can revert + a hand-applied state be fast and repeatable?"""

import faulthandler

faulthandler.dump_traceback_later(140, exit=True)
import os
import statistics as st
import struct
import sys
import time
from pathlib import Path

from art98.session import boot_local as boot
from art98.session import private_stage

OUT = Path(sys.argv[1])
PAINT = r'"C:\Program Files\Accessories\MSPAINT.EXE"'
GUEST_BMP = r"C:\ART98\P.BMP"


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


def read(path):
    data = Path(path).read_bytes()
    parts, pos = [], 0
    while len(parts) < 4:
        tok = data[pos:].split(None, 1)[0]
        parts.append(tok)
        pos = data.index(tok, pos) + len(tok)
    pos += 1
    return int(parts[1]), int(parts[2]), data[pos:]


def diff(a, b):
    wa, ha, pa = read(a)
    wb, hb, pb = read(b)
    if (wa, ha) != (wb, hb):
        return f"size {wa}x{ha} vs {wb}x{hb}"
    if pa == pb:
        return "identical"
    xs, ys, n = [], [], 0
    for i in range(0, len(pa), 3):
        if pa[i : i + 3] != pb[i : i + 3]:
            n += 1
            xs.append(i // 3 % wa)
            ys.append(i // 3 // wa)
    return f"{n} px differ, x {min(xs)}-{max(xs)}, y {min(ys)}-{max(ys)}"


class Clock:
    def __init__(self):
        self.t = {}
        self.last = time.perf_counter()

    def mark(self, name):
        now = time.perf_counter()
        self.t[name] = (now - self.last) * 1000
        self.last = now
        if os.environ.get("TRACE"):
            print("   ", name, round(self.t[name]), flush=True)


def place(g, hwnd, x, y, w, h):
    g.user32.SetWindowPos(hwnd, 0, x, y, w, h, 0x14)
    g.move_window(hwnd, x, y)


def revert(vm, g, c):
    vm.load_snapshot("ready")
    c.mark("loadvm")
    g.ping()
    c.mark("first_ping")


def state_a(s, c):
    g = s.bridge
    revert(s.vm, g, c)
    g.put_file(GUEST_BMP, IMG)
    c.mark("put_bmp")
    g.spawn("notepad.exe")
    n = g.find_window(class_name="Notepad")
    c.mark("notepad")
    g.spawn(f"{PAINT} {GUEST_BMP}")
    p = g.find_window(class_name="MSPaintApp")
    c.mark("paint")
    place(g, n.hwnd, 60, 60, 300, 200)
    place(g, p.hwnd, 300, 140, 420, 340)
    c.mark("place")
    g.user32.SetCursorPos(400, 500)
    g.sync()
    c.mark("pointer_sync")


def state_b(s, c):
    g = s.bridge
    revert(s.vm, g, c)
    g.spawn("notepad.exe")
    n = g.find_window(class_name="Notepad")
    c.mark("notepad")
    place(g, n.hwnd, 200, 100, 400, 300)
    g.user32.SetCursorPos(100, 500)
    g.sync()
    c.mark("pointer_sync")


IMG = bmp()
print("bmp bytes", len(IMG))
with private_stage("work") as stage, boot(stage) as s:
    g, vm = s.bridge, s.vm
    vm.screenshot(OUT / "ready.ppm", format="ppm")

    print("\n== A: same state 10 times")
    times = []
    for i in range(int(os.environ.get("N", "10"))):
        c = Clock()
        t0 = c.last
        state_a(s, c)
        total = (time.perf_counter() - t0) * 1000
        c.t["TOTAL"] = total
        times.append(c.t)
        vm.screenshot(OUT / f"a{i}.ppm", format="ppm")
        print(i, f"{total:.0f} ms", diff(OUT / "a0.ppm", OUT / f"a{i}.ppm"))
    for k in times[0]:
        v = [t[k] for t in times]
        print(
            f"  {k:14} median {st.median(v):8.1f}  min {min(v):8.1f}  max {max(v):8.1f}"
        )

    print("\n== B: A, other state, A again")
    c = Clock()
    state_b(s, c)
    vm.screenshot(OUT / "b.ppm", format="ppm")
    print("b total ms", round(sum(c.t.values())))
    c = Clock()
    state_a(s, c)
    vm.screenshot(OUT / "a_again.ppm", format="ppm")
    print("a again vs a0:", diff(OUT / "a0.ppm", OUT / "a_again.ppm"))

    print("\n== C: revert leaves nothing behind")
    c = Clock()
    revert(vm, g, c)
    print("windows visible:", [w.class_name for w in g.windows() if w.visible][:12])
    vm.screenshot(OUT / "after.ppm", format="ppm")
    print("after revert vs ready:", diff(OUT / "ready.ppm", OUT / "after.ppm"))

    print("\n== D: display switch then revert")
    g.set_display_mode(640, 480, 16, persist=False)
    g.sync()
    vm.screenshot(OUT / "d640.ppm", format="ppm")
    print("mode size:", read(OUT / "d640.ppm")[:2])
    c = Clock()
    revert(vm, g, c)
    vm.screenshot(OUT / "d_after.ppm", format="ppm")
    print(
        "after revert vs ready:",
        diff(OUT / "ready.ppm", OUT / "d_after.ppm"),
        {k: round(v, 1) for k, v in c.t.items()},
    )

    print("\n== E: revert with requests open")
    pending = g.acall("kernel32", "Sleep", 4000)
    c = Clock()
    revert(vm, g, c)
    print("ping after revert ok", {k: round(v, 1) for k, v in c.t.items()})
    try:
        print("open acall:", pending.wait(timeout=6))
    except Exception as e:  # noqa: BLE001
        print("open acall ended with", type(e).__name__, e)
    print(
        "ping again",
        g.ping() is not None,
        "extra events:",
        len(getattr(g, "_events", [])) if hasattr(g, "_events") else "n/a",
    )
    t = time.perf_counter()
    r = g.user32.GetSystemMetrics(0)
    print("call ok", r.value, f"{(time.perf_counter() - t) * 1000:.1f} ms")
print("done")
