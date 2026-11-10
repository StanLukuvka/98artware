"""Parked: the programs on the image, as props that know their own controls.

Programs are out of the MVP, and each one (Notepad, Paint, Minesweeper, the
screensavers and message boxes) comes back later as its own action class. Until
then this module still works and is tested, but `art98.anim` doesn't export it:
import the classes from `art98.anim.apps`. `PARKED` lists them.
"""

from __future__ import annotations

import math
import time

from ..bridge import BridgeTimeout
from ..actions.keyboard import Keys, TypeKeys
from ..actions.pointer import Click, Drag, RightClick
from ..actions.window.win import Win
from ..base.props import Spot
from ..base.vectors import Vec
from ..win32 import WM_SETTEXT, window_rect

EM_SETMODIFY = 0x00B9
SW_HIDE, SW_SHOWNA = 0, 8
BLACK = 0
PARKED = ("Dialog", "Minesweeper", "Notepad", "Paint", "Screensaver")


class Dialog(Win):
    """A real message box, opened by the agent on a guest thread of its own.

    `button` gives a control to click. `answer` is the button pressed, once
    the box has closed. `icon` is one of Dialog.ICONS and `buttons` one of
    Dialog.BUTTONS.
    """

    window_class = "#32770"
    ICONS = {None: 0, "error": 0x10, "question": 0x20, "warning": 0x30, "info": 0x40}
    BUTTONS = {"ok": 0, "okcancel": 1, "abortretryignore": 2, "yesnocancel": 3,
               "yesno": 4, "retrycancel": 5}
    ANSWERS = {1: "ok", 2: "cancel", 3: "abort", 4: "retry", 5: "ignore", 6: "yes", 7: "no"}

    def __init__(self, text: str, title: str = "art98", *, icon: str | None = None,
                 buttons: str = "ok", at: tuple[int, int] | None = None):
        super().__init__(title, at=at)
        self.message = text
        self.style = self.ICONS[icon] | self.BUTTONS[buttons]
        self._call = None

    def attach(self, scene) -> None:
        self._call = scene.guest.acall(
            "user32", "MessageBoxA", 0, self.message, self.title_text, self.style)
        super().attach(scene)

    def button(self, label: str) -> Win:
        """A button of the box, by its text."""
        return self.control("Button", label)

    @property
    def answer(self) -> str:
        return self.ANSWERS.get(self._call.wait().value, "unknown")


class Notepad(Win):
    """Notepad and its Edit control. Text goes to `edit_hwnd`."""

    command = "notepad.exe"
    window_class = "Notepad"

    def ready(self) -> None:
        self._edit = self.children("Edit")[0].hwnd
        super().ready()

    @property
    def edit_hwnd(self) -> int:
        return self._edit

    @property
    def text(self) -> str:
        return self._read_text(self._edit)

    def set_text(self, text: str) -> None:
        self.guest.user32.SendMessageA(self._edit, WM_SETTEXT, 0, text)

    def close(self) -> None:
        """Close without the save prompt, by marking the text as saved."""
        self.guest.user32.SendMessageA(self._edit, EM_SETMODIFY, 0, 0)
        super().close()


class Paint(Win):
    """Paint, with every button found from the live window.

    `tool` and `color` give targets that are located when an animation begins,
    from the ToolChild buttons and the Colors box, so they stay right after
    the window moves or resizes. Colours are Paint's default palette.
    """

    command = r'"C:\Program Files\Accessories\MSPAINT.EXE"'
    window_class = "MSPaintApp"

    # Control ids of the ToolChild buttons.
    TOOLS = {
        "free_select": 621, "select": 620, "eraser": 637, "fill": 623,
        "pick_color": 639, "magnifier": 638, "pencil": 636, "brush": 640,
        "airbrush": 627, "text": 622, "line": 624, "curve": 628,
        "rectangle": 641, "polygon": 632, "ellipse": 643, "rounded_rectangle": 634,
    }
    PALETTE = (
        ("black", "gray", "maroon", "olive", "green", "teal", "navy", "purple",
         "khaki", "dark_teal", "azure", "steel", "indigo", "brown"),
        ("white", "silver", "red", "yellow", "lime", "cyan", "blue", "magenta",
         "cream", "mint", "sky", "periwinkle", "rose", "orange"),
    )
    SWATCH = 16
    SWATCH_LEFT, SWATCH_TOP = 40, 16  # centre of the first swatch, inside the Colors box
    CANVAS_MARGIN = 3  # between the canvas view's corner and pixel (0, 0)
    WORKSPACE_GREY = 0x808080

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._canvas_size: tuple[int, int] | None = None

    def ready(self) -> None:
        deadline = time.monotonic() + 10
        while True:
            children = self.children()
            buttons = [c for c in children if c.class_name == "ToolChild"]
            if len(buttons) == len(self.TOOLS):
                break
            if time.monotonic() > deadline:
                raise BridgeTimeout(f"Paint showed {len(buttons)} tool buttons")
            time.sleep(0.05)
        ids = {self.guest.user32.GetDlgCtrlID(c.hwnd).value: c.hwnd for c in buttons}
        self._tools = {name: ids[number] for name, number in self.TOOLS.items()}
        self._colors = next(c.hwnd for c in children
                            if c.class_name == "AfxWnd42" and c.title == "Colors")
        self._view = next(c.hwnd for c in children if c.class_name.startswith("Afx:"))
        super().ready()

    def _rect_of(self, hwnd: int) -> tuple[int, int, int, int]:
        return window_rect(self.guest, hwnd)

    def tool(self, name: str) -> Spot:
        """The toolbox button with this name. See `Paint.TOOLS`."""
        if name not in self.TOOLS:
            raise ValueError(f"no tool {name!r}; Paint has {', '.join(self.TOOLS)}")

        def locate():
            left, top, right, bottom = self._rect_of(self._tools[name])
            return (left + right) // 2, (top + bottom) // 2

        return Spot(locate)

    def color(self, name: str) -> Spot:
        """A swatch of the palette. Left click sets ink, right click sets paper."""
        for row, names in enumerate(self.PALETTE):
            if name in names:
                column = names.index(name)
                break
        else:
            raise ValueError(f"no colour {name!r} in Paint's palette")

        def locate():
            left, top, _, _ = self._rect_of(self._colors)
            return (left + self.SWATCH_LEFT + column * self.SWATCH,
                    top + self.SWATCH_TOP + row * self.SWATCH)

        return Spot(locate)

    def canvas(self, x: float, y: float) -> Spot:
        """A pixel of the canvas, as a place on screen."""

        def locate():
            left, top, _, _ = self._rect_of(self._view)
            return left + self.CANVAS_MARGIN + x, top + self.CANVAS_MARGIN + y

        return Spot(locate)

    @property
    def canvas_size(self) -> tuple[int, int]:
        """The canvas in pixels, measured the first time it is needed.

        Paint doesn't report it, so the edge is found with GetPixel between
        the white canvas and the grey workspace. That needs a blank canvas,
        and after `resize_canvas` the new size is simply remembered.
        """
        if self._canvas_size is None:
            self._canvas_size = self._measure_canvas()
        return self._canvas_size

    def _measure_canvas(self) -> tuple[int, int]:
        left, top, right, bottom = self._rect_of(self._view)
        x0, y0 = left + self.CANVAS_MARGIN, top + self.CANVAS_MARGIN
        screen = self.guest.user32.GetDC(0).value

        def in_canvas(x: int, y: int) -> bool:
            colour = self.guest.gdi32.GetPixel(screen, x, y).value & 0xFFFFFF
            return colour != self.WORKSPACE_GREY

        def edge(low: int, high: int, inside) -> int:
            while high - low > 1:
                middle = (low + high) // 2
                low, high = (middle, high) if inside(middle) else (low, middle)
            return low

        # Ten pixels in from the corner, clear of the handles on the edges.
        width = edge(x0 + 4, right, lambda x: in_canvas(x, y0 + 10)) - x0 + 1
        height = edge(y0 + 4, bottom, lambda y: in_canvas(x0 + 10, y)) - y0 + 1
        self.guest.user32.ReleaseDC(0, screen)
        return width, height

    @property
    def canvas_handle(self) -> Spot:
        """The grab handle on the canvas's bottom right corner."""
        return Spot(lambda: self.canvas(self.canvas_size[0] + 1, self.canvas_size[1]).point())

    def resize_canvas(self, width: int, height: int, **kwargs) -> Drag:
        """Drag the corner handle to give the canvas a new size."""
        return _CanvasDrag(self, (width, height), **kwargs)


class _CanvasDrag(Drag):
    def __init__(self, paint: Paint, size: tuple[int, int], **kwargs):
        super().__init__(paint.canvas_handle, paint.canvas(size[0] + 1, size[1]), **kwargs)
        self.paint, self.size = paint, size

    def finish(self, scene) -> None:
        super().finish(scene)
        self.paint._canvas_size = self.size


class Minesweeper(Win):
    """Minesweeper, with the board found from the window's client area."""

    command = r"C:\WINDOWS\WINMINE.EXE"
    window_class = "Minesweeper"

    BOARD_LEFT, BOARD_TOP = 12, 55  # the first cell, in client coordinates
    MARGIN_X, MARGIN_Y = 20, 63  # client area outside the cells
    CELL = 16
    MINES = {(8, 8): 10, (16, 16): 40, (30, 16): 99}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mines: set[tuple[int, int]] = set()

    @property
    def board_size(self) -> tuple[int, int]:
        """Columns and rows, from the size of the client area."""
        width, height = self.client_size()
        return (width - self.MARGIN_X) // self.CELL, (height - self.MARGIN_Y) // self.CELL

    def cell(self, column: int, row: int) -> Spot:
        """The centre of a board cell, as a place on screen."""
        return self.client(self.BOARD_LEFT + column * self.CELL + self.CELL // 2,
                           self.BOARD_TOP + row * self.CELL + self.CELL // 2)

    def find_mines(self) -> set[tuple[int, int]]:
        """Read the board through Minesweeper's own XYZZY cheat.

        After XYZZY and Shift it paints the top left pixel of the screen black
        over a mine and white elsewhere. This happens between two video frames
        and needs no frames of its own. Progman would clip that pixel, so it
        is hidden while the pointer visits every cell. No window may cover
        the top left corner of the screen. The pointer goes back afterwards.
        """
        guest, vm = self.guest, self.scene.vm
        self.activate()
        for letter in "xyzzy":
            vm.send_keys(letter)
            time.sleep(0.15)
        vm.send_keys("shift")
        time.sleep(0.2)

        columns, rows = self.board_size
        desktop = guest.find_window(class_name="Progman")
        guest.user32.ShowWindow(desktop.hwnd, SW_HIDE)
        guest.sync()
        screen = guest.user32.GetDC(0).value
        pointer = self.scene.pointer
        home = pointer.get_center()
        mines = set()
        for row in range(rows):
            for column in range(columns):
                guest.user32.SetCursorPos(*self.cell(column, row).point().rounded())
                guest.sync()
                if guest.gdi32.GetPixel(screen, 0, 0).value & 0xFFFFFF == BLACK:
                    mines.add((column, row))
        guest.user32.ReleaseDC(0, screen)
        guest.user32.ShowWindow(desktop.hwnd, SW_SHOWNA)
        guest.sync()
        guest.user32.SetCursorPos(*Vec(*home).rounded())
        time.sleep(0.3)

        expected = self.MINES.get((columns, rows))
        if expected is not None and len(mines) != expected:
            raise RuntimeError(f"expected {expected} mines, read {len(mines)}")
        self.mines = mines
        return mines

    def neighbours(self, cell: tuple[int, int]) -> list[tuple[int, int]]:
        columns, rows = self.board_size
        return [
            (c, r)
            for c in range(cell[0] - 1, cell[0] + 2)
            for r in range(cell[1] - 1, cell[1] + 2)
            if (c, r) != cell and 0 <= c < columns and 0 <= r < rows
        ]

    def opened_by(self, cell: tuple[int, int]) -> set[tuple[int, int]]:
        """The cells a click opens: all of a flood fill from an empty cell."""
        opened, queue = {cell}, [cell]
        while queue:
            current = queue.pop()
            near = self.neighbours(current)
            if not self.mines.intersection(near):
                for other in near:
                    if other not in opened:
                        opened.add(other)
                        queue.append(other)
        return opened

    def clear(self) -> None:
        """Win the game: open the biggest area, flag every mine, finish the rest.

        Call `find_mines` first. This plays its own animations.
        """
        if not self.mines:
            self.find_mines()
        scene = self.scene
        columns, rows = self.board_size
        cells = {(c, r) for c in range(columns) for r in range(rows)}
        centres = {cell: self.cell(*cell).point() for cell in cells}

        def nearest(group):
            here = scene.pointer.get_center()
            return min(group, key=lambda c: math.hypot(*(centres[c] - here)))

        remaining = cells - self.mines
        first = max(sorted(remaining), key=lambda cell: len(self.opened_by(cell)))
        scene.play(Click(self.cell(*first)))
        remaining -= self.opened_by(first)
        scene.pause(0.5)

        flags = set(self.mines)
        while flags:
            mine = nearest(flags)
            flags.discard(mine)
            scene.play(RightClick(self.cell(*mine), run_time=0.43))
        while remaining:
            cell = nearest(remaining)
            scene.play(Click(self.cell(*cell), run_time=0.43))
            remaining -= self.opened_by(cell)

    def sign_scoreboard(self, name: str = "art98") -> None:
        """Answer the best time prompt that follows a win, and show the table.

        Winning a first game always beats the best time, so the prompt comes up.
        """
        scene = self.scene
        scene.guest.find_window(title="Congratulations")
        scene.pause(1)
        scene.play(TypeKeys(name + "\n", run_time=0.3 * (len(name) + 1)))
        scene.guest.find_window(title="Best Times")
        scene.pause(2)
        scene.play(Keys("enter"))
        scene.pause(1)


class Screensaver(Win):
    """A screensaver, started directly with /s.

    Adding it starts it. Follow with `self.live(seconds)`, because it runs by
    itself. `stop` nudges the pointer, which is how a real one is dismissed.
    """

    window_class = "WindowsScreenSaverClass"
    NAMES = (
        "3D Flower Box", "3D Flying Objects", "3D Maze", "3D Pipes", "3D Text",
        "Blank Screen", "Curves and Colors", "Flying Through Space", "Flying Windows",
        "Mystify Your Mind",
    )

    def __init__(self, name: str = "3D Pipes"):
        if name not in self.NAMES:
            raise ValueError(f"no screensaver {name!r}; the image has {', '.join(self.NAMES)}")
        super().__init__(command=f'"C:\\WINDOWS\\SYSTEM\\{name}.scr" /s')
        self.name = name

    def ready(self) -> None:
        pass  # it paints for ever, so waiting for it to settle would only time out

    def apply(self) -> None:
        pass

    def stop(self, timeout: float = 5.0) -> None:
        """Move the pointer, and wait for the screensaver to end."""
        pointer = self.scene.pointer
        pointer.refresh()
        deadline = time.monotonic() + timeout
        step = 40
        while self.guest.user32.IsWindow(self.hwnd):
            if time.monotonic() > deadline:
                raise BridgeTimeout(f"{self.name} did not stop")
            pointer.place(pointer.get_center() + Vec(step, step))
            step = -step
            time.sleep(0.1)

    def remove(self) -> None:
        self.stop()
