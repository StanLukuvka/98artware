"""A screensaver, launched directly and recorded live, then dismissed."""

from art98.anim import *


class ScreensaverRun(Scene):
    desktop = "stock"  # made before the blank start, and it shows the pointer

    def construct(self):
        self.pause(0.4)
        saver = Screensaver("Mystify Your Mind")
        self.add(saver)
        self.live(5)
        saver.stop()
        self.pause(0.6)
