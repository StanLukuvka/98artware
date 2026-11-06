"""A tour of Windows 98, driven entirely from the host.

Paint draws a rose with the mouse, Minesweeper is cleared without a wrong
move, and 3D Pipes takes over the screen. Only the screensaver runs on a
wall clock: everything else is drawn when the script asks for a frame.

    uv run python examples/showcase.py
"""

import math
import time

from art98 import boot

FPS = 30

PAINT = r'"C:\Program Files\Accessories\MSPAINT.EXE"'
MINESWEEPER = r"C:\WINDOWS\WINMINE.EXE"
PIPES = r'"C:\WINDOWS\SYSTEM\3D Pipes.scr" /s'

# Paint's layout with its window at PAINT_RECT.
PAINT_RECT = (20, 10, 600, 520)
BRUSH = (65, 139)
BUCKET = (65, 89)
CANVAS_HANDLE = (487, 357)
CANVAS_END = (606, 446)
NAVY = (159, 468)
RED, YELLOW, LIME, CYAN, MAGENTA = [(x, 484) for x in (95, 111, 127, 143, 175)]

ROSE_CENTRE = (345, 250)
ROSE_RADIUS = 178

MINESWEEPER_AT = (630, 150)
BOARD_OFFSET = (15, 96)
CELL = 16
BOARD_SIZE = 8
MINES = 10

MOUSE_LEFT = (0x0002, 0x0004)
MOUSE_RIGHT = (0x0008, 0x0010)
SW_HIDE, SW_SHOWNA = 0, 8
SWP_NOZORDER = 0x0004
BLACK = 0


def ease(t: float) -> float:
    return t * t * (3 - 2 * t)


class Hand:
    """The guest's mouse pointer, moved one video frame at a time."""

    def __init__(self, guest, video, x: int, y: int):
        self.guest, self.video = guest, video
        self.x, self.y = x, y

    def place(self, x: int, y: int) -> None:
        self.x, self.y = x, y
        self.guest.user32.SetCursorPos(x, y)

    def glide(self, x: int, y: int, frames: int = 14) -> None:
        start_x, start_y = self.x, self.y
        for i in range(1, frames + 1):
            t = ease(i / frames)
            self.place(round(start_x + (x - start_x) * t), round(start_y + (y - start_y) * t))
            self.video.frame()

    def press(self, button=MOUSE_LEFT) -> None:
        self.guest.user32.mouse_event(button[0], 0, 0, 0, 0)

    def release(self, button=MOUSE_LEFT) -> None:
        self.guest.user32.mouse_event(button[1], 0, 0, 0, 0)

    def click(self, x: int, y: int, button=MOUSE_LEFT, frames: int = 14) -> None:
        self.glide(x, y, frames)
        self.press(button)
        self.video.frame(hold=2)
        self.release(button)
        self.video.frame(hold=3)


def grow_window(guest, video, hwnd: int, start: tuple, end: tuple, frames: int) -> None:
    for i in range(1, frames + 1):
        t = ease(i / frames)
        x, y, width, height = [round(a + (b - a) * t) for a, b in zip(start, end)]
        guest.user32.SetWindowPos(hwnd, 0, x, y, width, height, SWP_NOZORDER)
        video.frame()


def rose_point(angle: float, scale: float = 1.0) -> tuple[int, int]:
    """Five petals: r = cos(5 angle)."""
    radius = ROSE_RADIUS * scale * math.cos(5 * angle)
    return (
        round(ROSE_CENTRE[0] + radius * math.cos(angle)),
        round(ROSE_CENTRE[1] - radius * math.sin(angle)),
    )


def draw_rose(hand: Hand, frames: int = 6 * FPS, steps_per_frame: int = 4) -> None:
    hand.click(*BRUSH)
    hand.click(*NAVY)
    hand.glide(*rose_point(0))
    hand.press()
    total = frames * steps_per_frame
    for step in range(1, total + 1):
        hand.place(*rose_point(math.pi * ease(step / total)))
        hand.guest.sync()
        if step % steps_per_frame == 0:
            hand.video.frame()
    hand.release()
    hand.video.frame(hold=FPS // 2)


def fill_rose(hand: Hand) -> None:
    hand.click(*BUCKET)
    for petal, colour in enumerate((RED, YELLOW, LIME, CYAN, MAGENTA)):
        hand.click(*colour, frames=10)
        hand.click(*rose_point(petal * math.pi / 5, scale=0.6), frames=12)
    hand.click(*NAVY, frames=10)
    hand.click(120, 80, frames=12)
    hand.video.frame(hold=FPS)


def find_mines(stage, origin: tuple[int, int]) -> set[tuple[int, int]]:
    """Read the board through Minesweeper's own cheat, between video frames.

    After XYZZY and Shift it paints the desktop window's top left pixel black
    over a mine and white elsewhere. Progman would clip that pixel, so it is
    hidden while the pointer visits every cell.
    """
    guest, vm = stage.bridge, stage.vm
    desktop = guest.find_window(class_name="Progman")
    for letter in "xyzzy":
        vm.send_keys(letter)
        time.sleep(0.15)
    vm.send_keys("shift")
    time.sleep(0.2)

    guest.user32.ShowWindow(desktop.hwnd, SW_HIDE)
    guest.sync()
    screen = guest.user32.GetDC(0).value
    mines = set()
    for row in range(BOARD_SIZE):
        for column in range(BOARD_SIZE):
            guest.user32.SetCursorPos(
                origin[0] + column * CELL + CELL // 2, origin[1] + row * CELL + CELL // 2
            )
            guest.sync()
            if guest.gdi32.GetPixel(screen, 0, 0).value & 0xFFFFFF == BLACK:
                mines.add((column, row))
    guest.user32.ReleaseDC(0, screen)
    guest.user32.ShowWindow(desktop.hwnd, SW_SHOWNA)
    guest.sync()
    time.sleep(0.3)

    if len(mines) != MINES:
        raise RuntimeError(f"expected {MINES} mines, read {len(mines)}")
    return mines


def neighbours(cell: tuple[int, int]) -> list[tuple[int, int]]:
    column, row = cell
    return [
        (c, r)
        for c in range(column - 1, column + 2)
        for r in range(row - 1, row + 2)
        if (c, r) != cell and 0 <= c < BOARD_SIZE and 0 <= r < BOARD_SIZE
    ]


def sign_scoreboard(stage, video, name: str = "art98") -> None:
    """Winning a first game always beats the best time, so Minesweeper asks."""
    guest, vm = stage.bridge, stage.vm
    guest.find_window(title="Congratulations")
    video.frame(hold=FPS)
    for key in (*name, "ret"):
        vm.send_keys(key)
        time.sleep(0.15)
        video.frame(hold=5)
    guest.find_window(title="Best Times")
    video.frame(hold=2 * FPS)
    vm.send_keys("ret")
    time.sleep(0.2)
    video.frame(hold=2 * FPS)


def clear_board(hand: Hand, mines: set, origin: tuple[int, int]) -> None:
    """Open the biggest empty area, flag every mine, then finish the rest."""

    def centre(cell):
        return origin[0] + cell[0] * CELL + CELL // 2, origin[1] + cell[1] * CELL + CELL // 2

    def distance(cell):
        x, y = centre(cell)
        return math.hypot(x - hand.x, y - hand.y)

    def opened_by(cell):
        opened, queue = {cell}, [cell]
        while queue:
            current = queue.pop()
            if not mines.intersection(neighbours(current)):
                for near in neighbours(current):
                    if near not in opened:
                        opened.add(near)
                        queue.append(near)
        return opened

    cells = [(c, r) for c in range(BOARD_SIZE) for r in range(BOARD_SIZE)]
    remaining = set(cells) - mines
    first = max(remaining, key=lambda cell: len(opened_by(cell)))
    hand.click(*centre(first), frames=16)
    remaining -= opened_by(first)
    hand.video.frame(hold=FPS // 2)

    flags = set(mines)
    while flags:
        mine = min(flags, key=distance)
        flags.discard(mine)
        hand.click(*centre(mine), button=MOUSE_RIGHT, frames=8)

    while remaining:
        cell = min(remaining, key=distance)
        hand.click(*centre(cell), frames=8)
        remaining -= opened_by(cell)


with boot("work") as stage, stage.record("showcase.mp4", fps=FPS) as video:
    guest = stage.bridge
    hand = Hand(guest, video, 400, 300)
    hand.place(hand.x, hand.y)
    video.frame(hold=FPS)

    guest.spawn(PAINT)
    paint = guest.find_window(class_name="MSPaintApp")
    left, top, right, bottom = paint.rect
    grow_window(guest, video, paint.hwnd, (left, top, right - left, bottom - top), PAINT_RECT, FPS)
    video.frame(hold=FPS // 3)

    hand.glide(*CANVAS_HANDLE, frames=20)
    hand.press()
    hand.glide(*CANVAS_END, frames=20)
    hand.release()
    video.frame(hold=FPS // 3)

    draw_rose(hand)
    fill_rose(hand)

    # The scan happens between two frames, so it never reaches the video.
    guest.spawn(MINESWEEPER)
    mine_window = guest.find_window(class_name="Minesweeper")
    time.sleep(0.5)
    start_left, start_top = mine_window.rect[:2]
    mines = find_mines(stage, (start_left + BOARD_OFFSET[0], start_top + BOARD_OFFSET[1]))
    hand.place(hand.x, hand.y)
    video.frame(hold=FPS // 2)

    end_left, end_top = MINESWEEPER_AT
    for i in range(1, FPS + 1):
        t = ease(i / FPS)
        guest.move_window(
            mine_window.hwnd,
            round(start_left + (end_left - start_left) * t),
            round(start_top + (end_top - start_top) * t),
        )
        video.frame()

    clear_board(hand, mines, (end_left + BOARD_OFFSET[0], end_top + BOARD_OFFSET[1]))
    sign_scoreboard(stage, video)

    guest.spawn(PIPES)
    guest.find_window(class_name="WindowsScreenSaverClass")
    video.live(12)

    hand.place(hand.x + 40, hand.y + 40)
    video.frame(hold=2 * FPS)
