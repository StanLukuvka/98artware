"""Probe R4: display-mode switching with vmdisp9x on `-vga std`, on a COPY of R3c's run-A disk.

usage (host QEMU: `. .tools/env.sh`; PROBE = ~/art98-release-check/probes/r4-*, PROBE/vm/{golden.qcow2,image.json}):
  python3 r4.py table   PROBE   Q1 + Q3: switch table, frame costs, vgamem on the default 16 MB
  python3 r4.py persist PROBE   Q2: CDS_UPDATEREGISTRY over a reboot; mode set before savevm over loadvm
  python3 r4.py modes   PROBE   Q4: a non-listed 960x540 and a MODES registry line
  python3 r4.py vga32   PROBE   Q3: the same 1920x1080x32 with -global VGA.vgamem_mb=32
Every boot goes through safe_boot.check_vm, one VM at a time. Results go to PROBE/<cmd>.json and stdout.
"""

from __future__ import annotations

import json
import struct
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "r3"))
sys.path.insert(0, str(HERE.parent / "r3b"))
sys.path.insert(0, str(HERE.parent / "r3c"))
import r3c  # noqa: E402
import safe_boot  # noqa: E402
from art98.bridge import Bridge, BridgeError  # noqa: E402
from art98.protocol import Out  # noqa: E402
from art98.qemu import VM, VMConfig  # noqa: E402
from r3 import HKLM, dump_modes, psi, reg_get, reg_subkeys, say  # noqa: E402

CLS = r"System\CurrentControlSet\Services\Class\Display"


class Ctx(r3c.Ctx):
    """r3c's Ctx plus extra QEMU args and a vga that stays std."""

    extra: list[str] = []

    def start(self, wait: bool = True) -> None:
        data = json.loads((self.probe / "vm" / "image.json").read_text())
        c = VMConfig.from_json(data)
        c.disk, c.floppy, c.loadvm, c.vga, c.machine = self.probe / "vm" / "golden.qcow2", None, self.loadvm, self.vga, data["machine"]
        c.extra_args = list(self.extra)
        self.vm = VM(c, log=self.probe / f"qemu-{self.boots}-{int(time.time())}.log")
        safe_boot.check_vm(self.vm, self.probe)
        self.vm.start()
        self.boots += 1
        self.bridge = Bridge.connect(self.vm.serial_path)
        self.loadvm = None
        say(f"boot {self.boots} vga={self.vga} extra={self.extra} loadvm={c.loadvm} {psi()}")
        if wait:
            self.wait_agent()


class Spy:
    """Records the return code of ChangeDisplaySettingsA calls made by bridge.set_display_mode."""

    def __init__(self, dll):
        self.dll, self.rc = dll, []

    def __getattr__(self, name):
        fn = getattr(self.dll, name)
        if name != "ChangeDisplaySettingsA":
            return fn

        def call(*a, **k):
            r = fn(*a, **k)
            self.rc.append((r.signed, a[1]))
            return r

        return call


def ppm_size(vm: VM, path: Path) -> tuple[int, int]:
    vm.screenshot(path, format="ppm")
    with open(path, "rb") as f:
        head = f.read(32).split()
    return int(head[1]), int(head[2])


def caps(b: Bridge) -> tuple[int, int, int]:
    dc = b.user32.GetDC(0).value
    out = tuple(b.gdi32.GetDeviceCaps(dc, i).signed for i in (8, 10, 12))
    b.user32.ReleaseDC(0, dc)
    return out  # HORZRES, VERTRES, BITSPIXEL


def visible(b: Bridge) -> list[str]:
    return sorted(f"{w.class_name}|{w.title}|{w.rect}" for w in b.windows() if w.visible)


def agent_up(b: Bridge) -> bool:
    try:
        b.request("PING", timeout=2.0)
        return True
    except BridgeError:
        return False


def settle_dump(ctx: Ctx, want: tuple[int, int], tag: str, limit: float = 15) -> tuple[tuple[int, int], float]:
    t0 = time.monotonic()
    while True:
        size = ppm_size(ctx.vm, ctx.shots / "tmp.ppm")
        if size == want or time.monotonic() - t0 > limit:
            return size, time.monotonic() - t0
        time.sleep(0.1)


def switch(ctx: Ctx, w: int, h: int, d: int, persist: bool = False, shot: bool = True) -> dict:
    """bridge.set_display_mode itself, with timing, rc, dump size, caps, dialogs, agent."""
    b = ctx.bridge
    spy = Spy(b.user32)
    b.user32, orig = spy, b.user32
    before = set(visible(b))
    row: dict = {"mode": f"{w}x{h}x{d}", "persist": persist, "psi": psi()}
    t0 = time.monotonic()
    try:
        b.set_display_mode(w, h, d, persist=persist)
        row["error"] = None
    except BridgeError as e:
        row["error"] = str(e)
    row["switch_s"] = round(time.monotonic() - t0, 3)
    b.user32 = orig
    row["rc"] = spy.rc[0][0] if spy.rc else None
    size, t_dump = settle_dump(ctx, (w, h), row["mode"])
    row["dump_size"], row["dump_match_after_s"] = f"{size[0]}x{size[1]}", round(t_dump, 2)
    time.sleep(1.5)
    row["agent_up"] = agent_up(b)
    if row["agent_up"]:
        row["caps"] = caps(b)
        row["new_windows"] = sorted(set(visible(b)) - before)
    if shot:
        ctx.vm.screenshot(ctx.shots / f"{row['mode']}{'-persist' if persist else ''}.png")
    say("switch", json.dumps(row, default=str))
    return row


def frame_cost(ctx: Ctx, label: str, n: int = 100) -> dict:
    b, vm, tmp = ctx.bridge, ctx.vm, ctx.shots / "fc.ppm"
    out: dict = {"mode": label, "psi_before": psi()}
    t = time.monotonic()
    for _ in range(n):
        b.sync()
        vm.screenshot(tmp, format="ppm")
        tmp.read_bytes()
    out["frame_ms"] = round((time.monotonic() - t) / n * 1000, 2)
    t = time.monotonic()
    for _ in range(n):
        b.sync()
    out["sync_ms"] = round((time.monotonic() - t) / n * 1000, 2)
    t = time.monotonic()
    for _ in range(n):
        vm.screenshot(tmp, format="ppm")
    out["ppm_ms"] = round((time.monotonic() - t) / n * 1000, 2)
    out["ppm_bytes"] = tmp.stat().st_size
    png = ctx.shots / "fc.png"
    t = time.monotonic()
    for _ in range(n):
        vm.screenshot(png)
    out["png_ms"] = round((time.monotonic() - t) / n * 1000, 2)
    out["png_bytes"] = png.stat().st_size
    out["psi_after"] = psi()
    say("frame", json.dumps(out))
    return out


def finish(probe: Path, name: str, res: dict, ctx: Ctx) -> None:
    res["psi_end"] = psi()
    (probe / f"{name}.json").write_text(json.dumps(res, indent=1, default=str))
    try:
        ctx.stop()
    except Exception as e:  # noqa: BLE001
        say("stop:", e)


def current(ctx: Ctx) -> dict:
    m = dump_modes(ctx.bridge)
    return {"current": m.get("current"), "caps": m["caps"], "n_modes": len(m["modes"]), "dump": ppm_size(ctx.vm, ctx.shots / "tmp.ppm")}


def table(probe: Path, persist_flag: bool = False) -> None:
    name = "table-persist" if persist_flag else "table"
    ctx = Ctx(probe, "std", loadvm="ready")
    res: dict = {"psi_start": psi(), "rows": [], "frames": []}
    t0 = time.monotonic()
    ctx.start()
    res["agent_up_s"] = round(time.monotonic() - t0)
    try:
        m = dump_modes(ctx.bridge)
        res["modes"], res["start"] = m["modes"], current(ctx)
        res["baseline_windows"] = visible(ctx.bridge)
        say("start", res["start"], len(m["modes"]), "modes")
        ctx.vm.screenshot(ctx.shots / "start-800x600.png")
        for mode in [(1280, 720, 16), (1280, 720, 32), (1920, 1080, 16), (1920, 1080, 32), (1600, 900, 16), (1024, 768, 16), (800, 600, 16)]:
            row = switch(ctx, *mode, persist=persist_flag)
            row["taskbar"] = bar_px(ctx, "x".join(map(str, mode)) + ("-p" if persist_flag else "-n"))
            res["rows"].append(row)
            if mode in ((1280, 720, 16), (1920, 1080, 32), (1920, 1080, 16)):
                res["frames"].append(frame_cost(ctx, "x".join(map(str, mode))))
        res["frames"].append(frame_cost(ctx, "800x600x16 (final)"))
    finally:
        finish(probe, name, res, ctx)


def persist(probe: Path) -> None:
    ctx = Ctx(probe, "std", loadvm="ready")
    res: dict = {"psi_start": psi()}
    ctx.start()
    try:
        res["set_persist"] = switch(ctx, 1280, 720, 16, persist=True)
        r = ctx.bridge.advapi32  # registry view of what CDS_UPDATEREGISTRY wrote
        res["reg_after_set"] = {k: reg_get(ctx.bridge, r"Config\0001\Display\Settings", k) for k in ("Resolution", "BitsPerPixel")}
        ctx.step("command", "clean reboot (ExitWindowsEx), cold boot, no loadvm")
        t0 = time.monotonic()
        ctx.reboot()
        res["reboot_agent_up_s"] = ctx.wait_agent()
        time.sleep(5)
        res["after_reboot"] = current(ctx)
        res["reg_after_reboot"] = {k: reg_get(ctx.bridge, r"Config\0001\Display\Settings", k) for k in ("Resolution", "BitsPerPixel")}
        res["dialogs_after_reboot"] = visible(ctx.bridge)
        ctx.vm.screenshot(ctx.shots / "persist-after-reboot.png")
        res["reboot_total_s"] = round(time.monotonic() - t0)
        # savevm part: the mode is set WITHOUT persist, then savevm, then a new process loadvm
        res["set_1024"] = switch(ctx, 1024, 768, 16, persist=False)
        ctx.vm.pause()
        ctx.vm.save_snapshot("m1024")
        res["snapshots"] = ctx.vm.snapshots()
    finally:
        finish(probe, "persist-a", res, ctx)
    ctx = Ctx(probe, "std", loadvm="m1024")
    res2: dict = {"psi_start": psi()}
    t0 = time.monotonic()
    ctx.start()
    try:
        res2["agent_up_s"] = round(time.monotonic() - t0)
        res2["after_loadvm"] = current(ctx)
        res2["windows"] = visible(ctx.bridge)
        ctx.vm.screenshot(ctx.shots / "persist-after-loadvm.png")
        say("after loadvm", res2["after_loadvm"])
    finally:
        finish(probe, "persist-b", res2, ctx)


def raw_cds(b: Bridge, w: int, h: int, d: int) -> int:
    """ChangeDisplaySettingsA with a hand-built DEVMODE (not from the list)."""
    dm = bytearray(156)
    struct.pack_into("<H", dm, 36, 156)
    struct.pack_into("<I", dm, 40, 0x40000 | 0x80000 | 0x100000)  # BITSPERPEL | PELSWIDTH | PELSHEIGHT
    struct.pack_into("<III", dm, 104, d, w, h)
    return b.user32.ChangeDisplaySettingsA(bytes(dm), 0).signed


def keys(b: Bridge, key: str) -> dict:
    h = b.advapi32  # noqa: F841
    return {k: {n: reg_get(b, f"{key}\\{k}", n) for n in ("DPI", "Colors", "")} for k in reg_subkeys(b, key)}


def modes(probe: Path) -> None:
    ctx = Ctx(probe, "std", loadvm="ready")
    res: dict = {"psi_start": psi()}
    ctx.start()
    b = ctx.bridge
    try:
        cls = next(s for s in reg_subkeys(b, CLS) if (reg_get(b, f"{CLS}\\{s}", "DriverDesc") or (0, ""))[1].startswith("QEMU STD"))
        res["class_key"] = cls
        base = f"{CLS}\\{cls}\\MODES"
        res["MODES_bpp_keys"] = reg_subkeys(b, base)
        res["MODES_16_count"] = len(reg_subkeys(b, base + "\\16"))
        res["MODES_16_sample"] = reg_subkeys(b, base + "\\16")[:12]
        res["MODES_16_1280,720"] = {k: reg_get(b, base + "\\16\\1280,720", k) for k in ("DPI", "Colors", "")}
        res["MODES_16_960,540"] = reg_get(b, base + "\\16\\960,540", "")
        res["in_list_before"] = (960, 540, 16) in [tuple(m) for m in dump_modes(b)["modes"]]
        res["files"] = {}
        for f in ("INF\\vesamode.exe", "VESAMODE.EXE", "SYSTEM\\vesamode.exe"):
            try:
                res["files"][f] = len(b.get_file("C:\\WINDOWS\\" + f))
            except BridgeError:
                res["files"][f] = None
        res["set_960x540_before"] = switch(ctx, 960, 540, 16)
        res["raw_cds_960x540"] = raw_cds(b, 960, 540, 16)
        say("raw CDS 960x540 rc", res["raw_cds_960x540"])
        # add a MODES line (what the INF's HKR,"MODES\16\960,540" does) and look again without a reboot
        t = time.monotonic()
        for bpp in ("16", "32"):
            ctx.reg(HKLM, f"{base}\\{bpp}\\960,540", "", "")
        res["reg_added_s"] = round(time.monotonic() - t, 2)
        res["key_values_like_1280x720"] = res["MODES_16_1280,720"]
        res["in_list_after_reg_no_reboot"] = (960, 540, 16) in [tuple(m) for m in dump_modes(b)["modes"]]
        ctx.step("command", "clean reboot with the 960,540 MODES key added")
        ctx.reboot()
        res["reboot_agent_up_s"] = ctx.wait_agent()
        time.sleep(3)
        m = dump_modes(b := ctx.bridge)
        res["in_list_after_reboot"] = {d: (960, 540, d) in [tuple(x) for x in m["modes"]] for d in (16, 32)}
        res["n_modes_after_reboot"] = len(m["modes"])
        if res["in_list_after_reboot"][16]:
            res["set_960x540_after"] = switch(ctx, 960, 540, 16)
            res["frame_960x540"] = frame_cost(ctx, "960x540x16", n=30)
    finally:
        finish(probe, "modes", res, ctx)


def vga32(probe: Path) -> None:
    ctx = Ctx(probe, "std", loadvm="ready")
    res: dict = {"psi_start": psi()}
    ctx.start()
    try:
        res["n_modes_default"] = len(dump_modes(ctx.bridge)["modes"])
        ctx.extra = ["-global", "VGA.vgamem_mb=32"]
        ctx.reboot()
        res["reboot_agent_up_s"] = ctx.wait_agent()
        time.sleep(3)
        m = dump_modes(ctx.bridge)
        res["n_modes_32mb"], res["modes_32mb_max"] = len(m["modes"]), sorted(set((w, h, d) for w, h, d in m["modes"]))[-6:]
        res["rows"] = [switch(ctx, 1920, 1080, 32), switch(ctx, 1920, 1080, 16)]
        res["frames"] = [frame_cost(ctx, "1920x1080x32 vgamem32", n=50)]
    finally:
        finish(probe, "vga32", res, ctx)


def bar_px(ctx: Ctx, tag: str) -> dict:
    """Taskbar colour (189,190,189) across the last rows: width covered and Shell_TrayWnd rect."""
    from PIL import Image  # probe only

    p = ctx.shots / f"tb-{tag}.png"
    ctx.vm.screenshot(p)
    im = Image.open(p).convert("RGB")
    w, h = im.size
    n = sum(im.getpixel((x, h - 6)) == (189, 190, 189) for x in range(w))
    tray = [wd.rect for wd in ctx.bridge.windows() if wd.class_name == "Shell_TrayWnd"]
    return {"tag": tag, "size": (w, h), "bar_px_bottom": n, "bar_ok": n > w * 0.9, "tray": tray}


def raw(probe: Path) -> None:
    """A mode not in the list straight into ChangeDisplaySettingsA: rc, and what the screen does."""
    ctx = Ctx(probe, "std", loadvm="ready")
    res: dict = {}
    ctx.start()
    try:
        for flags_note, wh in (("960x540x16", (960, 540, 16)), ("1000x700x16", (1000, 700, 16))):
            res[flags_note] = {"rc": raw_cds(ctx.bridge, *wh), "caps": caps(ctx.bridge), "dump": ppm_size(ctx.vm, ctx.shots / "tmp.ppm")}
            say(flags_note, res[flags_note])
    finally:
        finish(probe, "raw", res, ctx)


def taskbar2(probe: Path) -> None:
    """Non-persist switch, then try to make the shell move the taskbar: SetWindowPos on Shell_TrayWnd, CDS(NULL,0), CDS_RESET."""
    ctx = Ctx(probe, "std", loadvm="ready")
    res: dict = {"steps": []}
    ctx.start()
    b = ctx.bridge
    try:
        res["steps"].append(switch(ctx, 1280, 720, 16, shot=False))
        res["steps"].append(bar_px(ctx, "start"))
        tray = next(w for w in b.windows() if w.class_name == "Shell_TrayWnd")
        b.user32.SetWindowPos(tray.hwnd, 0, 0, 720 - 28, 1280, 28, 0x14)  # SWP_NOZORDER|NOACTIVATE
        time.sleep(2)
        res["steps"].append(bar_px(ctx, "after-SetWindowPos"))
        res["cds_null_rc"] = b.user32.ChangeDisplaySettingsA(0, 0).signed
        time.sleep(3)
        res["steps"].append(bar_px(ctx, "after-CDS-null"))
        res["steps"].append(switch(ctx, 1280, 720, 32, shot=False))
        res["steps"].append(bar_px(ctx, "32-nonpersist"))
        b.user32.PostMessageA(tray.hwnd, 0x7E, 16, 1280 | (720 << 16))
        b.user32.PostMessageA(0xFFFF, 0x1A, 0x2F, 0)  # WM_SETTINGCHANGE SPI_SETWORKAREA
        time.sleep(3)
        res["steps"].append(bar_px(ctx, "32-after-posted-DISPLAYCHANGE-to-tray"))
    finally:
        finish(probe, "taskbar2", res, ctx)


def taskbar(probe: Path) -> None:
    """Why does the taskbar stay behind on a non-persist switch? Try waiting, a broadcast, a work-area reset."""
    ctx = Ctx(probe, "std", loadvm="ready")
    res: dict = {"psi_start": psi(), "steps": []}
    ctx.start()
    b = ctx.bridge
    try:
        res["steps"].append(switch(ctx, 1280, 720, 16, shot=False))
        res["steps"].append(bar_px(ctx, "immediate"))
        time.sleep(10)
        res["steps"].append(bar_px(ctx, "wait10s"))
        b.user32.SendMessageTimeoutA(0xFFFF, 0x7E, 16, 1280 | (720 << 16), 2, 2000, Out(4))  # WM_DISPLAYCHANGE broadcast
        time.sleep(2)
        res["steps"].append(bar_px(ctx, "after-WM_DISPLAYCHANGE"))
        rect = struct.pack("<IIII", 0, 0, 1280, 720)
        b.user32.SystemParametersInfoA(47, 0, rect, 2)  # SPI_SETWORKAREA, SPIF_SENDCHANGE
        time.sleep(2)
        res["steps"].append(bar_px(ctx, "after-SETWORKAREA"))
        # a second switch of the same kind (CDS flags 0), then with persist
        res["steps"].append(switch(ctx, 1024, 768, 16, shot=False))
        res["steps"].append(bar_px(ctx, "1024-nonpersist"))
        res["steps"].append(switch(ctx, 1280, 720, 16, persist=True, shot=False))
        res["steps"].append(bar_px(ctx, "1280-persist"))
        res["steps"].append(switch(ctx, 800, 600, 16, persist=True, shot=False))
        res["steps"].append(bar_px(ctx, "800-persist"))
        res["steps"].append(switch(ctx, 1280, 720, 16, persist=False, shot=False))
        res["steps"].append(bar_px(ctx, "1280-nonpersist-after-persist-run"))
    finally:
        finish(probe, "taskbar", res, ctx)


if __name__ == "__main__":
    if sys.argv[1] == "table-persist":
        table(Path(sys.argv[2]).resolve(), True)
        sys.exit(0)
    {"table": table, "persist": persist, "modes": modes, "vga32": vga32, "taskbar": taskbar, "taskbar2": taskbar2, "raw": raw}[sys.argv[1]](Path(sys.argv[2]).resolve())
