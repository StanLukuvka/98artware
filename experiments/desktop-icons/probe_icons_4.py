"""Throwaway probe 4: the rectangle of a fake icon, and a 32-bit icon with an alpha channel.

    uv run art98 vm start
    .venv/bin/python experiments/desktop-icons/probe_icons_4.py OUTDIR

  Q  LVM_GETITEMRECT (bounds, icon, label) for a fake placed at (200, 200), on blank and stock
  R  a 32-bit .ico with a soft alpha edge: does Windows 98 draw it, and how?
  S  a 640x480 display after the fake is placed: does the place hold?
"""

import importlib.util
import struct
import time
from pathlib import Path

_spec = importlib.util.spec_from_file_location("p3", Path(__file__).with_name("probe_icons_3.py"))
p3 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p3)
p1 = p3.p1
rec, shot, items = p1.rec, p1.shot, p1.items

from art98.container.service import attach  # noqa: E402
from art98.desktop import blank, shell_windows  # noqa: E402
from art98.guest.win32 import set_display_mode  # noqa: E402

LVM_GETITEMRECT = 0x100E
LVIR = {"bounds": 0, "icon": 1, "label": 2}


def rects(g, name):
    k = g.kernel32
    mem = k.VirtualAlloc(0, 4096, 0x08003000, 4).value
    out = {}
    try:
        index = items(g)[name]["index"]
        for key, code in LVIR.items():
            k.RtlMoveMemory(mem, struct.pack("<4i", code, 0, 0, 0), 16)
            g.user32.SendMessageA(shell_windows(g)[2], LVM_GETITEMRECT, index, mem)
            out[key] = list(struct.unpack("<4i", k.RtlMoveMemory(p1.Out(16), mem, 16).buffers[0]))
    finally:
        k.VirtualFree(mem, 0, 0x8000)
    return out


def alpha_ico() -> bytes:
    """32x32 32-bit: a blue disc whose edge fades out over 4 px; AND mask all opaque."""
    w = h = 32
    xor = bytearray()
    for y in range(h - 1, -1, -1):
        for x in range(w):
            r = ((x - 15.5) ** 2 + (y - 15.5) ** 2) ** 0.5
            a = max(0, min(255, int((15 - r) / 4 * 255)))
            xor += bytes((255 * a // 255, 0, 0, a))  # premultiplied blue, BGRA
    andm = bytes(4 * h)
    header = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, len(xor) + len(andm), 0, 0, 0, 0)
    image = header + bytes(xor) + andm
    entry = struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(image), 22)
    return struct.pack("<HHH", 0, 1, 1) + entry + image


def main():
    rec("psi_start", Path("/proc/pressure/cpu").read_text().splitlines()[0])
    with attach() as s:
        g = s.bridge
        p3.add(g, "Rect Stock", r"C:\WINDOWS\SYSTEM\shell32.dll", 15)
        p3.wait(lambda: "Rect Stock" in items(g))
        p3.place(g, "Rect Stock", 200, 200)
        g.sync()
        rec("Q/stock", {"pos": items(g)["Rect Stock"]["pos"], **rects(g, "Rect Stock")})

        g.put_file(r"C:\WINDOWS\ART98AL.ICO", alpha_ico())
        p3.add(g, "Alpha", r"C:\WINDOWS\ART98AL.ICO", 0)
        p3.wait(lambda: "Alpha" in items(g))
        p3.place(g, "Alpha", 320, 200)
        g.sync()
        shot(s, "r_alpha_stock")

        s.revert()
        blank(g)
        g.user32.ShowWindow(shell_windows(g)[2], p3.SW_SHOW)
        p3.delete_stock(g)
        p3.add(g, "Rect Blank", r"C:\WINDOWS\SYSTEM\shell32.dll", 15)
        p3.wait(lambda: "Rect Blank" in items(g))
        p3.place(g, "Rect Blank", 200, 200)
        g.put_file(r"C:\WINDOWS\ART98AL.ICO", alpha_ico())
        p3.add(g, "Alpha", r"C:\WINDOWS\ART98AL.ICO", 0)
        p3.wait(lambda: "Alpha" in items(g))
        p3.place(g, "Alpha", 320, 200)
        g.sync()
        rec("Q/blank", {"pos": items(g)["Rect Blank"]["pos"], **rects(g, "Rect Blank")})
        shot(s, "r_alpha_blank")

        set_display_mode(g, 640, 480, 16)
        time.sleep(2)
        g.sync()
        rec("S/after_640", {k: v for k, v in items(g).items()})
        shot(s, "s_640")
        s.revert()
    rec("psi_end", Path("/proc/pressure/cpu").read_text().splitlines()[0])
    (p1.OUT / "results4.json").write_text(p1.json.dumps(p1.RES, indent=1))


if __name__ == "__main__":
    main()
