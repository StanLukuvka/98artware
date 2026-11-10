"""art98: script animations with a real Windows 98 desktop inside a VM."""

from .bridge import Bridge, BridgeError, BridgeTimeout, CallResult, GuestCrashed, Window
from .protocol import Out
from .qemu import VM, VMConfig
from .session import Session, boot

__all__ = [
    "Bridge",
    "BridgeError",
    "BridgeTimeout",
    "CallResult",
    "GuestCrashed",
    "Out",
    "Session",
    "VM",
    "VMConfig",
    "Window",
    "boot",
]
