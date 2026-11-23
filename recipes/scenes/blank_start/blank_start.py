"""A blank desktop, a state, a picture and Notepad, the pointer, and three sections.

uv run art98 render recipes/scenes/blank_start/blank_start.py -o blank_start.mp4
uv run art98 render recipes/scenes/blank_start/blank_start.py --section close
"""

from art98.anim import *


class BlankStart(Scene):
    state = "states/desk.json"  # blank desktop + picture "flower" + notepad "note"
    desktop = Desktop(pointer=True)

    def construct(self):
        self.section("type", self.typing)
        self.section("move", self.move)
        self.section("close", self.close_both)

    def typing(self):
        note = self.prop("note")
        self.pause(1)
        self.play(Glide(note.title_bar), run_time=1)
        self.play(TypeWithCursor(note, "hello from a blank desktop\n"))
        self.pause(0.5)

    def move(self):
        flower, note = self.prop("flower"), self.prop("note")
        self.play(Drag(note.title_bar, by=(-200, 80)), run_time=1.5)
        self.play(Teleport(flower, to=(500, 60), aligned_edge=UL))
        self.pause(1)

    def close_both(self):
        flower, note = self.prop("flower"), self.prop("note")
        self.play(Close(flower), Close(note))
        self.pause(1)
