"""Turn probe_drift.py's JSONL into the README tables.

Run: .venv/bin/python experiments/drift/summarize.py OUTDIR [name ...]   (default: drift, i.e. OUTDIR/drift.jsonl)
Counts per scene and backend: frames audited, frames with a position drift (A), frames whose pixels
differ from a forced full repaint (B), and how many of the runs had any B frame. Not counted as B:
the Notepad caret blinking between the two screendumps (a diff of at most 3x20 px in a scene with a
Notepad) and the taskbar clock ticking (a diff inside the tray, x >= 690, y >= 572).
"""

import functools
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "core" / "tests"))
from drift_check import real_diff as pixel_diff

OUT = Path(sys.argv[1])
BACKENDS = sys.argv[2:] or [
    "drift"
]  # a name N reads OUT/N.jsonl and OUT/diffs-N or OUT/diffs


def pixels(path):
    data = path.read_bytes()
    head, rest = data.split(b"\n255\n", 1)
    return int(head.split()[1]), rest


@functools.cache
def real_diff(backend, scene, run, frame):
    """(count, bbox) of the differing pixels that are not the tray clock (x >= 690, y >= 572, every scene
    but storm's blank desktop shows the taskbar) and not a caret blinking. Read from the saved screendumps."""
    folder = OUT / f"diffs-{backend}"
    if not folder.exists():
        folder = OUT / "diffs"
    stem = folder / f"{scene}-{run}-{frame}"
    w, a = pixels(Path(f"{stem}-a.ppm"))
    _, b = pixels(Path(f"{stem}-b.ppm"))
    return pixel_diff(a, b, w, taskbar=scene != "storm")


def noise(backend, row) -> bool:
    """True when the frame's pixel diff is only the clock or a caret."""
    if not row["b_px"]:
        return True
    row["b_px"], row["b_bbox"] = real_diff(
        backend, row["scene"], row["run"], row["frame"]
    )
    return not row["b_px"]


def load(backend):
    path = OUT / f"{backend}.jsonl"
    return (
        [json.loads(line) for line in path.read_text().splitlines()]
        if path.exists()
        else []
    )


def pct(n, d):
    return f"{n}/{d} ({100 * n / d:.1f}%)" if d else "-"


def table(key):
    print(
        f"\n| {key} | backend | frames | A: frames off | A: runs off | B: frames differ | B: runs differ | B px (max) |"
    )
    print("|---|---|---|---|---|---|---|---|")
    for backend in BACKENDS:
        groups = defaultdict(list)
        for row in load(backend):
            groups[
                row["scene"] if key == "scene" else f"{row['scene']}/{row['phase']}"
            ].append(row)
            if key == "phase" and row["scene"] != "storm":
                groups.pop(f"{row['scene']}/{row['phase']}", None)
        for name, rows in groups.items():
            a = [r for r in rows if r["a_bad"]]
            b = [r for r in rows if r["b_px"] and not noise(backend, r)]
            runs = {r["run"] for r in rows}
            print(
                f"| {name} | {backend} | {len(rows)} | {pct(len(a), len(rows))} | "
                f"{len({r['run'] for r in a})}/{len(runs)} | {pct(len(b), len(rows))} | "
                f"{len({r['run'] for r in b})}/{len(runs)} | {max((r['b_px'] for r in b), default=0)} |"
            )


def who():
    print("\nWhat was off (A: prop and size of the gap; B: bbox first seen)")
    for backend in BACKENDS:
        seen = defaultdict(int)
        for row in load(backend):
            for bad in row["a_bad"]:
                seen[f"{backend} A {row['scene']} {bad['prop']}"] += 1
            if row["b_px"] and not noise(backend, row):
                seen[
                    f"{backend} B {row['scene']}/{row['phase']} bbox {tuple(row['b_bbox'])}"
                ] += 1
        for name, n in sorted(seen.items()):
            print(f"  {n:4d}  {name}")


def cost():
    print(
        "\n| scene | backend | plain sync ms | read-back, per prop ms | forced repaint + sync ms | top-level windows | cpu psi avg10 |"
    )
    print("|---|---|---|---|---|---|---|")
    for backend in BACKENDS:
        groups = defaultdict(list)
        for row in load(backend):
            if "windows" in row:
                groups[row["scene"]].append(row)

        def mp(rows, f):
            v = sorted(f(r) for r in rows if f(r) is not None)
            return (
                f"{statistics.median(v):.1f} / {v[max(0, int(len(v) * 0.95) - 1)]:.1f}"
            )

        for name, rows in groups.items():
            print(
                f"| {name} | {backend} | {mp(rows, lambda r: r['sync_ms'])} | "
                f"{mp(rows, lambda r: r['read_ms'] / r['props'])} | {mp(rows, lambda r: r['repaint_ms'])} | "
                f"{statistics.median(r['windows'] for r in rows):.0f} (max {max(r['windows'] for r in rows)}) | "
                f"{statistics.median(r['psi'] for r in rows):.1f} |"
            )
    print("(each cell: median / p95)")


if __name__ == "__main__":
    table("scene")
    table("phase")
    who()
    cost()
