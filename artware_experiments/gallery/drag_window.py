"""Dragging: Windows moves the window itself, because the pointer holds its title bar."""

from art98.anim import *
from art98.anim.apps import Notepad  # parked, see apps.py


class DragWindow(Scene):
    desktop = "stock"  # made before the blank start, and it shows the pointer

    def construct(self):
        pad = Notepad(at=(90, 60), size=(340, 240))
        self.add(pad)
        pad.set_text("Pulled by the title bar.")
        self.pause(0.3)
        self.play(Drag(pad.title_bar, by=(280, 150), run_time=1.6))
        self.pause(0.3)
        self.play(Drag(pad.corner(DR), by=(-60, 100), run_time=1.4))
        self.pause(0.8)
