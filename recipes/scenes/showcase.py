"""A tour of Windows 98, driven entirely from the host.

Paint draws a rose with the mouse, Minesweeper is cleared without a wrong
move, and 3D Pipes takes over the screen. Only the screensaver runs on a
wall clock: everything else is drawn when the script asks for a frame.

    uv run art98 render recipes/scenes/showcase.py Showcase -o showcase.mp4
"""

import math

from art98.anim import *

CANVAS = (496, 376)
ROSE_CENTRE = (248, 188)
ROSE_RADIUS = 178
PETAL_COLOURS = ("red", "yellow", "lime", "cyan", "magenta")


class Showcase(Scene):
    desktop = "stock"  # made before the blank start, and it shows the pointer

    def rose(self, paint, scale=1.0):
        """Five petals: r = cos(5 angle), as canvas pixels turned to screen points."""

        def point(t):
            angle = math.pi * t
            radius = ROSE_RADIUS * scale * math.cos(5 * angle)
            return paint.canvas(
                ROSE_CENTRE[0] + radius * math.cos(angle),
                ROSE_CENTRE[1] - radius * math.sin(angle),
            ).point()

        return point

    def draw_rose(self, paint):
        self.play(Click(paint.tool("brush")))
        self.play(Click(paint.color("navy")))
        self.play(Stroke(self.rose(paint), run_time=6.4))
        self.pause(0.5)

    def fill_rose(self, paint):
        self.play(Click(paint.tool("fill")))
        inner = self.rose(paint, scale=0.6)
        for petal, colour in enumerate(PETAL_COLOURS):
            self.play(Click(paint.color(colour), run_time=0.5))
            self.play(Click(inner(petal / 5), run_time=0.55))
        self.play(Click(paint.color("navy"), run_time=0.5))
        self.play(Click(paint.canvas(20, 20), run_time=0.55))
        self.pause(1)

    def construct(self):
        self.pause(1)

        paint = Paint()
        self.add(paint)
        self.play(paint.animate.set_rect(20, 10, 580, 510), run_time=1)
        self.pause(0.33)

        self.play(paint.resize_canvas(*CANVAS, run_time=1.8))
        self.pause(0.33)

        self.draw_rose(paint)
        self.fill_rose(paint)

        # The scan happens between two frames, so it never reaches the video.
        board = Minesweeper()
        self.add(board)
        board.find_mines()
        self.pause(0.5)
        self.play(board.animate.move_to((630, 150), aligned_edge=UL))
        board.clear()
        board.sign_scoreboard()

        pipes = Screensaver("3D Pipes")
        self.add(pipes)
        self.live(12)

        pipes.stop()
        self.pause(2)
