"""The programs a state file can open, by their name in the file."""

from __future__ import annotations

from .programs.notepad import Notepad
from .window.picture import Picture

APPS = {"picture": Picture, "notepad": Notepad}
