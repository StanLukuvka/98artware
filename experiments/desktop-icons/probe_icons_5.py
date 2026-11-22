"""Throwaway probe 5: the review's open points.

    uv run art98 vm start
    .venv/bin/python experiments/desktop-icons/probe_icons_5.py OUTDIR

  T  all-caps labels ("PC", "TEMP", "MY STUFF"): how does Explorer list them?
  U  remove "Swap" and add "Swap" again with a different image at a new .ico path
  V  every named guest image Dialog uses (shell32, main.cpl, modem.cpl, user.exe)
  W  blank: remove the last fake icon with the list shown, hide the list, then RMDIR with it hidden
"""

import importlib.util
import time
from pathlib import Path

_spec = importlib.util.spec_from_file_location("p3", Path(__file__).with_name("probe_icons_3.py"))
p3 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p3)
p1 = p3.p1
rec, shot, items = p1.rec, p1.shot, p1.items

from art98.container.service import attach  # noqa: E402
from art98.desktop import blank, shell_windows  # noqa: E402
from art98.actions.programs.dialog import Dialog  # noqa: E402

SW_HIDE = 0


def red_ico():
    return p1.ico_bytes().replace(bytes((0, 128, 255)), bytes((0, 0, 255)))


def main():
    rec("psi_start", Path("/proc/pressure/cpu").read_text().splitlines()[0])
    with attach() as s:
        g = s.bridge
        for label in ["PC", "TEMP", "MY STUFF", "ABCDEFGHI"]:
            p3.add(g, label, r"C:\WINDOWS\SYSTEM\shell32.dll", 4)
        time.sleep(1.0)
        g.sync()
        rec("T/listed", sorted(k for k in items(g) if k.upper() in {"PC", "TEMP", "MY STUFF", "ABCDEFGHI"}))

        g.put_file(r"C:\WINDOWS\SWAPA.ICO", p1.ico_bytes())
        p3.add(g, "Swap", r"C:\WINDOWS\SWAPA.ICO", 0)
        p3.wait(lambda: "Swap" in items(g))
        p3.remove(g, "Swap")
        p3.wait(lambda: "Swap" not in items(g))
        g.put_file(r"C:\WINDOWS\SWAPB.ICO", red_ico())
        p3.add(g, "Swap", r"C:\WINDOWS\SWAPB.ICO", 0)
        p3.wait(lambda: "Swap" in items(g))
        p3.place(g, "Swap", 300, 100)

        for n, (key, (dll, index)) in enumerate(Dialog.CUSTOM_ICONS.items()):
            p3.add(g, f"Key {key}", dll, index)
            p3.wait(lambda key=key: f"Key {key}" in items(g))
            p3.place(g, f"Key {key}", 200 + 75 * (n % 6), 250 + 75 * (n // 6))
        g.sync()
        shot(s, "tuv")

        s.revert()
        blank(g)
        g.user32.ShowWindow(shell_windows(g)[2], p3.SW_SHOW)
        p3.delete_stock(g)
        p3.add(g, "Last", r"C:\WINDOWS\SYSTEM\shell32.dll", 15)
        p3.wait(lambda: "Last" in items(g))
        p3.remove(g, "Last")
        rec("W/gone_s", p3.wait(lambda: "Last" not in items(g)))
        g.user32.ShowWindow(shell_windows(g)[2], SW_HIDE)
        rec("W/list_visible", g.user32.IsWindowVisible(shell_windows(g)[2]).value)
        p3.add(g, "Hidden", r"C:\WINDOWS\SYSTEM\shell32.dll", 15)
        rec("W/added_while_hidden_s", p3.wait(lambda: "Hidden" in items(g)))
        p3.remove(g, "Hidden")
        rec("W/removed_while_hidden_s", p3.wait(lambda: "Hidden" not in items(g)))
        time.sleep(1.0)
        rec("W/items_left", items(g))
        rec("W/list_visible_end", g.user32.IsWindowVisible(shell_windows(g)[2]).value)
        g.sync()
        shot(s, "w_blank_after")
        s.revert()
    rec("psi_end", Path("/proc/pressure/cpu").read_text().splitlines()[0])
    (p1.OUT / "results5.json").write_text(p1.json.dumps(p1.RES, indent=1))


if __name__ == "__main__":
    main()
