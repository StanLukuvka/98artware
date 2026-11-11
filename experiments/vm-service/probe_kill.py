"""V8b: kill -9 a render mid-call, then attach and render again in a fresh process.

usage: probe_kill.py OUTDIR [ROUNDS=5]
Child mode (internal): probe_kill.py --child OUTFILE
Kill delays (s after the child reports it is attached; the render takes about 1.8 s): spread so the kill lands
before the first frame, mid-typing, mid-wait, mid-close.
"""

import subprocess
import sys
import time
from pathlib import Path

from art98 import service
from art98.anim import render
from common import SETTINGS, Longer, cpu

DELAYS = [0.05, 0.3, 0.6, 0.9, 1.2, 0.15, 0.45, 0.75]


def child(out):
    with service.attach(SETTINGS) as session:
        print("attached", flush=True)
        render(Longer, out, session=session)


def parent(outdir, rounds):
    outdir.mkdir(parents=True, exist_ok=True)
    print(
        "round\tkill_at_s\tkilled\tbusy_wait_s\tping\trender_s\tbytes\tcpu_avg10\tnote"
    )
    for r in range(1, rounds + 1):
        delay = DELAYS[(r - 1) % len(DELAYS)]
        proc = subprocess.Popen(
            [sys.executable, __file__, "--child", str(outdir / f"killed-{r}.mp4")],
            stdout=subprocess.PIPE,
            text=True,
        )
        proc.stdout.readline()  # "attached"
        time.sleep(delay)
        alive = proc.poll() is None
        if alive:
            proc.kill()  # SIGKILL, by PID
        proc.wait()
        note = "" if alive else "child had already finished"
        # Fresh process: attach (waiting briefly for the lock), render, check ping.
        ok = subprocess.run(
            [sys.executable, __file__, "--again", str(outdir / f"after-{r}.mp4")],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        line = (ok.stdout.strip().splitlines() or ["FAIL"])[-1]
        if ok.returncode:
            note += (
                " AGAIN FAILED: " + (ok.stderr.strip().splitlines() or [""])[-1][:200]
            )
        print(f"{r}\t{delay}\t{alive}\t{line}\t{cpu()}\t{note}", flush=True)


def again(out):
    t0 = time.monotonic()
    with service.attach(SETTINGS, wait=15) as session:
        waited = time.monotonic() - t0
        ping = session.bridge.ping()
        t1 = time.monotonic()
        render(Longer, out, session=session)
    print(
        f"{waited:.2f}\t{ping}\t{time.monotonic() - t1:.1f}\t{Path(out).stat().st_size}"
    )


if __name__ == "__main__":
    if sys.argv[1] == "--child":
        child(sys.argv[2])
    elif sys.argv[1] == "--again":
        again(sys.argv[2])
    else:
        parent(Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 5)
