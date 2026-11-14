"""Probe R3: install the vmdisp9x QEMU driver by script, route I1 (put_file + DevicePath + PnP on -vga std).

usage (host QEMU: `. .tools/env.sh`):
  python3 r3.py install PROBE   cold boot (cirrus), put the driver files, extend DevicePath, reboot (QEMU exits)
  python3 r3.py observe PROBE [vga]   cold boot (default std), sample screens/windows, dump driver/caps/modes, reboot
PROBE holds vm/{golden.qcow2,image.json} (copy, never a real work dir), ext/ (unpacked zip), shots/.
Every boot goes through safe_boot.
"""

from __future__ import annotations

import json
import struct
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "core"))
sys.path.insert(0, str(REPO / "experiments" / "wide-display"))
import safe_boot  # noqa: E402
from art98.bridge import Bridge, BridgeError  # noqa: E402
from art98.protocol import Out  # noqa: E402
from art98.qemu import VM, VMConfig  # noqa: E402

HKLM = 0x80000002
DEVPATH_KEY = r"Software\Microsoft\Windows\CurrentVersion"
DRV_DIR = "C:\\DRIVERS\\VMDISP"
EWX_REBOOT_FORCE = 2 | 4


def psi() -> str:
    return Path("/proc/pressure/cpu").read_text().splitlines()[0]


def say(*a) -> None:
    print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)


def make_vm(probe: Path, vga: str, tag: str) -> VM:
    data = json.loads((probe / "vm" / "image.json").read_text())
    c = VMConfig.from_json(data)
    c.disk, c.floppy, c.loadvm, c.vga, c.machine = probe / "vm" / "golden.qcow2", None, None, vga, data["machine"]
    vm = VM(c, log=probe / f"qemu-{tag}.log")
    safe_boot.check_vm(vm, probe)
    return vm


def reg_open(b: Bridge, key: str) -> int | None:
    r = b.advapi32.RegOpenKeyExA(HKLM, key, 0, 0xF003F, Out(4))
    return struct.unpack("<I", r.buffers[0])[0] if r.value == 0 else None


def reg_get(b: Bridge, key: str, name: str):
    h = reg_open(b, key)
    if h is None:
        return None
    r = b.advapi32.RegQueryValueExA(h, name, 0, Out(4), Out(1024), struct.pack("<I", 1024))
    b.advapi32.RegCloseKey(h)
    if r.value:
        return None
    typ = struct.unpack("<I", r.buffers[0])[0]
    return typ, r.buffers[1].split(b"\0", 1)[0].decode("cp1252")


def reg_subkeys(b: Bridge, key: str) -> list[str]:
    h, out, i = reg_open(b, key), [], 0
    while h is not None:
        r = b.advapi32.RegEnumKeyA(h, i, Out(260), 260)
        if r.value:
            break
        out.append(r.buffers[0].split(b"\0", 1)[0].decode("cp1252"))
        i += 1
    return out


def display_info(b: Bridge) -> dict:
    out: dict = {}
    cls = r"System\CurrentControlSet\Services\Class\Display"
    for sub in reg_subkeys(b, cls):
        out[f"Class\\Display\\{sub}"] = {
            n: reg_get(b, f"{cls}\\{sub}", n) for n in ("DriverDesc", "MatchingDeviceId", "InfPath", "DevLoader", "Ver")
        }
    pci = r"Enum\PCI"
    out["Enum\\PCI"] = {}
    for dev in reg_subkeys(b, pci):
        if "VEN_1234" in dev.upper():
            for inst in reg_subkeys(b, f"{pci}\\{dev}"):
                out["Enum\\PCI"][f"{dev}\\{inst}"] = {n: reg_get(b, f"{pci}\\{dev}\\{inst}", n) for n in ("DeviceDesc", "Driver", "Class")}
    out["all_pci"] = reg_subkeys(b, pci)
    out["Enum_other"] = {k: reg_subkeys(b, f"Enum\\{k}") for k in ("DISPLAY", "BIOS", "Display", "Unknown")}
    out["DevicePath"] = reg_get(b, DEVPATH_KEY, "DevicePath")
    files = {}
    for f in ("SYSTEM\\qemumini.drv", "SYSTEM\\VMM32\\qemumini.vxd", "SYSTEM\\vmdisp9x.dll", "INF\\OEM0.INF", "INF\\OTHER\\OEM0.INF"):
        try:
            files[f] = len(b.get_file("C:\\WINDOWS\\" + f))
        except BridgeError as e:
            files[f] = f"absent ({str(e)[:40]})"
    out["files"] = files
    return out


def dump_modes(b: Bridge) -> dict:
    out: dict = {"modes": []}
    for mode in range(400):
        blank = bytearray(156)
        struct.pack_into("<H", blank, 36, 156)
        r = b.user32.EnumDisplaySettingsA(None, mode, blank)
        if r.value == 0:
            break
        bpp, w, h = struct.unpack_from("<III", bytearray(r.buffers[0]), 104)
        out["modes"].append((w, h, bpp))
    blank = bytearray(156)
    struct.pack_into("<H", blank, 36, 156)
    r = b.user32.EnumDisplaySettingsA(None, 0xFFFFFFFF, blank)
    if r.value:
        bpp, w, h = struct.unpack_from("<III", bytearray(r.buffers[0]), 104)
        out["current"] = (w, h, bpp)
    dc = b.user32.GetDC(0).value
    caps = {"HORZRES": 8, "VERTRES": 10, "BITSPIXEL": 12, "PLANES": 14, "NUMCOLORS": 24}
    out["caps"] = {k: b.gdi32.GetDeviceCaps(dc, i).signed for k, i in caps.items()}
    b.user32.ReleaseDC(0, dc)
    return out


def wait_agent(vm: VM, b: Bridge, shots: Path, tag: str, limit: int = 420, extra: int = 0) -> int | None:
    t0, agent_at, i = time.monotonic(), None, 0
    while time.monotonic() - t0 < limit and vm.running:
        t = int(time.monotonic() - t0)
        vm.screenshot(shots / f"{tag}-{i:03d}-t{t:03d}.png")
        row = [f"shot {i}", f"t={t}s", psi()]
        try:
            b.request("PING", timeout=1.0)
            if agent_at is None:
                agent_at = t
                row.append("AGENT UP")
            row.append(str([(w.class_name, w.title) for w in b.windows() if w.visible and w.class_name not in ("Shell_TrayWnd", "Progman")]))
        except BridgeError as e:
            row.append(f"no agent ({str(e)[:30]})")
        say(*row)
        if agent_at is not None and t > agent_at + extra:
            return agent_at
        i += 1
        time.sleep(10)
    return agent_at


def reboot(vm: VM, b: Bridge) -> None:
    b.acall("user32", "ExitWindowsEx", EWX_REBOOT_FORCE, 0)
    say("reboot requested; QEMU exit:", vm.wait_exit(300))


def install(probe: Path) -> None:
    vm = make_vm(probe, "cirrus", "install")
    with vm as v:
        b = Bridge.connect(v.serial_path)
        try:
            if wait_agent(v, b, probe / "shots", "inst") is None:
                raise SystemExit("agent never answered")
            b.wait_ready()
            say("DevicePath before:", reg_get(b, DEVPATH_KEY, "DevicePath"))
            for d in ("C:\\DRIVERS", DRV_DIR):
                say("mkdir", d, b.kernel32.CreateDirectoryA(d, 0).value)
            for f in sorted((probe / "ext").iterdir()):
                t = time.monotonic()
                b.put_file(f"{DRV_DIR}\\{f.name.upper()}", f.read_bytes())
                say("put", f.name, f.stat().st_size, f"{time.monotonic() - t:.1f}s")
            old = reg_get(b, DEVPATH_KEY, "DevicePath")
            assert old, "cannot read DevicePath; aborting before any registry write"
            typ, val = old
            new = (val.rstrip(";") + ";" + DRV_DIR).encode("cp1252") + b"\0"
            h = reg_open(b, DEVPATH_KEY)
            say("RegSetValueEx:", b.advapi32.RegSetValueExA(h, "DevicePath", 0, typ, new, len(new)).value)
            b.advapi32.RegFlushKey(h)
            b.advapi32.RegCloseKey(h)
            say("DevicePath after:", reg_get(b, DEVPATH_KEY, "DevicePath"))
            say("display before:", json.dumps(dump_modes(b), default=str))
            reboot(v, b)
        finally:
            b.close()


def observe(probe: Path, vga: str) -> None:
    tag = f"obs-{vga}-{time.strftime('%H%M%S')}"
    vm = make_vm(probe, vga, tag)
    with vm as v:
        b = Bridge.connect(v.serial_path)
        try:
            at = wait_agent(v, b, probe / "shots", tag, extra=60)
            say("agent_at", at)
            if at is None:
                return
            res = {"vga": vga, "info": display_info(b), "display": dump_modes(b), "psi": psi()}
            say("RESULT", json.dumps(res, indent=1, default=str))
            (probe / f"{tag}.json").write_text(json.dumps(res, indent=1, default=str))
            v.screenshot(probe / "shots" / f"{tag}-final.png")
            reboot(v, b)
        finally:
            b.close()


def _kids(b: Bridge, title: str):
    w = b.find_window(title)
    return [(k.hwnd, k.class_name, k.title, k.visible) for k in b.windows(w.hwnd)]


def _btn(b: Bridge, title: str, text: str):
    """Press a button of the window whose title contains `title` (BM_CLICK)."""
    w = b.find_window(title)
    for k in b.windows(w.hwnd):
        if k.visible and text.lower() in k.title.lower().replace("&", ""):
            return b.user32.PostMessageA(k.hwnd, 0xF5, 0, 0).value, k.title
    return None


def drive(probe: Path, vga: str) -> None:
    """Boot and obey lines appended to PROBE/cmd.txt: `keys a b`, `shot NAME`, `win`, `dump`, `reboot`, `quit`. Log: PROBE/drive.out."""
    cmd = probe / "cmd.txt"
    cmd.write_text("")
    vm = make_vm(probe, vga, "drive")
    done, n = False, 0
    with vm as v:
        b = Bridge.connect(v.serial_path)
        try:
            while not done and v.running:
                lines = cmd.read_text().splitlines()
                for line in lines[n:]:
                    a = line.split()
                    try:
                        if a[0] == "keys":
                            v.send_keys(*a[1:])
                        elif a[0] == "shot":
                            say("shot", v.screenshot(probe / "shots" / f"{a[1]}.png"))
                        elif a[0] == "win":
                            say("win", [(w.class_name, w.title, w.visible) for w in b.windows()], psi())
                        elif a[0] == "dump":
                            say("DUMP", json.dumps({"info": display_info(b), "display": dump_modes(b)}, default=str))
                        elif a[0] == "reboot":
                            reboot(v, b)
                        elif a[0] == "py":  # probe-only: eval an expression with b (bridge), v (vm)
                            say("py", repr(eval(line[3:], {"b": b, "v": v, "reg_subkeys": reg_subkeys, "reg_get": reg_get, "btn": lambda t, x: _btn(b, t, x), "kids": lambda t: _kids(b, t)}))[:1500])
                        elif a[0] == "quit":
                            done = True
                    except Exception as e:  # noqa: BLE001
                        say("ERR", line, repr(e)[:200])
                    say("did", line)
                n = len(lines)
                time.sleep(0.5)
        finally:
            b.close()


if __name__ == "__main__":
    cmd, probe = sys.argv[1], Path(sys.argv[2]).resolve()
    if cmd == "install":
        install(probe)
    elif cmd == "drive":
        drive(probe, sys.argv[3] if len(sys.argv) > 3 else "std")
    else:
        observe(probe, sys.argv[3] if len(sys.argv) > 3 else "std")
