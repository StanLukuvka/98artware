"""Turns a Windows 98 SE disc into a known, repeatable desktop.

Stages run in order and are recorded in work/state.json, so a failure can be
fixed and resumed without repeating the long install. See README.md for what
each one does.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import pecheck
from .bridge import Bridge, BridgeError, BridgeTimeout
from .protocol import Out
from .qemu import QEMU_BINARY, QemuError, VM, VMConfig
from .session import IMAGE_FILE, SNAPSHOT

SECTOR = 512
CD_SECTOR = 2048
HEADS = 16
SECTORS_PER_TRACK = 63
PARTITION_START = SECTORS_PER_TRACK  # the traditional first partition slot
PARTITION_OFFSET = PARTITION_START * SECTOR
FAT32_LBA = 0x0C
EL_TORITO_FLOPPY_SIZES = {1: 1228800, 2: 1474560, 3: 2949120}

DISPLAY_MODE = (800, 600, 16)
GUEST_DIR = r"C:\ART98"
AGENT_PATH = GUEST_DIR + r"\AGENT.EXE"
AGENT_RUN_VALUE = "Art98Agent"
KEPT_RUN_VALUES = {AGENT_RUN_VALUE.lower(), "systemtray"}

INSTALL_TIMEOUT = 3 * 3600
STALL_LIMIT = 20 * 60
WIZARD_PAGE_TIMEOUT = 2 * 60
SHUTDOWN_TIMEOUT = 5 * 60
SETUP_BOOTS = 8  # Setup restarts the machine a few times on its own
EWX_REBOOT, EWX_FORCE = 2, 4
SHOT_INTERVAL = 30
SETTLE_SECONDS = 30

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
    ".Default", "AppGPFault", "Close", "EmptyRecycleBin", "Maximize", "MenuCommand",
    "MenuPopup", "Minimize", "Open", "RestoreDown", "RestoreUp", "SystemAsterisk",
    "SystemExclamation", "SystemExit", "SystemHand", "SystemQuestion", "SystemStart",
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
    (HKCU, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Tips", "Show", b"\0\0\0\0"),
    (HKCU, r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer",
     "NoDriveTypeAutoRun", b"\xff\0\0\0"),
    *((HKCU, rf"AppEvents\Schemes\Apps\.Default\{event}\.Current", "", "")
      for event in SILENCED_EVENTS),
]

MSDOS_SYS_OPTIONS = {
    "AutoScan": "0",  # no ScanDisk prompt if a run is cut short
    "BootDelay": "0",
    "BootGUI": "1",
    "BootMenu": "0",
    "DisableLog": "1",
    "Logo": "0",
}


class PrepError(RuntimeError):
    pass


def doctor() -> list[tuple[str, str | None, str]]:
    """Report (tool, path or None, package that provides it)."""
    return [(tool, shutil.which(tool), package) for tool, package in HOST_TOOLS.items()]


def _run(*args, **kwargs) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, check=True, capture_output=True, **kwargs)
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or b"").decode(errors="replace").strip()
        raise PrepError(f"{args[0]} failed: {detail}") from None


def _mtools_env() -> dict:
    # mtools rejects images whose geometry is not a textbook floppy or disk.
    return {**os.environ, "MTOOLS_SKIP_CHECK": "1"}


def _mtool(*args, **kwargs) -> subprocess.CompletedProcess:
    return _run(*args, env=_mtools_env(), **kwargs)


# ---- disc ----


def boot_floppy_image(iso: Path) -> bytes:
    """Read the floppy image a bootable disc uses for its El Torito boot."""
    with open(iso, "rb") as disc:
        disc.seek(17 * CD_SECTOR)
        record = disc.read(CD_SECTOR)
        if record[1:6] != b"CD001" or not record[7:30].startswith(b"EL TORITO"):
            raise PrepError(f"{iso} is not a bootable disc")
        catalog_sector = struct.unpack_from("<I", record, 0x47)[0]
        disc.seek(catalog_sector * CD_SECTOR)
        catalog = disc.read(CD_SECTOR)
        entry = catalog[32:64]
        media = entry[1] & 0x0F
        if entry[0] != 0x88 or media not in EL_TORITO_FLOPPY_SIZES:
            raise PrepError(f"{iso} does not boot from an emulated floppy")
        load_sector = struct.unpack_from("<I", entry, 8)[0]
        disc.seek(load_sector * CD_SECTOR)
        return disc.read(EL_TORITO_FLOPPY_SIZES[media])


def extract_setup_files(iso: Path, dest: Path) -> Path:
    """Unpack the disc's WIN98 folder and return it."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    _run("7z", "x", "-y", "-ssc-", f"-o{dest}", str(iso), "WIN98")
    found = [p for p in dest.iterdir() if p.is_dir() and p.name.upper() == "WIN98"]
    if not found:
        raise PrepError(f"{iso} has no WIN98 folder; is it a Windows 98 disc?")
    names = {p.name.upper() for p in found[0].iterdir()}
    missing = {"SETUP.EXE", "PRECOPY1.CAB"} - names
    if missing:
        raise PrepError(f"{iso} WIN98 folder lacks {sorted(missing)}")
    return found[0]


# ---- disk ----


def build_mbr(boot_code: bytes, total_sectors: int) -> bytes:
    """Boot code plus one active FAT32 partition filling the disk."""
    if len(boot_code) > 440:
        raise PrepError(f"boot code is {len(boot_code)} bytes, over the 440 byte limit")
    partition_sectors = total_sectors - PARTITION_START
    entry = struct.pack(
        "<B3BB3BII", 0x80, 0xFE, 0xFF, 0xFF, FAT32_LBA, 0xFE, 0xFF, 0xFF,
        PARTITION_START, partition_sectors,
    )
    return boot_code.ljust(446, b"\0") + entry + bytes(48) + b"\x55\xaa"


def create_disk(path: Path, size_mb: int, boot_code: bytes) -> None:
    """Make a raw disk with an MBR and an empty FAT32 partition."""
    cylinders = size_mb * 1024 * 1024 // (HEADS * SECTORS_PER_TRACK * SECTOR)
    total = cylinders * HEADS * SECTORS_PER_TRACK
    with open(path, "wb") as disk:
        disk.truncate(total * SECTOR)
        disk.write(build_mbr(boot_code, total))
    _mtool(
        "mformat", "-i", f"{path}@@{PARTITION_OFFSET}", "-F", "-c", "8",
        "-H", str(PARTITION_START), "-T", str(total - PARTITION_START),
        "-h", str(HEADS), "-s", str(SECTORS_PER_TRACK), "-v", "ART98", "::",
    )


def disk_spec(path: Path) -> str:
    return f"{path}@@{PARTITION_OFFSET}"


# ---- unattended setup ----


# Names as they appear in the disc's INF files. Setup ignores ones it doesn't know.
OPTIONAL_COMPONENTS = (
    "Accessories", "Games", "Character Map", "Screen Savers", "Flying Windows",
    "OpenGL Screen Savers", "Additional Screen Savers", "Desktop Wallpaper",
    "Mouse Pointers", "Multimedia Sound Schemes", "Sample Sounds",
    "Desktop Themes", "Desktop Themes Support",
)


def render_msbatch(product_key: str, timezone: str = "GMT") -> str:
    """The answer file for Setup.

    ShowEula=0 accepts the licence on the user's behalf, which is why `prep`
    only runs with the user's own disc and key. NoPrompt2Boot follows Microsoft's
    own sample script, not the inverted description in its parameter table.
    """
    lines = [
        "[BatchSetup]", "Version=3.0 (32-bit)", "",
        "[Version]", 'Signature="$CHICAGO$"', "",
        "[Setup]", "Express=1", 'InstallDir="C:\\WINDOWS"', "InstallType=1",
        f'ProductKey="{product_key}"', "EBD=0", "ShowEula=0", "ChangeDir=0",
        "OptionalComponents=1", "CleanBoot=1", "DevicePath=0", "NoDirWarn=1",
        f'TimeZone="{timezone}"', "Uninstall=0", "PenWinWarning=0", "NoPrompt2Boot=1", "",
        "[OptionalComponents]", *(f'"{name}"=1' for name in OPTIONAL_COMPONENTS), "",
        "[System]", "Locale=L0409", "SelectedKeyboard=KEYBOARD_00000409", "",
        "[NameAndOrg]", 'Name="art98"', 'Org=""', "Display=0", "",
        # Windows refuses a workgroup with the same name as the computer.
        "[Network]", 'ComputerName="art98"', 'Workgroup="WORKGROUP"', 'Description="art98"',
        "Display=0", "",
        "[Install]", "AddReg=Art98.AddReg", "",
        "[Art98.AddReg]",
        f'HKLM,"Software\\Microsoft\\Windows\\CurrentVersion\\Run",'
        f'"{AGENT_RUN_VALUE}",,"{AGENT_PATH}"',
        "",
    ]
    return "\r\n".join(lines)


def render_autoexec() -> str:
    return "\r\n".join([
        "@ECHO OFF",
        "C:",
        "CD \\WIN98",
        "SETUP.EXE C:\\WIN98\\MSBATCH.INF /IS /IE /IM /IQ /IV /NF",
        "",
    ])


def render_config_sys() -> str:
    return "\r\n".join(["DEVICE=A:\\HIMEM.SYS", "DOS=HIGH", "FILES=40", "BUFFERS=30", ""])


# OEM media ignores the answer file's request to skip its first-boot wizard, so
# prep presses through it. Name and product key arrive filled in from
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
            raise PrepError("unexpected screenshot format")
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


def patch_floppy(image: Path, scratch: Path) -> None:
    """Replace the disc's boot menu with a direct call to Setup."""
    listing = _mtool("mdir", "-a", "-b", "-i", str(image), "::", text=True).stdout.upper()
    if "HIMEM.SYS" not in listing:
        raise PrepError("the disc's boot floppy has no HIMEM.SYS")
    # JO.SYS is the disc's startup menu. IO.SYS runs it before CONFIG.SYS, and
    # after a timeout it boots the hard disk, so Setup would never start.
    if "JO.SYS" in listing:
        _mtool("mattrib", "-i", str(image), "-r", "-h", "-s", "::JO.SYS")
        _mtool("mdel", "-i", str(image), "::JO.SYS")
    for name, text in (("AUTOEXEC.BAT", render_autoexec()), ("CONFIG.SYS", render_config_sys())):
        local = scratch / name
        local.write_bytes(text.encode("ascii"))
        _mtool("mcopy", "-o", "-i", str(image), str(local), f"::{name}")


def patch_msdos_sys(text: str, options: dict[str, str]) -> str:
    """Set values in the [Options] section of MSDOS.SYS, keeping everything else."""
    lines = text.replace("\r\n", "\n").split("\n")
    remaining = dict(options)
    out: list[str] = []
    in_options = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("["):
            if in_options:
                out += [f"{k}={v}" for k, v in remaining.items()]
                remaining = {}
            in_options = stripped.lower() == "[options]"
        elif in_options and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            match = next((k for k in remaining if k.lower() == key.lower()), None)
            if match:
                out.append(f"{match}={remaining.pop(match)}")
                continue
        out.append(line)
    if remaining:
        tail = [f"{k}={v}" for k, v in remaining.items()]
        if not in_options:
            tail.insert(0, "[Options]")
        out += tail
    return "\r\n".join(out)


# ---- pipeline ----


@dataclass
class Prep:
    work: Path
    guest_build: Path
    iso: Path | None = None
    product_key: str | None = None
    disk_mb: int = 2047
    watch: bool = False
    log: object = print

    STAGES = ("media", "disk", "install", "patch", "harden")

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

    def _done(self) -> list[str]:
        if self.state_file.exists():
            return json.loads(self.state_file.read_text())
        return []

    def _mark(self, stage: str) -> None:
        self.state_file.write_text(json.dumps(self._done() + [stage]))

    def run(self, from_stage: str | None = None) -> None:
        done = self._done()
        if from_stage:
            done = done[:self.STAGES.index(from_stage)]
            self.state_file.write_text(json.dumps(done))
        for stage in self.STAGES:
            if stage in done:
                self.log(f"[{stage}] already done")
                continue
            self.log(f"[{stage}] starting")
            started = time.monotonic()
            getattr(self, f"stage_{stage}")()
            self._mark(stage)
            self.log(f"[{stage}] done in {time.monotonic() - started:.0f}s")

    # helpers

    def _config(self, **overrides) -> VMConfig:
        display = "gtk" if self.watch else "none"
        return VMConfig(disk=self.golden, machine=self._machine(), display=display, **overrides)

    def _machine(self) -> str:
        """Pin the machine version: snapshots only load on the one they came from."""
        output = _run(QEMU_BINARY, "-machine", "help", text=True).stdout
        for line in output.splitlines():
            name, *rest = line.split()
            if name == "pc" and "alias" in line:
                return line.split("alias of")[1].split(")")[0].strip()
        raise PrepError("could not determine the default QEMU machine type")

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
                raise PrepError(
                    f"no disk writes for {STALL_LIMIT // 60} minutes during {label}; "
                    f"see {shot}, or rerun with --watch to see the VM")
            if now > deadline:
                raise PrepError(f"{label} did not finish; last screen: {shot}")

    def _require_agent(self, vm: VM, bridge: Bridge, label: str) -> None:
        if not self._wait_for_agent(vm, bridge, label, 15 * 60, self._answer_setup_prompts):
            raise PrepError(f"the guest rebooted during {label} before the agent started")
        bridge.wait_ready()

    def _reboot(self, vm: VM, bridge: Bridge) -> None:
        """Shut Windows down. The call never returns, so it runs on its own thread."""
        bridge.acall("user32", "ExitWindowsEx", EWX_REBOOT | EWX_FORCE, 0)
        if not vm.wait_exit(SHUTDOWN_TIMEOUT):
            raise PrepError(f"Windows did not shut down; see "
                            f"{vm.screenshot(self.shots / 'shutdown.png')}")

    # stages

    def stage_media(self) -> None:
        if not self.iso:
            raise PrepError("the media stage needs --iso")
        if not self.product_key:
            raise PrepError("the media stage needs --key")
        agent = self.guest_build / "agent.exe"
        if not agent.exists():
            raise PrepError(f"{agent} missing; run make in windows_handlers/")
        pecheck.check_agent(agent)
        extract_setup_files(self.iso, self.media)
        self.floppy.write_bytes(boot_floppy_image(self.iso))
        patch_floppy(self.floppy, self.work)
        self.log(f"  setup files in {self.media}")

    def stage_disk(self) -> None:
        if not self.product_key:
            raise PrepError("the disk stage needs --key")
        win98 = next(p for p in self.media.iterdir() if p.name.upper() == "WIN98")
        mbr = (self.guest_build / "mbr.bin").read_bytes()
        create_disk(self.raw, self.disk_mb, mbr)
        spec = disk_spec(self.raw)
        self.log("  copying setup files to the disk")
        _mtool("mmd", "-i", spec, "::WIN98")
        _mtool("mmd", "-i", spec, "::ART98")
        _mtool("mcopy", "-s", "-Q", "-m", "-i", spec, *map(str, win98.iterdir()), "::WIN98/")
        answer = self.work / "MSBATCH.INF"
        answer.write_bytes(render_msbatch(self.product_key).encode("ascii"))
        _mtool("mcopy", "-o", "-i", spec, str(answer), "::WIN98/MSBATCH.INF")
        answer.unlink()  # it holds the product key
        _mtool("mcopy", "-o", "-i", spec, str(self.guest_build / "agent.exe"),
               "::ART98/AGENT.EXE")

    def stage_install(self) -> None:
        config = self._config(floppy=self.floppy, boot_once="a")
        config.disk, config.disk_format = self.raw, "raw"
        self.log(f"  running Setup, this takes a while; progress shots in {self.shots}")
        for boot in range(1, SETUP_BOOTS + 1):
            with VM(config, log=self._vm_log()) as vm:
                with Bridge.connect(vm.serial_path) as bridge:
                    if self._wait_for_agent(vm, bridge, f"install{boot}", INSTALL_TIMEOUT,
                                            self._answer_setup_prompts):
                        bridge.wait_ready()
                        self._reboot(vm, bridge)
                        return
            self.log(f"  Setup restarted the machine (boot {boot})")
            config.floppy, config.boot_once = None, None  # only the first boot uses it
        raise PrepError(f"Windows did not come up after {SETUP_BOOTS} boots")

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
                    raise PrepError("the first-boot wizard did not advance; see "
                                    f"{vm.screenshot(self.shots / 'wizard.png')}")
                time.sleep(1)

    def _wait_for_quiet_screen(self, vm: VM, label: str) -> None:
        """Wait until nothing on screen has moved for a while."""
        path = self.shots / f"{label}.png"
        last, since = None, time.monotonic()
        while time.monotonic() - since < SETTLE_SECONDS:
            time.sleep(1)
            digest = hashlib.sha256(vm.screenshot(path).read_bytes()).digest()
            if digest != last:
                last, since = digest, time.monotonic()

    def stage_patch(self) -> None:
        spec = disk_spec(self.raw)
        text = _mtool("mtype", "-i", spec, "::MSDOS.SYS").stdout.decode("cp437")
        patched = self.work / "MSDOS.SYS"
        patched.write_bytes(patch_msdos_sys(text, MSDOS_SYS_OPTIONS).encode("cp437"))
        _mtool("mattrib", "-i", spec, "-r", "-h", "-s", "::MSDOS.SYS")
        _mtool("mcopy", "-o", "-i", spec, str(patched), "::MSDOS.SYS")
        _mtool("mattrib", "-i", spec, "+r", "+h", "+s", "::MSDOS.SYS")
        patched.unlink()
        _run("qemu-img", "convert", "-f", "raw", "-O", "qcow2", str(self.raw), str(self.golden))

    def stage_harden(self) -> None:
        config = self._config()
        with VM(config, log=self._vm_log()) as vm:
            with Bridge.connect(vm.serial_path) as bridge:
                self._require_agent(vm, bridge, "harden")
                apply_settings(bridge)
                bridge.set_display_mode(*DISPLAY_MODE)
                self._reboot(vm, bridge)
        with VM(config, log=self._vm_log()) as vm:
            with Bridge.connect(vm.serial_path) as bridge:
                self._require_agent(vm, bridge, "reboot")
                self._wait_for_quiet_screen(vm, "ready")
                verify_desktop(bridge)
                vm.pause()
                vm.save_snapshot(SNAPSHOT)
                vm.screenshot(self.shots / "ready.png")
        (self.work / IMAGE_FILE).write_text(json.dumps(config.to_json(), indent=2))
        self.raw.unlink(missing_ok=True)


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
        result = bridge.advapi32.RegSetValueExA(handle, name or None, 0, kind, blob, len(blob))
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
            handle, index, Out(260), struct.pack("<I", 260), 0, 0, 0, 0)
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
        raise PrepError(f"unexpected windows on the desktop: {strays}")
    if not any(w.class_name == "Shell_TrayWnd" for w in bridge.windows()):
        raise PrepError("the taskbar is missing")
