"""A dialog storm: a cascade of message boxes, a jittered pair, typing text, a new
desktop colour and a wallpaper (docs/design/inspiration.md, B3 to B7).

    art98 render recipes/scenes/dialog_storm/dialog_storm.py DialogStorm
    art98 render recipes/scenes/dialog_storm/dialog_storm.py DialogStormStock
"""

import random

from art98.anim import *

FRAME = 1 / 24
BOX = (300, 130)  # outer size, a bit more than the stock box


class DialogStorm(Scene):
    fps = 24
    desktop = "blank"

    def construct(self):
        self.pause(0.5)
        self.play(Backdrop("teal"))
        self.pause(0.5)

        # Cascade candidate: this loop by hand is the case for a library helper.
        x0, y0 = 60, 330
        for i in range(8):
            self.add(
                Dialog(
                    "???",
                    "???",
                    icon="warning",
                    at=(x0 + 24 * i, y0 - 18 * i),
                    size=BOX,
                )
            )
            self.pause(2 * FRAME)
        self.pause(0.5)
        self.next_section("pair")

        rng = random.Random(98)
        for _ in range(2):
            jitter = (rng.randint(-4, 4), rng.randint(-4, 4))
            self.add(
                Dialog(
                    "???",
                    "???",
                    icon="computer",
                    disabled=True,
                    size=BOX,
                    at=(400 + jitter[0], 380 + jitter[1]),
                )
            )
            self.pause(2 * FRAME)
        self.pause(0.5)

        self.next_section("typing")
        typed = Dialog("", "???", at=(120, 60), size=BOX)
        self.add(typed)
        self.pause(FRAME)
        for n in range(1, 8):
            typed.set_message("ABCDEFG"[:n])
            self.pause(FRAME)
        self.pause(0.5)

        self.next_section("colour")
        self.play(Backdrop("dark_red"))
        self.pause(0.5)
        self.cut()
        self.set_state("states/wall.json")
        self.add(Dialog("???", "???", icon="warning", at=(260, 200), size=BOX))
        self.pause(1)


class DialogStormStock(Scene):
    """The same boxes on the stock desktop: taskbar and icons, on a dark red colour."""

    fps = 24
    desktop = "stock"

    def construct(self):
        self.pause(0.5)
        self.play(Backdrop("dark_red"))
        for i in range(4):
            self.add(
                Dialog(
                    "???",
                    "???",
                    icon="warning",
                    at=(200 + 24 * i, 250 - 18 * i),
                    size=BOX,
                )
            )
            self.pause(2 * FRAME)
        self.pause(1)
