"""The Windows 98 equivalent of a triangle on screen.

Notepad opens, types a line, drifts across the desktop and closes. The script
draws a frame only when it asks for one, so the video does not depend on how
fast the host happens to run.

    uv run python examples/hello.py
"""

from art98 import boot

FPS = 30
WM_CHAR = 0x0102
WM_CLOSE = 0x0010
EM_SETMODIFY = 0x00B9


def ease(t: float) -> float:
    return t * t * (3 - 2 * t)


with boot("work") as stage, stage.record("hello.mp4", fps=FPS) as video:
    guest = stage.bridge

    guest.spawn("notepad.exe")
    notepad = guest.find_window(class_name="Notepad")
    edit = guest.find_window(class_name="Edit", parent=notepad.hwnd)
    video.frame(hold=FPS // 2)

    for letter in "hello from 1998":
        guest.user32.SendMessageA(edit.hwnd, WM_CHAR, ord(letter), 1)
        video.frame(hold=3)
    video.frame(hold=FPS)

    left, top, _, _ = notepad.rect
    for i in range(2 * FPS):
        t = ease(i / (2 * FPS - 1))
        guest.move_window(notepad.hwnd, int(left + 280 * t), int(top + 120 * t))
        video.frame()
    video.frame(hold=FPS)

    # Mark the text as saved so Notepad closes without asking.
    guest.user32.SendMessageA(edit.hwnd, EM_SETMODIFY, 0, 0)
    guest.user32.PostMessageA(notepad.hwnd, WM_CLOSE, 0, 0)
    video.frame(hold=FPS)
