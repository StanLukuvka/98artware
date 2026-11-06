"""Paint: real strokes and real fills, with buttons found from the live window.

Paint is moved and resized first, so nothing here can rest on one layout.
"""

import math

from art98.anim import *

WIDTH, HEIGHT = 400, 310
RADIUS = 110


class PaintDrawing(Scene):
    def construct(self):
        paint = Paint(at=(150, 40), size=(520, 480))
        self.add(paint)
        self.pause(0.3)
        self.play(paint.animate.shift(90 * LEFT + 30 * DOWN), paint.animate.resize(500, 460),
                  run_time=0.7)
        self.play(paint.resize_canvas(WIDTH, HEIGHT, run_time=1))

        def flower(t):
            angle = 2 * math.pi * t
            radius = RADIUS * (1 + 0.3 * math.cos(6 * angle))
            return paint.canvas(WIDTH / 2 + radius * math.cos(angle),
                                HEIGHT / 2 + radius * math.sin(angle)).point()

        self.play(Click(paint.tool("brush")))
        self.play(Click(paint.color("navy"), run_time=0.5))
        self.play(Stroke(flower, run_time=2.6))
        self.play(Click(paint.tool("fill"), run_time=0.5))
        self.play(Click(paint.color("yellow"), run_time=0.5))
        self.play(Click(paint.canvas(20, 20), run_time=0.5))
        self.play(Click(paint.color("red"), run_time=0.5))
        self.play(Click(paint.canvas(WIDTH / 2, HEIGHT / 2), run_time=0.5))
        self.pause(1)
