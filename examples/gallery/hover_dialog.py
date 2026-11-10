"""A tooltip, which the guest times itself, and a real message box."""

from art98.anim import *
from art98.anim.apps import Dialog  # parked, see apps.py


class HoverDialog(Scene):
    desktop = "stock"  # made before the blank start, and it shows the pointer

    def construct(self):
        self.pause(0.3)
        self.play(Hover((768, 587), hold=1.5))
        self.play(Glide((500, 150)))
        box = Dialog("Are you still there?", "art98", icon="question", buttons="yesno")
        self.add(box)
        self.pause(0.8)
        self.play(box.animate.shift(90 * LEFT + 100 * UP), run_time=0.8)
        self.pause(0.3)
        self.play(Click(box.button("Yes")))
        self.pause(0.7)
