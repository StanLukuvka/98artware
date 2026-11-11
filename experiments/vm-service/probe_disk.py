"""V8a: N consecutive renders of one short scene; run-copy qcow2 size and time per render.

usage: probe_disk.py OUTDIR [N=30] [KIB=0]  (KIB>0: also put_file KIB of random data on the guest each render, a disk stress;
 a TSV: i, seconds, MiB allocated, MiB apparent, cpu avg10)
"""

import os
import sys
import time
from pathlib import Path

from art98 import service
from art98.anim import render
from common import SETTINGS, Short, cpu, run_copy, sizes

out = Path(sys.argv[1])
n = int(sys.argv[2]) if len(sys.argv) > 2 else 30
kib = int(sys.argv[3]) if len(sys.argv) > 3 else 0
out.mkdir(parents=True, exist_ok=True)
copy = run_copy()
print("run copy:", copy.parent.name)
print("i\tseconds\talloc_MiB\tapparent_MiB\tcpu_avg10")
a, b = sizes(copy)
print(f"0\t-\t{a}\t{b}\t{cpu()}")
for i in range(1, n + 1):
    t0 = time.monotonic()
    with service.attach(SETTINGS) as session:
        if kib:
            session.bridge.put_file(f"C:\\STRESS{i}.BIN", os.urandom(kib * 1024))
        render(Short, out / f"disk-{i:02d}.mp4", session=session)
    seconds = time.monotonic() - t0
    a, b = sizes(copy)
    print(f"{i}\t{seconds:.1f}\t{a}\t{b}\t{cpu()}", flush=True)
