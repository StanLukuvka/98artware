"""Probes R1 (std VGA cold boot, vgamem, screendump time) and R2 (Cirrus frame cost).

usage: python3 probe.py {std|std32|r2} PROBE_DIR SHOTS_DIR
PROBE_DIR holds golden.qcow2 + image.json copies (made by the caller, outside
the repo). Every boot goes through safe_boot. Needs `. .tools/env.sh`.
"""

from __future__ import annotations

import json
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "core"))
sys.path.insert(0, str(REPO / "experiments" / "wide-display"))
import safe_boot  # noqa: E402
from art98.bridge import Bridge, BridgeError  # noqa: E402
from art98.qemu import VM, VMConfig  # noqa: E402
from art98.session import stage  # noqa: E402


def psi() -> str:
    return Path("/proc/pressure/cpu").read_text().splitlines()[0]


def timed(label: str, fn, n: int = 100) -> dict:
    before = psi()
    t0 = time.monotonic()
    for _ in range(n):
        fn()
    dt = time.monotonic() - t0
    row = {"label": label, "n": n, "total_s": round(dt, 2),
           "per_call_ms": round(dt / n * 1000, 1), "psi_before": before, "psi_after": psi()}
    print(json.dumps(row), flush=True)
    return row


def png_size(path: Path) -> tuple[int, int]:
    return struct.unpack(">II", path.read_bytes()[16:24])


def dump_modes(bridge: Bridge) -> dict:
    out: dict = {"modes": []}
    b0 = bytearray(156)
    struct.pack_into("<H", b0, 36, 156)
    r0 = bridge.user32.EnumDisplaySettingsA(None, 0, b0)
    out["mode0_raw"] = (r0.value, r0.last_error)
    out["windows"] = [(w.class_name, w.title, w.visible, w.rect) for w in bridge.windows()]
    mode = 0
    while mode < 400:
        blank = bytearray(156)
        struct.pack_into("<H", blank, 36, 156)
        r = bridge.user32.EnumDisplaySettingsA(None, mode, blank)
        if r.value == 0:
            break
        bpp, w, h = struct.unpack_from("<III", bytearray(r.buffers[0]), 104)
        out["modes"].append((w, h, bpp))
        mode += 1
    blank = bytearray(156)
    struct.pack_into("<H", blank, 36, 156)
    r = bridge.user32.EnumDisplaySettingsA(None, 0xFFFFFFFF, blank)
    if r.value:
        bpp, w, h = struct.unpack_from("<III", bytearray(r.buffers[0]), 104)
        out["current"] = (w, h, bpp)
    dc = bridge.user32.GetDC(0).value
    caps = {"HORZRES": 8, "VERTRES": 10, "BITSPIXEL": 12, "PLANES": 14, "NUMCOLORS": 24}
    out["caps"] = {k: bridge.gdi32.GetDeviceCaps(dc, i).signed for k, i in caps.items()}
    bridge.user32.ReleaseDC(0, dc)
    return out


def cold(variant: str, probe: Path, shots: Path) -> dict:
    data = json.loads((probe / "image.json").read_text())
    disk = probe / f"{variant}.qcow2"
    subprocess.run(["cp", "--reflink=auto", str(probe / "golden.qcow2"), str(disk)], check=True)
    config = VMConfig.from_json(data)
    config.disk, config.floppy, config.loadvm = disk, None, None
    config.vga = "std"
    config.machine = data["machine"]
    if variant == "std32":
        config.extra_args = ["-global", "VGA.vgamem_mb=32"]
    vm = VM(config, log=probe / f"{variant}.log")
    safe_boot.check_vm(vm, probe)
    res: dict = {"variant": variant, "argv": config.argv(vm.qmp_path, vm.serial_path), "shots": []}
    vm.start()
    res["pid"] = vm._process.pid
    t0 = time.monotonic()
    bridge = None
    try:
        bridge = Bridge.connect(vm.serial_path)
        agent_at = None
        i = 0
        while time.monotonic() - t0 < 360 and vm.running:
            p = shots / f"{variant}-{i:03d}-t{int(time.monotonic() - t0):03d}.png"
            vm.screenshot(p)
            res["shots"].append((p.name, int(time.monotonic() - t0), png_size(p), psi()))
            print(res["shots"][-1], flush=True)
            if agent_at is None:
                try:
                    bridge.request("PING", timeout=1.0)
                    agent_at = int(time.monotonic() - t0)
                    res["agent_at_s"] = agent_at
                    print("agent answered at", agent_at, flush=True)
                except BridgeError as e:
                    res["last_ping_error"] = str(e)
            elif time.monotonic() - t0 > agent_at + 40:
                break
            i += 1
            time.sleep(10)
        res["vm_running_at_end"] = vm.running
        if res.get("agent_at_s") is not None:
            res["display"] = dump_modes(bridge)
            print(json.dumps(res["display"]), flush=True)
        t = shots / f"{variant}-timing.png"
        res["timing"] = [
            timed(f"{variant} screendump png", lambda: vm.screenshot(t, "png")),
            timed(f"{variant} screendump ppm", lambda: vm.screenshot(t.with_suffix(".ppm"), "ppm")),
        ]
        t.with_suffix(".ppm").unlink(missing_ok=True)
        vm.screenshot(shots / f"{variant}-final.png")
    finally:
        if bridge:
            bridge.close()
        vm.close()
    return res


def r2(probe: Path, shots: Path) -> dict:
    work = probe / "w"
    work.mkdir()
    shutil.copy(probe / "golden.qcow2", work / "golden.qcow2")
    data = json.loads((probe / "image.json").read_text())
    data["disk"] = str(work / "golden.qcow2")
    (work / "image.json").write_text(json.dumps(data, indent=2))
    safe_boot.check_stage(work, probe)
    res: dict = {"timing": []}
    with stage(work) as s:
        res["start_mode"] = dump_modes(s.bridge)["current"]
        ppm = probe / "frame.ppm"

        def frame():
            s.bridge.sync()
            s.vm.screenshot(ppm, format="ppm")
            ppm.read_bytes()

        for w, h in ((800, 600), (1024, 768)):
            s.bridge.set_display_mode(w, h, 16, persist=False)
            time.sleep(3)
            s.bridge.sync()
            s.vm.screenshot(shots / f"r2-{w}x{h}.png")
            res["timing"].append(timed(f"cirrus {w}x{h} frame (sync+ppm dump+read)", frame))
            res["timing"].append(timed(f"cirrus {w}x{h} sync only", s.bridge.sync))
            res["timing"].append(timed(f"cirrus {w}x{h} dump ppm only", lambda: s.vm.screenshot(ppm, format="ppm")))
            res["timing"].append(timed(f"cirrus {w}x{h} dump png only", lambda: s.vm.screenshot(ppm.with_suffix(".png"), format="png")))
            res.setdefault("ppm_bytes", {})[f"{w}x{h}"] = ppm.stat().st_size
    return res


if __name__ == "__main__":
    mode, probe, shots = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    shots.mkdir(parents=True, exist_ok=True)
    out = r2(probe, shots) if mode == "r2" else cold(mode, probe, shots)
    (shots / f"{mode}.json").write_text(json.dumps(out, indent=2, default=str))
