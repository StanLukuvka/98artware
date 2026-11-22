"""Fake desktop icons on the stock desktop: do they show, with which image, and can they be placed?

    uv run art98 vm start
    .venv/bin/python experiments/desktop-icons/probe_icons.py OUTDIR

Attaches to the running VM, which reverts it first. Throwaway probe: no source edits, no savevm.
Writes OUTDIR/results.json and a PPM per step.

  A  folder + desktop.ini naming a shell32 icon (an image already on the guest)
  B  folder + desktop.ini naming an .ico copied to the guest (a provided image)
  C  .url file with IconFile/IconIndex (does it get the shortcut arrow?)
  D  move the new items with LVM_SETITEMPOSITION and read the positions back
  E  a full refresh (SHCNE_ASSOCCHANGED): do the items, places and images stay?
"""

import json
import struct
import sys
import time
from pathlib import Path

from art98 import Out
from art98.container.service import attach
from art98.desktop import shell_windows

OUT = Path(sys.argv[1]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
RES: dict = {}
T0 = time.perf_counter()

LVM_GETITEMCOUNT, LVM_GETITEMPOSITION, LVM_GETITEMTEXTA = 0x1004, 0x1010, 0x102D
LVM_SETITEMPOSITION = 0x100F
SHCNE_MKDIR, SHCNE_CREATE, SHCNE_UPDATEDIR, SHCNE_ASSOCCHANGED = 0x8, 0x2, 0x1000, 0x08000000
SHCNF_PATHA, SHCNF_IDLIST, SHCNF_FLUSH = 0x1, 0x0, 0x1000
ATTR_HIDDEN, ATTR_SYSTEM = 0x2, 0x4
DESK = r"C:\WINDOWS\DESKTOP"


def rec(key, value):
    RES[key] = value
    print(f"[{time.perf_counter() - T0:6.1f}s] {key} = {value}", flush=True)


def lparam(x, y):
    return (y & 0xFFFF) << 16 | x & 0xFFFF


def cstring(data):
    return data.split(b"\0", 1)[0].decode("cp1252")


def shot(session, name):
    session.vm.screenshot(OUT / f"{name}.ppm", format="ppm")


def ico_bytes() -> bytes:
    """A 32x32 24-bit icon: an orange diamond with a black edge, transparent outside."""
    w = h = 32
    xor = bytearray()
    andm = bytearray()
    for y in range(h - 1, -1, -1):  # bottom-up
        bits = 0
        for x in range(w):
            d = abs(x - 15.5) + abs(y - 15.5)
            if d <= 14:
                xor += bytes((0, 0, 0)) if d > 12 else bytes((0, 128, 255))  # BGR
            else:
                xor += bytes((0, 0, 0))
                bits |= 1 << (31 - x)
        andm += bits.to_bytes(4, "big")
    header = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 24, 0, len(xor) + len(andm), 0, 0, 0, 0)
    image = header + bytes(xor) + bytes(andm)
    entry = struct.pack("<BBBBHHII", w, h, 0, 0, 1, 24, len(image), 22)
    return struct.pack("<HHH", 0, 1, 1) + entry + image


def items(g):
    """{label: {index, pos}} for every item in the desktop list (it lives in Explorer)."""
    u, k = g.user32, g.kernel32
    lv = shell_windows(g)[2]
    mem = k.VirtualAlloc(0, 4096, 0x08003000, 4).value  # shared, so Explorer can write it
    out = {}
    try:
        n = u.SendMessageA(lv, LVM_GETITEMCOUNT, 0, 0).value
        for i in range(n):
            item = struct.pack("<IiiIIIiiI", 1, i, 0, 0, 0, mem + 256, 200, 0, 0)
            k.RtlMoveMemory(mem, item, len(item))
            u.SendMessageA(lv, LVM_GETITEMTEXTA, i, mem)
            name = cstring(k.RtlMoveMemory(Out(200), mem + 256, 200).buffers[0])
            u.SendMessageA(lv, LVM_GETITEMPOSITION, i, mem + 512)
            pos = struct.unpack("<ii", k.RtlMoveMemory(Out(8), mem + 512, 8).buffers[0])
            out[name] = {"index": i, "pos": list(pos)}
    finally:
        k.VirtualFree(mem, 0, 0x8000)
    return out


def folder_icon(g, name, icon_file, index):
    path = rf"{DESK}\{name}"
    rec(f"{name}/mkdir", g.kernel32.CreateDirectoryA(path, 0).value)
    ini = f"[.ShellClassInfo]\r\nIconFile={icon_file}\r\nIconIndex={index}\r\n".encode()
    g.put_file(rf"{path}\desktop.ini", ini)
    g.kernel32.SetFileAttributesA(rf"{path}\desktop.ini", ATTR_HIDDEN | ATTR_SYSTEM)
    rec(f"{name}/attr", g.kernel32.SetFileAttributesA(path, ATTR_SYSTEM).value)
    g.shell32.SHChangeNotify(SHCNE_MKDIR, SHCNF_PATHA | SHCNF_FLUSH, path, 0)
    g.shell32.SHChangeNotify(SHCNE_UPDATEDIR, SHCNF_PATHA | SHCNF_FLUSH, DESK, 0)


def settle(g):
    time.sleep(1.5)
    g.sync()


def main():
    rec("psi_start", Path("/proc/pressure/cpu").read_text().splitlines()[0])
    with attach() as s:
        g = s.bridge
        before = items(g)
        rec("stock_items", before)

        folder_icon(g, "Fake Computer", r"C:\WINDOWS\SYSTEM\shell32.dll", 15)
        g.put_file(r"C:\WINDOWS\ART98.ICO", ico_bytes())
        folder_icon(g, "Fake Diamond", r"C:\WINDOWS\ART98.ICO", 0)
        url = (
            b"[InternetShortcut]\r\nURL=about:blank\r\n"
            b"IconFile=C:\\WINDOWS\\SYSTEM\\shell32.dll\r\nIconIndex=13\r\n"
        )
        g.put_file(rf"{DESK}\Fake Globe.url", url)
        g.shell32.SHChangeNotify(
            SHCNE_CREATE, SHCNF_PATHA | SHCNF_FLUSH, rf"{DESK}\Fake Globe.url", 0
        )
        settle(g)
        after = items(g)
        rec("new_items", {k: v for k, v in after.items() if k not in before})
        shot(s, "abc_added")

        for name, x, y in [
            ("Fake Computer", 300, 150),
            ("Fake Diamond", 400, 150),
            ("Fake Globe", 500, 150),
        ]:
            it = after.get(name)
            if it:
                g.user32.SendMessageA(
                    shell_windows(g)[2], LVM_SETITEMPOSITION, it["index"], lparam(x, y)
                )
        settle(g)
        rec("moved", {k: v for k, v in items(g).items() if k.startswith("Fake")})
        shot(s, "d_moved")

        g.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST | SHCNF_FLUSH, 0, 0)
        settle(g)
        rec("after_assocchanged", {k: v for k, v in items(g).items() if k.startswith("Fake")})
        shot(s, "e_refreshed")

        s.revert()
        rec("after_revert", [k for k in items(g) if k.startswith("Fake")])
    rec("psi_end", Path("/proc/pressure/cpu").read_text().splitlines()[0])
    (OUT / "results.json").write_text(json.dumps(RES, indent=1))


if __name__ == "__main__":
    main()
