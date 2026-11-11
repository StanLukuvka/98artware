"""M7a: render one scene quiet, then under CPU hogs, with /proc/pressure/cpu next to each timing.

    . .tools/env.sh
    .venv/bin/python experiments/host-checks/busy_check.py OUT_DIR [BUSY_RUNS]

`art98 vm start` must be running: the renders go to the VM service, not a local QEMU.

Hogs are `python3 -c "while True: pass"`, started here by PID and killed by PID
in the `finally` (never pkill). Output goes to OUT_DIR (not the repo).
"""

import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
busy_runs = int(sys.argv[2]) if len(sys.argv) > 2 else 2
SCENE = "examples/blank_start/blank_start.py"
HERE = Path(__file__).parent


def some10() -> float:
    return float(open("/proc/pressure/cpu").read().split()[1].split("=")[1])


def render(name: str) -> dict:
    video, timings = out / f"{name}.mp4", out / f"{name}.json"
    samples, stop = [], threading.Event()

    def sampler():
        while not stop.wait(2):
            samples.append(some10())

    before = some10()
    t = threading.Thread(target=sampler)
    t.start()
    start = time.monotonic()
    p = subprocess.run(  # noqa: PLW1510
        [
            sys.executable,
            str(HERE / "timed_render.py"),
            str(timings),
            "--",
            "render",
            SCENE,
            "--work",
            "work",
            "-o",
            str(video),
        ],
        capture_output=True,
        text=True,
    )
    wall = time.monotonic() - start
    stop.set()
    t.join()
    (out / f"{name}.log").write_text(p.stdout + p.stderr)
    r = {
        "name": name,
        "exit": p.returncode,
        "wall_s": round(wall, 1),
        "psi_before": before,
        "psi_during_min": min(samples, default=None),
        "psi_during_max": max(samples, default=None),
        "psi_during_mean": round(sum(samples) / len(samples), 1) if samples else None,
        "psi_after": some10(),
    }
    if timings.exists():
        tm = json.loads(timings.read_text())
        s = [d for d, _ in tm["sync"]]
        r |= {
            "sync_calls": len(s),
            "sync_max_s": max(s, default=0),
            "sync_total_s": round(sum(s), 2),
            "put_file_s": round(sum(x[2] for x in tm["put_file"]), 2),
            "timeouts": tm["timeouts"],
        }
    print(json.dumps(r), flush=True)
    return r


results, hogs = [], []
try:
    results.append(render("quiet"))
    for _ in range(os.cpu_count() + 8):
        hogs.append(subprocess.Popen([sys.executable, "-c", "while True: pass"]).pid)
    print("hog pids", hogs, flush=True)
    for i in range(busy_runs):
        t0 = time.monotonic()
        while some10() <= 40 and time.monotonic() - t0 < 120:
            time.sleep(2)
        print("psi before busy render", some10(), flush=True)
        results.append(render(f"busy{i + 1}"))
finally:
    for pid in hogs:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    for pid in hogs:
        try:
            os.waitpid(pid, 0)
        except ChildProcessError:
            pass
    left = [pid for pid in hogs if Path(f"/proc/{pid}").exists()]
    print("hogs left:", left, "psi after kill:", some10(), flush=True)
(out / "results.json").write_text(json.dumps(results, indent=1))
