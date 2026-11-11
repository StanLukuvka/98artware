"""Drift audit: does the host's picture of the guest, and the captured frame, match the guest?

Run: . .tools/env.sh; .venv/bin/python experiments/drift/probe_drift.py OUTDIR RUNS [local|container] [scene ...]
(real Docker: env -u DOCKER_HOST sg docker -c '... container')

Scenes: motion drag typing menus storm cmds (default all). Each runs RUNS times on one private
stage, reverting before every run. At EVERY frame of a run the recorder is replaced by one that
 A. compares the host's model (prop rect, pointer) with GetWindowRect / GetCursorPos on the guest;
 B. screendumps the frame, forces a full repaint of every visible top-level window (RDW_REPAINT_ALL,
    then sync), screendumps again and counts the differing pixels.
It also times a plain sync, a read-back of every prop and the forced repaint. One JSON line per frame
goes to OUTDIR/<backend>.jsonl; summarize.py turns that into the README table.
The forced repaint changes the screen, so a stale pixel is counted at the frame that first shows it
and is gone after: later frames then differ only if something new went stale.
No snapshot is saved, no frame is encoded. Keep OUTDIR outside the repo.
"""

import importlib.util
import json
import sys
import time
from pathlib import Path

from art98.actions.window.win import Win
from art98.anim import Maximize, Minimize, Notepad, RestoreWindow, Scene, Teleport
from art98.recorder import Recorder
from art98.session import stage
from art98.win32 import RDW_REPAINT_ALL, cursor_pos, window_rect

OUT = Path(sys.argv[1]).resolve()
RUNS = int(sys.argv[2])
BACKEND = sys.argv[3] if len(sys.argv) > 3 else "local"
ONLY = sys.argv[4:]
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


class Commands(Scene):
    """Maximize, restore, teleport and minimize: Windows moves the window, Python only asks."""

    desktop = "blank"

    def construct(self):
        pad = Notepad(at=(100, 80), size=(320, 220))
        self.add(pad)
        pad.set_text("commands")
        self.pause(0.3)
        for step in (
            Maximize(pad),
            RestoreWindow(pad),
            Teleport(pad, to=(400, 300)),
            Minimize(pad),
            RestoreWindow(pad),
        ):
            self.play(step)
            self.pause(0.3)


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


def ppm(data: bytes):
    head, rest = data.split(b"\n255\n", 1)
    w, h = (int(v) for v in head.split()[1:3])
    return w, h, rest


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


class AuditRecorder(Recorder):
    """Takes no video: at each frame it audits instead of encoding."""

    def __init__(self, session, scene_name, run, sink, keep):
        super().__init__(session, "unused.mp4")
        self.name, self.run, self.sink, self.keep = scene_name, run, sink, keep
        self.scene = None
        self.cuts = 0
        self.index = 0

    def cut(self, path=None):
        self.cuts += 1

    def frame(self, hold=1):
        t = time.perf_counter()
        self._session.bridge.sync()
        self._sync_ms = (time.perf_counter() - t) * 1000
        self._capture(hold, "play")

    def live(self, seconds, stop_condition=None):
        for _ in range(round(seconds * self._fps)):
            if stop_condition is not None and stop_condition():
                return
            time.sleep(1 / self._fps)
            self._sync_ms = None
            self._capture(1, "live")

    def _dump(self, tag):
        path = self._dir / f"{tag}.ppm"
        self._session.vm.screenshot(path, format="ppm")
        return ppm(path.read_bytes())

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
        bad = []
        for prop in scene.props:
            if isinstance(prop, Win) and prop.hwnd is not None:
                real = window_rect(guest, prop.hwnd)
                if real is None:
                    continue
                model = (*prop.rect[:2], *prop.size)
                got = (real[0], real[1], real[2] - real[0], real[3] - real[1])
                if model != got:
                    bad.append(
                        {
                            "prop": type(prop).__name__,
                            "hwnd": prop.hwnd,
                            "model": model,
                            "guest": got,
                        }
                    )
        if scene.pointer is not None:
            want = scene.pointer.get_center().rounded()
            got = cursor_pos(guest)
            if tuple(want) != tuple(got):
                bad.append({"prop": "Pointer", "model": tuple(want), "guest": got})
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
            (self.keep / f"{stem}-a.ppm").write_bytes(
                f"P6\n{w} {h}\n255\n".encode() + a
            )
            (self.keep / f"{stem}-b.ppm").write_bytes(
                f"P6\n{w} {h}\n255\n".encode() + b
            )
        self.sink.write(json.dumps(row) + "\n")
        self.sink.flush()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    keep = OUT / f"diffs-{BACKEND}"
    keep.mkdir(exist_ok=True)
    names = ONLY or list(SCENES)
    print(f"backend {BACKEND} start pressure {psi()}", flush=True)
    with (
        stage("work", backend=BACKEND) as session,
        (OUT / f"{BACKEND}.jsonl").open("a") as sink,
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
