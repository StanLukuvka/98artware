"""The MVP sample: picture windows, set from state files and moved on camera.

    art98 render examples/mvp/mvp.py
"""

from pathlib import Path

from art98.anim import *

HERE = Path(__file__).parent


class Mvp(Scene):
    state = "states/two_windows.json"

    def construct(self):
        flower = self.prop("flower")
        self.pause(0.5)
        self.play(flower.animate.shift(200 * RIGHT), run_time=2)
        self.pause(0.5)
        self.play(Teleport(flower, to=(40, 40), aligned_edge=UL))
        self.pause(0.5)
        self.play(Close(flower))
        self.pause(0.5)
        self.add(Picture("Sky", image=HERE / "assets" / "sky.bmp", at=(100, 260), size=(240, 200)))
        self.pause(1)

        self.set_state("states/gallery.json")
        self.pause(1)
        self.play(self.prop("picture").animate.shift(100 * DOWN), run_time=2)
        self.pause(0.5)
