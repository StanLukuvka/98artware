"""Throwaway: does a baseline with apps already launched once make Set faster, and is it still repeatable?"""

import faulthandler
import statistics as st
import struct
import sys
import time
from pathlib import Path

faulthandler.dump_traceback_later(170, exit=True)
from art98.session import boot_local as boot
from art98.session import private_stage

OUT = Path(sys.argv[1])
OUT.mkdir(exist_ok=True)
PAINT = r'"C:\Program Files\Accessories\MSPAINT.EXE"'
GUEST = r"C:\ART98\P.BMP"


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
    return open("/proc/pressure/cpu").readline().split()[1]


def place(g, hwnd, x, y, w, h):
    g.user32.SetWindowPos(hwnd, 0, x, y, w, h, 0x14)
    g.move_window(hwnd, x, y)


def set_a(vm, g, base):
    marks = {}
    t0 = last = time.perf_counter()

    def m(n):
        nonlocal last
        now = time.perf_counter()
        marks[n] = (now - last) * 1000
        last = now

    vm.load_snapshot(base)
    g.ping()
    m("revert")
    g.put_file(GUEST, IMG)
    m("put")
    g.spawn("notepad.exe")
    n = g.find_window(class_name="Notepad")
    m("notepad")
    g.spawn(f"{PAINT} {GUEST}")
    p = g.find_window(class_name="MSPaintApp")
    m("paint")
    place(g, n.hwnd, 60, 60, 300, 200)
    place(g, p.hwnd, 300, 140, 420, 340)
    m("place")
    g.user32.SetCursorPos(400, 500)
    g.sync()
    m("pointer")
    marks["TOTAL"] = (time.perf_counter() - t0) * 1000
    return marks


def report(label, runs):
    print(label, pressure())
    for k in runs[0]:
        v = [r[k] for r in runs]
        print(
            f"  {k:8} med {st.median(v):7.0f}  min {min(v):7.0f}  max {max(v):7.0f}",
            flush=True,
        )


def close(g, hwnd):
    g.user32.PostMessageA(hwnd, 0x10, 0, 0)
    for _ in range(100):
        if not g.user32.IsWindow(hwnd).value:
            return
        time.sleep(0.05)
    raise SystemExit("window did not close")


with private_stage("work") as stage, boot(stage) as s:
    g, vm = s.bridge, s.vm
    runs = [set_a(vm, g, "ready") for _ in range(3)]
    vm.screenshot(OUT / "cold.ppm", format="ppm")
    report("cold baseline", runs)
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
    runs = []
    for i in range(4):
        runs.append(set_a(vm, g, "warm"))
        vm.screenshot(OUT / f"warm{i}.ppm", format="ppm")
    report("warm baseline", runs)
print(
    "shots match:",
    [
        (OUT / f"warm{i}.ppm").read_bytes() == (OUT / "warm0.ppm").read_bytes()
        for i in range(4)
    ],
    "warm vs cold:",
    (OUT / "warm0.ppm").read_bytes() == (OUT / "cold.ppm").read_bytes(),
)
