"""Throwaway (T1.4 probe): which frame first shows a pointer on the blank desktop?

Run from the repo root:
    . .tools/env.sh; .venv/bin/python experiments/stray-pointer/probe.py WORK OUT_DIR
WORK is a COPY of a prepared work dir (never this repo's work/, never the VM container's).
Each variant plays a Scene through art98's own Scene.run on a private stage (session.stage),
recording lossless, then ffmpeg decodes the first frames and any non-black pixel is reported
as a bounding box. Crops of the first frame with pixels go to OUT_DIR/crops/.
Other modes: `... WORK OUT_DIR examples` (only the two examples), `... WORK OUT_DIR crops` (re-cut crops).
lazy: pure-Python pixel scan of the first N frames (no numpy installed); fine for N <= 30.
"""

import faulthandler

faulthandler.dump_traceback_later(2400, exit=True)
import subprocess
import sys
import time
from pathlib import Path

from art98.anim import Scene
from art98.session import stage
from art98.win32 import cursor_pos

WORK = Path(sys.argv[1])
OUT = Path(sys.argv[2])
(OUT / "crops").mkdir(parents=True, exist_ok=True)
W, H = 800, 600
NFRAMES = 12
ONLY_EXAMPLES = len(sys.argv) > 3 and sys.argv[3] == "examples"  # skip the idle variants
HERE = Path(__file__).resolve().parents[2]


def psi():
    return open("/proc/pressure/cpu").read().splitlines()[0]


class Idle(Scene):
    desktop = "blank"
    pointer_visible = False
    log = None

    def setup(self):
        self.log = {"cursor_after_attach": cursor_pos(self.guest)}
        self.prep()

    def prep(self):
        pass

    def construct(self):
        self.pause(0.3)


class IdleVisible(Idle):
    pointer_visible = True


class Corner(Idle):
    def prep(self):
        self.pointer.place((799, 599))


class CornerVisible(Corner):
    pointer_visible = True


class Sync(Idle):
    def prep(self):
        self.guest.sync()


class SameSpot(Idle):
    def prep(self):
        self.guest.user32.SetCursorPos(*cursor_pos(self.guest))
        self.guest.sync()


class SameSpotVisible(SameSpot):
    pointer_visible = True


class Own(Idle):
    """A program window under a hidden pointer: does the program's own cursor show?
    Pointer at A for 3 frames, then at B for 3 frames (both over the same part of the window)."""

    exe, cls, A, B = "notepad.exe", "Notepad", (400, 300), (480, 340)

    def setup(self):
        g = self.guest
        g.spawn(self.exe)
        w = g.find_window(class_name=self.cls)
        g.user32.SetWindowPos(w.hwnd, 0, 200, 100, 500, 400, 0x14)
        g.move_window(w.hwnd, 200, 100)
        g.sync()
        self.pointer.place((10, 590))  # park, so frame 0 has the pointer outside the window
        g.sync()

    def construct(self):
        self.pointer.place(self.A)
        self.pause(0.1)
        self.pointer.place(self.B)
        self.pause(0.1)


class OwnPaint(Own):
    exe, cls, A, B = r'"C:\Program Files\Accessories\MSPAINT.EXE"', "MSPaintApp", (400, 300), (480, 340)


def diff_box(fa, fb, region):
    """Bounding box and count of pixels that differ between two frames inside region (x0,y0,x1,y1)."""
    n, box = 0, None
    x0, y0, x1, y1 = region
    for y in range(max(0, y0), min(H, y1)):
        ra, rb = fa[(y * W) * 3 : (y * W + W) * 3], fb[(y * W) * 3 : (y * W + W) * 3]
        if ra == rb:
            continue
        for x in range(max(0, x0), min(W, x1)):
            if ra[x * 3 : x * 3 + 3] != rb[x * 3 : x * 3 + 3]:
                n += 1
                box = [x, y, x, y] if box is None else [min(box[0], x), min(box[1], y), max(box[2], x), max(box[3], y)]
    return n, box


def frames(path, n):
    """First n frames as (w*h*3 bytes) RGB."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-frames:v", str(n),
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        check=True, capture_output=True,
    ).stdout
    size = W * H * 3
    return [raw[i : i + size] for i in range(0, len(raw), size)]


def bbox(frame):
    """(count, [x0, y0, x1, y1]) of non-black pixels, or (0, None)."""
    n, box = 0, None
    for i in range(0, len(frame), 3):
        if frame[i] or frame[i + 1] or frame[i + 2]:
            x, y = i // 3 % W, i // 3 // W
            n += 1
            box = [x, y, x, y] if box is None else [
                min(box[0], x), min(box[1], y), max(box[2], x), max(box[3], y)]
    return n, box


def template(path):
    """The arrow's non-black pixels {(dx, dy): rgb}, from frame 0 of the visible-pointer idle clip."""
    f = frames(path, 1)[0]
    _n, (x0, y0, x1, y1) = bbox(f)
    t = {}
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            px = f[(y * W + x) * 3 : (y * W + x) * 3 + 3]
            if any(px):
                t[(x - x0, y - y0)] = px
    return t


def find_arrow(frame, t):
    """Positions (x0, y0 of the template box) where every non-black template pixel matches exactly."""
    top = min(dy for _dx, dy in t)
    row = sorted((dx, px) for (dx, dy), px in t.items() if dy == top)
    left = row[0][0]
    needle = b"".join(px for _dx, px in row)  # lazy: only the first row's non-black pixels, adjacent
    hits, pos = [], frame.find(needle)
    while pos != -1:
        i = pos // 3
        x, y = i % W - left, i // W - top
        if 0 <= x < W and all(
            0 <= x + dx < W and 0 <= y + dy < H and frame[((y + dy) * W + x + dx) * 3 : ((y + dy) * W + x + dx) * 3 + 3] == px
            for (dx, dy), px in t.items()
        ):
            hits.append((x, y))
        pos = frame.find(needle, pos + 1)
    return hits


def scan(clips, t):
    """Every frame of every clip: where is the arrow? Returns [(clip, first, last, (x, y))] runs."""
    runs = []
    for clip in clips:
        proc = subprocess.Popen(
            ["ffmpeg", "-v", "error", "-i", str(clip), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            stdout=subprocess.PIPE)
        n = 0
        while (f := proc.stdout.read(W * H * 3)) and len(f) == W * H * 3:
            at = find_arrow(f, t)
            key = at[0] if at else None
            if runs and runs[-1][0] == clip.name and runs[-1][3] == key and runs[-1][2] == n - 1:
                runs[-1][2] = n
            else:
                runs.append([clip.name, n, n, key])
            n += 1
        proc.stdout.close(); proc.wait()
    return runs


def crop(path, index, box, name):
    x0, y0, x1, y1 = box
    pad = 6
    x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
    w, h = min(W, x1 + pad + 1) - x0, min(H, y1 + pad + 1) - y0
    out = OUT / "crops" / f"{name}-f{index}.png"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(path), "-vf",
         f"select=eq(n\\,{index}),crop={w}:{h}:{x0}:{y0},scale=iw*8:ih*8:flags=neighbor",
         "-frames:v", "1", str(out)], check=True)
    return out


def run(session, scene, name):
    path = OUT / f"{name}.mkv"
    t = time.perf_counter()
    video = session.record(path, fps=30, lossless=True)
    with video:
        scene.run(session, video)
    secs = time.perf_counter() - t
    if not path.exists():  # a scene that calls cut() writes name-01, name-02, ...
        path = path.with_name(f"{path.stem}-01{path.suffix}")
    fr = frames(path, NFRAMES)
    rows, first = [], None
    for i, f in enumerate(fr):
        n, box = bbox(f)
        rows.append((i, n, box))
        if n and first is None:
            first = i
            crop(path, i, box, name)
    return rows, first, secs, getattr(scene, "log", None)


def report(name, rows, first, secs, log):
    print(f"== {name}  ({secs:.1f}s)  psi {psi()}  log {log}")
    shown = [r for r in rows if r[1]]
    print("  first non-black frame:", first, "| frames with pixels:", [r[0] for r in shown], "of", len(rows))
    for i, n, box in shown[:3]:
        print(f"  frame {i}: {n} px, box {box}")


def save_crops():
    """Crops (8x, nearest) of the frames that show a pointer, from the clips an earlier run left."""
    for name, index, box in (
        ("idle-visible", 0, [401, 302, 408, 317]),  # arrow, pointer_visible=True
        ("own-paint", 1, [400, 294, 406, 300]),  # Paint's own cursor, pointer hidden, at A
        ("own-paint", 4, [480, 334, 486, 340]),  # same, at B
        ("blank_start-01", 0, [401, 542, 408, 557]),  # arrow, pointer_visible=True in the scene
    ):
        print("crop:", crop(OUT / f"{name}.mkv", index, box, name))


if __name__ == "__main__":
    if len(sys.argv) > 3 and sys.argv[3] == "crops":
        save_crops()
        sys.exit()
    print("psi start:", psi())
    variants = [] if ONLY_EXAMPLES else [(n, c) for n, c in [
        ("idle", Idle), ("idle-visible", IdleVisible), ("corner", Corner),
        ("corner-visible", CornerVisible), ("sync", Sync),
        ("samespot", SameSpot), ("samespot-visible", SameSpotVisible)]]
    extra = []
    sys.path.insert(0, str(HERE / "examples" / "blank_start"))
    for label, path, cls in (("blank_start", "examples/blank_start/blank_start.py", "BlankStart"),
                             ("mvp", "examples/mvp/mvp.py", "Mvp")):
        extra.append((label, path, cls))
    for name, cls in variants:
        with stage(WORK) as s:
            report(name, *run(s, cls(), name))
    import importlib.util

    for name, cls in (("own-notepad", Own), ("own-paint", OwnPaint)):
        with stage(WORK) as s:
            scene = cls()
            _rows, _first, secs, _log = run(s, scene, name)
        fr = frames(OUT / f"{name}.mkv", 7)
        print(f"== {name} ({secs:.1f}s) psi {psi()}; {len(fr)} frames; pointer A {cls.A} (frames 0-2), B {cls.B} (frames 3-5)")
        for label, i, j, pt in (("A vs B, near A", 1, 4, cls.A), ("A vs B, near B", 1, 4, cls.B)):
            n, box = diff_box(fr[i], fr[j], (pt[0] - 6, pt[1] - 6, pt[0] + 40, pt[1] + 40))
            print(f"  {label}: frames {i} vs {j}: {n} px differ, box {box}")
        n, box = diff_box(fr[0], fr[1], (0, 0, W, H))
        print(f"  frame 0 vs 1 (pointer parked at (10, 590)): {n} px differ, box {box}")
    tpl = template(OUT / "idle-visible.mkv")
    print("arrow template:", len(tpl), "px, box", max(dx for dx, _ in tpl) + 1, "x", max(dy for _, dy in tpl) + 1)
    for label, path, cls in extra:
        spec = importlib.util.spec_from_file_location(label, HERE / path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[label] = mod  # Scene state paths are found via inspect.getfile
        spec.loader.exec_module(mod)
        scenes = [v for v in vars(mod).values() if isinstance(v, type) and issubclass(v, Scene) and v is not Scene and v.__module__ == label]
        for c in scenes[:1]:
            with stage(WORK) as s:
                report(label, *run(s, c(), label))
            clips = sorted(OUT.glob(f"{label}*.mkv"))
            for r in scan(clips, tpl):
                print(f"  {label} scan: {r[0]} frames {r[1]}-{r[2]}: arrow at {r[3]}")
    print("psi end:", psi())
