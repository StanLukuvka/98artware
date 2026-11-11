"""Step 4, ready: the desktop every run starts from.

Applies HARDEN_SETTINGS (quiet, fast, deterministic), clears everything that
starts on its own, sets the display mode, reboots, waits for a still screen,
checks the desktop is clean and saves the `ready` snapshot. Future "blank start"
settings belong here.
"""

from __future__ import annotations

import hashlib
import json
import struct
import time

from art98.bridge import Bridge, BridgeError
from art98.protocol import Out
from art98.qemu import VM
from art98.session import IMAGE_FILE, SNAPSHOT

from .builder import AGENT_RUN_VALUE, Setup, SetupError

DISPLAY_MODE = (800, 600, 16)
KEPT_RUN_VALUES = {AGENT_RUN_VALUE.lower(), "systemtray"}
SETTLE_SECONDS = 30

HKCU = 0x80000001
HKLM = 0x80000002
REG_SZ = 1
REG_BINARY = 3

RUN_KEYS = [
    (HKLM, r"Software\Microsoft\Windows\CurrentVersion\Run"),
    (HKLM, r"Software\Microsoft\Windows\CurrentVersion\RunServices"),
    (HKCU, r"Software\Microsoft\Windows\CurrentVersion\Run"),
]

SILENCED_EVENTS = [
    ".Default",
    "AppGPFault",
    "Close",
    "EmptyRecycleBin",
    "Maximize",
    "MenuCommand",
    "MenuPopup",
    "Minimize",
    "Open",
    "RestoreDown",
    "RestoreUp",
    "SystemAsterisk",
    "SystemExclamation",
    "SystemExit",
    "SystemHand",
    "SystemQuestion",
    "SystemStart",
]

# Registry state of the prepared desktop: (root, key, value name, data).
HARDEN_SETTINGS: list[tuple[int, str, str, str | bytes]] = [
    (HKCU, r"Control Panel\Desktop", "ScreenSaveActive", "0"),
    (HKCU, r"Control Panel\Desktop", "ScreenSaveLowPowerActive", "0"),
    (HKCU, r"Control Panel\Desktop", "ScreenSavePowerOffActive", "0"),
    (HKCU, r"Control Panel\Desktop", "DragFullWindows", "1"),
    (HKCU, r"Control Panel\Desktop", "FontSmoothing", "0"),
    (HKCU, r"Control Panel\Desktop", "MenuShowDelay", "0"),
    (HKCU, r"Control Panel\Desktop", "SmoothScroll", b"\0\0\0\0"),
    (HKCU, r"Control Panel\Desktop", "UserPreferencesMask", b"\0\0\0\0"),
    (HKCU, r"Control Panel\Desktop", "Wallpaper", ""),
    (HKCU, r"Control Panel\Desktop\WindowMetrics", "MinAnimate", "0"),
    (HKCU, r"Control Panel\PowerCfg", "CurrentPowerPolicy", "3"),
    (HKCU, r"AppEvents\Schemes", "", ".None"),
    (
        HKCU,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\Tips",
        "Show",
        b"\0\0\0\0",
    ),
    (
        HKCU,
        r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer",
        "NoDriveTypeAutoRun",
        b"\xff\0\0\0",
    ),
    *(
        (HKCU, rf"AppEvents\Schemes\Apps\.Default\{event}\.Current", "", "")
        for event in SILENCED_EVENTS
    ),
]


def wait_for_quiet_screen(setup: Setup, vm: VM, label: str) -> None:
    """Wait until nothing on screen has moved for a while."""
    path = setup.shots / f"{label}.png"
    last, since = None, time.monotonic()
    while time.monotonic() - since < SETTLE_SECONDS:
        time.sleep(1)
        digest = hashlib.sha256(vm.screenshot(path).read_bytes()).digest()
        if digest != last:
            last, since = digest, time.monotonic()


def harden(setup: Setup) -> None:
    config = setup._config()
    with (
        VM(config, log=setup._vm_log()) as vm,
        Bridge.connect(vm.serial_path) as bridge,
    ):
        setup._require_agent(vm, bridge, "harden")
        apply_settings(bridge)
        bridge.set_display_mode(*DISPLAY_MODE)
        setup._reboot(vm, bridge)
    with (
        VM(config, log=setup._vm_log()) as vm,
        Bridge.connect(vm.serial_path) as bridge,
    ):
        setup._require_agent(vm, bridge, "reboot")
        wait_for_quiet_screen(setup, vm, "ready")
        verify_desktop(bridge)
        vm.pause()
        vm.save_snapshot(SNAPSHOT)
        vm.screenshot(setup.shots / "ready.png")
    (setup.work / IMAGE_FILE).write_text(json.dumps(config.to_json(), indent=2))
    setup.raw.unlink(missing_ok=True)


def run(setup: Setup) -> None:
    harden(setup)


def _open_key(bridge: Bridge, root: int, path: str) -> int:
    result = bridge.advapi32.RegCreateKeyA(root, path, Out(4))
    if result.value:
        raise BridgeError(f"cannot open {path}: error {result.value}")
    return struct.unpack("<I", result.buffers[0])[0]


def apply_settings(bridge: Bridge) -> None:
    """Write HARDEN_SETTINGS and clear everything that starts on its own."""
    for root, key, name, data in HARDEN_SETTINGS:
        handle = _open_key(bridge, root, key)
        if isinstance(data, str):
            kind, blob = REG_SZ, data.encode("cp1252") + b"\0"
        else:
            kind, blob = REG_BINARY, data
        result = bridge.advapi32.RegSetValueExA(
            handle, name or None, 0, kind, blob, len(blob)
        )
        bridge.advapi32.RegCloseKey(handle)
        if result.value:
            raise BridgeError(f"cannot set {key}\\{name}: error {result.value}")
    for root, key in RUN_KEYS:
        clear_run_key(bridge, root, key)


def run_key_values(bridge: Bridge, handle: int) -> list[str]:
    names = []
    index = 0
    while True:
        result = bridge.advapi32.RegEnumValueA(
            handle, index, Out(260), struct.pack("<I", 260), 0, 0, 0, 0
        )
        if result.value:  # ERROR_NO_MORE_ITEMS
            return names
        names.append(result.buffers[0].split(b"\0", 1)[0].decode("cp1252"))
        index += 1


def clear_run_key(bridge: Bridge, root: int, key: str) -> None:
    handle = _open_key(bridge, root, key)
    for name in run_key_values(bridge, handle):
        if name.lower() not in KEPT_RUN_VALUES:
            bridge.advapi32.RegDeleteValueA(handle, name)
    bridge.advapi32.RegCloseKey(handle)


def verify_desktop(bridge: Bridge) -> None:
    """Refuse to snapshot anything but a clean desktop."""
    windows = [w for w in bridge.windows() if w.visible and w.title]
    expected = {"program manager"}
    strays = [w.title for w in windows if w.title.lower() not in expected]
    if strays:
        raise SetupError(f"unexpected windows on the desktop: {strays}")
    if not any(w.class_name == "Shell_TrayWnd" for w in bridge.windows()):
        raise SetupError("the taskbar is missing")
