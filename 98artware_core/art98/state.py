"""States: hand-written JSON files describing a static starting desktop.

A state is checked completely when it is loaded, before the guest is
touched, so a mistake in the file never leaves a half-made desktop.

    {
      "version": 1,
      "display": [800, 600, 16],
      "windows": [
        {"id": "flower", "app": "picture", "title": "Flower",
         "at": [60, 60], "size": [300, 220], "show": "normal",
         "open": {"file": "assets/flower.bmp", "sha256": "..."}}
      ],
      "pointer": [400, 500]
    }

Windows are listed back to front, so the last one is on top and active.
Anything a state leaves out stays as it is on the baseline. Files are found
relative to the state file, and their hash must match. Unknown fields fail.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .guestfiles import check_bmp

VERSION = 1
APPS = ("picture",)
SHOWS = ("normal", "minimized", "maximized")
DEPTHS = (8, 16, 24, 32)
TOP_FIELDS = {"version", "display", "windows", "pointer"}
WINDOW_FIELDS = {"id", "app", "title", "at", "size", "show", "open"}
FILE_FIELDS = {"file", "sha256"}
LATER = {"desktop": "wallpaper, icons and tray come after the MVP",
         "focus": "the last window is the active one"}


class StateError(ValueError):
    """A state file that can't be used, with every problem found in it."""

    def __init__(self, path: Path | str, problems: list[str]):
        self.path, self.problems = Path(path), problems
        super().__init__(f"{path}:\n" + "\n".join(f"  {p}" for p in problems))


@dataclass(frozen=True)
class FileRef:
    path: Path
    sha256: str
    data: bytes


@dataclass(frozen=True)
class WindowState:
    id: str
    app: str
    title: str
    at: tuple[int, int]
    size: tuple[int, int]
    show: str = "normal"
    open: FileRef | None = None


@dataclass(frozen=True)
class State:
    path: Path
    display: tuple[int, int, int] | None
    windows: tuple[WindowState, ...]
    pointer: tuple[int, int] | None

    def window(self, id: str) -> WindowState:
        for window in self.windows:
            if window.id == id:
                return window
        raise KeyError(f"{self.path} has no window {id!r}")


def _whole_numbers(value, count: int) -> bool:
    return (isinstance(value, list) and len(value) == count
            and all(isinstance(v, int) and not isinstance(v, bool) for v in value))


class _Reader:
    def __init__(self, path: Path):
        self.path, self.base, self.problems = path, path.parent, []

    def fail(self, where: str, message: str) -> None:
        self.problems.append(f"{where}: {message}")

    def fields(self, value, allowed: set[str], where: str) -> bool:
        if not isinstance(value, dict):
            self.fail(where, "should be an object")
            return False
        for key in sorted(set(value) - allowed):
            reason = LATER.get(key)
            self.fail(f"{where}.{key}" if where != "state" else key,
                      f"not supported yet: {reason}" if reason else "unknown field")
        return True

    def numbers(self, value, count: int, where: str, positive: bool = False):
        if not _whole_numbers(value, count):
            self.fail(where, f"needs {count} whole numbers")
            return None
        if positive and any(v <= 0 for v in value):
            self.fail(where, "needs numbers above 0")
            return None
        return tuple(value)

    def file(self, value, where: str) -> FileRef | None:
        if not self.fields(value, FILE_FIELDS, where):
            return None
        name, digest = value.get("file"), value.get("sha256")
        if not isinstance(name, str) or not name:
            self.fail(f"{where}.file", "needs a path, relative to the state file")
            return None
        path = (self.base / name).resolve()
        if not path.is_file():
            self.fail(f"{where}.file", f"{path} doesn't exist")
            return None
        data = path.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        if digest != actual:
            self.fail(f"{where}.sha256", f"should be {actual} for {name}"
                      + ("" if digest is None else f", not {digest}"))
            return None
        return FileRef(path, actual, data)

    def window(self, value, where: str) -> WindowState | None:
        if not self.fields(value, WINDOW_FIELDS, where):
            return None
        problems = len(self.problems)
        id_ = value.get("id")
        if not isinstance(id_, str) or not id_:
            self.fail(f"{where}.id", "needs a name")
        app = value.get("app")
        if app not in APPS:
            self.fail(f"{where}.app", f"should be one of {', '.join(APPS)}, not {app!r}")
        title = value.get("title", "Picture")
        if not isinstance(title, str) or '"' in title:
            self.fail(f"{where}.title", "needs text without double quotes")
        at = self.numbers(value.get("at"), 2, f"{where}.at")
        size = self.numbers(value.get("size"), 2, f"{where}.size", positive=True)
        show = value.get("show", "normal")
        if show not in SHOWS:
            self.fail(f"{where}.show", f"should be one of {', '.join(SHOWS)}, not {show!r}")
        opened = None
        if "open" in value:
            opened = self.file(value["open"], f"{where}.open")
            if opened is not None and app == "picture":
                try:
                    check_bmp(opened.data, str(opened.path))
                except ValueError as error:
                    self.fail(f"{where}.open", str(error))
        if len(self.problems) > problems:
            return None
        return WindowState(id_, app, title, at, size, show, opened)

    def state(self, value) -> State | None:
        if not self.fields(value, TOP_FIELDS, "state"):
            return None
        if value.get("version") != VERSION:
            self.fail("version", f"should be {VERSION}")
        display = None
        if "display" in value:
            display = self.numbers(value["display"], 3, "display", positive=True)
            if display and display[2] not in DEPTHS:
                self.fail("display", f"colour depth should be one of {DEPTHS}")
        windows, seen = [], set()
        raw = value.get("windows", [])
        if not isinstance(raw, list):
            self.fail("windows", "should be a list, back to front")
            raw = []
        for index, item in enumerate(raw):
            window = self.window(item, f"windows[{index}]")
            if window is None:
                continue
            if window.id in seen:
                self.fail(f"windows[{index}].id", f"{window.id!r} is used twice")
            seen.add(window.id)
            windows.append(window)
        pointer = None
        if "pointer" in value:
            pointer = self.numbers(value["pointer"], 2, "pointer")
            if pointer and min(pointer) < 0:
                self.fail("pointer", "should be on the screen")
        if self.problems:
            return None
        return State(self.path, display, tuple(windows), pointer)


def load_state(path: Path | str) -> State:
    """Read and check a state file, or raise StateError listing every problem."""
    path = Path(path).resolve()
    try:
        value = json.loads(path.read_text())
    except FileNotFoundError:
        raise StateError(path, ["the file doesn't exist"]) from None
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise StateError(path, [f"not valid JSON: {error}"]) from None
    reader = _Reader(path)
    state = reader.state(value)
    if state is None:
        raise StateError(path, reader.problems)
    return state
