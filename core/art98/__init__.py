"""art98: script animations with a real Windows 98 desktop inside a VM."""

from .bridge import Bridge, BridgeError, BridgeTimeout, CallResult, GuestCrashed, Window
from .errors import Art98Error, NotFound, UsageError
from .protocol import Out
from .qemu import VM, VMConfig
from .recorder import Recorder, RecorderError
from .service import attach
from .session import Session

__all__ = [
    "VM",
    "Art98Error",
    "Bridge",
    "BridgeError",
    "BridgeTimeout",
    "CallResult",
    "GuestCrashed",
    "NotFound",
    "Out",
    "Recorder",
    "RecorderError",
    "Session",
    "UsageError",
    "VMConfig",
    "Window",
    "attach",
]
