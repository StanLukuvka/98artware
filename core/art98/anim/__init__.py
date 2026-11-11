"""A Manim-style layer over the bridge: `from art98.anim import *`.

Names follow Manim where the meaning matches. Units do not: everything is in
screen pixels with y running down, because that is what Win32 speaks.
"""

# The program classes are parked in .apps: they still work but aren't exported.
from ..actions.keyboard import Keys, TypeKeys, TypeWithCursor, UntypeWithCursor
from ..actions.pointer import Click, DoubleClick, Drag, Glide, Hover, Pointer, RightClick, Stroke
from ..actions.programs import Notepad
from ..actions.window import Close, Maximize, Menu, Minimize, Picture, RestoreWindow, Teleport, Win
from ..base.animation import (
    Animate, Animation, AnimationGroup, Instant, LaggedStart, MoveAlongPath, Succession, Wait,
)
from ..base.props import Box, Prop, Spot
from ..base.rate_functions import linear, rush_from, rush_into, smooth, smoothstep, there_and_back
from ..base.vectors import DL, DOWN, DR, LEFT, ORIGIN, RIGHT, UL, UP, UR, Vec, lerp
from .renderer import render, write_gif
from .scene import Scene

__all__ = [
    "Animate", "Animation", "AnimationGroup", "Box", "Click", "Close", "DL", "DOWN", "DR",
    "DoubleClick", "Drag", "Glide", "Hover", "Instant", "Keys", "LEFT", "LaggedStart",
    "Maximize", "Menu", "Minimize", "MoveAlongPath", "Notepad", "ORIGIN",
    "Picture", "Pointer", "Prop", "RIGHT", "RestoreWindow", "RightClick", "Scene",
    "Spot", "Stroke", "Succession", "Teleport", "TypeKeys", "TypeWithCursor", "UL", "UP", "UR",
    "UntypeWithCursor", "Vec", "Wait", "Win", "lerp", "linear", "render", "rush_from",
    "rush_into", "smooth", "smoothstep", "there_and_back", "write_gif",
]
