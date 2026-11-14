"""Probe A1, container side. Run by probe.py inside the art98 image:
  guest.py a   copy of golden: loadvm ready (QMP), cold reboot, savevm ready over the inherited tag
  guest.py b   copy of golden: cold boot, no loadvm (does ScanDisk run?)
/work is read-only, /work/addons read-write (nested). Everything is written under /work/addons/a1."""

import dataclasses
import faulthandler
import signal
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from art98.qemu import VM, VMConfig

OUT = Path("/work/addons/a1")
faulthandler.register(signal.SIGUSR1)  # debug: docker kill -s USR1 dumps the stack


def say(*a):
    print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)


def pressure():
    return Path("/proc/pressure/cpu").read_text().splitlines()[0]


def vm_for(mode, disk, loadvm):
    cfg = VMConfig.from_json(json.loads(Path("/work/image.json").read_text()))
    cfg = dataclasses.replace(cfg, disk=disk, loadvm=loadvm)
    # mirrors the host-side safe_boot.check_vm: every path must sit under /work/addons
    argv = cfg.argv(Path("/q/qmp"), Path("/q/serial"))
    bad = [t for t in argv if "/" in t and "/work/addons/" not in t and "/q/" not in t
           and not t.startswith("qemu")]
    assert not bad, bad
    return VM(cfg, log=OUT / f"qemu-{mode}.log")


def settle(vm, tag, limit=420):
    """Screenshot every 10 s; stop after 4 identical frames past 60 s. Keep one frame per 30 s."""
    t0, last, same, n = time.monotonic(), None, 0, 0
    while time.monotonic() - t0 < limit:
        time.sleep(10)
        n += 1
        p = vm.screenshot(OUT / f"{tag}-{int(time.monotonic() - t0):03d}s.png")
        data = p.read_bytes()
        same = same + 1 if data == last else 0
        last = data
        if n % 3:
            p.unlink()
        if same >= 4 and time.monotonic() - t0 > 60:
            break
    say(tag, "settled after", int(time.monotonic() - t0), "s, identical frames", same, pressure())


def tags(disk):
    return subprocess.run(["qemu-img", "snapshot", "-l", str(disk)], capture_output=True, text=True).stdout


def copy(name):
    dst = OUT / name
    t = time.monotonic()
    r = subprocess.run(["cp", "--reflink=auto", "/work/golden.qcow2", str(dst)])
    say("cp --reflink=auto rc", r.returncode, f"{time.monotonic() - t:.2f}s")
    return dst


def main(mode):
    OUT.mkdir(exist_ok=True)
    disk = copy(f"{mode}.qcow2")
    say("snapshots on fresh copy:\n" + tags(disk))
    if mode == "b":
        with vm_for("b", disk, None) as vm:
            settle(vm, "b-cold")
            say("b info status:", vm.qmp.human("info status").strip())
        return
    # `-loadvm ready` on the command line fails here with a "write" lock error and QEMU hangs
    # (see README.md), so the snapshot is loaded over QMP, as Session.revert does.
    with vm_for("a1", disk, None) as vm:
        vm.load_snapshot("ready")
        time.sleep(20)
        vm.screenshot(OUT / "a-loadvm.png")
        say("a loadvm ready: snapshots", vm.snapshots(), "status", vm.qmp.human("info status").strip())
    # "reboot": QEMU runs -no-reboot, so a reboot is a new process; no loadvm = cold boot
    with vm_for("a2", disk, None) as vm:
        settle(vm, "a-cold")
        vm.pause()
        say("before savevm:", vm.snapshots())
        try:
            vm.save_snapshot("ready")
            say("savevm ready over inherited tag: ok")
        except Exception as e:
            say("savevm ready over inherited tag: ERROR", repr(e))
        say("after savevm:", vm.snapshots())
    say("qemu-img snapshot -l after:\n" + tags(disk))
    with vm_for("a3", disk, None) as vm:  # the new snapshot loads
        vm.load_snapshot("ready")
        time.sleep(20)
        vm.screenshot(OUT / "a-loadvm2.png")
        say("a loadvm of the new ready: status", vm.qmp.human("info status").strip())


main(sys.argv[1])
