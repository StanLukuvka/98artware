"""Window motion: a move, a resize, and both at once, as one SetWindowPos a frame."""

from art98.anim import *
from art98.anim.apps import Notepad  # parked, see apps.py


class WindowMotion(Scene):
    desktop = "stock"  # made before the blank start, and it shows the pointer

    def construct(self):
        pad = Notepad(at=(100, 80), size=(320, 220))
        self.add(pad)
        self.pointer.place((780, 20))
        pad.set_text("Everything here is a real window.")
        self.pause(0.4)
        self.play(pad.animate.shift(320 * RIGHT + 60 * DOWN), run_time=1.2)
        self.play(pad.animate.resize(200, 140), run_time=0.8)
        self.play(pad.animate.to_corner(UL, buff=90), pad.animate.resize(420, 300), run_time=1.2)
        self.play(MoveAlongPath(pad, [(400, 200), (480, 340), (300, 340), (400, 200)]), run_time=2)
        self.pause(0.6)
