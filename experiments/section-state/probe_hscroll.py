"""B4 follow-up: the Notepad Edit's horizontal scroll info, typed (full run) vs set (solo).

Typed: blank_start's desk.json, then the full run's typing. Set: the 02-move capture.
Each reads GetScrollInfo(edit, SB_HORZ) and the edit's window style.

    env -u DOCKER_HOST sg docker -c 'uv run python experiments/section-state/probe_hscroll.py'
Nothing is recorded, and no snapshot is saved.
"""

import json
import os
import struct
import sys
from pathlib import Path

from art98.anim import *
from art98.anim import Scene
from art98.container import service
from art98.guest.win32 import window_style
from art98.settings import load as load_settings

sys.path.insert(0, str(Path(__file__).parent))
from probe import NullRecorder, psi

BLANK = Path(__file__).resolve().parents[2] / "recipes/scenes/blank_start"
SB_HORZ, SIF_ALL = 0, 0x17


def hscroll(scene, note):
    g = scene.guest
    buf = struct.pack("<IIiiIii", 28, SIF_ALL, 0, 0, 0, 0, 0)
    r = g.user32.GetScrollInfo(note.edit_hwnd, SB_HORZ, buf)
    info = struct.unpack("<IIiiIii", r.buffers[0])[2:] if r.value else None
    return {"min,max,page,pos,track": info, "style": hex(window_style(g, note.edit_hwnd))}


class Typed(Scene):
    state = BLANK / "states/desk.json"
    pointer_visible = True

    def construct(self):
        note = self.prop("note")
        self.report["start"] = hscroll(self, note)
        self.play(TypeWithCursor(note, "hello from a blank desktop\n"))
        self.report["typed"] = hscroll(self, note)


class Set(Scene):
    state = BLANK / "blank_start.BlankStart.sections/02-move.state.json"
    pointer_visible = True

    def construct(self):
        note = self.prop("note")
        self.report["start"] = hscroll(self, note)
        u, e = self.guest.user32, note.edit_hwnd
        u.SendMessageA(e, 0x00B1, 28, 28)
        for name, code in (("x", ord("x")), ("back", 8), ("enter", 13), ("back2", 8)):
            u.SendMessageA(e, 0x0102, code, 1)
            self.report[name] = hscroll(self, note)


def main():
    settings = load_settings(os.environ.get("ART98_WORK"))
    out = {"psi": psi()}
    with service.attach(settings) as session:
        for cls in (Typed, Set):
            scene = cls()
            scene.report = {}
            scene.run(session, NullRecorder())
            out[cls.__name__] = scene.report
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
