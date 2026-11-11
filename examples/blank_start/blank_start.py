"""A blank desktop, a state, a picture and Notepad, the pointer, and a cut.

    uv run art98 render examples/blank_start/blank_start.py -o blank_start.mp4
"""

from art98.anim import *


class BlankStart(Scene):
    state = "states/desk.json"  # blank desktop + picture "flower" + notepad "note"
    pointer_visible = True

    def construct(self):
        flower, note = self.prop("flower"), self.prop("note")
        self.pause(1)
        self.play(Glide(note.title_bar), run_time=1)
        self.play(TypeWithCursor(note, "hello from a blank desktop\n"))
        self.pause(0.5)
        self.next_section("move")  # clip 1 ends here
        self.play(Drag(note.title_bar, by=(-200, 80)), run_time=1.5)
        self.play(Teleport(flower, to=(500, 60), aligned_edge=UL))
        self.pause(1)
        self.next_section("close")
        self.play(Close(flower), Close(note))
        self.pause(1)
