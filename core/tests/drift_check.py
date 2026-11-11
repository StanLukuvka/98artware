"""The drift checks, shared by the VM tests (test_stage.py) and experiments/drift/probe_drift.py.

A: the host's rect for every window prop, and the pointer, against GetWindowRect / GetCursorPos.
B: the frame against the same moment after a forced full repaint, minus the two things that change
   by themselves (the taskbar clock and a blinking caret).
`AuditRecorder` takes no video: at each frame it audits instead of encoding.
"""

import time
from pathlib import Path

from art98.actions.window.win import Win
from art98.anim import Maximize, Minimize, Notepad, RestoreWindow, Scene, Teleport
from art98.recorder import Recorder
from art98.win32 import RDW_REPAINT_ALL, cursor_pos, window_rect


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


def ppm(data: bytes):
    head, rest = data.split(b"\n255\n", 1)
    w, h = (int(v) for v in head.split()[1:3])
    return w, h, rest


def write_ppm(path: Path, w: int, h: int, pixels: bytes) -> None:
    path.write_bytes(f"P6\n{w} {h}\n255\n".encode() + pixels)


def a_bad(scene, guest) -> list[dict]:
    """Every window prop (and the pointer) whose host model differs from the guest."""
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
        want = tuple(scene.pointer.get_center().rounded())
        got = cursor_pos(guest)
        if want != tuple(got):
            bad.append({"prop": "Pointer", "model": want, "guest": tuple(got)})
    return bad


def real_diff(a: bytes, b: bytes, w: int, taskbar: bool = True):
    """(count, bbox) of the differing pixels that are not the tray clock (x >= 690, y >= 572, when the
    desktop shows the taskbar) and not a caret blinking (a box of at most 3 x 20 px)."""
    xs, ys = [], []
    for y in range(len(a) // (3 * w)):
        if a[y * w * 3 : (y + 1) * w * 3] != b[y * w * 3 : (y + 1) * w * 3]:
            for x in range(w):
                if (
                    a[(y * w + x) * 3 : (y * w + x) * 3 + 3]
                    != b[(y * w + x) * 3 : (y * w + x) * 3 + 3]
                ) and not (taskbar and x >= 690 and y >= 572):
                    xs.append(x)
                    ys.append(y)
    if not xs:
        return 0, None
    box = (min(xs), min(ys), max(xs), max(ys))
    if taskbar and box[2] - box[0] <= 3 and box[3] - box[1] <= 20:
        return 0, None
    return len(xs), box


class AuditRecorder(Recorder):
    """Audits at every frame. `failures` collects a line per drift; with `pixels` it also runs B,
    and a frame that fails B is saved as `<name>-<frame>-a.ppm` / `-b.ppm` in `keep`."""

    def __init__(self, session, name, *, pixels=False, keep=None, taskbar=True):
        super().__init__(session, "unused.mp4")
        self.name, self.pixels, self.keep, self.taskbar = name, pixels, keep, taskbar
        self.scene = None
        self.cuts = 0
        self.index = 0
        self.failures: list[str] = []
        self._sync_ms = None

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

    def _capture(self, hold, kind):
        self.count += hold
        self.total += hold
        self.index += 1
        guest = self._session.bridge
        w, h, a = self._dump("a") if self.pixels else (0, 0, b"")
        for bad in a_bad(self.scene, guest):
            self.failures.append(
                f"A {self.name} frame {self.index}: {bad['prop']} hwnd {bad.get('hwnd')}"
                f" host (x, y, w, h) {bad['model']} != guest {bad['guest']}"
            )
        if not self.pixels:
            return
        # back to front, as win32.repaint_all does: the front window has the last say
        for win in reversed([w_ for w_ in guest.windows() if w_.visible]):
            guest.user32.RedrawWindow(win.hwnd, 0, 0, RDW_REPAINT_ALL)
        guest.sync()
        _, _, b = self._dump("b")
        n, box = real_diff(a, b, w, self.taskbar)
        if n:
            stem = f"{self.name}-{self.index}"
            if self.keep is not None:
                write_ppm(self.keep / f"{stem}-a.ppm", w, h, a)
                write_ppm(self.keep / f"{stem}-b.ppm", w, h, b)
            self.failures.append(
                f"B {self.name} frame {self.index}: {n} px differ from a forced repaint, bbox {box}"
                f" (images: {self.keep / stem if self.keep else 'not saved'}-[ab].ppm)"
            )


def audit(session, scene, name, **options) -> AuditRecorder:
    """Run `scene` on `session` under an AuditRecorder and return it (see `failures`, `index`)."""
    rec = AuditRecorder(session, name, **options)
    rec._fps = scene.fps
    rec.scene = scene
    try:
        scene.run(session, rec)
    finally:
        rec.abort()
    return rec
