"""Old path of art98.actions.keyboard. The module is aliased so patching a constant here patches the real one."""

import sys

from ..actions import keyboard

sys.modules[__name__] = keyboard
