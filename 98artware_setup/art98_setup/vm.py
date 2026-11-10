"""Step 1, vm: the disc's boot floppy and Setup files, and a blank disk to install onto.

Unpacks the WIN98 folder from the user's disc, patches the disc's boot floppy
to start Setup directly, builds a disk with the MBR, copies the Setup files, the
answer file and AGENT.EXE onto it.
"""

from __future__ import annotations

import shutil
import struct
from pathlib import Path

from . import pecheck
from .builder import (
    AGENT_PATH, AGENT_RUN_VALUE, PARTITION_OFFSET, PARTITION_START, SECTOR,
    SECTORS_PER_TRACK, Setup, SetupError, _mtool, _run, disk_spec,
)

CD_SECTOR = 2048
HEADS = 16
FAT32_LBA = 0x0C
EL_TORITO_FLOPPY_SIZES = {1: 1228800, 2: 1474560, 3: 2949120}

# ---- disc ----


def boot_floppy_image(iso: Path) -> bytes:
    """Read the floppy image a bootable disc uses for its El Torito boot."""
    with open(iso, "rb") as disc:
        disc.seek(17 * CD_SECTOR)
        record = disc.read(CD_SECTOR)
        if record[1:6] != b"CD001" or not record[7:30].startswith(b"EL TORITO"):
            raise SetupError(f"{iso} is not a bootable disc")
        catalog_sector = struct.unpack_from("<I", record, 0x47)[0]
        disc.seek(catalog_sector * CD_SECTOR)
        catalog = disc.read(CD_SECTOR)
        entry = catalog[32:64]
        media = entry[1] & 0x0F
        if entry[0] != 0x88 or media not in EL_TORITO_FLOPPY_SIZES:
            raise SetupError(f"{iso} does not boot from an emulated floppy")
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
        raise SetupError(f"{iso} has no WIN98 folder; is it a Windows 98 disc?")
    names = {p.name.upper() for p in found[0].iterdir()}
    missing = {"SETUP.EXE", "PRECOPY1.CAB"} - names
    if missing:
        raise SetupError(f"{iso} WIN98 folder lacks {sorted(missing)}")
    return found[0]


# ---- disk ----


def build_mbr(boot_code: bytes, total_sectors: int) -> bytes:
    """Boot code plus one active FAT32 partition filling the disk."""
    if len(boot_code) > 440:
        raise SetupError(f"boot code is {len(boot_code)} bytes, over the 440 byte limit")
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

    ShowEula=0 accepts the licence on the user's behalf, which is why `art98 setup`
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


def patch_floppy(image: Path, scratch: Path) -> None:
    """Replace the disc's boot menu with a direct call to Setup."""
    listing = _mtool("mdir", "-a", "-b", "-i", str(image), "::", text=True).stdout.upper()
    if "HIMEM.SYS" not in listing:
        raise SetupError("the disc's boot floppy has no HIMEM.SYS")
    # JO.SYS is the disc's startup menu. IO.SYS runs it before CONFIG.SYS, and
    # after a timeout it boots the hard disk, so Setup would never start.
    if "JO.SYS" in listing:
        _mtool("mattrib", "-i", str(image), "-r", "-h", "-s", "::JO.SYS")
        _mtool("mdel", "-i", str(image), "::JO.SYS")
    for name, text in (("AUTOEXEC.BAT", render_autoexec()), ("CONFIG.SYS", render_config_sys())):
        local = scratch / name
        local.write_bytes(text.encode("ascii"))
        _mtool("mcopy", "-o", "-i", str(image), str(local), f"::{name}")


# ---- the step ----


def media(setup: Setup) -> None:
    if not setup.iso:
        raise SetupError("the media stage needs --iso")
    if not setup.product_key:
        raise SetupError("the media stage needs --key")
    agent = setup.guest_build / "agent.exe"
    if not agent.exists():
        raise SetupError(f"{agent} missing; run make in windows_handlers/")
    pecheck.check_agent(agent)
    extract_setup_files(setup.iso, setup.media)
    setup.floppy.write_bytes(boot_floppy_image(setup.iso))
    patch_floppy(setup.floppy, setup.work)
    setup.log(f"  setup files in {setup.media}")


def disk(setup: Setup) -> None:
    if not setup.product_key:
        raise SetupError("the disk stage needs --key")
    win98 = next(p for p in setup.media.iterdir() if p.name.upper() == "WIN98")
    mbr = (setup.guest_build / "mbr.bin").read_bytes()
    create_disk(setup.raw, setup.disk_mb, mbr)
    spec = disk_spec(setup.raw)
    setup.log("  copying setup files to the disk")
    _mtool("mmd", "-i", spec, "::WIN98")
    _mtool("mmd", "-i", spec, "::ART98")
    _mtool("mcopy", "-s", "-Q", "-m", "-i", spec, *map(str, win98.iterdir()), "::WIN98/")
    answer = setup.work / "MSBATCH.INF"
    answer.write_bytes(render_msbatch(setup.product_key).encode("ascii"))
    _mtool("mcopy", "-o", "-i", spec, str(answer), "::WIN98/MSBATCH.INF")
    answer.unlink()  # it holds the product key
    _mtool("mcopy", "-o", "-i", spec, str(setup.guest_build / "agent.exe"),
           "::ART98/AGENT.EXE")


def run(setup: Setup) -> None:
    media(setup)
    disk(setup)
