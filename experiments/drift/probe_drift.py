"""Drift audit: does the host's picture of the guest, and the captured frame, match the guest?

Run: . .tools/env.sh; .venv/bin/python experiments/drift/probe_drift.py OUTDIR RUNS [scene ...]
Attaches to the running VM service (`art98 vm start`), so the engine is whatever the VM runs in
(real Docker: start the VM with DOCKER_HOST unset, `env -u DOCKER_HOST sg docker -c '...'`). The same
checks run as tests in core/tests/test_stage.py, from core/tests/drift_check.py.

Scenes: motion drag typing menus storm cmds (default all). Each runs RUNS times on one private
stage, reverting before every run. At EVERY frame of a run the recorder is replaced by one that
 A. compares the host's model (prop rect, pointer) with GetWindowRect / GetCursorPos on the guest;
 B. screendumps the frame, forces a full repaint of every visible top-level window (RDW_REPAINT_ALL,
    then sync), screendumps again and counts the differing pixels.
It also times a plain sync, a read-back of every prop and the forced repaint. One JSON line per frame
goes to OUTDIR/drift.jsonl; summarize.py turns that into the README table.
The forced repaint changes the screen, so a stale pixel is counted at the frame that first shows it
and is gone after: later frames then differ only if something new went stale.
No snapshot is saved, no frame is encoded. Keep OUTDIR outside the repo.
"""

import importlib.util
import json
import sys
import time
from pathlib import Path

from art98 import service
from art98.actions.window.win import Win
from art98.settings import load as load_settings
from art98.win32 import RDW_REPAINT_ALL

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "core" / "tests"))
import drift_check
from drift_check import Commands, a_bad, write_ppm

OUT = Path(sys.argv[1]).resolve()
RUNS = int(sys.argv[2])
ONLY = sys.argv[3:]
ROOT = Path(__file__).resolve().parents[2]
SCENES = {  # name -> (file, class, fps override or None)
    "motion": ("examples/gallery/window_motion.py", "WindowMotion", 10),
    "drag": ("examples/gallery/drag_window.py", "DragWindow", 10),
    "typing": ("examples/gallery/typing.py", "Typing", 10),
    "menus": ("examples/gallery/menus_keys.py", "MenusKeys", 10),
    "storm": ("examples/dialog_storm/dialog_storm.py", "DialogStorm", None),
    "cmds": (None, "Commands", 10),
}
STORM_PHASES = [
    "cascade",
    "pair",
    "typing",
    "colour",
]  # DialogStorm's sections; "wallpaper" after the cut


def psi() -> float:
    return float(
        Path("/proc/pressure/cpu").read_text().splitlines()[0].split()[1].split("=")[1]
    )


def load(name):
    file, cls, fps = SCENES[name]
    if file is None:
        scene = Commands()
        scene.fps = fps
        return scene
    spec = importlib.util.spec_from_file_location(f"drift_{name}", ROOT / file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    scene = getattr(module, cls)()
    if fps:
        scene.fps = fps
    return scene


def diff(a: bytes, b: bytes, w: int):
    """(count, bbox) of the pixels that differ."""
    if a == b:
        return 0, None
    xs, ys, n = [], [], 0
    for y in range(len(a) // (3 * w)):
        ra, rb = a[y * w * 3 : (y + 1) * w * 3], b[y * w * 3 : (y + 1) * w * 3]
        if ra != rb:
            for x in range(w):
                if ra[x * 3 : x * 3 + 3] != rb[x * 3 : x * 3 + 3]:
                    n += 1
                    xs.append(x)
                    ys.append(y)
    return n, (min(xs), min(ys), max(xs), max(ys))


class AuditRecorder(drift_check.AuditRecorder):
    """Takes no video: at each frame it audits and times instead of encoding."""

    def __init__(self, session, scene_name, run, sink, keep):
        super().__init__(session, scene_name)
        self.run, self.sink, self.keep = run, sink, keep

    def _phase(self):
        scene = self.scene
        if self.name != "storm":
            return ""
        n = len(scene.sections)
        return STORM_PHASES[n] if self.cuts == n else "wallpaper"

    def _capture(self, hold, kind):
        scene, guest = self.scene, self._session.bridge
        self.count += hold
        self.total += hold
        self.index += 1
        row = {
            "scene": self.name,
            "run": self.run,
            "frame": self.index,
            "kind": kind,
            "phase": self._phase(),
            "psi": psi(),
            "sync_ms": self._sync_ms,
        }
        w, h, a = self._dump("a")
        # A: model vs guest
        t = time.perf_counter()
        bad = a_bad(scene, guest)
        row["read_ms"] = (time.perf_counter() - t) * 1000
        row["props"] = (
            sum(isinstance(p, Win) and p.hwnd is not None for p in scene.props) + 1
        )
        row["a_bad"] = bad
        # B: the same moment after a forced full repaint
        t = time.perf_counter()
        # back to front: Windows 98 draws a covered window's caption text over the window in front of it
        # (RDW_FRAME), so repainting the front window last keeps that out of the comparison
        shown = [win for win in reversed(guest.windows()) if win.visible]
        for win in shown:
            guest.user32.RedrawWindow(win.hwnd, 0, 0, RDW_REPAINT_ALL)
        row["windows"] = len(shown)
        guest.sync()
        row["repaint_ms"] = (time.perf_counter() - t) * 1000
        _, _, b = self._dump("b")
        n, box = diff(a, b, w)
        row["b_px"], row["b_bbox"] = n, box
        # a caret (or other blinker) that moved between the two dumps is not a stale pixel
        row["b_blink"] = bool(box) and box[2] - box[0] <= 3 and box[3] - box[1] <= 20
        if n and self.keep is not None:
            stem = f"{self.name}-{self.run}-{self.index}"
            write_ppm(self.keep / f"{stem}-a.ppm", w, h, a)
            write_ppm(self.keep / f"{stem}-b.ppm", w, h, b)
        self.sink.write(json.dumps(row) + "\n")
        self.sink.flush()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    keep = OUT / "diffs"
    keep.mkdir(exist_ok=True)
    names = ONLY or list(SCENES)
    print(f"start pressure {psi()}", flush=True)
    with (
        service.attach(load_settings()) as session,
        (OUT / "drift.jsonl").open("a") as sink,
    ):
        for name in names:
            for run in range(RUNS):
                session.revert()
                scene = load(name)
                rec = AuditRecorder(session, name, run, sink, keep)
                rec._fps = scene.fps
                rec.scene = scene
                scene.session, scene.recorder = session, rec
                t = time.perf_counter()
                try:
                    scene.run(session, rec)
                except Exception as error:  # keep auditing the next run  # noqa: BLE001
                    print(f"{name} run {run} FAILED: {error!r}", flush=True)
                rec.abort()
                print(
                    f"{name} run {run}: {rec.index} frames in {time.perf_counter() - t:.0f}s pressure {psi()}",
                    flush=True,
                )


if __name__ == "__main__":
    main()
