"""A Manim-style layer over the bridge: `from art98.anim import *`.

Names follow Manim where the meaning matches. Units do not: everything is in
screen pixels with y running down, because that is what Win32 speaks.
"""

from .actions import (
    Click, Close, DoubleClick, Drag, Glide, Hover, Keys, Maximize, Menu, Minimize, Pointer,
    RestoreWindow, RightClick, Stroke, TypeKeys, TypeWithCursor, UntypeWithCursor,
)
from .animation import (
    Animate, Animation, AnimationGroup, Instant, LaggedStart, MoveAlongPath, Succession, Wait,
)
from .apps import Dialog, Minesweeper, Notepad, Paint, Screensaver
from .picture import Picture, Teleport
from .props import Box, Prop, Spot, Win
from .rate_functions import linear, rush_from, rush_into, smooth, smoothstep, there_and_back
from .renderer import render, write_gif
from .scene import Scene
from .vectors import DL, DOWN, DR, LEFT, ORIGIN, RIGHT, UL, UP, UR, Vec, lerp

__all__ = [
    "Animate", "Animation", "AnimationGroup", "Box", "Click", "Close", "DL", "DOWN", "DR",
    "Dialog", "DoubleClick", "Drag", "Glide", "Hover", "Instant", "Keys", "LEFT", "LaggedStart",
    "Maximize", "Menu", "Minesweeper", "Minimize", "MoveAlongPath", "Notepad", "ORIGIN", "Paint",
    "Picture", "Pointer", "Prop", "RIGHT", "RestoreWindow", "RightClick", "Scene", "Screensaver",
    "Spot", "Stroke", "Succession", "Teleport", "TypeKeys", "TypeWithCursor", "UL", "UP", "UR",
    "UntypeWithCursor", "Vec", "Wait", "Win", "lerp", "linear", "render", "rush_from",
    "rush_into", "smooth", "smoothstep", "there_and_back", "write_gif",
]
