"""Hiding parts of the taskbar on the stock desktop, and what undoes it.

    uv run art98 vm start
    .venv/bin/python experiments/taskbar/probe_taskbar.py OUTDIR

Attaches to the running VM and reverts before every case, so cases don't leak into each other.
Throwaway probe: no source edits, no savevm. Writes OUTDIR/results.json and a PNG per step.
Per-window taskbar buttons are left out: hiding the buttons area covers that.
"""

import json
import sys
import time
from pathlib import Path

from art98.container.service import attach
from art98.desktop import set_colour, shell_windows

OUT = Path(sys.argv[1]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
RES: dict = {}
T0 = time.perf_counter()

SW_HIDE = 0
TCM_GETITEMCOUNT, TB_BUTTONCOUNT = 0x1304, 0x418
PARTS = ["MSTaskSwWClass", "TrayClockWClass", "ReBarWindow32", "TrayNotifyWnd"]
TEAL = (0, 128, 128)


def rec(key, value):
    RES[key] = value
    print(f"[{time.perf_counter() - T0:6.1f}s] {key} = {value}", flush=True)


def tree(guest, hwnd, depth=0, out=None):
    out = [] if out is None else out
    for w in guest.windows(hwnd):
        out.append(
            {"depth": depth, "hwnd": w.hwnd, "class": w.class_name, "visible": w.visible,
             "rect": list(w.rect), "title": w.title}
        )  # fmt: skip
        tree(guest, w.hwnd, depth + 1, out)
    return out


def find(guest, root, class_name):
    for w in guest.windows(root):
        if w.class_name == class_name:
            return w.hwnd
        found = find(guest, w.hwnd, class_name)
        if found:
            return found
    return 0


def buttons(guest) -> int | None:
    """How many window buttons the taskbar shows (tab control on Win98, toolbar on later shells)."""
    taskbar = shell_windows(guest)[0]
    tab = find(guest, taskbar, "SysTabControl32")
    if tab:
        return guest.user32.SendMessageA(tab, TCM_GETITEMCOUNT, 0, 0).value
    bar = find(guest, find(guest, taskbar, "MSTaskSwWClass"), "ToolbarWindow32")
    if bar:
        return guest.user32.SendMessageA(bar, TB_BUTTONCOUNT, 0, 0).value
    return None


def shot(session, name):
    ppm = session.vm.screenshot(OUT / f"{name}.ppm", format="ppm")
    try:
        from PIL import Image

        Image.open(ppm).save(OUT / f"{name}.png")
        ppm.unlink()
    except Exception:  # noqa: BLE001, S110
        pass


def part_visible(guest, class_name):
    hwnd = find(guest, shell_windows(guest)[0], class_name)
    return bool(hwnd) and bool(guest.user32.IsWindowVisible(hwnd).value)


def main():
    rec("psi_start", Path("/proc/pressure/cpu").read_text().splitlines()[0])
    with attach() as session:
        g = session.bridge
        taskbar = shell_windows(g)[0]
        rec("taskbar_tree", tree(g, taskbar))
        rec("baseline_buttons", buttons(g))
        shot(session, "00-baseline")

        # A: hide each part; does a colour change undo it; does a revert undo it.
        for part in PARTS:
            session.revert()
            hwnd = find(g, shell_windows(g)[0], part)
            if not hwnd:
                rec(f"A.{part}", "not found")
                continue
            g.user32.ShowWindow(hwnd, SW_HIDE)
            g.sync()
            hidden = not part_visible(g, part)
            shot(session, f"A-{part}-hidden")
            set_colour(g, TEAL)
            g.sync()
            after_colour = part_visible(g, part)
            shot(session, f"A-{part}-after-colour")
            # a second hide after the colour change: does it stay hidden?
            g.user32.ShowWindow(find(g, shell_windows(g)[0], part), SW_HIDE)
            set_colour(g, (0, 0, 128))
            g.sync()
            after_second = part_visible(g, part)
            session.revert()
            after_revert = part_visible(g, part)
            rec(f"A.{part}", {"hidden": hidden, "visible_after_colour": after_colour,
                              "visible_after_rehide_and_colour": after_second,
                              "visible_after_revert": after_revert})  # fmt: skip

        session.revert()
    rec("psi_end", Path("/proc/pressure/cpu").read_text().splitlines()[0])
    (OUT / "results.json").write_text(json.dumps(RES, indent=2) + "\n")


if __name__ == "__main__":
    main()
