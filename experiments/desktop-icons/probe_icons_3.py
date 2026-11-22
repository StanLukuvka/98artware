"""Throwaway probe 3: fake icons on a blank desktop without bringing the stock icons back.

    uv run art98 vm start
    .venv/bin/python experiments/desktop-icons/probe_icons_3.py OUTDIR

  L  blank(), show the list, delete the stock items, then add a fake with SHCNE_MKDIR only
     (no SHCNE_UPDATEDIR): do the stock items stay away? how long until it shows?
  M  clear the focus and selection of every item (LVM_SETITEMSTATE, index -1)
  N  remove the fake (RMDIR + SHCNE_RMDIR): do the stock items stay away?
  O  open and close Notepad, and wait 5 s: does anything bring the stock items back?
  P  a second fake at a place another fake already holds: does Explorer move either one?
"""

import importlib.util
import struct
import time
from pathlib import Path

_spec = importlib.util.spec_from_file_location("p1", Path(__file__).with_name("probe_icons.py"))
p1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p1)  # sets p1.OUT from sys.argv[1]
rec, shot, items, ico_bytes, lparam = p1.rec, p1.shot, p1.items, p1.ico_bytes, p1.lparam

from art98.container.service import attach  # noqa: E402
from art98.desktop import blank, shell_windows  # noqa: E402

LVM_DELETEITEM, LVM_SETITEMPOSITION, LVM_SETITEMSTATE = 0x1008, 0x100F, 0x102B
LVIS_FOCUSED, LVIS_SELECTED = 0x1, 0x2
SHCNE_MKDIR, SHCNE_RMDIR = 0x8, 0x10
SHCNF_PATHA, SHCNF_FLUSH = 0x1, 0x1000
ATTR_HIDDEN, ATTR_SYSTEM = 0x2, 0x4
WM_CLOSE, SW_SHOW = 0x10, 5
DESK = p1.DESK
STOCK = {"My Computer", "My Documents", "Internet Explorer", "Recycle Bin",
         "Setup MSN Internet Access", "Online Services", "Outlook Express"}  # fmt: skip


def stock_left(g):
    return sorted(STOCK & set(items(g)))


def delete_stock(g):
    lv = shell_windows(g)[2]
    for name in STOCK:
        it = items(g).get(name)
        if it:
            g.user32.SendMessageA(lv, LVM_DELETEITEM, it["index"], 0)


def add(g, name, icon_file, index):
    path = rf"{DESK}\{name}"
    g.kernel32.CreateDirectoryA(path, 0)
    ini = f"[.ShellClassInfo]\r\nIconFile={icon_file}\r\nIconIndex={index}\r\n".encode()
    g.put_file(rf"{path}\desktop.ini", ini)
    g.kernel32.SetFileAttributesA(rf"{path}\desktop.ini", ATTR_HIDDEN | ATTR_SYSTEM)
    g.kernel32.SetFileAttributesA(path, ATTR_SYSTEM)
    g.shell32.SHChangeNotify(SHCNE_MKDIR, SHCNF_PATHA | SHCNF_FLUSH, path, 0)


def remove(g, name):
    path = rf"{DESK}\{name}"
    g.kernel32.SetFileAttributesA(rf"{path}\desktop.ini", 0)
    g.kernel32.DeleteFileA(rf"{path}\desktop.ini")
    g.kernel32.SetFileAttributesA(path, 0)
    ok = g.kernel32.RemoveDirectoryA(path).value
    g.shell32.SHChangeNotify(SHCNE_RMDIR, SHCNF_PATHA | SHCNF_FLUSH, path, 0)
    return ok


def wait(look, timeout=10.0):
    t = time.perf_counter()
    while time.perf_counter() - t < timeout:
        if look():
            return round(time.perf_counter() - t, 2)
        time.sleep(0.05)
    return None


def place(g, name, x, y):
    it = items(g)[name]
    g.user32.SendMessageA(shell_windows(g)[2], LVM_SETITEMPOSITION, it["index"], lparam(x, y))


def clear_state(g):
    k = g.kernel32
    mem = k.VirtualAlloc(0, 4096, 0x08003000, 4).value
    try:
        mask = LVIS_FOCUSED | LVIS_SELECTED
        item = struct.pack("<IiiIIIiiI", 0x8, 0, 0, 0, mask, 0, 0, 0, 0)  # LVIF_STATE
        k.RtlMoveMemory(mem, item, len(item))
        return g.user32.SendMessageA(shell_windows(g)[2], LVM_SETITEMSTATE, -1 & 0xFFFFFFFF, mem).value
    finally:
        k.VirtualFree(mem, 0, 0x8000)


def main():
    rec("psi_start", Path("/proc/pressure/cpu").read_text().splitlines()[0])
    with attach() as s:
        g = s.bridge
        blank(g)
        g.user32.ShowWindow(shell_windows(g)[2], SW_SHOW)
        delete_stock(g)
        rec("L/stock_after_delete", stock_left(g))
        g.put_file(r"C:\WINDOWS\ART98A.ICO", ico_bytes())
        add(g, "Fake One", r"C:\WINDOWS\ART98A.ICO", 0)
        rec("L/appear_s", wait(lambda: "Fake One" in items(g)))
        time.sleep(1.0)
        rec("L/stock_after_add", stock_left(g))
        place(g, "Fake One", 200, 200)
        g.sync()
        shot(s, "l_added")

        rec("M/clear_state", clear_state(g))
        g.sync()
        shot(s, "m_cleared")

        add(g, "Fake Two", r"C:\WINDOWS\SYSTEM\shell32.dll", 15)
        wait(lambda: "Fake Two" in items(g))
        place(g, "Fake Two", 200, 200)
        g.sync()
        time.sleep(1.0)
        rec("P/same_place", {k: v for k, v in items(g).items() if k.startswith("Fake")})
        place(g, "Fake Two", 320, 200)
        clear_state(g)
        g.sync()
        shot(s, "p_two")

        rec("N/rmdir", remove(g, "Fake One"))
        rec("N/gone_s", wait(lambda: "Fake One" not in items(g)))
        time.sleep(1.0)
        rec("N/stock_after_remove", stock_left(g))
        rec("N/items", items(g))

        seen = {w.hwnd for w in g.windows() if w.class_name == "Notepad"}
        g.spawn("notepad.exe")
        pad = p1_wait_window(g, seen)
        time.sleep(1.0)
        g.user32.PostMessageA(pad, WM_CLOSE, 0, 0)
        time.sleep(5.0)
        g.sync()
        rec("O/stock_after_notepad_and_5s", stock_left(g))
        shot(s, "o_after")
        s.revert()
    rec("psi_end", Path("/proc/pressure/cpu").read_text().splitlines()[0])
    (p1.OUT / "results3.json").write_text(p1.json.dumps(p1.RES, indent=1))


def p1_wait_window(g, seen):
    t = time.perf_counter()
    while time.perf_counter() - t < 15:
        for w in g.windows():
            if w.class_name == "Notepad" and w.visible and w.hwnd not in seen:
                return w.hwnd
        time.sleep(0.2)
    raise RuntimeError("no notepad")


if __name__ == "__main__":
    main()
