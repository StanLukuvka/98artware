"""V8c: does a VNC viewer change the recorded frames? The VM must run with `art98 vm start --vnc`.

usage: probe_vnc.py OUTDIR [PORT=5900]
Renders the Longer scene: none1, none2 (no viewer twice: the noise floor), stay (view-only viewer
requesting updates all through), reconnect (viewer reconnecting every ~0.5 s), none3. For each:
frame count, time, cpu avg10, and the framemd5 of the decoded video (ffmpeg -f framemd5) in OUTDIR.
"""

import signal
import subprocess
import sys
import time
from pathlib import Path

from art98 import service
from art98.anim import render
from common import SETTINGS, Longer, cpu

out = Path(sys.argv[1])
port = sys.argv[2] if len(sys.argv) > 2 else "5900"
out.mkdir(parents=True, exist_ok=True)
VIEWER = Path(__file__).with_name("rfb_viewer.py")


def framemd5(video):
    text = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video), "-f", "framemd5", "-"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [
        line.split(",")[-1].strip()
        for line in text.splitlines()
        if line and line[0] != "#"
    ]


hashes = {}
print("run\tviewer_stats\tframes\tseconds\tcpu_before\tcpu_after")
for tag, mode in [
    ("none1", None),
    ("none2", None),
    ("stay", "stay"),
    ("reconnect", "reconnect"),
    ("none3", None),
]:
    viewer = None
    before = cpu()
    if mode:
        viewer = subprocess.Popen(
            [sys.executable, str(VIEWER), "127.0.0.1", port, mode],
            stdout=subprocess.PIPE,
            text=True,
        )
        time.sleep(1.0)  # let it connect and start requesting
    t0 = time.monotonic()
    with service.attach(SETTINGS) as session:
        render(Longer, out / f"{tag}.mp4", session=session)
    seconds = time.monotonic() - t0
    stats = "-"
    if viewer:
        viewer.send_signal(signal.SIGTERM)  # our own child, by PID
        stats = viewer.communicate(timeout=10)[0].strip()
    hashes[tag] = framemd5(out / f"{tag}.mp4")
    (out / f"{tag}.framemd5").write_text("\n".join(hashes[tag]) + "\n")
    print(
        f"{tag}\t{stats}\t{len(hashes[tag])}\t{seconds:.1f}\t{before}\t{cpu()}",
        flush=True,
    )

base = hashes["none1"]
print("\ncompared with none1: frames differing (by index) / count equal?")
for tag, h in hashes.items():
    diff = [i for i, (a, b) in enumerate(zip(base, h)) if a != b]
    print(
        f"{tag}\tcount_equal={len(h) == len(base)}\tdiffering={len(diff)}\t{diff[:12]}"
    )
