"""Scene: a script for one recording of the desktop."""

from __future__ import annotations

import inspect
import time
import warnings
from pathlib import Path

from ..desktop import blank, work_area
from ..actions.pointer import Pointer
from ..base.animation import Animation
from ..base.props import DESKTOP_AREA, Box, Prop

DESKTOPS = ("blank", "stock")


class Scene:
    """Subclass this and write `construct`.

    `self.guest` is the raw Bridge, so any Win32 call can sit between
    animations, `self.vm` is the VM, and `self.pointer` is the mouse pointer.
    `self.time` is video time, frames written over fps, and it never reads a
    clock. Only the `free` clock exists so far: the guest runs all the time,
    and what the script drives lands on exact frames while anything the guest
    times for itself runs by the host's clock.

    `desktop` is what the scene starts on. "blank", the default, is a black
    screen with no icons or taskbar (see art98.desktop), and no pointer
    unless `pointer_visible` is True. "stock" is the Windows 98 desktop as
    the `ready` snapshot has it, pointer included. Either way it is set again
    after every revert, so `set_state` starts from it too.

    `state`, a path to a state file, sets the desktop before `setup` runs.
    `set_state` jumps to another state at any point, and `prop(id)` is the
    prop for a window the state opened.
    """

    fps = 30
    clock = "free"
    desktop = "blank"
    pointer_visible = False
    state: str | Path | None = None

    def __init__(self):
        self.session = None
        self.video = None
        self.guest = None
        self.vm = None
        self.pointer: Pointer | None = None
        self.props: list[Prop] = []
        self.work_area = DESKTOP_AREA
        self._state_props: dict[str, Prop] = {}

    # ---- what a scene writes ----

    def setup(self) -> None:
        pass

    def construct(self) -> None:
        pass

    def tear_down(self) -> None:
        pass

    # ---- running ----

    @property
    def time(self) -> float:
        return self.video.count / self.fps

    def run(self, session, video) -> None:
        """Play this scene on a booted session, into an open recorder."""
        if self.clock != "free":
            raise NotImplementedError(f"clock {self.clock!r}: only 'free' exists so far")
        if self.desktop not in DESKTOPS:
            raise ValueError(f"desktop {self.desktop!r}: use one of {', '.join(DESKTOPS)}")
        self.session, self.video = session, video
        self.guest, self.vm = session.bridge, session.vm
        if self.state is not None:
            self.set_state(self.state)
        else:
            self._start_desktop()
        self.setup()
        self.construct()
        self.tear_down()

    def render(self, output: Path | str | None = None, **options) -> Path:
        """Boot a private VM, play the scene, and write the video."""
        from .renderer import render

        return render(self, output, **options)

    # ---- the stage ----

    def set_state(self, path: Path | str) -> None:
        """Make the desktop look like a state file, all within one frame.

        This is a Set: revert the guest to the snapshot, apply the state, and
        check it took. Props from before are gone, as are their windows. A
        relative path is looked for next to the scene's file, then in the
        current folder. Nothing is recorded, so the next frame shows the state.
        """
        from ..state import load_state
        from .setstate import apply_state, check_state

        state = load_state(self._find_state(Path(path)))
        self.session.revert()
        for prop in self.props:
            prop.forget()
        self.props.clear()
        self._state_props = {}
        self._start_desktop()
        props = apply_state(self, state)
        check_state(self, state, props)
        self._state_props = props

    def prop(self, window_id: str) -> Prop:
        """The prop for a window the last state opened, by its id."""
        try:
            return self._state_props[window_id]
        except KeyError:
            known = ", ".join(self._state_props) or "none"
            raise KeyError(f"no window {window_id!r} in the state (it has {known})") from None

    def _start_desktop(self) -> None:
        """After a boot or a revert: the desktop the scene asked for, and a new pointer."""
        self.prepare_desktop()
        self.pointer = Pointer()
        self.pointer.attach(self)

    def prepare_desktop(self) -> None:
        """Put the desktop the scene asked for in place, then read the work area."""
        if self.desktop == "blank":
            blank(self.guest, pointer=self.pointer_visible)
        self.read_work_area()

    def read_work_area(self) -> None:
        """Read the desktop area from the guest: above the taskbar, or the whole
        screen on a blank desktop."""
        self.work_area = work_area(self.guest)

    def _find_state(self, path: Path) -> Path:
        if path.is_absolute():
            return path
        try:
            beside = Path(inspect.getfile(type(self))).resolve().parent / path
        except (TypeError, OSError):
            beside = None
        if beside is not None and beside.exists():
            return beside
        return Path.cwd() / path

    @property
    def screen(self) -> Box:
        """The work area, as a box to measure against."""
        left, top, right, bottom = self.work_area
        return Box(left, top, right - left, bottom - top)

    def add(self, *props: Prop) -> None:
        """Bring props on stage: start the program, find the window, place it."""
        for prop in props:
            if prop not in self.props:
                prop.attach(self)
                self.props.append(prop)

    def remove(self, *props: Prop) -> None:
        """Take props off stage. For a window that means closing it."""
        for prop in props:
            prop.remove()
            if prop in self.props:
                self.props.remove(prop)

    def refresh_props(self) -> None:
        """Read positions back, after something other than the script moved them."""
        for prop in self.props:
            prop.refresh()

    # ---- time ----

    def play(self, *animations: Animation, run_time: float | None = None,
             rate_func=None, live: bool = False) -> None:
        """Run animations together, one captured frame at a time.

        run_time and rate_func override every animation given. Shorter
        animations finish early and hold. With live=True, frames follow the
        host clock, for guest behaviour that needs real time to happen.
        """
        if not animations:
            raise ValueError("play needs at least one animation")
        self._check_claims(animations)
        for animation in animations:
            if run_time is not None:
                animation.run_time = run_time
            if rate_func is not None:
                animation.rate_func = rate_func
            animation.begin(self)
        total = max(animation.run_time for animation in animations)
        count = max(1, round(total * self.fps))
        live = live or any(animation.live for animation in animations)
        running = list(animations)
        started = time.monotonic()
        for index in range(1, count + 1):
            elapsed = index / count * total
            for animation in list(running):
                length = animation.run_time
                progress = 1.0 if length <= 0 or index == count else min(1.0, elapsed / length)
                animation.update(progress)
                if progress >= 1:
                    animation.finish(self)
                    running.remove(animation)
            self._apply()
            if live:
                time.sleep(max(0.0, started + index / self.fps - time.monotonic()))
            self.video.frame()

    def wait(self, duration: float = 1.0, stop_condition=None, frozen_frame: bool = False) -> None:
        """Hold for a while, or until stop_condition() is true.

        The guest keeps running, so a caret blinks and a clock ticks. These
        frames follow the host clock. frozen_frame=True repeats one capture
        instead, which costs almost nothing. See also `pause`.
        """
        if frozen_frame:
            self.pause(duration)
        else:
            self.live(duration, stop_condition)

    def pause(self, duration: float = 1.0) -> None:
        """Hold one capture. Nothing the guest does in this time is seen."""
        self._apply()
        self.video.frame(hold=max(1, round(duration * self.fps)))

    def live(self, seconds: float, stop_condition=None) -> None:
        """Record something that moves by itself, such as a screensaver.

        Frames follow the host clock and skip the repaint wait, so this
        stretch depends on host speed. It wraps `FrameRecorder.live`.
        """
        self._apply()
        self.video.live(seconds, stop_condition)

    def wait_until(self, stop_condition, max_time: float = 60.0) -> None:
        """Hold until stop_condition() is true, giving up after max_time."""
        self.live(max_time, stop_condition)
        if not stop_condition():
            warnings.warn(f"wait_until gave up after {max_time} s", stacklevel=2)

    def _apply(self) -> None:
        self.pointer.apply()
        for prop in self.props:
            prop.apply()

    @staticmethod
    def _check_claims(animations) -> None:
        taken: set[str] = set()
        for animation in animations:
            for claim in animation.claims:
                if claim in taken:
                    raise ValueError(f"two animations in one play both drive the {claim}")
                taken.add(claim)
