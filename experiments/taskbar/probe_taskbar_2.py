"""The open points the taskbar requirements left for a probe (requirements.md, questions 1, 4, 7, 8, 9).

    uv run art98 vm start
    .venv/bin/python experiments/taskbar/probe_taskbar_2.py OUTDIR

Attaches to the running VM and reverts before every case. Throwaway probe: no source
edits, no savevm. Reuses the helpers in probe_taskbar.py. Writes OUTDIR/results.json and
a PNG per step.
"""

import importlib.util
import json
from pathlib import Path

from art98.container.service import attach
from art98.desktop import hide_pointer, set_colour, set_wallpaper, shell_windows
from art98.guest.bridge import wait_for
from art98.guest.win32 import set_display_mode

_spec = importlib.util.spec_from_file_location("p1", Path(__file__).with_name("probe_taskbar.py"))
p1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p1)  # sets p1.OUT from sys.argv[1]
rec, shot, find, part_visible = p1.rec, p1.shot, p1.find, p1.part_visible

SW_HIDE = 0
WM_SIZE, WM_SETTINGCHANGE, WM_WININICHANGE = 0x0005, 0x001A, 0x001A
TEAL = (0, 128, 128)
HIDE = ["MSTaskSwWClass", "TrayClockWClass", "TrayNotifyWnd"]


def rect(g, class_name):
    hwnd = find(g, shell_windows(g)[0], class_name)
    return next((list(w.rect) for w in g.windows(shell_windows(g)[0]) if w.hwnd == hwnd), None)


def hide(g, class_name):
    g.user32.ShowWindow(find(g, shell_windows(g)[0], class_name), SW_HIDE)


def open_notepad(g):
    seen = {w.hwnd for w in g.windows() if w.class_name == "Notepad"}
    g.spawn("notepad.exe")
    hwnd = wait_for(
        lambda: next((w.hwnd for w in g.windows()
                      if w.class_name == "Notepad" and w.visible and w.hwnd not in seen), None),
        15, 0.2,
    )  # fmt: skip
    g.sync()
    return hwnd


def visible(g):
    return {part: part_visible(g, part) for part in HIDE}


def main():
    rec("psi_start", Path("/proc/pressure/cpu").read_text().splitlines()[0])
    with attach() as s:
        g = s.bridge

        # Q1: quick launch hidden on its own, with a window open.
        s.revert()
        open_notepad(g)
        before = {"quick_launch": rect(g, "ToolbarWindow32"), "buttons": rect(g, "MSTaskSwWClass")}
        hide(g, "ToolbarWindow32")
        g.sync()
        shot(s, "Q1-quick-launch-hidden")
        set_colour(g, TEAL)
        after_colour = part_visible(g, "ToolbarWindow32")
        shot(s, "Q1-quick-launch-after-colour")
        rec("Q1", {"before": before, "buttons_after": rect(g, "MSTaskSwWClass"),
                   "hidden_visible": False, "visible_after_colour": after_colour})  # fmt: skip

        # Q7: settle the tray after hiding the clock, without a colour change.
        tries = {
            "none": lambda: None,
            "WM_SIZE_taskbar": lambda: g.user32.SendMessageA(shell_windows(g)[0], WM_SIZE, 0, 0),
            "WM_SETTINGCHANGE_taskbar": lambda: g.user32.SendMessageA(
                shell_windows(g)[0], WM_SETTINGCHANGE, 0, 0),
            "same_colour": lambda: set_colour(g, TEAL),
        }  # fmt: skip
        out = {}
        for name, settle in tries.items():
            s.revert()
            base = rect(g, "TrayNotifyWnd")
            hide(g, "TrayClockWClass")
            settle()
            g.sync()
            out[name] = {"tray_before": base, "tray_after": rect(g, "TrayNotifyWnd"),
                         "clock_visible": part_visible(g, "TrayClockWClass")}  # fmt: skip
            shot(s, f"Q7-{name}")
        rec("Q7", out)

        # Q8: does the wallpaper's broadcast or a display mode change show hidden parts?
        cases = {
            "wallpaper_none": lambda: set_wallpaper(g, "", "center"),
            "display_1024": lambda: set_display_mode(g, 1024, 768, 16, persist=False),
        }
        for name, change in cases.items():
            s.revert()
            for part in HIDE:
                hide(g, part)
            g.sync()
            hidden = visible(g)
            try:
                change()
                g.sync()
                error = None
            except Exception as e:  # noqa: BLE001
                error = repr(e)
            rec(f"Q8.{name}", {"after_hide": hidden, "after_change": visible(g), "error": error,
                               "rects": {p: rect(g, p) for p in [*HIDE, "ReBarWindow32"]}})  # fmt: skip
            shot(s, f"Q8-{name}")

        # Q9: other resolutions: hide after the mode change, read the rects back.
        for mode in [(640, 480, 16), (1024, 768, 16), (1280, 1024, 16)]:
            s.revert()
            try:
                set_display_mode(g, *mode, persist=False)
                g.sync()
            except Exception as e:  # noqa: BLE001
                rec(f"Q9.{mode[0]}", {"error": repr(e)})
                continue
            open_notepad(g)
            for part in HIDE:
                hide(g, part)
            g.sync()
            rec(f"Q9.{mode[0]}", {"visible": visible(g),
                                  "taskbar": next(list(w.rect) for w in g.windows()
                                                  if w.hwnd == shell_windows(g)[0]),
                                  "rebar": rect(g, "ReBarWindow32")})  # fmt: skip
            shot(s, f"Q9-{mode[0]}")

        # Q4: icons and the pointer on the stock desktop.
        s.revert()
        icons = shell_windows(g)[2]
        g.user32.ShowWindow(icons, SW_HIDE)
        g.sync()
        hidden = not g.user32.IsWindowVisible(icons).value
        set_colour(g, (0, 0, 128))
        after_colour = bool(g.user32.IsWindowVisible(icons).value)
        shot(s, "Q4-icons-hidden-after-colour")
        s.revert()
        g.user32.SetCursorPos(400, 300)
        g.sync()
        shot(s, "Q4-pointer-before")
        hide_pointer(g)
        g.user32.SetCursorPos(420, 320)
        g.sync()
        shot(s, "Q4-pointer-hidden")
        rec("Q4", {"icons_hidden": hidden, "icons_visible_after_colour": after_colour})
        s.revert()
    rec("psi_end", Path("/proc/pressure/cpu").read_text().splitlines()[0])
    (p1.OUT / "results.json").write_text(json.dumps(p1.RES, indent=2) + "\n")


if __name__ == "__main__":
    main()
