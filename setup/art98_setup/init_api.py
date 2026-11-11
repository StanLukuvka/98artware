"""Step 3, init_api: make the installed system start its agent and check that it does.

Sets the MSDOS.SYS boot options, converts the raw disk to qcow2, then boots the
result once, waits for AGENT.EXE (HELLO, then a PING answer) and shuts Windows
down cleanly. Failing here means the call proxy does not come up on its own.
"""

from __future__ import annotations

from art98.bridge import Bridge
from art98.qemu import VM

from .builder import Setup, _mtool, _run, disk_spec

MSDOS_SYS_OPTIONS = {
    "AutoScan": "0",  # no ScanDisk prompt if a run is cut short
    "BootDelay": "0",
    "BootGUI": "1",
    "BootMenu": "0",
    "DisableLog": "1",
    "Logo": "0",
}


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


def patch(setup: Setup) -> None:
    spec = disk_spec(setup.raw)
    text = _mtool("mtype", "-i", spec, "::MSDOS.SYS").stdout.decode("cp437")
    patched = setup.work / "MSDOS.SYS"
    patched.write_bytes(patch_msdos_sys(text, MSDOS_SYS_OPTIONS).encode("cp437"))
    _mtool("mattrib", "-i", spec, "-r", "-h", "-s", "::MSDOS.SYS")
    _mtool("mcopy", "-o", "-i", spec, str(patched), "::MSDOS.SYS")
    _mtool("mattrib", "-i", spec, "+r", "+h", "+s", "::MSDOS.SYS")
    patched.unlink()
    _run(
        "qemu-img",
        "convert",
        "-f",
        "raw",
        "-O",
        "qcow2",
        str(setup.raw),
        str(setup.golden),
    )


def boot_and_ping(setup: Setup) -> None:
    """Boot the converted image once and shut it down: the agent must answer."""
    with (
        VM(setup._config(), log=setup._vm_log()) as vm,
        Bridge.connect(vm.serial_path) as bridge,
    ):
        setup._require_agent(vm, bridge, "init_api")
        setup._reboot(vm, bridge)


def run(setup: Setup) -> None:
    patch(setup)
    boot_and_ping(setup)
