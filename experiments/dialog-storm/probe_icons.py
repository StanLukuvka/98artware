"""Throwaway (P1): custom icons on a message box (STM_SETICON) and what size/disable/text change do.

Run from the repo root:
    . .tools/env.sh; .venv/bin/python experiments/dialog-storm/probe_icons.py [OUT_DIR] [part ...]
parts: sheets (icon contact sheets, one boot per file), icons (the 7 named icons in real boxes),
       struct (children of a box, hInst 0 vs agent, DestroyIcon), layout (size / MoveWindow),
       misc (EnableWindow, SetWindowTextA). No part given = all but sheets.
Runs on a private copy of work/ (art98.session.stage, backend local); never writes the base image,
never savevm. Screenshots go to OUT_DIR (default: a fresh mktemp dir), never the repo.
lazy: talks to the bridge directly, not through Dialog/Scene (Dialog is still the parked apps.py
class and P1 only needs the raw calls). Upgrade: none, throwaway.
"""
import faulthandler; faulthandler.dump_traceback_later(280, exit=True)
import struct, sys, tempfile, time
from pathlib import Path
from art98.session import stage
from art98.protocol import Out
from art98.win32 import window_rect

args = sys.argv[1:]
OUT = Path(args.pop(0)) if args and ("/" in args[0]) else Path(tempfile.mkdtemp(prefix="p1-"))
OUT.mkdir(parents=True, exist_ok=True)
PARTS = args or ["icons", "struct", "layout", "misc"]
print("out", OUT)

STM_SETICON, STM_GETICON, SS_ICON, GWL_STYLE, GWL_ID = 0x0170, 0x0171, 3, -16, -12
MB_INFO, MB_OK, MB_YESNO = 0x40, 0, 4
WM_CLOSE = 0x10

DLLS = {
    "shell32": r"C:\WINDOWS\SYSTEM\shell32.dll", "moricons": r"C:\WINDOWS\moricons.dll",
    "pifmgr": r"C:\WINDOWS\SYSTEM\pifmgr.dll", "progman": r"C:\WINDOWS\progman.exe",
    "cool": r"C:\WINDOWS\SYSTEM\cool.dll", "setupx": r"C:\WINDOWS\SYSTEM\setupx.dll",
    "inetcpl": r"C:\WINDOWS\SYSTEM\inetcpl.cpl", "mmsys": r"C:\WINDOWS\SYSTEM\mmsys.cpl",
    "url": r"C:\WINDOWS\SYSTEM\url.dll", "user": r"C:\WINDOWS\SYSTEM\user.exe",
    "explorer": r"C:\WINDOWS\explorer.exe", "mplayer": r"C:\WINDOWS\mplayer.exe",
    "cdplayer": r"C:\WINDOWS\cdplayer.exe", "main": r"C:\WINDOWS\SYSTEM\main.cpl",
    "sysdm": r"C:\WINDOWS\SYSTEM\sysdm.cpl", "regedit": r"C:\WINDOWS\regedit.exe",
    "modem": r"C:\WINDOWS\SYSTEM\modem.cpl", "telephon": r"C:\WINDOWS\SYSTEM\telephon.cpl",
    "joy": r"C:\WINDOWS\SYSTEM\joy.cpl", "sticpl": r"C:\WINDOWS\SYSTEM\sticpl.cpl",
}
# measured from the sheets (see README-p1.md)
NAMED = {
    "computer": ("shell32", 15), "printer": ("shell32", 16), "mouse": ("main", 0),
    "telephone": ("modem", 0), "cd": ("shell32", 11), "globe": ("shell32", 13),
    "flag": ("user", 0),
}


def psi():
    return open("/proc/pressure/cpu").read().splitlines()[0]


def shoot(s, name):
    s.vm.screenshot(OUT / f"{name}.png")


def s32(v):
    return v - (1 << 32) if v & 0x80000000 else v


def open_box(g, text, title="art98", style=MB_INFO | MB_OK):
    call = g.acall("user32", "MessageBoxA", 0, text, title, style)
    w = g.find_window(class_name="#32770", title=title)
    g.sync(w.hwnd)
    return call, w.hwnd


def close_box(g, call, hwnd):
    # WM_CLOSE only ends an OK box; a Yes/No box has no cancel, so answer IDNO (7) / IDOK (1) by WM_COMMAND
    g.user32.PostMessageA(hwnd, WM_CLOSE, 0, 0)
    g.user32.PostMessageA(hwnd, 0x111, 7, 0)
    try:
        call.wait(3)
    except Exception as e:  # a box with only OK closes on WM_CLOSE; others may not
        print("  close:", e)


def kids(g, hwnd):
    """[(hwnd, class, style, id, rect, text)] of the box's children."""
    rows = []
    for c in g.windows(hwnd):
        rows.append((c.hwnd, c.class_name, g.user32.GetWindowLongA(c.hwnd, GWL_STYLE & 0xFFFFFFFF).value,
                     s32(g.user32.GetDlgCtrlID(c.hwnd).value), c.rect, c.title))
    return rows


def icon_static(g, hwnd):
    return next(h for h, cls, st, _, _, _ in kids(g, hwnd) if cls.lower() == "static" and st & 0x1F == SS_ICON)


def text_static(g, hwnd):
    return next(h for h, cls, st, _, _, _ in kids(g, hwnd) if cls.lower() == "static" and st & 0x1F != SS_ICON)


def buttons(g, hwnd):
    return [h for h, cls, *_ in kids(g, hwnd) if cls.lower() == "button"]


def dump(g, hwnd, label):
    print(f"-- {label}: box rect {window_rect(g, hwnd)}")
    for h, cls, st, cid, rect, text in kids(g, hwnd):
        w, hh = rect[2] - rect[0], rect[3] - rect[1]
        print(f"   {h:#x} {cls:8} style={st:#010x} id={cid:#x} rect={rect} {w}x{hh} text={text[:30]!r}")


def part_sheets(out):
    for name, path in DLLS.items():
        with stage("work", backend="local") as s:
            g = s.bridge
            n = g.shell32.ExtractIconA(0, path, 0xFFFFFFFF).value
            hdc = g.user32.GetDC(0).value
            g.gdi32.PatBlt(hdc, 0, 0, 800, 600, 0x00FF0062)   # WHITENESS
            lab = f"{name} {path}"
            g.gdi32.TextOutA(hdc, 2, 2, lab, len(lab))
            for i in range(min(n, 240)):
                h = g.shell32.ExtractIconA(0, path, i).value
                x, y = (i % 20) * 40 + 4, 18 + (i // 20) * 46
                if h > 1:
                    g.user32.DrawIcon(hdc, x, y, h)
                    g.user32.DestroyIcon(h)
                t = str(i)
                g.gdi32.TextOutA(hdc, x + 4, y + 33, t, len(t))
            g.user32.ReleaseDC(0, hdc)
            s.vm.screenshot(out / f"sheet_{name}.png")
            print(name, path, n, "icons")


def set_icon(g, hwnd, path, index, hinst=0):
    h = g.shell32.ExtractIconA(hinst, path, index).value
    slot = icon_static(g, hwnd)
    prev = g.user32.SendMessageA(slot, STM_SETICON, h, 0).value
    g.user32.RedrawWindow(slot, 0, 0, 0x1 | 0x4 | 0x100)
    return h, slot, prev


def part_icons(s):
    g = s.bridge
    for name, (key, idx) in NAMED.items():
        call, box = open_box(g, f"{name}: {DLLS[key]} #{idx}")
        h, slot, prev = set_icon(g, box, DLLS[key], idx)
        g.sync(box)
        shoot(s, f"icon_{name}")
        print(f"icon {name} {DLLS[key]} #{idx}: hicon={h:#x} prev={prev:#x} slot={slot:#x}")
        close_box(g, call, box)
        g.user32.DestroyIcon(h)


def part_struct(s):
    g = s.bridge
    call, box = open_box(g, "Hello from the probe, a longer line of text.\nSecond line.")
    dump(g, box, "MB_ICONINFORMATION|OK")
    shoot(s, "struct_stock_info")
    # hInst 0 vs agent module
    agent = g.kernel32.GetModuleHandleA(None).value
    h0 = g.shell32.ExtractIconA(0, DLLS["shell32"], 15).value
    ha = g.shell32.ExtractIconA(agent, DLLS["shell32"], 15).value
    print(f"hInst: agent module {agent:#x}; ExtractIconA(0)={h0:#x} ExtractIconA(agent)={ha:#x}")
    slot = icon_static(g, box)
    old = g.user32.SendMessageA(slot, STM_GETICON, 0, 0).value
    print(f"STM_GETICON before: {old:#x}")
    prev = g.user32.SendMessageA(slot, STM_SETICON, ha, 0).value
    print(f"STM_SETICON(agent-hInst icon) returned prev {prev:#x}; GETICON now {g.user32.SendMessageA(slot, STM_GETICON, 0, 0).value:#x}")
    g.user32.RedrawWindow(slot, 0, 0, 0x1 | 0x4 | 0x100); g.sync(box)
    shoot(s, "struct_hinst_agent")
    prev = g.user32.SendMessageA(slot, STM_SETICON, h0, 0).value
    g.user32.RedrawWindow(slot, 0, 0, 0x1 | 0x4 | 0x100); g.sync(box)
    shoot(s, "struct_hinst_zero")
    print("  (same pixels for both? compare struct_hinst_agent.png / struct_hinst_zero.png)")
    # DestroyIcon while still shown: is the icon copied?
    r = g.user32.DestroyIcon(h0); print("DestroyIcon(h0) while set:", r.value, r.last_error)
    g.user32.RedrawWindow(slot, 0, 0, 0x1 | 0x4 | 0x100); g.sync(box)
    shoot(s, "struct_after_destroy_while_set")
    g.user32.DestroyIcon(ha)
    close_box(g, call, box)
    # leak: GetFreeSystemResources is not exported to the agent (NOFUNC), so watch the handle values
    # instead: a leak shows as ever-new handles (and eventually 0), a freed icon is recycled.
    def storm(destroy, limit=2000):
        for n in range(limit):
            h = g.shell32.ExtractIconA(0, DLLS["shell32"], 15).value
            if h <= 1:
                return f"ExtractIconA returned {h} at call {n}"
            if destroy:
                g.user32.DestroyIcon(h)
        return f"{limit} calls fine"
    t = time.perf_counter()
    print("no DestroyIcon:  ", storm(False), f"({time.perf_counter()-t:.1f} s, psi {psi()})")
    s.revert(); g.sync()
    t = time.perf_counter()
    print("with DestroyIcon:", storm(True), f"({time.perf_counter()-t:.1f} s, psi {psi()})")
    print("done")


def part_layout(s):
    g = s.bridge
    for label, text, style, size in (
        ("ok_wide", "A short line.", MB_INFO | MB_OK, (460, 160)),
        ("yesno_wide", "A short line.", MB_INFO | MB_YESNO, (460, 160)),
        ("yesno_tall", "Three\nshort\nlines.", MB_INFO | MB_YESNO, (300, 260)),
        ("yesno_narrow", "A somewhat longer message that wraps in the stock box.", MB_INFO | MB_YESNO, (200, 150)),
    ):
        call, box = open_box(g, text, style=style)
        dump(g, box, f"{label} before")
        shoot(s, f"layout_{label}_0_before")
        g.user32.SetWindowPos(box, 0, 0, 0, size[0], size[1], 0x2 | 0x4)   # SWP_NOMOVE|SWP_NOZORDER (NOSIZE is 0x1!)
        g.sync(box)
        dump(g, box, f"{label} after SetWindowPos {size}")
        shoot(s, f"layout_{label}_1_setwindowpos")
        g.user32.RedrawWindow(box, 0, 0, 0x1 | 0x4 | 0x80 | 0x100 | 0x400)
        g.sync(box)
        shoot(s, f"layout_{label}_2_redraw")
        close_box(g, call, box)
    # re-lay out by hand: centre buttons, widen text
    call, box = open_box(g, "A short line.", style=MB_INFO | MB_YESNO)
    bl, bt, br, bb = window_rect(g, box)
    g.user32.SetWindowPos(box, 0, 0, 0, 460, 160, 0x2 | 0x4)
    g.sync(box)
    bl, bt, br, bb = window_rect(g, box)
    # client size
    rc = g.user32.GetClientRect(box, Out(16)).buffers[0]
    cw, ch = struct.unpack("<iiii", rc)[2:]
    print("client", cw, ch)
    btns = buttons(g, box)
    rects = [window_rect(g, h) for h in btns]
    bw, bh = rects[0][2] - rects[0][0], rects[0][3] - rects[0][1]
    gap = rects[1][0] - rects[0][2] if len(rects) > 1 else 0
    total = bw * len(btns) + gap * (len(btns) - 1)
    # ScreenToClient: rect origin of the box client = box rect left + border; derive from first button
    origin = None
    pt = g.user32.ScreenToClient(box, Out(8))  # lazy probe: see what the call gives for a zero point
    print("ScreenToClient(Out) ->", pt)
    ox, oy = struct.unpack("<ii", pt.buffers[0]) if pt.buffers else (0, 0)
    print("client origin offset (ScreenToClient of (0,0)):", ox, oy)
    x0 = (cw - total) // 2
    y_btn = rects[0][1] + oy
    for i, h in enumerate(btns):
        g.user32.MoveWindow(h, x0 + i * (bw + gap), y_btn, bw, bh, 1)
    ts = text_static(g, box)
    tl, tt, tr, tb = window_rect(g, ts)
    isl, ist, isr, isb = window_rect(g, icon_static(g, box))
    g.user32.MoveWindow(ts, tl + ox - 0, tt + oy, cw - (tl + ox) - 16, tb - tt, 1)
    g.user32.RedrawWindow(box, 0, 0, 0x1 | 0x4 | 0x80 | 0x100 | 0x400)
    g.sync(box)
    dump(g, box, "after manual relayout")
    shoot(s, "layout_manual")
    close_box(g, call, box)


def part_misc(s):
    g = s.bridge
    call, box = open_box(g, "Enable / text test", style=MB_INFO | MB_YESNO)
    btns = buttons(g, box)
    shoot(s, "misc_0_start")
    r = g.user32.EnableWindow(btns[1], 0)
    print("EnableWindow(btn1, 0) ->", r.value, "(prev disabled state)")
    print("IsWindowEnabled now:", g.user32.IsWindowEnabled(btns[1]).value)
    g.sync(box); shoot(s, "misc_1_disabled_no_invalidate")
    # does a disabled button stay unclickable and answer by Enter/Esc? (not tested; screenshot only)
    ts = text_static(g, box)
    dump(g, box, "before text change")
    g.user32.SetWindowTextA(ts, "A much longer replacement message that goes past the width of the first line and wraps.")
    g.sync(box); shoot(s, "misc_2_longer_no_invalidate")
    g.user32.SetWindowTextA(ts, "Short.")
    g.sync(box); shoot(s, "misc_3_shorter_no_invalidate")
    g.user32.RedrawWindow(ts, 0, 0, 0x1 | 0x4 | 0x100)
    g.sync(box); shoot(s, "misc_4_shorter_after_redraw_static")
    g.user32.SetWindowTextA(ts, "Line one\nLine two\nLine three\nLine four")
    g.user32.RedrawWindow(box, 0, 0, 0x1 | 0x4 | 0x80 | 0x100 | 0x400)
    g.sync(box); shoot(s, "misc_5_four_lines_redraw_box")
    dump(g, box, "after text changes")
    # a longer / multi-line message: the static is clipped to its own rect, so resize it first
    l, t, r_, b = window_rect(g, ts)
    g.user32.SetWindowPos(box, 0, 0, 0, 340, 200, 0x2 | 0x4)   # grow the box (children stay put)
    g.user32.MoveWindow(ts, 62, 20, 250, 15 * 2, 1)             # client coords: the stock static sits at (62, 20)
    g.user32.SetWindowTextA(ts, "Line one\nLine two, wider than the first stock box.")
    g.sync(box); shoot(s, "misc_7_static_resized_then_text")
    dump(g, box, "after resizing the static")
    # DestroyIcon while the icon is shown, then move the box so it must repaint the slot
    h = g.shell32.ExtractIconA(0, DLLS["shell32"], 13).value
    g.user32.SendMessageA(icon_static(g, box), STM_SETICON, h, 0)
    g.user32.DestroyIcon(h)
    g.user32.SetWindowPos(box, 0, 100, 60, 0, 0, 0x1 | 0x4)       # move (NOSIZE|NOZORDER)
    g.user32.RedrawWindow(box, 0, 0, 0x1 | 0x4 | 0x80 | 0x100 | 0x400)
    g.sync(box); shoot(s, "misc_8_icon_destroyed_then_moved_and_repainted")
    r = g.user32.EnableWindow(btns[1], 1)
    print("EnableWindow(btn1, 1) ->", r.value)
    g.user32.EnableWindow(btns[0], 0)
    g.user32.EnableWindow(btns[1], 0)
    g.user32.RedrawWindow(box, 0, 0, 0x1 | 0x4 | 0x80 | 0x100 | 0x400)
    g.sync(box); shoot(s, "misc_6_both_disabled_redraw")
    close_box(g, call, box)


if "sheets" in PARTS:
    part_sheets(OUT)
for part in ("icons", "struct", "layout", "misc"):
    if part in PARTS:
        print(f"=== {part}  psi {psi()}")
        t0 = time.perf_counter()
        with stage("work", backend="local") as s:
            print(f"boot {1000*(time.perf_counter()-t0):.0f} ms  psi {psi()}")
            t1 = time.perf_counter()
            globals()["part_" + part](s)
            print(f"{part} done in {time.perf_counter()-t1:.1f} s  psi {psi()}")
