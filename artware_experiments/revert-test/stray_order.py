"""Throwaway: when do label pixels land in Notepad's frame, and does a final repaint clear them?"""
import faulthandler, os, struct, sys, time
from pathlib import Path
faulthandler.dump_traceback_later(400, exit=True)
from art98.session import boot, private_stage
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
N = int(os.environ.get("N", 8))
PAINT = r'"C:\Program Files\Accessories\MSPAINT.EXE"'; GUEST = r"C:\ART98\P.BMP"
def bmp(w=160, h=120):
    pad = (4 - (w * 3) % 4) % 4
    rows = b"".join(bytes(v for x in range(w) for v in (x * 255 // w, y * 255 // h, 128)) + b"\0" * pad for y in range(h))
    return b"BM" + struct.pack("<IHHI", 54 + len(rows), 0, 0, 54) + struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, len(rows), 2835, 2835, 0, 0) + rows
IMG = bmp()
def pressure(): return open("/proc/pressure/cpu").readline().split()[1]
def read(path):
    data = Path(path).read_bytes(); parts, pos = [], 0
    while len(parts) < 4:
        tok = data[pos:].split(None, 1)[0]; parts.append(tok); pos = data.index(tok, pos) + len(tok)
    return int(parts[1]), int(parts[2]), data[pos + 1:]
def leak(path):
    """White pixels in Notepad's left sizing frame (x 60-63) where the label crosses it."""
    w, h, px = read(path)
    return sum(1 for y in range(118, 124) for x in range(60, 64) if px[(y * w + x) * 3] == 248 and not (x == 61))
def place(g, hwnd, x, y, w, h):
    g.user32.SetWindowPos(hwnd, 0, x, y, w, h, 0x14); g.move_window(hwnd, x, y)
RDW = 1 | 4 | 0x80 | 0x100 | 0x400
def shot(vm, name): p = OUT / f"{name}.ppm"; vm.screenshot(p, format="ppm"); return leak(p)
def run(vm, g, order, tag):
    vm.load_snapshot("ready"); g.ping(); g.put_file(GUEST, IMG)
    g.spawn("notepad.exe"); n = g.find_window(class_name="Notepad")
    g.spawn(f"{PAINT} {GUEST}"); p = g.find_window(class_name="MSPaintApp")
    r = {}
    if order == "notepad_first":
        place(g, n.hwnd, 60, 60, 300, 200); g.sync(); r["after_notepad"] = shot(vm, f"{tag}_mid")
        place(g, p.hwnd, 300, 140, 420, 340)
    else:
        place(g, p.hwnd, 300, 140, 420, 340); g.sync(); r["after_paint"] = shot(vm, f"{tag}_mid")
        place(g, n.hwnd, 60, 60, 300, 200)
    g.user32.SetCursorPos(400, 500); g.sync(); r["end"] = shot(vm, f"{tag}_end")
    g.user32.RedrawWindow(n.hwnd, 0, 0, RDW); g.sync(); r["notepad_redrawn"] = shot(vm, f"{tag}_fix")
    return r
print("start", pressure(), flush=True)
with private_stage("work") as stage, boot(stage) as s:
    g, vm = s.bridge, s.vm
    vm.load_snapshot("ready"); g.ping()
    for order in ("notepad_first", "paint_first"):
        for i in range(N):
            print(order, i, run(vm, g, order, f"{order}{i}"), pressure(), flush=True)
print("end", pressure())
