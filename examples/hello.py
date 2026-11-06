"""The Windows 98 equivalent of a triangle on screen.

Notepad opens, types a line, drifts across the desktop and closes.

    uv run art98 render examples/hello.py Hello -o hello.mp4
"""

from art98.anim import *


class Hello(Scene):
    def construct(self):
        pad = Notepad()
        self.add(pad)
        self.pause(0.5)
        self.play(TypeWithCursor(pad, "hello from 1998"))
        self.wait(1)
        self.play(pad.animate.shift(280 * RIGHT + 120 * DOWN), run_time=2)
        self.pause(1)
        self.play(Close(pad))
        self.pause(1)
