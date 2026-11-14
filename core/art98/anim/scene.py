"""Scene: a script for one recording of the desktop."""

from __future__ import annotations

import time
import warnings
from pathlib import Path

from .. import win32
from ..actions.pointer import Pointer
from ..base.animation import Animation
from ..base.props import Box, Prop
from ..base.space import STOCK, DesktopSpace
from ..base.units import frames
from ..recorder import warn_if_late
from . import setstate

DESKTOPS = ("blank", "stock")

# Only Scene class attributes a scene author sets, whose rename or removal would
# otherwise be silently ignored, go here. It is emptied at each release.
RETIRED = {
    "fps": "renamed to output_fps",
    "clock": "removed: the guest always runs on its own clock",
}


def pin_legacy(cls) -> None:
    """Last resort: refuse a retired setting a scene still defines, rather than
    let it be ignored silently. Never maps an old name onto a new one."""
    for name, why in RETIRED.items():
        if name in vars(cls):
            raise TypeError(f"{cls.__name__}.{name}: {why}")


class Scene:
    """Subclass this and write `construct`.

    `self.guest` is the raw Bridge, so any Win32 call can sit between
    animations, `self.vm` is the VM, and `self.pointer` is the mouse pointer.
    `self.time` is video time, frames written over output_fps, and it never reads a
    clock. `self.recorder` (also `self.video`) writes the frames, and
    `cut()` starts a new clip, and `next_section(name)` does the same with a label. The guest runs
    all the time: what the script drives lands on exact frames, while anything
    the guest times for itself follows the host clock.

    `desktop` is what the scene starts on. "blank", the default, is a black
    screen with no icons or taskbar (see art98.desktop), and no pointer
    unless `pointer_visible` is True. "stock" is the Windows 98 desktop as
    the `ready` snapshot has it, pointer included. Either way it is set again
    after every revert, so `set_state` starts from it too.

    `state`, a path to a state file, sets the desktop before `setup` runs.
    `set_state` jumps to another state at any point, and `prop(id)` is the
    prop for a window the state opened.

    `output_fps` is the finished video's frame rate: set it to match the edit
    timeline (24, 30, 60). It is not a capture or run rate.
    """

    output_fps = 30
    desktop = "blank"
    pointer_visible = False
    state: str | Path | None = None
    strict_placement = (
        False  # True: a clamped size or a lost window raises PlacementError
    )

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        pin_legacy(cls)

    def __init__(self):
        self.session = None
        self.recorder = None
        self.guest = None
        self.vm = None
        self.pointer: Pointer | None = None
        self.props: list[Prop] = []
        self.space: DesktopSpace = STOCK
        self._state_props: dict[str, Prop] = {}
        self.sections: list[tuple[str, float]] = []

    # ---- what a scene writes ----

    def setup(self) -> None:
        pass

    def construct(self) -> None:
        pass

    def tear_down(self) -> None:
        pass

    # ---- running ----

    @property
    def video(self):
        """Another name for `self.recorder`."""
        return self.recorder

    @video.setter
    def video(self, recorder) -> None:
        self.recorder = recorder

    @property
    def time(self) -> float:
        """Video time so far, across every clip."""
        return self.recorder.total / self.output_fps

    def run(self, session, video) -> None:
        """Play this scene on a booted session, into an open recorder."""
        if self.desktop not in DESKTOPS:
            raise ValueError(
                f"desktop {self.desktop!r}: use one of {', '.join(DESKTOPS)}"
            )
        self.session, self.recorder = session, video
        self.sections = []
        self.guest, self.vm = session.bridge, session.vm
        # Every scene starts from the baseline: revert unless nothing has touched
        # the guest since the last revert. Forget whatever an earlier run left.
        if not session.fresh:
            session.revert()
        for prop in self.props:
            prop.forget()
        self.props.clear()
        self._state_props = {}
        self.space = STOCK
        if self.state is not None:
            self.set_state(self.state)  # owns the flag; reverts only if not fresh
        else:
            session.fresh = False  # before the start: a half-done start touched it
            self._start_desktop()
        self.setup()
        self.construct()
        self.tear_down()

    def render(self, output: Path | str | None = None, *, session, **options) -> Path:
        """Play the scene on `session` (see `art98.attach`) and write the video.

        `options` are those of `renderer.render`: gif, keep_clips and so on.
        """
        from .renderer import render

        return render(self, output, session=session, **options)

    # ---- desktop state ----

    def set_state(self, path: Path | str) -> None:
        """Make the desktop look like a state file, all within one frame.

        This is a Set: revert the guest to the snapshot, apply the state, and
        check it took. Props from before are gone, as are their windows. A
        relative path is looked for next to the scene's file, then in the
        current folder. Nothing is recorded, so the next frame shows the state.
        """
        setstate.set_state(self, path)

    def prop(self, window_id: str) -> Prop:
        """The prop for a window the last state opened, by its id."""
        try:
            return self._state_props[window_id]
        except KeyError:
            known = ", ".join(self._state_props) or "none"
            raise KeyError(
                f"no window {window_id!r} in the state (it has {known})"
            ) from None

    def _start_desktop(self) -> None:
        """After a boot or a revert: the desktop the scene asked for, and a new pointer."""
        setstate.start_desktop(self)

    def prepare_desktop(self) -> None:
        """Put the desktop the scene asked for in place, then read the work area."""
        setstate.prepare_desktop(self)

    def calibrate(self) -> None:
        """Read the desktop from the guest again: screen, work area and metrics.
        Call it after a script changes any of them with raw guest calls."""
        self.space = win32.calibrate(self.guest, self.strict_placement)

    @property
    def work_area(self) -> tuple[int, int, int, int]:
        """(left, top, right, bottom) above the taskbar, or the whole screen when blank."""
        return self.space.work_area

    def _find_state(self, path: Path) -> Path:
        return setstate.find_state(self, path)

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

    def play(
        self,
        *animations: Animation,
        run_time: float | None = None,
        rate_func=None,
        live: bool = False,
    ) -> None:
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
        count = max(1, frames(total, self.output_fps))
        live = live or any(animation.live for animation in animations)
        running = list(animations)
        started = time.monotonic()
        for index in range(1, count + 1):
            elapsed = index / count * total
            for animation in list(running):
                length = animation.run_time
                progress = (
                    1.0 if length <= 0 or index == count else min(1.0, elapsed / length)
                )
                animation.update(progress)
                if progress >= 1:
                    animation.finish(self)
                    running.remove(animation)
            self._apply()
            if live:
                time.sleep(
                    max(0.0, started + index / self.output_fps - time.monotonic())
                )
            self.recorder.frame()
        if live:
            warn_if_late(count, self.output_fps, started)

    def wait(
        self, duration: float = 1.0, stop_condition=None, frozen_frame: bool = False
    ) -> None:
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
        self.recorder.frame(hold=max(1, frames(duration, self.output_fps)))

    def live(self, seconds: float, stop_condition=None) -> None:
        """Record something that moves by itself, such as a screensaver.

        Frames follow the host clock and skip the repaint wait, so this
        stretch depends on host speed. It wraps `Recorder.live`.
        """
        self._apply()
        self.recorder.live(seconds, stop_condition)

    def cut(self, path: Path | str | None = None) -> Path | None:
        """End the current clip here and start a new one, between two frames.

        `render` keeps the clips beside the output, as `<stem>-01.mp4` and
        on, and joins them into the output. It wraps `Recorder.cut`.
        """
        return self.recorder.cut(path)

    def next_section(self, name: str) -> Path | None:
        """Start a new section here: end the current clip and begin the next, between two frames.

        A thin wrapper around cut(). `name` labels the section in `self.sections`
        as (name, video time it starts at); clip files stay numbered. Returns the
        closed clip's path, or None when nothing was recorded since the last cut.
        """
        if not isinstance(name, str) or not name.strip():
            raise ValueError("next_section needs a name")
        self.sections.append((name, self.time))
        return self.cut()

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
                    raise ValueError(
                        f"two animations in one play both drive the {claim}"
                    )
                taken.add(claim)
