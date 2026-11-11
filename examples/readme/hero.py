"""The README's opening clip: Notepad, Paint, Minesweeper and a message box in one take.

uv run art98 render examples/readme/hero.py -o hero.mp4 --gif hero.gif
"""

import math

from art98.anim import *

CANVAS = (300, 250)


class Hero(Scene):
    desktop = "stock"  # the taskbar and icons say "Windows 98" at a glance

    def construct(self):
        self.pointer.place((400, 500))
        self.pause(0.5)

        pad = Notepad(at=(20, 20), size=(240, 150))
        self.add(pad)
        self.play(TypeWithCursor(pad, "Hello from 1998.", run_time=1.3))

        # Paint opens big enough to show its whole canvas, so the corner handle is in reach.
        paint = Paint(at=(270, 10), size=(520, 480))
        self.add(paint)
        self.play(paint.resize_canvas(*CANVAS, run_time=0.8))
        self.play(paint.animate.set_rect(330, 10, 450, 400), run_time=0.6)

        def heart(t):
            a = 2 * math.pi * t
            x = 16 * math.sin(a) ** 3
            y = 13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a)
            y -= math.cos(4 * a)
            return paint.canvas(
                CANVAS[0] / 2 + 6.5 * x, CANVAS[1] / 2 - 10 - 6.5 * y
            ).point()

        self.play(Click(paint.tool("brush"), run_time=0.45))
        self.play(Click(paint.color("navy"), run_time=0.4))
        self.play(Stroke(heart, run_time=1.8))
        self.play(Click(paint.tool("fill"), run_time=0.45))
        self.play(Click(paint.color("red"), run_time=0.4))
        self.play(Click(paint.canvas(CANVAS[0] / 2, CANVAS[1] / 2), run_time=0.4))

        board = Minesweeper(at=(40, 220))
        self.add(board)
        mines = board.find_mines()  # between two frames, so it is never seen
        columns, rows = board.board_size
        safe = [(c, r) for c in range(columns) for r in range(rows)]
        best = max(
            (cell for cell in safe if cell not in mines),
            key=lambda cell: len(board.opened_by(cell)),
        )
        self.play(Click(board.cell(*best), run_time=0.6))
        self.pause(0.3)

        self.play(Drag(pad.title_bar, by=(200, 385), run_time=1.2))

        box = Dialog(
            "Keep this drawing?",
            "art98",
            icon="question",
            buttons="yesno",
            at=(540, 430),
        )
        self.add(box)
        self.pause(0.7)
        self.play(Click(box.button("Yes"), run_time=0.6))
        self.pause(1.2)
