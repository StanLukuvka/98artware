"""A Manim-style layer over the bridge: `from art98.anim import *`.

Names follow Manim where the meaning matches. Units do not: everything is in
screen pixels with y running down, because that is what Win32 speaks.
"""

from .animation import (
    Animate, Animation, AnimationGroup, Instant, LaggedStart, MoveAlongPath, Succession, Wait,
)
# The program classes are parked in .apps: they still work but aren't exported.
from .keys import Keys, TypeKeys, TypeWithCursor, UntypeWithCursor
from .picture import Picture
from .pointer import Click, DoubleClick, Drag, Glide, Hover, Menu, Pointer, RightClick, Stroke
from .props import Box, Prop, Spot, Win
from .rate_functions import linear, rush_from, rush_into, smooth, smoothstep, there_and_back
from .renderer import render, write_gif
from .scene import Scene
from .vectors import DL, DOWN, DR, LEFT, ORIGIN, RIGHT, UL, UP, UR, Vec, lerp
from .window import Close, Maximize, Minimize, RestoreWindow, Teleport

__all__ = [
    "Animate", "Animation", "AnimationGroup", "Box", "Click", "Close", "DL", "DOWN", "DR",
    "DoubleClick", "Drag", "Glide", "Hover", "Instant", "Keys", "LEFT", "LaggedStart",
    "Maximize", "Menu", "Minimize", "MoveAlongPath", "ORIGIN",
    "Picture", "Pointer", "Prop", "RIGHT", "RestoreWindow", "RightClick", "Scene",
    "Spot", "Stroke", "Succession", "Teleport", "TypeKeys", "TypeWithCursor", "UL", "UP", "UR",
    "UntypeWithCursor", "Vec", "Wait", "Win", "lerp", "linear", "render", "rush_from",
    "rush_into", "smooth", "smoothstep", "there_and_back", "write_gif",
]
