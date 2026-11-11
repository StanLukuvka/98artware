"""P2: CD drive, medium change after loadvm, wallpaper (local backend).

    . .tools/env.sh && .venv/bin/python experiments/dialog-storm/probe_cd.py OUTDIR [section ...]

Sections: query drive detect wallpaper blank color revert (default: all).
Writes OUTDIR/*.png|ppm and OUTDIR/results.json; ISOs live in OUTDIR too.
Throwaway probe: no source edits, no savevm, private stage only.
"""

import io
import json
import struct
import sys
import time
from pathlib import Path

import pycdlib
from art98 import Out
from art98.desktop import blank, check_blank, shell_windows
from art98.session import stage

OUT = Path(sys.argv[1]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
WANT = sys.argv[2:] or [
    "query",
    "drive",
    "detect",
    "wallpaper",
    "getwp",
    "blank",
    "color",
    "revert",
]
CD = "ide1-cd0"
RES: dict = {}
T0 = time.perf_counter()


def psi() -> str:
    return (
        Path("/proc/pressure/cpu").read_text().splitlines()[0].split()[1]
    )  # some avg10=x


def rec(section: str, key: str, value) -> None:
    RES.setdefault(section, {})[key] = value
    print(f"[{time.perf_counter() - T0:7.1f}s] {section}.{key} = {value}", flush=True)


def timed(section: str, key: str, ms: float, **extra) -> None:
    rec(section, key, {"ms": round(ms), "cpu_psi": psi(), **extra})


# ---------- assets ----------
def bmp(w, h, pixel) -> bytes:
    stride = (w * 3 + 3) // 4 * 4
    rows = []
    for y in reversed(range(h)):
        row = b"".join(bytes(reversed(pixel(x, y))) for x in range(w))
        rows.append(row + bytes(stride - len(row)))
    pix = b"".join(rows)
    return (
        b"BM"
        + struct.pack("<IHHI", 54 + len(pix), 0, 0, 54)
        + struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, len(pix), 2835, 2835, 0, 0)
        + pix
    )


def grad(x, y):  # distinctive everywhere: red grows with x, green with y
    return (x * 255 // 799 % 256, y * 255 // 599 % 256, 128)


def small(x, y):
    return (30 + x, 20 + y, 200)  # x<160, y<120


FILES = {
    "WALL0001.BMP": bmp(800, 600, grad),  # ~1.44 MB, screen sized
    "WALL0002.BMP": bmp(640, 500, grad),  # ~960 KB
    "SMALL001.BMP": bmp(160, 120, small),
}  # tile / stretch


def build_iso(files: dict) -> bytes:
    iso = pycdlib.PyCdlib()
    iso.new(interchange_level=1, vol_ident="ART98")
    for name, data in files.items():
        iso.add_fp(io.BytesIO(data), len(data), f"/{name};1")
    out = io.BytesIO()
    iso.write_fp(out)
    iso.close()
    return out.getvalue()


ISO = OUT / "wall.iso"
ISO.write_bytes(build_iso(FILES))
print("iso bytes", ISO.stat().st_size, {k: len(v) for k, v in FILES.items()})


# ---------- helpers ----------
def read_ppm(path):
    data = Path(path).read_bytes()
    toks, pos = [], 0
    while len(toks) < 4:
        while data[pos : pos + 1].isspace():
            pos += 1
        end = pos
        while not data[end : end + 1].isspace():
            end += 1
        toks.append(data[pos:end])
        pos = end
    return int(toks[1]), int(toks[2]), data[pos + 1 :]


def shot(s, name):
    s.vm.screenshot(OUT / f"{name}.png")
    s.vm.screenshot(OUT / f"{name}.ppm", format="ppm")
    return OUT / f"{name}.ppm"


def ppm_px(ppm, x, y):
    w, _h, d = read_ppm(ppm)
    i = (y * w + x) * 3
    return tuple(d[i : i + 3])


def guest_px(g, x, y):
    dc = g.user32.GetDC(0).value
    v = g.gdi32.GetPixel(dc, x, y).value
    g.user32.ReleaseDC(0, dc)
    return (v & 255, v >> 8 & 255, v >> 16 & 255) if v != 0xFFFFFFFF else None


def block(s):
    return next(
        (d for d in s.vm.qmp.execute("query-block") if d.get("device") == CD), None
    )


def insert(s, iso=ISO):
    t = time.perf_counter()
    s.vm.qmp.execute(
        "blockdev-change-medium",
        device=CD,
        filename=str(iso),
        format="raw",
        **{"read-only-mode": "read-only", "force": True},
    )
    return (time.perf_counter() - t) * 1000


def eject(s):
    t = time.perf_counter()
    cd = block(s)
    if cd and "inserted" in cd:
        s.vm.qmp.execute("blockdev-open-tray", device=CD, force=True)
        s.vm.qmp.execute("blockdev-remove-medium", id=cd["qdev"])
        s.vm.qmp.execute("blockdev-close-tray", device=CD)
    return (time.perf_counter() - t) * 1000


def drives(g):
    mask = g.kernel32.GetLogicalDrives().value
    out = {}
    for i in range(26):
        if mask >> i & 1:
            out[chr(65 + i) + ":"] = g.kernel32.GetDriveTypeA(chr(65 + i) + ":\\").value
    return out


def cd_letter(g):
    return next((d for d, t in drives(g).items() if t == 5), None)


def detect(g, letter, name="WALL0001.BMP", timeout=15.0):
    """Poll GetFileAttributesA every 50 ms. Returns (ms, polls, distinct last_errors)."""
    t = time.perf_counter()
    errs, n = set(), 0
    while time.perf_counter() - t < timeout:
        r = g.kernel32.GetFileAttributesA(f"{letter}\\{name}")
        n += 1
        if r.value != 0xFFFFFFFF:
            return (time.perf_counter() - t) * 1000, n, sorted(errs)
        errs.add(r.last_error)
        time.sleep(0.05)
    return None, n, sorted(errs)


def top_windows(g):
    return [(w.class_name, w.title, w.rect) for w in g.windows() if w.visible]


def set_wp(g, path, tile="0", style="0", flags=3):
    key = g.advapi32.RegOpenKeyExA(0x80000001, r"Control Panel\Desktop", 0, 2, Out(4))
    hkey = struct.unpack("<I", key.buffers[0])[0]
    for n, v in (("TileWallpaper", tile), ("WallpaperStyle", style)):
        d = v.encode() + b"\0"
        assert g.advapi32.RegSetValueExA(hkey, n, 0, 1, d, len(d)).value == 0
    g.advapi32.RegCloseKey(hkey)
    t = time.perf_counter()
    r = g.user32.SystemParametersInfoA(0x14, 0, path, flags)
    ms = (time.perf_counter() - t) * 1000
    t = time.perf_counter()
    g.sync()
    return ms, (time.perf_counter() - t) * 1000, r.value, r.last_error


def get_wp(g):
    r = g.user32.SystemParametersInfoA(0x73, 260, Out(260), 0)
    return r.value, r.buffers[0].split(b"\0")[0].decode("cp1252")


def fresh(s, iso=ISO):
    """D7 sequence: eject, loadvm, insert; returns letter and per-step ms."""
    t0 = time.perf_counter()
    e = eject(s)
    t = time.perf_counter()
    s.revert()
    r = (time.perf_counter() - t) * 1000
    i = insert(s, iso)
    letter = cd_letter(s.bridge)
    ms, n, errs = detect(s.bridge, letter or "D:")
    return letter, {
        "eject": round(e),
        "revert": round(r),
        "insert": round(i),
        "detect": ms and round(ms),
        "polls": n,
        "errs": errs,
        "total": round((time.perf_counter() - t0) * 1000),
    }


# ---------- sections ----------
def sec_query(s):
    cd = block(s)
    rec("query", "after_boot_loadvm_ready_via_boot", cd)
    s.vm.load_snapshot("ready")
    s.bridge.ping()
    rec("query", "after_explicit_loadvm", block(s))
    rec(
        "query",
        "all_block_devices",
        [
            (
                d.get("device"),
                d.get("qdev"),
                d.get("removable"),
                d.get("tray_open"),
                "inserted" in d,
            )
            for d in s.vm.qmp.execute("query-block")
        ],
    )
    rec("query", "guest_drives_empty_tray", drives(s.bridge))


def sec_drive(s):
    g = s.bridge
    s.revert()
    before = top_windows(g)
    t_insert = insert(s)
    rec("drive", "block_after_insert", block(s))
    letter = cd_letter(g)
    rec("drive", "letter", letter)
    rec("drive", "drives_after_insert", drives(g))
    timed("drive", "insert_qmp", t_insert)
    ms, n, errs = detect(g, letter)
    timed("drive", "detect_poll_from_after_insert", ms or -1, polls=n, errs=errs)
    time.sleep(3)
    after = top_windows(g)
    rec("drive", "windows_before", before)
    rec("drive", "windows_after_3s", after)
    rec("drive", "new_windows", [w for w in after if w not in before])
    shot(s, "drive_after_insert")
    # file really readable? attributes + a read through CreateFile is overkill; size via FindFirstFile skipped.
    rec(
        "drive",
        "attrs",
        hex(g.kernel32.GetFileAttributesA(f"{letter}\\WALL0001.BMP").value),
    )


def sec_detect(s):
    """G2: does Win98 notice a swap without polling? Single access after fixed delays, no polling."""
    g = s.bridge
    for delay in (0.0, 0.1, 0.5, 1.0, 3.0):
        eject(s)
        s.revert()
        letter = cd_letter(g)
        t = time.perf_counter()
        insert(s)
        time.sleep(delay)
        r = g.kernel32.GetFileAttributesA(f"{letter}\\WALL0001.BMP")
        timed(
            "detect",
            f"single_access_after_{delay}s",
            (time.perf_counter() - t) * 1000,
            ok=r.value != 0xFFFFFFFF,
            last_error=r.last_error,
        )
        # drive type / GetVolumeInformation as alternative nudges
    # forced loop from a no-delay start, 5 repeats
    for k in range(5):
        eject(s)
        s.revert()
        letter = cd_letter(g)
        t = time.perf_counter()
        insert(s)
        ms, n, errs = detect(g, letter)
        timed(
            "detect",
            f"poll_run{k}",
            (time.perf_counter() - t) * 1000,
            detect_ms=ms and round(ms),
            polls=n,
            errs=errs,
        )


def sec_wallpaper(s):
    g = s.bridge
    for flags in (0, 2, 3):
        letter, tm = fresh(s)
        sw = g.user32.GetSystemMetrics(0).value, g.user32.GetSystemMetrics(1).value
        rec("wallpaper", f"flags{flags}_fresh_timing", tm)
        path = f"{letter}\\WALL0001.BMP"
        a, b, rv, le = set_wp(g, path, "0", "0", flags)
        timed(
            "wallpaper",
            f"flags{flags}_center_800x600_set",
            a,
            sync_ms=round(b),
            ret=rv,
            last_error=le,
        )
        ppm = shot(s, f"wp_flags{flags}_center")
        rec("wallpaper", f"flags{flags}_getwp", get_wp(g))
        for x, y in ((790, 590), (10, 10), (400, 300)):
            rec(
                "wallpaper",
                f"flags{flags}_px_{x}_{y}",
                {
                    "guest": guest_px(g, x, y),
                    "screendump": ppm_px(ppm, x, y),
                    "expected_bmp": grad(x, y),
                },
            )
        rec("wallpaper", f"flags{flags}_screen", sw)
    # 960 KB centred
    letter, _ = fresh(s)
    a, b, rv, le = set_wp(g, f"{letter}\\WALL0002.BMP", "0", "0", 3)
    ppm = shot(s, "wp_center_640x500")
    timed("wallpaper", "center_640x500_set", a, sync_ms=round(b), ret=rv)
    rec(
        "wallpaper",
        "center_640x500_px",
        {
            "in_bmp(200,200)": (guest_px(g, 200 + 80, 200 + 50), grad(200, 200)),
            "outside(5,5)": guest_px(g, 5, 5),
            "desktop_colour": hex(g.user32.GetSysColor(1).value),
        },
    )
    rec("wallpaper", "center_640x500_getwp", get_wp(g))
    # tile
    letter, _ = fresh(s)
    a, b, rv, le = set_wp(g, f"{letter}\\SMALL001.BMP", "1", "0", 3)
    ppm = shot(s, "wp_tile_160x120")
    exp = lambda x, y: small(x % 160, y % 120)
    rec("wallpaper", "tile_set_ms", round(a))
    rec(
        "wallpaper",
        "tile_px",
        {
            f"{x},{y}": (guest_px(g, x, y), ppm_px(ppm, x, y), exp(x, y))
            for x, y in ((790, 590), (5, 5), (300, 250))
        },
    )
    rec("wallpaper", "tile_getwp", get_wp(g))
    # stretch (G3)
    letter, _ = fresh(s)
    a, b, rv, le = set_wp(g, f"{letter}\\SMALL001.BMP", "0", "2", 3)
    ppm = shot(s, "wp_stretch_160x120")
    rec(
        "wallpaper",
        "stretch_px",
        {
            f"{x},{y}": (guest_px(g, x, y), ppm_px(ppm, x, y))
            for x, y in ((790, 590), (5, 5), (400, 300), (100, 100))
        },
    )
    rec("wallpaper", "stretch_getwp", get_wp(g))
    # centre of the small bmp under same registry for comparison
    a, b, rv, le = set_wp(g, f"{letter}\\SMALL001.BMP", "0", "0", 3)
    ppm = shot(s, "wp_center_160x120_after_stretch")
    rec(
        "wallpaper",
        "center_small_px(790,590)",
        (guest_px(g, 790, 590), ppm_px(ppm, 790, 590)),
    )
    # stock desktop + colour change + wallpaper
    letter, _ = fresh(s)
    r, gg, bb = 200, 10, 30
    g.user32.SetSysColors(
        1, struct.pack("<I", 1), struct.pack("<I", r | gg << 8 | bb << 16)
    )
    set_wp(g, f"{letter}\\WALL0002.BMP", "0", "0", 3)
    shot(s, "wp_stock_colour_640x500")
    rec("wallpaper", "stock_windows", top_windows(g))
    rec(
        "wallpaper",
        "stock_shell_visible",
        [g.user32.IsWindowVisible(h).value for h in shell_windows(g)],
    )


def reg_wallpaper(g):
    key = g.advapi32.RegOpenKeyExA(0x80000001, r"Control Panel\Desktop", 0, 1, Out(4))
    hkey = struct.unpack("<I", key.buffers[0])[0]
    r = g.advapi32.RegQueryValueExA(hkey, "Wallpaper", 0, Out(4), Out(260), Out(4))
    g.advapi32.RegCloseKey(hkey)
    return r.value, r.buffers[1].split(b"\0")[0].decode("cp1252")


def sec_getwp(s):
    """G8: SPI_GETDESKWALLPAPER variants after a set; known pixel above the taskbar."""
    g = s.bridge
    for flags in (3, 0):
        letter, _ = fresh(s)
        rec(
            "getwp",
            f"flags{flags}_before_set",
            {"spi": get_wp(g), "registry": reg_wallpaper(g)},
        )
        set_wp(g, f"{letter}\\WALL0001.BMP", "0", "0", flags)
        r = g.user32.SystemParametersInfoA(0x73, 260, Out(260), 0)
        rec(
            "getwp",
            f"flags{flags}_spi_0x73_ret_lasterr",
            (r.value, r.last_error, r.buffers[0][:40].hex()),
        )
        r = g.user32.SystemParametersInfoA(0x73, 0, Out(260), 0)
        rec(
            "getwp",
            f"flags{flags}_spi_0x73_uiParam0",
            (r.value, r.last_error, r.buffers[0][:40].hex()),
        )
        r = g.user32.SystemParametersInfoW(0x73, 260, Out(520), 0)
        rec(
            "getwp",
            f"flags{flags}_spi_0x73_W",
            (r.value, r.last_error, r.buffers[0][:40].hex()),
        )
        rec("getwp", f"flags{flags}_registry_Wallpaper", reg_wallpaper(g))
        ppm = shot(s, f"getwp_flags{flags}")
        rec(
            "getwp",
            f"flags{flags}_px_above_taskbar",
            {
                f"{x},{y}": (guest_px(g, x, y), ppm_px(ppm, x, y), grad(x, y))
                for x, y in ((790, 560), (400, 300), (10, 10))
            },
        )


def sec_blank(s):
    g = s.bridge
    for flags in (3, 0):
        letter, _ = fresh(s)
        blank(g)
        shot(s, f"blank_before_wp_flags{flags}")
        rec("blank", f"flags{flags}_check_before", check_blank(g))
        a, b, _rv, _le = set_wp(g, f"{letter}\\WALL0001.BMP", "0", "0", flags)
        timed("blank", f"flags{flags}_set", a, sync_ms=round(b))
        shot(s, f"blank_after_wp_flags{flags}")
        problems = check_blank(g)
        rec("blank", f"flags{flags}_check_after", problems)
        tb, desk, icons = shell_windows(g)
        rec(
            "blank",
            f"flags{flags}_vis",
            {
                "taskbar": g.user32.IsWindowVisible(tb).value,
                "icons": g.user32.IsWindowVisible(icons).value,
                "taskbar_enabled": g.user32.IsWindowEnabled(tb).value,
                "desk_enabled": g.user32.IsWindowEnabled(desk).value,
            },
        )
        rec("blank", f"flags{flags}_windows", top_windows(g))
        if problems:
            g.user32.ShowWindow(icons, 0)
            g.user32.ShowWindow(tb, 0)
            g.sync()
            rec("blank", f"flags{flags}_after_rehide", check_blank(g))
            shot(s, f"blank_after_rehide_flags{flags}")


def sec_color(s):
    g = s.bridge
    s.revert()
    blank(g)
    r, gg, bb = 200, 10, 30
    cr = r | gg << 8 | bb << 16
    g.user32.SetSysColors(1, struct.pack("<I", 1), struct.pack("<I", cr))
    g.sync()
    ppm = shot(s, "color_blank")
    rec("color", "packed_colorref", hex(cr))
    rec("color", "GetSysColor", hex(g.user32.GetSysColor(1).value))
    rec("color", "px_guest(790,590)", guest_px(g, 790, 590))
    rec("color", "px_screendump(790,590)", ppm_px(ppm, 790, 590))
    # reversed order for contrast
    g.user32.SetSysColors(
        1, struct.pack("<I", 1), struct.pack("<I", bb | gg << 8 | r << 16)
    )
    g.sync()
    rec(
        "color",
        "px_screendump_if_reversed_packing",
        ppm_px(shot(s, "color_blank_rev"), 790, 590),
    )
    s.revert()
    g.user32.SetSysColors(1, struct.pack("<I", 1), struct.pack("<I", cr))
    g.sync()
    shot(s, "color_stock")


def sec_revert(s):
    g = s.bridge
    # (a) WITHOUT eject, 5 runs
    for k in range(5):
        s.revert()
        t_ins = insert(s)
        letter = cd_letter(g)
        ms, n, errs = detect(g, letter)
        block(s)
        t = time.perf_counter()
        try:
            s.vm.load_snapshot("ready")  # no eject
            err = None
        except Exception as e:  # noqa: BLE001
            err = str(e)
        t_rev = (time.perf_counter() - t) * 1000
        try:
            g.ping()
        except Exception as e:  # noqa: BLE001
            err = (err or "") + " ping:" + str(e)
        after = block(s)
        info = {
            "insert_ms": round(t_ins),
            "detect_ms": ms and round(ms),
            "loadvm_ms": round(t_rev),
            "loadvm_err": err,
            "qemu_after_inserted": "inserted" in (after or {}),
            "qemu_tray_open": (after or {}).get("tray_open"),
            "guest_drive_type": g.kernel32.GetDriveTypeA(letter + "\\").value
            if letter
            else None,
        }
        r = g.kernel32.GetFileAttributesA(f"{letter}\\WALL0001.BMP")
        info["guest_sees_file_without_reinsert"] = r.value != 0xFFFFFFFF
        info["last_error"] = r.last_error
        # what if we insert again over the stale medium?
        try:
            t = time.perf_counter()
            insert(s)
            ms2, _n2, errs2 = detect(g, letter, timeout=8)
            info["reinsert_over_stale_detect_ms"] = ms2 and round(ms2)
            info["reinsert_errs"] = errs2
        except Exception as e:  # noqa: BLE001
            info["reinsert_err"] = str(e)
        timed("revert", f"no_eject_run{k}", t_rev, **info)
        if k == 0:
            shot(s, "revert_no_eject_run0")
    # (b) WITH eject, 5 runs, each cycle: insert, detect, eject, loadvm, (next iteration insert)
    s.revert()
    for k in range(5):
        t0 = time.perf_counter()
        i = insert(s)
        letter = cd_letter(g)
        ms, n, errs = detect(g, letter)
        wait = (time.perf_counter() - t0) * 1000
        e = eject(s)
        t = time.perf_counter()
        s.revert()
        r = (time.perf_counter() - t) * 1000
        after = block(s)
        timed(
            "revert",
            f"eject_run{k}",
            wait + e + r,
            insert_ms=round(i),
            detect_ms=ms and round(ms),
            polls=n,
            errs=errs,
            eject_ms=round(e),
            revert_ms=round(r),
            qemu_inserted_after="inserted" in (after or {}),
            tray_open=(after or {}).get("tray_open"),
            guest_letter_after=cd_letter(g),
        )
        # empty tray in guest after revert? file must be gone
        rr = g.kernel32.GetFileAttributesA(f"{letter}\\WALL0001.BMP")
        RES["revert"][f"eject_run{k}"]["guest_file_after_revert"] = (
            rr.value != 0xFFFFFFFF
        )


SECTIONS = {
    "query": sec_query,
    "drive": sec_drive,
    "detect": sec_detect,
    "wallpaper": sec_wallpaper,
    "blank": sec_blank,
    "color": sec_color,
    "getwp": sec_getwp,
    "revert": sec_revert,
}

with stage(work="work", backend="local") as s:
    rec("env", "psi_at_start", psi())
    rec(
        "env",
        "screen",
        (
            s.bridge.user32.GetSystemMetrics(0).value,
            s.bridge.user32.GetSystemMetrics(1).value,
        ),
    )
    rec(
        "env",
        "bpp",
        s.bridge.gdi32.GetDeviceCaps(s.bridge.user32.GetDC(0).value, 12).value,
    )
    for name in WANT:
        try:
            SECTIONS[name](s)
        except Exception:  # keep going; record  # noqa: BLE001
            import traceback

            rec(name, "ERROR", traceback.format_exc()[-800:])
        (OUT / "results.json").write_text(json.dumps(RES, indent=1, default=str))
print("done", OUT)
