"""B4 follow-up: which Edit control state a Set has to restore for a solo section to match.

`--section move` of recipes/scenes/blank_start differed from the full run's clip in two
places in the Notepad: the caret (start of line 2 in the full run, start of line 1 alone) and
the horizontal scroll bar (enabled with a thumb in the full run, disabled alone). The full
run typed its text; the Set sends it with WM_SETTEXT.

Each scene here starts from that capture (render blank_start in full first), changes the
Edit control one way, and holds a few frames. Compare their first frame with the full run's
clip 02.

    uv run art98 render experiments/section-state/probe_edit_state.py SCENE -o OUT.mp4
"""

from pathlib import Path

from art98.anim import Scene

CAPTURE = (
    Path(__file__).resolve().parents[2]
    / "recipes/scenes/blank_start/blank_start.BlankStart.sections/02-move.state.json"
)
EM_GETSEL, EM_SETSEL, EM_REPLACESEL = 0x00B0, 0x00B1, 0x00C2
CARET = len("hello from a blank desktop\r\n")  # where the full run's typing ended


class Base(Scene):
    state = CAPTURE
    pointer_visible = True

    def construct(self):
        note = self.prop("note")
        self.change(note, note.guest.user32, note.edit_hwnd)
        self.pause(0.5)

    def change(self, note, user32, edit):
        pass


class Caret(Base):
    """WM_SETTEXT as now, then the caret put where typing left it."""

    def change(self, note, user32, edit):
        user32.SendMessageA(edit, EM_SETSEL, CARET, CARET)


class Replace(Base):
    """The text sent again as if typed (EM_REPLACESEL), then the caret."""

    def change(self, note, user32, edit):
        text = note.text
        user32.SendMessageA(edit, EM_SETSEL, 0, -1)
        user32.SendMessageA(edit, EM_REPLACESEL, 0, "")
        user32.SendMessageA(edit, EM_REPLACESEL, 0, text)
        user32.SendMessageA(edit, EM_SETSEL, CARET, CARET)


WM_CHAR, VK_BACK = 0x0102, 0x08


class Nudge(Base):
    """Caret as Caret, then one typed character and a backspace (WM_CHAR, like typing)."""

    def change(self, note, user32, edit):
        user32.SendMessageA(edit, EM_SETSEL, CARET, CARET)
        user32.SendMessageA(edit, WM_CHAR, ord("x"), 1)
        user32.SendMessageA(edit, WM_CHAR, VK_BACK, 1)
