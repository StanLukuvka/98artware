"""Typing: letters reach a real Edit control, and the caret moves with them."""

from art98.anim import *
from art98.anim.apps import Notepad  # parked, see apps.py


class Typing(Scene):
    def construct(self):
        pad = Notepad(at=(120, 90), size=(480, 300))
        self.add(pad)
        self.pointer.place((700, 500))
        self.pause(0.4)
        self.play(TypeWithCursor(pad, "Dear diary,\n\nToday the computer wrote back.", run_time=3))
        self.wait(0.8)
        self.play(UntypeWithCursor(pad, 11, run_time=0.8))
        self.play(TypeWithCursor(pad, "typed by itself.", run_time=1.6))
        self.wait(1)
