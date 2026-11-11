"""Step 2, setup: unattended Windows Setup, through its reboots.

Boots the disk from the patched floppy, lets Setup restart the machine as often
as it needs, and answers the first-boot wizard and the logon prompt (which live
in builder.py, since every later boot watches for them too). Ends once
AGENT.EXE says HELLO, with a clean shutdown.
"""

from __future__ import annotations

from art98.bridge import Bridge
from art98.qemu import VM

from .builder import Setup, SetupError

INSTALL_TIMEOUT = 3 * 3600
SETUP_BOOTS = 8  # Setup restarts the machine a few times on its own


def install(setup: Setup) -> None:
    config = setup._config(floppy=setup.floppy, boot_once="a")
    config.disk, config.disk_format = setup.raw, "raw"
    setup.log(f"  running Setup, this takes a while; progress shots in {setup.shots}")
    for boot in range(1, SETUP_BOOTS + 1):
        with (
            VM(config, log=setup._vm_log()) as vm,
            Bridge.connect(vm.serial_path) as bridge,
        ):
            if setup._wait_for_agent(
                vm,
                bridge,
                f"install{boot}",
                INSTALL_TIMEOUT,
                setup._answer_setup_prompts,
            ):
                bridge.wait_ready()
                setup._reboot(vm, bridge)
                return
        setup.log(f"  Setup restarted the machine (boot {boot})")
        config.floppy, config.boot_once = None, None  # only the first boot uses it
    raise SetupError(f"Windows did not come up after {SETUP_BOOTS} boots")


def run(setup: Setup) -> None:
    install(setup)
