"""B2 check on the real image: get_state, then set_state of the capture, round trip.

A Picture and a Notepad (one maximized, one typed into) are captured with get_state, then a
second scene sets the capture (set_state runs check_state against the guest) and captures
again. The two JSON files should match.

Run (VM service up):
    env -u DOCKER_HOST sg docker -c 'uv run python experiments/section-state/probe_get_state.py OUTDIR'
Nothing is recorded, and no snapshot is saved.
"""

import os
import sys
from pathlib import Path

from art98.actions.programs.notepad import Notepad
from art98.actions.programs.picture import Picture
from art98.anim import Scene
from art98.container import service
from art98.settings import load as load_settings

sys.path.insert(0, str(Path(__file__).parent))
from probe import NullRecorder, psi

OUT = Path(sys.argv[1]).resolve()
ROOT = Path(__file__).resolve().parents[2]
IMAGE = next((ROOT / "recipes").rglob("*.bmp"))


class Capture(Scene):
    desktop = "stock"
    pointer_visible = True

    def construct(self):
        pic = Picture(image=IMAGE, at=(40, 40), size=(320, 240))
        self.add(pic, id="pic")
        pad = Notepad(at=(200, 120), size=(360, 240))
        self.add(pad, id="pad")
        pad.set_text("Hello from art98.\r\nSecond line.")
        pic.maximize()
        self.pointer.place((500, 400))
        self.get_state(OUT / "first.state.json")


class Restore(Scene):
    desktop = "stock"
    pointer_visible = True

    def construct(self):
        self.set_state(OUT / "first.state.json")
        self.get_state(OUT / "second.state.json")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    settings = load_settings(os.environ.get("ART98_WORK"))
    print("psi", psi())
    with service.attach(settings) as session:
        for cls in (Capture, Restore):
            cls().run(session, NullRecorder())
    first = (OUT / "first.state.json").read_text()
    second = (OUT / "second.state.json").read_text()
    print(first)
    print("round trip identical:", first == second)
    if first != second:
        print(second)
    print("psi", psi())


if __name__ == "__main__":
    main()
