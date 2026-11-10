"""Builds the prepared Windows 98 image in four steps: vm, setup, init_api, ready.

The steps run in order and are recorded in work/state.json, so a failure can be
fixed and resumed without repeating the long install. This module holds the
Setup class that runs them and the helpers every step shares; each step is its
own module. See docs/setup/ for what each one does.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Callable

from art98.bridge import Bridge, BridgeError, BridgeTimeout
from art98.guestfiles import GUEST_DIR
from art98.qemu import QEMU_BINARY, QemuError, VM, VMConfig

SECTOR = 512
SECTORS_PER_TRACK = 63
PARTITION_START = SECTORS_PER_TRACK  # the traditional first partition slot
PARTITION_OFFSET = PARTITION_START * SECTOR

AGENT_PATH = GUEST_DIR + r"\AGENT.EXE"
AGENT_RUN_VALUE = "Art98Agent"

STALL_LIMIT = 20 * 60
WIZARD_PAGE_TIMEOUT = 2 * 60
SHUTDOWN_TIMEOUT = 5 * 60
EWX_REBOOT, EWX_FORCE = 2, 4
SHOT_INTERVAL = 30

HOST_TOOLS = {
    QEMU_BINARY: "qemu-system-x86",
    "qemu-img": "qemu-img",
    "mcopy": "mtools",
    "7z": "7zip",
    "ffmpeg": "ffmpeg",
    "make": "make",
    "as": "binutils",
    "i686-w64-mingw32-gcc": "mingw32-gcc",
}


class SetupError(RuntimeError):
    pass


# Debian and Ubuntu name the same tools differently.
DEBIAN_PACKAGES = {
    QEMU_BINARY: "qemu-system-x86",
    "qemu-img": "qemu-utils",
    "mcopy": "mtools",
    "7z": "7zip",
    "ffmpeg": "ffmpeg",
    "make": "make",
    "as": "binutils",
    "i686-w64-mingw32-gcc": "gcc-mingw-w64-i686",
}


def doctor() -> list[tuple[str, str | None, str]]:
    """Report (tool, path or None, package that provides it)."""
    return [(tool, shutil.which(tool), package) for tool, package in HOST_TOOLS.items()]


def install_hints(tools: list[str]) -> list[tuple[str, str, list[str]]]:
    """(system, install command, packages) for each distribution family."""
    return [
        ("Fedora", "sudo dnf install", [HOST_TOOLS[tool] for tool in tools]),
        ("Debian, Ubuntu", "sudo apt install", [DEBIAN_PACKAGES[tool] for tool in tools]),
    ]


def _run(*args, **kwargs) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, check=True, capture_output=True, **kwargs)
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or b"").decode(errors="replace").strip()
        raise SetupError(f"{args[0]} failed: {detail}") from None


def _mtools_env() -> dict:
    # mtools rejects images whose geometry is not a textbook floppy or disk.
    return {**os.environ, "MTOOLS_SKIP_CHECK": "1"}


def _mtool(*args, **kwargs) -> subprocess.CompletedProcess:
    return _run(*args, env=_mtools_env(), **kwargs)


def disk_spec(path: Path) -> str:
    return f"{path}@@{PARTITION_OFFSET}"


# ---- first-boot prompts ----


# OEM media ignores the answer file's request to skip its first-boot wizard, so
# setup presses through it. Name and product key arrive filled in from
# MSBATCH.INF; the second page selects "I accept the Agreement".
WIZARD_PAGES = (
    [("ret",)],
    [("alt", "a"), ("ret",)],
    [("ret",)],
    [("ret",)],
)
WIZARD_HEADING = (220, 92, 560, 118)


@dataclass
class Screen:
    width: int
    height: int
    rgb: bytes

    @classmethod
    def from_ppm(cls, data: bytes) -> "Screen":
        fields, pos = [], 0
        while len(fields) < 4:
            start = pos
            while data[pos:pos + 1] not in (b" ", b"\n"):
                pos += 1
            fields.append(data[start:pos])
            pos += 1
        if fields[0] != b"P6" or fields[3] != b"255":
            raise SetupError("unexpected screenshot format")
        return cls(int(fields[1]), int(fields[2]), data[pos:])

    def pixel(self, x: int, y: int) -> tuple[int, int, int]:
        offset = (y * self.width + x) * 3
        return tuple(self.rgb[offset:offset + 3])

    def crop(self, left: int, top: int, right: int, bottom: int) -> bytes:
        rows = (self.rgb[(y * self.width + left) * 3:(y * self.width + right) * 3]
                for y in range(top, bottom))
        return b"".join(rows)


def setup_wizard_showing(screen: Screen) -> bool:
    """Recognise the first-boot wizard: a dialog alone on a blue screen."""
    return ((screen.width, screen.height) == (640, 480)
            and screen.pixel(10, 10) == (0, 0, 255)
            and screen.pixel(20, 470) == (0, 0, 255)
            and screen.pixel(300, 70) == (0, 0, 168)
            and screen.pixel(300, 360) == (192, 199, 200))


def logon_prompt_showing(screen: Screen) -> bool:
    """Recognise the logon dialog on the bare desktop of the first real boot."""
    return ((screen.width, screen.height) == (640, 480)
            and screen.pixel(10, 10) == (0, 128, 128)
            and screen.pixel(20, 470) == (0, 128, 128)
            and screen.pixel(300, 72) == (0, 0, 128)
            and screen.pixel(300, 245) == (192, 192, 192))


# ---- pipeline ----


@dataclass
class Setup:
    work: Path
    guest_build: Path
    iso: Path | None = None
    product_key: str | None = None
    disk_mb: int = 2047
    watch: bool = False
    log: object = print

    STAGES = ("vm", "setup", "init_api", "ready")
    # Steps used to be five stages; work/state.json from those builds still counts.
    OLD_STAGES = {
        "media": "vm", "disk": "vm", "install": "setup", "patch": "init_api", "harden": "ready",
    }

    def __post_init__(self) -> None:
        self.work = Path(self.work).resolve()
        self.work.mkdir(parents=True, exist_ok=True)
        self.shots = self.work / "shots"
        self.shots.mkdir(exist_ok=True)
        self.raw = self.work / "install.img"
        self.golden = self.work / "golden.qcow2"
        self.floppy = self.work / "boot.img"
        self.media = self.work / "media"
        self.state_file = self.work / "state.json"

    # state

    @classmethod
    def step_name(cls, name: str) -> str:
        """The step holding `name`, which may be a step or an old stage name."""
        if name in cls.STAGES:
            return name
        if name in cls.OLD_STAGES:
            return cls.OLD_STAGES[name]
        raise SetupError(f"unknown step {name!r}; choose from "
                         f"{', '.join(cls.STAGES + tuple(cls.OLD_STAGES))}")

    def _done(self) -> list[str]:
        """Finished steps, in order. Old stage names count: vm needs media and disk."""
        if not self.state_file.exists():
            return []
        recorded = set(json.loads(self.state_file.read_text()))
        for step in self.STAGES:
            old = {name for name, held in self.OLD_STAGES.items() if held == step}
            if old <= recorded:
                recorded.add(step)
        return [step for step in self.STAGES if step in recorded]

    def _mark(self, step: str) -> None:
        self.state_file.write_text(json.dumps(self._done() + [step]))

    def _execute(self, step: str) -> None:
        import_module(f"{__package__}.{step}").run(self)

    def run(self, from_stage: str | None = None) -> None:
        done = self._done()
        if from_stage:
            done = done[:self.STAGES.index(self.step_name(from_stage))]
            self.state_file.write_text(json.dumps(done))
        for step in self.STAGES:
            if step in done:
                self.log(f"[{step}] already done")
                continue
            self.log(f"[{step}] starting")
            started = time.monotonic()
            self._execute(step)
            self._mark(step)
            self.log(f"[{step}] done in {time.monotonic() - started:.0f}s")

    # helpers

    def _config(self, **overrides) -> VMConfig:
        # In the container there is no window to open: `art98 up --watch` sets VNC.
        display = os.environ.get("ART98_WATCH_DISPLAY", "gtk") if self.watch else "none"
        return VMConfig(disk=self.golden, machine=self._machine(), display=display, **overrides)

    def _machine(self) -> str:
        """Pin the machine version: snapshots only load on the one they came from."""
        output = _run(QEMU_BINARY, "-machine", "help", text=True).stdout
        for line in output.splitlines():
            name, *rest = line.split()
            if name == "pc" and "alias" in line:
                return line.split("alias of")[1].split(")")[0].strip()
        raise SetupError("could not determine the default QEMU machine type")

    def _vm_log(self) -> Path:
        return self.work / "qemu.log"

    def _wait_for_agent(self, vm: VM, bridge: Bridge, label: str, timeout: float,
                        on_poll: Callable[[VM], None] | None = None) -> bool:
        """Wait for HELLO while keeping screenshots to show where things stand.

        Returns False if the guest rebooted first, which ends the VM. Progress
        is judged by disk writes: a blinking caret keeps the screen changing
        while a dialog waits forever, so the screen can't be used.
        """
        deadline = time.monotonic() + timeout
        last_write, last_change = None, time.monotonic()
        count = 0
        while True:
            try:
                bridge.wait_event("HELLO", timeout=SHOT_INTERVAL)
                return True
            except BridgeTimeout:
                pass
            except BridgeError:
                if vm.wait_exit(10):
                    return False
                raise
            count += 1
            try:
                shot = vm.screenshot(self.shots / f"{label}-{count:04d}.png")
                if on_poll:
                    on_poll(vm)
            except (OSError, QemuError):
                if vm.wait_exit(10):
                    return False
                raise
            written = vm.config.disk.stat().st_mtime_ns
            now = time.monotonic()
            if written != last_write:
                last_write, last_change = written, now
            elif now - last_change > STALL_LIMIT:
                raise SetupError(
                    f"no disk writes for {STALL_LIMIT // 60} minutes during {label}; "
                    f"see {shot}, or rerun with --watch to see the VM")
            if now > deadline:
                raise SetupError(f"{label} did not finish; last screen: {shot}")

    def _require_agent(self, vm: VM, bridge: Bridge, label: str) -> None:
        if not self._wait_for_agent(vm, bridge, label, 15 * 60, self._answer_setup_prompts):
            raise SetupError(f"the guest rebooted during {label} before the agent started")
        bridge.wait_ready()

    def _reboot(self, vm: VM, bridge: Bridge) -> None:
        """Shut Windows down. The call never returns, so it runs on its own thread."""
        bridge.acall("user32", "ExitWindowsEx", EWX_REBOOT | EWX_FORCE, 0)
        if not vm.wait_exit(SHUTDOWN_TIMEOUT):
            raise SetupError(f"Windows did not shut down; see "
                             f"{vm.screenshot(self.shots / 'shutdown.png')}")

    # first-boot prompts

    def _screen(self, vm: VM) -> Screen:
        return Screen.from_ppm(vm.screenshot(self.shots / "probe.ppm", "ppm").read_bytes())

    def _answer_setup_prompts(self, vm: VM) -> None:
        screen = self._screen(vm)
        if logon_prompt_showing(screen):
            self.log("  answering the logon prompt with a blank password")
            vm.send_keys("ret")  # blank means Windows never asks again
        elif setup_wizard_showing(screen):
            self._answer_setup_wizard(vm)

    def _answer_setup_wizard(self, vm: VM) -> None:
        self.log("  answering the first-boot wizard, accepting the license agreement")
        for keys in WIZARD_PAGES:
            heading = self._screen(vm).crop(*WIZARD_HEADING)
            for chord in keys:
                vm.send_keys(*chord)
                time.sleep(1)
            deadline = time.monotonic() + WIZARD_PAGE_TIMEOUT
            while self._screen(vm).crop(*WIZARD_HEADING) == heading:
                if time.monotonic() > deadline:
                    raise SetupError("the first-boot wizard did not advance; see "
                                     f"{vm.screenshot(self.shots / 'wizard.png')}")
                time.sleep(1)
