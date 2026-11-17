"""B1 follow-up probe: which windows the gestures in the recipes leave up, and for how long.

Measures, on the stock desktop, the windows a tracking check would see right when a play
returns, and how long each takes to go (or come):
  - Hover on the taskbar clock (hover_dialog.py): the tooltip's class, and when it goes.
  - RightClick on the desktop (pointer_clicks.py): is the menu up when the play returns?
    How long after `esc` until it goes?
  - Menu(pad, "Edit", ...) (menus_keys.py): any #32768 left when the play returns?
  - DoubleClick on My Computer: its exact title and class, and when it appears.
  - Minesweeper clear + sign_scoreboard: the prompt and table classes and pids, and how
    long the table takes to go after sign_scoreboard returns.

Tracking checks are switched off for the probe (Scene.check_tracking is a no-op here), so
the scene sees what the guest does on its own.

Run (VM service up):
    env -u DOCKER_HOST sg docker -c 'uv run python experiments/section-state/probe_windows.py OUTDIR'
Writes OUTDIR/windows.json. Nothing is recorded, and no snapshot is saved.
"""

import json
import os
import sys
import time
from pathlib import Path

from art98.anim import *
from art98.anim import Scene
from art98.container import service
from art98.errors import Art98Error
from art98.settings import load as load_settings

sys.path.insert(0, str(Path(__file__).parent))
from probe import NullRecorder, psi

OUT = Path(sys.argv[1]).resolve()
Scene.check_tracking = lambda self: None  # measure the guest, not the check


def visible(guest, base):
    return [
        {"hwnd": w.hwnd, "class": w.class_name, "title": w.title, "pid": w.pid}
        for w in guest.windows()
        if w.visible and w.hwnd not in base
    ]


def poll(guest, base, until, timeout=5.0, step=0.02):
    """Seconds until `until(rows)` holds, or None after `timeout`. Plus the rows then."""
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        rows = visible(guest, base)
        if until(rows):
            return round(time.monotonic() - start, 3), rows
        time.sleep(step)
    return None, visible(guest, base)


def has(cls):
    return lambda rows: any(r["class"] == cls for r in rows)


def lacks(cls):
    return lambda rows: not any(r["class"] == cls for r in rows)


class Gestures(Scene):
    desktop = "stock"
    pointer_visible = True

    def construct(self):
        g, rep = self.guest, self.report
        base = set(self._baseline) or {w.hwnd for w in g.windows() if w.visible}

        # Hover on the clock.
        self.play(Hover((768, 587), hold=1.5))
        rep["hover_at_return"] = visible(g, base)
        self.play(Glide((500, 150)))
        rep["hover_after_glide"] = visible(g, base)
        rep["hover_gone_after_glide"] = poll(g, base, lambda rows: not rows)

        # Right click on the desktop.
        self.play(RightClick((640, 300)))
        rep["rightclick_at_return"] = visible(g, base)
        rep["rightclick_menu_appears"] = poll(g, base, has("#32768"))
        self.play(Keys("esc"))
        rep["esc_at_return"] = visible(g, base)
        rep["esc_menu_gone"] = poll(g, base, lacks("#32768"))

        # Double click My Computer.
        self.play(DoubleClick((38, 22), run_time=0.9))
        rep["doubleclick_at_return"] = visible(g, base)
        rep["mycomputer_appears"] = poll(
            g, base, lambda rows: any(r["title"] == "My Computer" for r in rows)
        )
        for w in g.windows():
            if w.visible and w.hwnd not in base:
                g.user32.PostMessageA(w.hwnd, 0x0010, 0, 0)  # WM_CLOSE
        rep["mycomputer_gone"] = poll(g, base, lambda rows: not rows)

        # Notepad menus.
        pad = Notepad(at=(130, 80), size=(460, 300))
        self.add(pad)
        base_pad = base | {pad.hwnd}
        pad.set_text("Delete me.")
        self.play(Menu(pad, "Edit", "Select All"))
        rep["menu_selectall_at_return"] = visible(g, base_pad)
        self.play(Menu(pad, "Edit", "Time/Date"))
        rep["menu_timedate_at_return"] = visible(g, base_pad)
        rep["menu_gone"] = poll(g, base_pad, lacks("#32768"))
        self.remove(pad)


class Mines(Scene):
    desktop = "stock"
    pointer_visible = True

    def construct(self):
        g, rep = self.guest, self.report
        board = Minesweeper(at=(300, 120))
        self.add(board)
        base = set(self._baseline) | {board.hwnd}
        rep["minesweeper_pid"] = board._identity[0] if board._identity else None
        board.find_mines()
        board.clear()
        rep["after_clear"] = visible(g, base)
        rep["prompt_appears"] = poll(g, base, lambda rows: bool(rows))
        start = time.monotonic()
        try:
            board.sign_scoreboard()
        except Art98Error as error:  # the claim's release check, if the table lingers
            rep["sign_error"] = f"{type(error).__name__}: {error}"
        rep["sign_seconds"] = round(time.monotonic() - start, 3)
        rep["after_sign_at_return"] = visible(g, base)
        rep["table_gone_after_sign"] = poll(g, base, lambda rows: not rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    settings = load_settings(os.environ.get("ART98_WORK"))
    results = {"psi_start": psi()}
    with service.attach(settings) as session:
        for cls in (Gestures, Mines):
            scene = cls()
            scene.report = {}
            try:
                scene.run(session, NullRecorder())
            except Art98Error as error:  # report what was measured so far
                scene.report["error"] = f"{type(error).__name__}: {error}"
            results[cls.__name__] = scene.report
    results["psi_end"] = psi()
    (OUT / "windows.json").write_text(json.dumps(results, indent=1))
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
