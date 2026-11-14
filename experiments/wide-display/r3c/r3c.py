"""Probe R3c: unattended install of the vmdisp9x QEMU driver, shaped like a future add-on `install.py`.

usage (host QEMU: `. .tools/env.sh`):
  python3 r3c.py dump  RUNDIR DISK VGA OUTPREFIX   boot a copy, export HKLM + file lists + ini files with regedit/dir (read only diagnostics)
  python3 r3c.py run   RUNDIR                       RUNDIR/vm/{golden.qcow2,image.json} = fresh copy; full unattended install, verify, savevm ready
  python3 r3c.py check RUNDIR                       loadvm ready on the result; agent + desktop
Every boot goes through safe_boot (via r3.make_vm-alike). `InstallContext` below only offers what the plan's ctx will:
bridge, vm, put, reg, run (a guest command through the agent), reboot, wait_quiet, shots.
"""

from __future__ import annotations

import hashlib
import json
import struct
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "r3"))
sys.path.insert(0, str(HERE.parent / "r3b"))
import r3  # noqa: E402
import safe_boot  # noqa: E402
from art98.bridge import Bridge, BridgeError  # noqa: E402
from art98.qemu import VM, VMConfig  # noqa: E402
from r3 import HKLM, dump_modes, psi, reg_get, reg_open, reg_subkeys, say  # noqa: E402

EXT = Path("/home/admin/art98-release-check/probes/r3c-20261113-2311/ext")  # untrusted, already zip-slip checked, read only
DRV = "C:\\DRIVERS\\VMDISP"
IMAGE_VM = {"vga": "std"}  # what the manifest's [image.vm] would say; applies from the first ctx.reboot()
SETTLE = 30


class Ctx:
    """Stand-in for the plan's InstallContext (same surface, plus `run` for guest commands)."""

    def __init__(self, probe: Path, vga: str = "cirrus", loadvm: str | None = None):
        self.probe, self.vga, self.loadvm = probe, vga, loadvm
        self.shots = probe / "shots"
        self.shots.mkdir(exist_ok=True)
        self.vm: VM
        self.bridge: Bridge
        self.boots = 0
        self.log: list[tuple[str, str]] = []  # (kind, text): registry / file / command / keystroke
        self.dialogs: list[str] = []
        self.t0 = time.monotonic()
        self._pending_vm = False

    def step(self, kind: str, text: str) -> None:
        self.log.append((kind, text))
        say(f"STEP [{kind}] {text}")

    # --- VM lifecycle -------------------------------------------------
    def start(self, wait: bool = True) -> None:
        data = json.loads((self.probe / "vm" / "image.json").read_text())
        c = VMConfig.from_json(data)
        c.disk, c.floppy, c.loadvm, c.vga, c.machine = self.probe / "vm" / "golden.qcow2", None, self.loadvm, self.vga, data["machine"]
        self.vm = VM(c, log=self.probe / f"qemu-{self.boots}.log")
        safe_boot.check_vm(self.vm, self.probe)
        self.vm.start()
        self.boots += 1
        self.bridge = Bridge.connect(self.vm.serial_path)
        self.loadvm = None
        say(f"boot {self.boots} vga={self.vga} {psi()}")
        if wait:
            self.wait_agent()

    def stop(self) -> None:
        try:
            self.bridge.close()
        finally:
            self.vm.close()

    def wait_agent(self, limit: int = 300) -> int:
        t0, n = time.monotonic(), 0
        while time.monotonic() - t0 < limit:
            self.vm.screenshot(self.shots / f"boot{self.boots}-{n:03d}.png")
            n += 1
            try:
                self.bridge.request("PING", timeout=1.0)
                self.bridge.wait_ready()
                say(f"agent up after {time.monotonic() - t0:.0f}s {psi()}")
                return int(time.monotonic() - t0)
            except BridgeError:
                self.note_dialogs()
                time.sleep(5)
        raise SystemExit(f"agent never answered in boot {self.boots}; see {self.shots}")

    def note_dialogs(self) -> None:
        pass  # without the agent there is no window list; the screenshot is the only evidence

    def reboot_off(self) -> None:
        self.bridge.acall("user32", "ExitWindowsEx", 2 | 4, 0)
        if not self.vm.wait_exit(300):
            raise SystemExit("QEMU did not exit after ExitWindowsEx")

    def restart(self) -> None:
        """The VM exited by itself (a restart was accepted in a dialog): start the next boot."""
        self.vm.wait_exit(60)
        self.bridge.close()
        self.vm.close()
        self.start(wait=False)

    def reboot(self) -> None:
        self.reboot_off()
        self.bridge.close()
        self.vm.close()
        self.vga = IMAGE_VM["vga"]  # [image.vm] applies from the first reboot (cold boot, no loadvm)
        self.start(wait=False)

    def wait_quiet(self, seconds: float = SETTLE) -> None:
        last, since, n = None, time.monotonic(), 0
        while time.monotonic() - since < seconds:
            time.sleep(1)
            d = hashlib.sha256(self.vm.screenshot(self.shots / "quiet.png").read_bytes()).digest()
            if d != last:
                last, since = d, time.monotonic()
            n += 1

    # --- guest operations ---------------------------------------------
    def put(self, dest: str, data: bytes) -> None:
        self.bridge.put_file(dest, data)

    def reg(self, root: int, key: str, name: str, data, create: bool = True) -> None:
        """Set a value; str -> REG_SZ, int -> REG_DWORD, bytes -> REG_BINARY. Creates the key."""
        b = self.bridge
        from art98.protocol import Out

        h = b.advapi32.RegCreateKeyExA(root, key, 0, 0, 0, 0xF003F, 0, Out(4), Out(4))
        if h.value:
            raise BridgeError(f"RegCreateKeyEx {key}: {h.value}")
        hk = struct.unpack("<I", h.buffers[0])[0]
        if isinstance(data, int):
            typ, raw = 4, struct.pack("<I", data)
        elif isinstance(data, bytes):
            typ, raw = 3, data
        else:
            typ, raw = 1, data.encode("cp1252") + b"\0"
        r = b.advapi32.RegSetValueExA(hk, name, 0, typ, raw, len(raw))
        b.advapi32.RegFlushKey(hk)
        b.advapi32.RegCloseKey(hk)
        if r.value:
            raise BridgeError(f"RegSetValueEx {key}\\{name}: {r.value}")

    def run(self, cmd: str, timeout: float = 120) -> None:
        """Run a guest command line through the agent and wait for it to end."""
        pid = self.bridge.spawn(cmd)
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            if pid not in [p for p, _ in self.bridge.processes()]:
                return
            time.sleep(0.5)
        raise BridgeError(f"guest command timed out: {cmd}")

    def get(self, path: str) -> bytes:
        return self.bridge.get_file(path)

    def windows(self) -> list[tuple[str, str]]:
        return [(w.class_name, w.title) for w in self.bridge.windows() if w.visible and w.class_name not in ("Shell_TrayWnd", "Progman")]


# ---------------------------------------------------------------- the install
GUID_SYSTEM = bytes.fromhex("7de9364d25e3ce11bfc108002be10318")  # {4D36E97D-E325-11CE-BFC1-08002BE10318}
WIZ = "Add New Hardware Wizard"
SSC = "System Settings Change"
REFS = HERE / "refs"  # white-text masks of dialog title bars (pre-shell dialogs: the agent is not up, so the screen is the only evidence)
BLIND = {"system_settings_change": (SSC, ["ret"]), "add_new_hardware_wizard": (WIZ, ["ret"])}  # Enter = Yes / Next (default buttons)


def title_on_screen(png: Path) -> str | None:
    """Name of the known dialog whose title-bar text is on the screendump (exact white-pixel match), or None."""
    import numpy as np  # lazy: probe-only; the engine needs a stdlib PNG/PPM reader instead
    from PIL import Image

    white = (np.array(Image.open(png).convert("RGB")) == 255).all(-1)
    H, W = white.shape
    for name in BLIND:
        t = np.array(Image.open(REFS / f"{name}.png")) > 0
        h, w = t.shape
        fy, fx = (int(v[0]) for v in np.nonzero(t))
        for y, x in np.argwhere(white):
            y0, x0 = y - fy, x - fx
            if y0 >= 0 and x0 >= 0 and y0 + h <= H and x0 + w <= W and (white[y0 : y0 + h, x0 : x0 + w] == t).all():
                return name
    return None


def btn(ctx: Ctx, hwnd: int, wanted: tuple[str, ...]) -> bool:
    """BM_CLICK the first visible button of window `hwnd` whose caption (no &, no < >) is in `wanted`."""
    kids = {k.title.replace("&", "").strip(" <>").lower(): k for k in ctx.bridge.windows(hwnd) if k.class_name == "Button" and k.visible}
    for w in wanted:
        if w in kids:
            ctx.bridge.user32.PostMessageA(kids[w].hwnd, 0xF5, 0, 0)
            return True
    return False


def pump(ctx: Ctx, restart: str) -> str | None:
    """Answer one known dialog the agent can see, by title. restart = 'yes' | 'no' for the "System Settings Change" box."""
    ctx.bridge.ping(timeout=3)  # BridgeError when the agent is not up
    wins = [w for w in ctx.bridge.windows() if w.visible and w.class_name not in ("Shell_TrayWnd", "Progman")]
    for w in wins:
        if w.title == SSC:
            btn(ctx, w.hwnd, (restart,))
            ctx.dialogs.append(f"{SSC} -> {restart}")
            return "restart"
        if w.title == WIZ:
            texts = [k.title for k in ctx.bridge.windows(w.hwnd) if k.class_name == "Static" and k.visible and k.title]
            what = next((t for t in texts if len(t) < 70 and not t.startswith(("Windows", "This wizard", "A device", "What do", "Upgrading", "\xff"))), texts[0] if texts else "")
            if btn(ctx, w.hwnd, ("finish", "next")):
                ctx.dialogs.append(f"{WIZ}: {what}")
                return "wizard"
    return None


def wait_idle(ctx: Ctx, restart: str = "yes", quiet: float = 20, limit: float = 900) -> bool:
    """Pump dialogs until the agent sees nothing to answer for `quiet` s. Returns False if the VM exited (a restart was accepted)."""
    t0, last = time.monotonic(), time.monotonic()
    while time.monotonic() - t0 < limit:
        if not ctx.vm.running:
            return False
        try:
            act = pump(ctx, restart)
        except BridgeError:
            act, last = None, time.monotonic()  # no agent: never "idle"
            png = ctx.vm.screenshot(ctx.shots / "noagent.png")
            name = title_on_screen(png)
            if name:
                title, keys = BLIND[name]
                ctx.step("keystroke", f"title bar '{title}' seen on screen (agent down): {' '.join(keys)}")
                ctx.dialogs.append(f"{title} (agent down) -> {' '.join(keys)}")
                ctx.vm.send_keys(*keys)
                act = title
                time.sleep(4)
        if act:
            last = time.monotonic()
            say("dialog:", act, psi())
        elif time.monotonic() - last > quiet:
            return True
        time.sleep(2)
    raise SystemExit("dialogs never settled")


def install(ctx: Ctx) -> None:
    """Cirrus boot -> PCI bus (wizard) + vmdisp9x INF + no root Cirrus; reboot on -vga std; answer what appears."""
    b = ctx.bridge
    # 1. vmdisp9x files: INF + binaries in C:\WINDOWS\INF (PnP finds the INF by hardware ID), binaries also in C:\WIN98 (Windows' source path)
    for f in sorted(EXT.iterdir()):
        ext = f.suffix.lower()
        if ext in (".inf", ".drv", ".vxd", ".dll", ".exe"):
            data = f.read_bytes()
            ctx.step("file", f"put C:\\WINDOWS\\INF\\{f.name.upper()}" + (" and C:\\WIN98" if ext != ".inf" else ""))
            ctx.put(f"C:\\WINDOWS\\INF\\{f.name.upper()}", data)
            if ext != ".inf":
                ctx.put(f"C:\\WIN98\\{f.name.upper()}", data)
    # 2. PCI bus: register a "PCI bus" (*PNP0A03) root device through setupapi; Windows opens the Add New Hardware wizard for it
    #    (the same wizard as System devices > PCI bus), which the agent answers by button title, then installs the PCI devices it finds
    ctx.step("command", "setupapi: SetupDiCreateDeviceInfo Root\\System\\0000 + HARDWAREID *PNP0A03 + SetupDiRegisterDeviceInfo")
    sd = b.dll("setupapi")  # lazy: fixed device name Root\\System\\0000 and hand-packed SP_DEVINFO_DATA; fine on core's image, check for an existing devnode before reuse elsewhere
    h = sd.SetupDiCreateDeviceInfoList(GUID_SYSTEM, 0).value
    did = bytearray(28)
    struct.pack_into("<I", did, 0, 28)
    r = sd.SetupDiCreateDeviceInfoA(h, "Root\\System\\0000", GUID_SYSTEM, "PCI bus", 0, 0, did)
    assert r.value, f"SetupDiCreateDeviceInfo: {r.last_error:#x}"
    did = bytes(r.buffers[-1])
    hw = b"*PNP0A03\0\0"
    assert sd.SetupDiSetDeviceRegistryPropertyA(h, did, 1, hw, len(hw)).value, "set HARDWAREID"
    b.acall("setupapi", "SetupDiRegisterDeviceInfo", h, did, 0, 0, 0, 0)  # async: the wizard it raises is modal
    ctx.vm.screenshot(ctx.shots / "after-register.png")
    time.sleep(3)
    assert wait_idle(ctx, restart="no"), "VM exited while installing the PCI bus"
    pci = r3.reg_subkeys(b, r"Enum\PCI")
    assert pci, "Enum\\PCI is still empty"
    # 3. the dead root Cirrus (holds the VGA ports; Code 12 for the new adapter otherwise)
    ctx.step("registry", r"RegDeleteKey Enum\Root\*PNP0905")
    r = b.advapi32.RegDeleteKeyA(HKLM, r"Enum\Root\*PNP0905")
    assert r.value == 0, f"RegDeleteKey *PNP0905: {r.value}"
    # 4. [image.vm] vga=std applies now; restart prompts and wizards that follow are answered
    ctx.step("command", "reboot (ExitWindowsEx) -> cold boot -vga std")
    ctx.reboot()
    for _ in range(6):
        if wait_idle(ctx):
            return
        ctx.step("command", "restart accepted by a dialog -> cold boot")
        ctx.restart()
    raise SystemExit("still restarting after 6 boots")


def verify(ctx: Ctx) -> dict:
    """Raise AssertionError on a bad result; returns what it read."""
    b = ctx.bridge
    d = r3.display_info(b)
    inst = next((v for k, v in d[r"Enum\PCI"].items() if k.startswith("VEN_1234&DEV_1111")), None)
    assert inst, f"no QEMU STD VGA in Enum\\PCI: {d['all_pci']}"
    drv = inst["Driver"][1]  # DISPLAY\0002
    cls = d["Class\\Display\\" + drv.split("\\")[1]]
    assert cls["DriverDesc"][1] == "QEMU STD VGA PCI Adapter", cls
    m = dump_modes(b)
    assert m["caps"]["BITSPIXEL"] >= 16, m["caps"]
    modes = {(w, h) for w, h, _ in m["modes"]}
    assert (1280, 720) in modes and (1920, 1080) in modes, sorted(modes)
    out = {"driver": cls["DriverDesc"][1], "class_key": drv, "caps": m["caps"], "current": m.get("current"), "n_modes": len(m["modes"]), "has_1280x720": True, "has_1920x1080": True}
    say("verify ok", out)
    return out


def snapshot_ready(ctx: Ctx) -> None:
    ctx.vm.pause()
    ctx.vm.save_snapshot("ready")
    say("snapshots:", ctx.vm.snapshots())


# ---------------------------------------------------------------- diagnostics
def dump(probe: Path, disk: Path, vga: str, out: Path) -> None:
    """Boot a copy of `disk`, export HKLM and file lists with regedit/command.com, fetch them. No changes made."""
    pass
    c = Ctx(probe, vga=vga)
    c.start()
    try:
        c.run("regedit /e C:\\HKLM.REG HKEY_LOCAL_MACHINE", 300)
        c.run("regedit /e C:\\HKCU.REG HKEY_CURRENT_USER", 300)
        c.run("C:\\WINDOWS\\COMMAND.COM /c dir /s /b C:\\WINDOWS > C:\\WINLIST.TXT", 300)
        c.run("C:\\WINDOWS\\COMMAND.COM /c dir /s /b C:\\DRIVERS > C:\\DRVLIST.TXT", 60)
        for f in ("HKLM.REG", "HKCU.REG", "WINLIST.TXT", "DRVLIST.TXT"):
            time.sleep(1)
            (out.parent / f"{out.name}-{f}").write_bytes(c.get("C:\\" + f))
        for f in ("SYSTEM.INI", "WIN.INI"):
            (out.parent / f"{out.name}-{f}").write_bytes(c.get("C:\\WINDOWS\\" + f))
        say("modes", json.dumps(dump_modes(c.bridge), default=str)[:300])
        c.vm.screenshot(c.shots / f"{out.name}-final.png")
        c.reboot_off()
    finally:
        c.stop()


def run(probe: Path) -> None:
    ctx = Ctx(probe, "cirrus", loadvm="ready")
    t0 = time.monotonic()
    res: dict = {"psi_start": psi()}
    ctx.start()
    try:
        install(ctx)
        res["install_s"] = round(time.monotonic() - t0)
        res["boots_install"] = ctx.boots
        n_dialogs = len(ctx.dialogs)
        # the engine's own final step: one clean reboot on the final hardware, which must be quiet
        ctx.step("command", "final clean reboot (cold -vga std)")
        ctx.reboot()
        res["final_boot_agent_up_s"] = ctx.wait_agent()
        res["final_boot_dialogs"] = ctx.dialogs[n_dialogs:]
        ctx.wait_quiet()
        res["verify"] = verify(ctx)
        snapshot_ready(ctx)
        res["snapshots"] = ctx.vm.snapshots()
    finally:
        res.update(total_s=round(time.monotonic() - t0), boots=ctx.boots, psi_end=psi(), steps=ctx.log, dialogs=ctx.dialogs)
        say(f"elapsed {res['total_s']}s boots={ctx.boots} {psi()}")
        (probe / "result.json").write_text(json.dumps(res, indent=1, default=str))
        ctx.stop()


def check(probe: Path) -> None:
    """loadvm ready on the result: desktop + agent."""
    ctx = Ctx(probe, IMAGE_VM["vga"], loadvm="ready")
    t0 = time.monotonic()
    ctx.start()
    try:
        say("loadvm ready: agent up", f"{time.monotonic() - t0:.0f}s", ctx.windows())
        ctx.vm.screenshot(ctx.shots / "loadvm-ready.png")
        out = {"windows": ctx.windows(), "verify": verify(ctx), "monitor": r3.reg_subkeys(ctx.bridge, "Enum\\MONITOR"), "psi": psi()}
        out["monitor_inst"] = {m: r3.reg_subkeys(ctx.bridge, "Enum\\MONITOR\\" + m) for m in out["monitor"]}
        (probe / "check.json").write_text(json.dumps(out, indent=1, default=str))
        ctx.vm.pause()  # no reboot: the snapshot stays as taken
    finally:
        ctx.stop()


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "run":
        run(Path(sys.argv[2]).resolve())
    elif cmd == "check":
        check(Path(sys.argv[2]).resolve())
    if cmd == "dump":
        dump(Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve(), sys.argv[4], Path(sys.argv[5]).resolve())
