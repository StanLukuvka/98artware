"""Pointer and clicks: a double click opens My Computer, a right click a menu."""

from art98.anim import *


class PointerClicks(Scene):
    desktop = Desktop("stock")  # made before the blank start, and it shows the pointer

    def construct(self):
        self.pause(0.4)
        self.play(Glide((200, 120)))
        # My Computer opens on the double click, before the scene has a prop for it.
        with self.claim("the icon's window", lambda w: w.title == "My Computer"):
            self.play(DoubleClick((38, 22), run_time=0.9))
            my_computer = Win("My Computer")
            self.add(my_computer)
        self.wait(0.9)
        self.play(RightClick((640, 300)))
        self.wait(0.8)
        self.play(Keys("esc"))
        self.play(Close(my_computer))
        self.pause(0.5)
