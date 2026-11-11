"""Throwaway (M2b): does the revert after boot fix a fresh boot's first frames?

A = frame right after boot (blank desktop + one window, no revert), B = after revert + blank +
the same window, C = B's desktop left to settle. Run from the repo root:
    . .tools/env.sh; .venv/bin/python experiments/first-frame/probe.py [OUT_DIR]
Runs on a private copy of work/ (art98.session.stage); never writes the base image, never savevm.
lazy: the window is Notepad, not a Picture (no scene here, so no guest file copy); same pixels
for the comparison. Upgrade: a Picture via a Scene if Notepad ever hides a difference.
"""
import faulthandler; faulthandler.dump_traceback_later(170, exit=True)
import sys, tempfile, time
from pathlib import Path
from art98.session import stage
from art98.desktop import blank
from art98.win32 import cursor_pos

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="first-frame-"))
OUT.mkdir(parents=True, exist_ok=True)
P2, P3 = (400, 500), (150, 450)
BOX = 24


def psi():
    return open("/proc/pressure/cpu").read().splitlines()[0]


def read(path):
    data = Path(path).read_bytes()
    parts, pos = [], 0
    while len(parts) < 4:
        tok = data[pos:].split(None, 1)[0]
        parts.append(tok); pos = data.index(tok, pos) + len(tok)
    return int(parts[1]), int(parts[2]), data[pos + 1:]


def mean(f):
    w, h, p = f
    return tuple(round(sum(p[c::3]) / (w * h), 3) for c in range(3))


def count(fa, fb, boxes=None, bbox=None):
    """Number of differing pixels; bbox (a list) gets [x0, y0, x1, y1] of them when given."""
    (wa, ha, pa), (wb, hb, pb) = fa, fb
    if (wa, ha) != (wb, hb):
        return f"size {wa}x{ha} vs {wb}x{hb}"
    n = 0
    for i in range(0, len(pa), 3):
        if pa[i:i + 3] != pb[i:i + 3]:
            x, y = i // 3 % wa, i // 3 // wa
            if boxes is None or any(abs(x - bx) <= BOX and abs(y - by) <= BOX for bx, by in boxes):
                n += 1
                if bbox is not None:
                    bbox[:] = [x, y, x, y] if not bbox else [min(bbox[0], x), min(bbox[1], y), max(bbox[2], x), max(bbox[3], y)]
    return n


def shoot(s, name):
    s.vm.screenshot(OUT / f"{name}.ppm", format="ppm")
    return read(OUT / f"{name}.ppm")


def window(g):
    g.spawn("notepad.exe"); n = g.find_window(class_name="Notepad")
    g.user32.SetWindowPos(n.hwnd, 0, 200, 100, 400, 300, 0x14)
    g.move_window(n.hwnd, 200, 100)


def frame(s, name, settle=0.0):
    """Pointer to P2, sync, shoot; then to P3, sync, shoot again to see if a pointer is drawn."""
    g = s.bridge
    g.user32.SetCursorPos(*P2); g.sync()
    if settle:
        time.sleep(settle); g.sync()
    f = shoot(s, name)
    g.user32.SetCursorPos(*P3); g.sync()
    f2 = shoot(s, name + "_p3")
    return f, count(f, f2, [P2, P3])


def raw_part(s):
    """Raw frames: no blank, no window. A0 straight after boot, A1 after sync, A2 after one pointer move,
    B0 after revert with no move. Pointer boxes: P0 where the pointer starts, P2 where A2 has it."""
    g = s.bridge
    P0 = cursor_pos(g)
    r = {"A0": shoot(s, "A0")}
    g.sync(); r["A1"] = shoot(s, "A1")
    g.user32.SetCursorPos(*P2); g.sync(); r["A2"] = shoot(s, "A2")
    s.revert(); r["B0"] = shoot(s, "B0")
    print("raw: pointer starts at", P0)
    print("raw: mean RGB", {k: mean(v) for k, v in r.items()})
    for k in ("A0", "A1", "B0"):
        outside = count(r[k], r["A2"])
        out_box = count_excluding(r[k], r["A2"], [P0, P2])
        box0 = count(r[k], r["A2"], [P0]) if P0 != P2 else 0
        box2 = count(r[k], r["A2"], [P2])
        # A2 has its pointer at P2 only. If k has a pointer at P0 it differs from A2 at both boxes.
        print(f"raw: {k}-vs-A2 all {outside}  outside pointer boxes {out_box}  in P0 box {box0}  in P2 box {box2}")


def count_excluding(fa, fb, boxes):
    (wa, ha, pa), (_, _, pb) = fa, fb
    n = 0
    for i in range(0, len(pa), 3):
        if pa[i:i + 3] != pb[i:i + 3]:
            x, y = i // 3 % wa, i // 3 // wa
            if not any(abs(x - bx) <= BOX and abs(y - by) <= BOX for bx, by in boxes):
                n += 1
    return n


def nudge_part(s):
    """Fix candidates on a fresh boot with no revert: SetCursorPos to where the pointer already is,
    and a 1 px step there and back. Compared with B0 (a revert, no move)."""
    g = s.bridge
    P0 = cursor_pos(g)
    g.user32.SetCursorPos(*P0); g.sync(); same = shoot(s, "N_same")
    s.revert(); b0 = shoot(s, "N_B0")
    s.revert(); g.sync()
    g.user32.SetCursorPos(P0[0] + 1, P0[1]); g.user32.SetCursorPos(*P0); g.sync(); step = shoot(s, "N_step")
    for name, f in (("same-spot SetCursorPos", same), ("1 px step and back", step)):
        print(f"nudge: {name}: mean {mean(f)}  vs B0: {count(f, b0)} px, mean B0 {mean(b0)}")


print("psi before:", psi())
with stage("work") as s:
    nudge_part(s)
print("psi after nudge:", psi())
t0 = time.perf_counter()
with stage("work") as s:
    g = s.bridge
    print("boot ms", round((time.perf_counter() - t0) * 1000), "cursor after boot", cursor_pos(g))
    raw_part(s)
    print("psi after raw:", psi())
    s.revert()
    g.sync(); blank(g, pointer=True); window(g); g.sync()
    A, a_ptr = frame(s, "A")
    s.revert()
    blank(g, pointer=True); window(g); g.sync()
    B, b_ptr = frame(s, "B")
    C, c_ptr = frame(s, "C", settle=1.5)
print("psi after: ", psi())
box_ac, box_bc = [], []
ac, bc, ab = count(A, C, bbox=box_ac), count(B, C, bbox=box_bc), count(A, B)
print(f"mean RGB  A {mean(A)}  B {mean(B)}  C {mean(C)}")
print(f"diff px   A-vs-B {ab}  A-vs-C {ac} bbox {box_ac}  B-vs-C {bc} bbox {box_bc}")
print(f"pointer drawn (px changed in pointer boxes when moved)  A {a_ptr}  B {b_ptr}  C {c_ptr}")
# a lone text caret (<= 3 px wide) blinking in the window is not a first-frame effect
caret = lambda b: bool(b) and b[2] - b[0] <= 2
if ac == 0 or (caret(box_ac) and ab == 0):
    verdict = "A (after a pointer move) matches C" + ("" if ac == 0 else " bar the caret blink") + "; see the raw: lines for the first frame before any move"
elif bc == 0 or caret(box_bc):
    verdict = "PASS"
else:
    verdict = "FAIL"
print("VERDICT", verdict, "frames in", OUT)
