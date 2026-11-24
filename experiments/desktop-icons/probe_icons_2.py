"""Throwaway probe 2: fake icons on a blank desktop, refreshes, timing, icon cache. No source edits.

  F  blank(): add a fake icon, show the list, delete the stock items with LVM_DELETEITEM
  G  set_colour after F: do the stock items come back? the fake one keep its place?
  H  SHChangeNotify(UPDATEDIR) after F: same question
  I  how long until a new folder shows in the list (poll), and until a removed one goes
  J  rewrite the .ico at the same path with a new image: stale icon from the cache?
  K  label rules: a long label, a label with a dot, a name clash with a stock item
"""

import importlib.util
import time
from pathlib import Path

_spec = importlib.util.spec_from_file_location("p1", Path(__file__).with_name("probe_icons.py"))
p1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p1)  # sets p1.OUT from sys.argv[1]
rec, shot, items, folder_icon, ico_bytes, lparam = p1.rec, p1.shot, p1.items, p1.folder_icon, p1.ico_bytes, p1.lparam

from art98.container.service import attach
from art98.desktop import NAMED_COLOURS, blank, set_colour, shell_windows

LVM_DELETEITEM, LVM_SETITEMPOSITION = 0x1008, 0x100F
SHCNE_RMDIR, SHCNE_UPDATEDIR = 0x10, 0x1000
SHCNF_PATHA, SHCNF_FLUSH = 0x1, 0x1000
SW_SHOW = 5
DESK = p1.DESK
STOCK = {"My Computer", "My Documents", "Internet Explorer", "Recycle Bin",
         "Setup MSN Internet Access", "Online Services", "Outlook Express"}  # fmt: skip


def wait_names(g, want, gone=False, timeout=10.0):
    t = time.perf_counter()
    while time.perf_counter() - t < timeout:
        names = set(items(g))
        if (not (want & names)) if gone else want <= names:
            return round(time.perf_counter() - t, 2)
        time.sleep(0.05)
    return None


def delete_stock(g):
    lv = shell_windows(g)[2]
    for name in STOCK:
        it = items(g).get(name)
        if it:
            g.user32.SendMessageA(lv, LVM_DELETEITEM, it["index"], 0)


def place(g, name, x, y):
    it = items(g).get(name)
    if it:
        g.user32.SendMessageA(shell_windows(g)[2], LVM_SETITEMPOSITION, it["index"], lparam(x, y))


def red_ico():
    data = bytearray(ico_bytes())
    return bytes(data).replace(bytes((0, 128, 255)), bytes((0, 0, 255)))  # orange -> red


def main():
    rec("psi_start", Path("/proc/pressure/cpu").read_text().splitlines()[0])
    with attach() as s:
        g = s.bridge
        # F
        blank(g)
        g.put_file(r"C:\WINDOWS\ART98.ICO", ico_bytes())
        folder_icon(g, "Fake Diamond", r"C:\WINDOWS\ART98.ICO", 0)
        rec("F/appear_s", wait_names(g, {"Fake Diamond"}))
        delete_stock(g)
        place(g, "Fake Diamond", 380, 260)
        g.user32.ShowWindow(shell_windows(g)[2], SW_SHOW)
        g.sync()
        rec("F/items", items(g))
        shot(s, "f_blank_fake")

        # G
        set_colour(g, NAMED_COLOURS["black"])
        g.user32.ShowWindow(shell_windows(g)[2], SW_SHOW)  # set_colour re-hides a hidden list
        time.sleep(1.0)
        g.sync()
        rec("G/items_after_colour", items(g))
        shot(s, "g_after_colour")

        # H
        delete_stock(g)
        g.shell32.SHChangeNotify(SHCNE_UPDATEDIR, SHCNF_PATHA | SHCNF_FLUSH, DESK, 0)
        time.sleep(1.5)
        g.sync()
        rec("H/items_after_updatedir", items(g))
        shot(s, "h_after_updatedir")

        # I
        s.revert()
        t = time.perf_counter()
        folder_icon(g, "Timing One", r"C:\WINDOWS\SYSTEM\shell32.dll", 15)
        rec("I/create_calls_s", round(time.perf_counter() - t, 2))
        rec("I/appear_s", wait_names(g, {"Timing One"}))
        t = time.perf_counter()
        path = rf"{DESK}\Timing One"
        g.kernel32.SetFileAttributesA(path, 0)
        g.kernel32.SetFileAttributesA(rf"{path}\desktop.ini", 0)
        rec("I/del_ini", g.kernel32.DeleteFileA(rf"{path}\desktop.ini").value)
        rec("I/rmdir", g.kernel32.RemoveDirectoryA(path).value)
        g.shell32.SHChangeNotify(SHCNE_RMDIR, SHCNF_PATHA | SHCNF_FLUSH, path, 0)
        rec("I/gone_s", wait_names(g, {"Timing One"}, gone=True))

        # J
        g.put_file(r"C:\WINDOWS\ART98.ICO", ico_bytes())
        folder_icon(g, "Cache A", r"C:\WINDOWS\ART98.ICO", 0)
        wait_names(g, {"Cache A"})
        place(g, "Cache A", 300, 100)
        g.put_file(r"C:\WINDOWS\ART98.ICO", red_ico())
        folder_icon(g, "Cache B", r"C:\WINDOWS\ART98.ICO", 0)
        wait_names(g, {"Cache B"})
        place(g, "Cache B", 400, 100)
        g.put_file(r"C:\WINDOWS\ART98B.ICO", red_ico())
        folder_icon(g, "Cache C", r"C:\WINDOWS\ART98B.ICO", 0)
        wait_names(g, {"Cache C"})
        place(g, "Cache C", 500, 100)

        # K
        for label in ["A Rather Long Label For An Icon", "notes.txt", "My Computer"]:
            folder_icon(g, label, r"C:\WINDOWS\SYSTEM\shell32.dll", 4)
        time.sleep(2)
        g.sync()
        rec("K/items", items(g))
        for n, label in enumerate(["A Rather Long Label For An Icon", "notes.txt"]):
            place(g, label, 300 + 120 * n, 300)
        g.sync()
        shot(s, "jk_cache_labels")
        s.revert()
    (p1.OUT / "results2.json").write_text(p1.json.dumps(p1.RES, indent=1))


if __name__ == "__main__":
    main()
