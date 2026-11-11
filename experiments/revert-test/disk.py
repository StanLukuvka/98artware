"""Throwaway: is the slow copy and launch the disk path, or a starved CPU?

usage: disk.py <btrfs|shm> <default|unsafe>
"""

import faulthandler
import json
import shutil
import statistics as st
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

faulthandler.dump_traceback_later(100, exit=True)

from art98 import qemu
from art98.session import boot

where, cache = sys.argv[1], sys.argv[2]
PAINT = r'"C:\Program Files\Accessories\MSPAINT.EXE"'
GUEST = r"C:\ART98\P.BMP"


def bmp(w=160, h=120):
    pad = (4 - (w * 3) % 4) % 4
    rows = b"".join(
        bytes(v for x in range(w) for v in (x * 255 // w, y * 255 // h, 128))
        + b"\0" * pad
        for y in range(h)
    )
    return (
        b"BM"
        + struct.pack("<IHHI", 54 + len(rows), 0, 0, 54)
        + struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, len(rows), 2835, 2835, 0, 0)
        + rows
    )


IMG = bmp()

if cache == "unsafe":
    argv = qemu.VMConfig.argv
    qemu.VMConfig.argv = lambda self, q, s: [
        a.replace(",if=ide,", ",if=ide,cache=unsafe,") for a in argv(self, q, s)
    ]

config = json.loads(Path("work/image.json").read_text())
parent = "/dev/shm" if where == "shm" else "work/runs"
stage = Path(tempfile.mkdtemp(prefix="render-", dir=parent))
try:
    disk = stage / Path(config["disk"]).name
    subprocess.run(["cp", "--reflink=auto", config["disk"], str(disk)], check=True)
    config["disk"] = str(disk.resolve())
    (stage / "image.json").write_text(json.dumps(config))

    def tm(fn):
        t = time.perf_counter()
        fn()
        return (time.perf_counter() - t) * 1000

    with boot(stage) as s:
        g, vm = s.bridge, s.vm
        puts, gets, paints = [], [], []
        ping = [tm(g.ping) for _ in range(20)]
        for _ in range(3):
            vm.load_snapshot("ready")
            g.ping()
            puts.append(tm(lambda: g.put_file(GUEST, IMG)))
            gets.append(tm(lambda: g.get_file(GUEST)))
            paints.append(
                tm(lambda: (g.spawn(PAINT), g.find_window(class_name="MSPaintApp")))
            )
    print(
        f"{where:6}{cache:8} ping {st.median(ping):5.1f}  put {st.median(puts):6.0f}  get {st.median(gets):6.0f}  paint {st.median(paints):6.0f}",
        flush=True,
    )
finally:
    shutil.rmtree(stage, ignore_errors=True)
