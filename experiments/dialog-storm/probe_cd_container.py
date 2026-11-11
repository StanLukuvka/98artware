"""P3: CD wallpaper route on the container (and local) backend.

    . .tools/env.sh
    .venv/bin/python experiments/dialog-storm/probe_cd_container.py OUTDIR container   # Podman (default DOCKER_HOST)
    env -u DOCKER_HOST sg docker -c '... OUTDIR container'                            # real Docker
    .venv/bin/python experiments/dialog-storm/probe_cd_container.py OUTDIR local

Throwaway probe: no source edits, no savevm, private copy only. Exit 1 if any check fails.
"""
import json
import struct
import sys
import time
from pathlib import Path

from art98.desktop import cd_drive, set_wallpaper, wait_for_disc
from art98.session import stage

OUT = Path(sys.argv[1]).resolve()
BACKEND = sys.argv[2]
OUT.mkdir(parents=True, exist_ok=True)
NAME = "WALL0001.BMP"
TOL = 12
RES: dict = {"fail": []}
T0 = time.perf_counter()


def psi() -> str:
    return Path("/proc/pressure/cpu").read_text().splitlines()[0]


def rec(key, value):
    RES[key] = value
    print(f"[{time.perf_counter() - T0:6.1f}s] {key} = {value}", flush=True)


def check(label, ok, detail=""):
    rec(f"check:{label}", "PASS" if ok else f"FAIL {detail}")
    if not ok:
        RES["fail"].append(label)


def make_bmp(w, h) -> bytes:
    """24-bit BMP: red grows with x, green with y, blue 128."""
    stride = (w * 3 + 3) // 4 * 4
    rows = []
    for y in reversed(range(h)):
        g = y * 255 // (h - 1)
        row = b"".join(bytes((128, g, x * 255 // (w - 1))) for x in range(w))  # BGR
        rows.append(row + bytes(stride - len(row)))
    pix = b"".join(rows)
    return (b"BM" + struct.pack("<IHHI", 54 + len(pix), 0, 0, 54)
            + struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, len(pix), 2835, 2835, 0, 0) + pix)


def ppm_px(path, x, y):
    data = Path(path).read_bytes()
    toks, pos = [], 0
    while len(toks) < 4:
        while data[pos:pos + 1].isspace():
            pos += 1
        end = pos
        while not data[end:end + 1].isspace():
            end += 1
        toks.append(data[pos:end])
        pos = end
    w = int(toks[1])
    i = pos + 1 + (y * w + x) * 3
    return tuple(data[i:i + 3])


def near(a, b):
    return all(abs(p - q) <= TOL for p, q in zip(a, b))


def medium_gone(s) -> bool:
    # RemoteVM has no disc_state(): the guest's own view is the only check on the container
    letter = cd_drive(s.bridge)
    readable = bool(letter) and s.bridge.kernel32.GetFileAttributesA(letter + NAME).value != 0xFFFFFFFF
    return not readable


def main():
    with stage(work="work", backend=BACKEND) as s:
        g = s.bridge
        w, h = g.user32.GetSystemMetrics(0).value, g.user32.GetSystemMetrics(1).value
        rec("screen", (w, h))
        bmp = make_bmp(w, h)
        rec("bmp_bytes", len(bmp))
        pts = [(10, 10), (w // 2, h // 2), (w - 10, h - 60)]  # stay above the taskbar
        exp = lambda x, y: (x * 255 // (w - 1), y * 255 // (h - 1), 128)

        def cycle(tag, style):
            t = time.perf_counter()
            s.attach_disc({NAME: bmp})            # send + insert (first check: no "unknown op")
            t1 = time.perf_counter()
            path = wait_for_disc(g, NAME)
            t2 = time.perf_counter()
            set_wallpaper(g, path, style)
            t3 = time.perf_counter()
            ms = lambda a, b: round((b - a) * 1000)
            RES[f"timing:{tag}"] = {"send_insert": ms(t, t1), "detect": ms(t1, t2), "set": ms(t2, t3),
                                    "total": ms(t, t3), "psi_cpu": psi()}
            rec(f"timing:{tag}", RES[f"timing:{tag}"])
            shot = OUT / f"{BACKEND}_{tag}.ppm"
            s.vm.screenshot(shot, format="ppm")
            s.vm.screenshot(OUT / f"{BACKEND}_{tag}.png")
            for x, y in pts:
                got, want = ppm_px(shot, x, y), exp(x, y)
                check(f"{tag}_px_{x}_{y}", near(got, want), f"got {got} want {want}")

        s.revert()  # start clean: no disc yet, so no eject op is sent
        cycle("center", "center")
        check("medium_readable_before_revert1", not medium_gone(s))
        t = time.perf_counter()
        s.revert()
        rec("revert1_ms", round((time.perf_counter() - t) * 1000))
        check("revert1_medium_gone", medium_gone(s))
        cycle("stretch", "stretch")               # fresh attach after revert 1
        t = time.perf_counter()
        s.revert()
        rec("revert2_ms", round((time.perf_counter() - t) * 1000))
        check("revert2_medium_gone", medium_gone(s))
        cycle("fresh_after_2_reverts", "center")


try:
    main()
except Exception:
    import traceback
    RES["fail"].append("exception")
    rec("EXCEPTION", traceback.format_exc()[-1500:])
(OUT / f"results_{BACKEND}.json").write_text(json.dumps(RES, indent=1, default=str))
print("FAILS:", RES["fail"] or "none")
sys.exit(1 if RES["fail"] else 0)
