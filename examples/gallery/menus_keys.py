"""Menus and keys: real menu clicks select and stamp, real key presses delete and type."""

from art98.anim import *
from art98.anim.apps import Notepad  # parked, see apps.py


class MenusKeys(Scene):
    desktop = "stock"  # made before the blank start, and it shows the pointer

    def construct(self):
        pad = Notepad(at=(130, 80), size=(460, 300))
        self.add(pad)
        pad.set_text("Delete me.")
        self.pause(0.3)
        self.play(Menu(pad, "Edit", "Select All"))
        self.pause(0.4)
        self.play(Keys("delete"))
        self.play(Menu(pad, "Edit", "Time/Date"))
        self.pause(0.4)
        self.play(TypeKeys("  Hello & 'goodbye'!", run_time=2))
        self.pause(0.8)
