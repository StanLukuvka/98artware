# App catalog

What is on the prepared image, and how each program behaves when driven. Everything here was
probed on the real guest: paths, classes, control ids and quirks. Code blocks use the setup from
[Win32 recipes](win32-recipes.md#setup), and each one ran from the `ready` snapshot.

For the scene props that wrap some of these programs, see the [Scene API](scene-api.md). Notepad is
the first program that is no longer parked: it is `Notepad` in `art98.anim`, and `"app": "notepad"` in a state.
`Dialog`, the message box, is the second, and [its own section](#message-box) is below. It is not in a state.

Sound Recorder is not covered, because audio is deferred.

## Summary

Time is from `spawn` to the first visible window.

| Program | File | Class | Format | Time |
| --- | --- | --- | --- | --- |
| [Notepad](#notepad) | `C:\WINDOWS\NOTEPAD.EXE` | `Notepad` | 32-bit | 0.18 s |
| [Calculator](#calculator) | `C:\WINDOWS\CALC.EXE` | `SciCalc` | 32-bit | 0.17 s |
| [Paint](#paint) | `C:\Program Files\Accessories\MSPAINT.EXE` | `MSPaintApp` | 32-bit | 0.27 s |
| [WordPad](#wordpad) | `C:\Program Files\Accessories\WORDPAD.EXE` | `WordPadClass` | 32-bit | 0.33 s |
| [Minesweeper](#minesweeper) | `C:\WINDOWS\WINMINE.EXE` | `Minesweeper` | 16-bit | 0.05 s |
| [Solitaire](#solitaire) | `C:\WINDOWS\SOL.EXE` | `Solitaire` | 16-bit | 0.09 s |
| [FreeCell](#freecell) | `C:\WINDOWS\FREECELL.EXE` | `FreeWClass` | 16-bit | 0.07 s |
| [Hearts](#hearts) | `C:\WINDOWS\MSHEARTS.EXE` | `AfxFrameOrView` | 16-bit | 0.09 s |
| [Character Map](#character-map) | `C:\WINDOWS\CHARMAP.EXE` | `MyDlgClass` | 16-bit | 0.13 s |
| [Command Prompt](#command-prompt) | `C:\COMMAND.COM` | `tty` | DOS | 0.23 s |
| [Media Player](#media-player) | `C:\Program Files\Windows Media Player\MPLAYER2.EXE` | `Media Player 2` | 32-bit | 0.41 s |
| [Explorer](#others) | `C:\WINDOWS\EXPLORER.EXE` | `ExploreWClass` | 32-bit | 0.67 s |

A new window's position depends on how many opened before it. Windows cascades them by 22 pixels.
The positions below are from one run, so read `rect` rather than rely on them.

A 16-bit program works the same as a 32-bit one for windows, messages and `GetPixel`. The format
comes from each file's header.

## Desktop

| Window | Class | Notes |
| --- | --- | --- |
| Desktop | `Progman` | Title `Program Manager`, 800 x 600. Hiding it uncovers the bare screen. |
| Desktop icons | `SysListView32` in `SHELLDLL_DefView` | 7 icons. See [the recipe](win32-recipes.md#pass-a-struct-to-another-process). |
| Taskbar | `Shell_TrayWnd` | `rect` is `(-2, 572, 802, 602)`. |
| Start button | `Button` in the taskbar | At `(2, 576, 56, 598)`. |
| Task list | `MSTaskSwWClass`, `SysTabControl32` | The buttons for running programs. |
| Clock | `TrayClockWClass` | Its title is the time, such as `9:01 AM`. |
| Start menu | `BaseBar` | Exists only while open. |

There are about 20 top-level windows at the idle desktop. Most are hidden.

The processes are `KERNEL32.DLL`, `MSGSRV32.EXE`, `SPOOL32.EXE`, `MPREXE.EXE`, `mmtask.tsk`,
`EXPLORER.EXE`, `AGENT.EXE` and `SYSTRAY.EXE`. The volume label of `C:` is `ART98`, the user is
`art98` and the computer is `ART98`.

After a display mode change the taskbar's `rect` was still at its old place 0.5 s later.

### Fonts

Character Map lists 34 fonts:

Abadi MT Condensed Light, Arial, Arial Black, Book Antiqua, Calisto MT, Century Gothic, Comic Sans
MS, Copperplate Gothic Bold, Copperplate Gothic Light, Courier, Courier New, Fixedsys, Impact,
Lucida Console, Lucida Handwriting, Lucida Sans, Lucida Sans Unicode, Marlett, Matisse ITC, MS Sans
Serif, MS Serif, News Gothic MT, OCR A Extended, Small Fonts, Symbol, System, Tahoma, Tempus Sans
ITC, Terminal, Times New Roman, Verdana, Webdings, Westminster, Wingdings.

## Notepad

`notepad.exe` or `C:\WINDOWS\NOTEPAD.EXE`. Pass a file to open it.

| Item | Value |
| --- | --- |
| Class | `Notepad` |
| Title | `Untitled - Notepad`, then `<Name> - Notepad` |
| First `rect` | `(68, 66, 668, 477)` |
| Client area | Starts at `rect` + (4, 42), and measures 592 x 365 |
| Child | `Edit`, id 15 |

Menu ids, for `WM_COMMAND`:

| Menu | Items |
| --- | --- |
| File | New 9, Open 10, Save 1, Save As 2, Page Setup 32, Print 14, Exit 28 |
| Edit | Undo 25, Cut 768, Copy 769, Paste 770, Delete 771, Select All 7, Time/Date 12, Word Wrap 27, Set Font 37 |
| Search | Find 3, Find Next 8 |
| Help | Help Topics 5, About 11 |

```python
g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
edit = g.find_window(class_name="Edit", parent=pad.hwnd)
u.SendMessageA(edit.hwnd, WM_SETTEXT, 0, "hello")
assert get_text(edit.hwnd) == "hello"
u.PostMessageA(pad.hwnd, WM_COMMAND, 7, 0)          # Select All
u.PostMessageA(pad.hwnd, WM_COMMAND, 769, 0)        # Copy
g.sync(pad.hwnd)
```

Quirks:

- `WM_CLOSE` on changed text opens a save prompt. Clear it with `EM_SETMODIFY` first, or answer it.
  See [Close a window](win32-recipes.md#close-a-window-answer-the-save-prompt).
- `SetWindowTextA` does not reach the Edit. Use `WM_SETTEXT`.
- Notepad updates its Word Wrap check mark only when the menu opens. So `GetMenuState` shows a stale
  value.
- A new Notepad may not be foreground for about 0.5 s. Real keys sent before that go elsewhere.

## Calculator

`calc.exe` or `C:\WINDOWS\CALC.EXE`.

| Item | Value |
| --- | --- |
| Class | `SciCalc` |
| Title | `Calculator` |
| First `rect` | `(110, 110, 370, 362)` in Standard view |
| Display | `Static`, id 403. Its title is the number, such as `42.` |

Buttons have no text. They are told apart by id.

| Button | Id | Button | Id |
| --- | --- | --- | --- |
| 0 to 9 | 124 to 133 | Backspace | 83 |
| `.` | 85 | CE | 82 |
| `+/-` | 80 | C | 81 |
| `/` | 90 | sqrt | 103 |
| `*` | 91 | `%` | 109 |
| `-` | 93 | `1/x` | 107 |
| `+` | 92 | `=` | 112 |
| MC, MR, MS, M+ | 113, 114, 115, 116 | | |

Post `WM_COMMAND` with the id to the main window, or `BM_CLICK` (`0xF5`) to the button. Both press
it visibly. The display's title gives the result.

```python
g.spawn("calc.exe")
calc = g.find_window(class_name="SciCalc")
for button in (131, 91, 130, 112):                  # 7 * 6 =
    u.PostMessageA(calc.hwnd, WM_COMMAND, button, 0)
g.sync(calc.hwnd)
display = next(c for c in g.windows(calc.hwnd) if u.GetDlgCtrlID(c.hwnd).value == 403)
assert display.title == "42."
```

Menu ids are Copy 300, Paste 301, Scientific 303, Standard 304, Help Topics 305, About 302.

Quirks:

- Changing view makes a new window, so the old `hwnd` becomes invalid. Find it again. Scientific
  view is 480 wide with 74 children.
- There is also a hidden top-level `Edit` window titled `CalcMsgPumpWnd`.
- After `WM_CLOSE` the window goes, but `CALC.EXE` stays in `processes()`, with that hidden window
  still alive. This was still so 2.5 s later. A new `spawn` starts a second process. Kill the old
  one if the process list matters.

## Paint

`"C:\Program Files\Accessories\MSPAINT.EXE"`, with a path to open a BMP. `PBRUSH.EXE` is a stub
that launches this, and its process id differs from what `spawn` returned.

| Item | Value |
| --- | --- |
| Class | `MSPaintApp` |
| Title | `untitled - Paint`, then `<Name> - Paint` |
| First `rect` | `(0, 0, 275, 400)` |
| Canvas view | `Afx:1000000:8` inside `AfxFrameOrView42`, id 59648 |
| Status bar | `msctls_statusbar32`, id 59393 |
| Toolbox | `AfxWnd42`, title `Tools`, id 59415 |
| Palette | `AfxWnd42`, title `Colors`, id 59416 |
| Tool buttons | `ToolChild` |

The canvas view's class name holds a number that could differ, so match on the `Afx:` prefix. The
image's top left pixel is 3 pixels in from the view's corner.

Tool ids, left then right, as they sit in the box:

| Row | Left | Right |
| --- | --- | --- |
| 1 | Free-form select 621 | Select 620 |
| 2 | Eraser 637 | Fill 623 |
| 3 | Pick colour 639 | Magnifier 638 |
| 4 | Pencil 636 | Brush 640 |
| 5 | Airbrush 627 | Text 622 |
| 6 | Line 624 | Curve 628 |
| 7 | Rectangle 641 | Polygon 632 |
| 8 | Ellipse 643 | Rounded rectangle 634 |

Tool buttons take posted mouse clicks, and so does the canvas, in view coordinates. Swatches are 16
pixels apart, and the first is at (40, 16) inside `Colors`. A left click sets the ink and a right
click sets the paper.

Top row: black, gray, maroon, olive, green, teal, navy, purple, khaki, dark teal, azure, steel,
indigo, brown. Second row starts white, silver, red, yellow, lime, cyan, blue, magenta.

```python
g.spawn(r'"C:\Program Files\Accessories\MSPAINT.EXE"')
paint = g.find_window(class_name="MSPaintApp")
time.sleep(0.5)
parts = g.windows(paint.hwnd)
view = next(c for c in parts if c.class_name.startswith("Afx:"))
colors = next(c for c in parts if c.class_name == "AfxWnd42" and c.title == "Colors")
tools = {u.GetDlgCtrlID(c.hwnd).value: c.hwnd for c in parts if c.class_name == "ToolChild"}


def click(hwnd, x, y):
    u.PostMessageA(hwnd, WM_LBUTTONDOWN, 1, lparam(x, y))
    u.PostMessageA(hwnd, WM_LBUTTONUP, 0, lparam(x, y))
    g.sync(paint.hwnd)


click(tools[640], 5, 5)                             # brush
click(colors.hwnd, 40 + 2 * 16, 16 + 16)            # red
u.PostMessageA(view.hwnd, WM_LBUTTONDOWN, 1, lparam(30, 30))
for x in range(30, 150, 5):
    u.PostMessageA(view.hwnd, 0x200, 1, lparam(x, 30))      # WM_MOUSEMOVE, button held
u.PostMessageA(view.hwnd, WM_LBUTTONUP, 0, lparam(150, 30))
g.sync(paint.hwnd)

canvas = u.GetDC(view.hwnd).value
assert gdi.GetPixel(canvas, 60, 30).value == 0x0000FF
u.ReleaseDC(view.hwnd, canvas)
```

Save a picture and read it back. The default canvas here is 400 x 300, at 24 bits.

```python
g.spawn(r'"C:\Program Files\Accessories\MSPAINT.EXE"')
paint = g.find_window(class_name="MSPaintApp")
time.sleep(0.5)
u.PostMessageA(paint.hwnd, WM_COMMAND, 57604, 0)    # Save As
dialog = g.find_window(title="Save As", timeout=4)
name = next(c for c in g.windows(dialog.hwnd) if c.class_name == "Edit")
u.SendMessageA(name.hwnd, WM_SETTEXT, 0, r"C:\ART.BMP")
u.PostMessageA(dialog.hwnd, WM_COMMAND, 1, 0)
time.sleep(0.8)
assert g.get_file(r"C:\ART.BMP")[:2] == b"BM"
```

Open a picture by copying it in. A BMP opens with a canvas of its own size.

```python
import io
from PIL import Image

picture = io.BytesIO()
Image.new("RGB", (64, 48), (200, 30, 30)).save(picture, "BMP")
g.put_file(r"C:\RED.BMP", picture.getvalue())
g.spawn(r'"C:\Program Files\Accessories\MSPAINT.EXE" C:\RED.BMP')
paint = g.find_window(title="Red - Paint")
time.sleep(0.5)
view = next(c for c in g.windows(paint.hwnd) if c.class_name.startswith("Afx:"))
canvas = u.GetDC(view.hwnd).value
assert gdi.GetPixel(canvas, 10, 10).value == 0x2020D0   # snapped to the 16-bit display
u.ReleaseDC(view.hwnd, canvas)
```

Menu ids are New 57600, Open 57601, Save 57603, Save As 57604, Undo 57643, Exit 57665, Tool Box
59415, Color Box 59416, Status Bar 59393.

Quirks:

- It opens small. Resize it before working. The Colors box moves with the window.
- `WM_CLOSE` with changes opens a `#32770` box titled `Paint`, with Yes 6, No 7, Cancel 2.
- Hidden OLE windows appear with it, such as `OleMainThreadWndClass`.
- The canvas size isn't reported anywhere. `art98.anim` measures it with `GetPixel`.

## WordPad

`"C:\Program Files\Accessories\WORDPAD.EXE"`. `WRITE.EXE` is a stub that launches it, and its
process id differs from what `spawn` returned.

| Item | Value |
| --- | --- |
| Class | `WordPadClass` |
| Title | `WordPad` for a moment, then `Document - WordPad` |
| First `rect` | `(0, 0, 600, 411)`, or a cascade position |
| Text | `RichEdit20A`, id 59648 |
| Font box | `ComboBox`, id 165, with 95 entries |
| Size box | `ComboBox`, id 166 |
| Toolbars | `ToolbarWindow32`, ids 59392 and 59396 |
| Ruler | `Afx:1000000:0:14be:10:0`, id 59397 |
| Status bar | `msctls_statusbar32`, id 59393 |

`WM_SETTEXT`, `WM_GETTEXT`, `EM_REPLACESEL` and posted `WM_CHAR` all work.

```python
g.spawn(r'"C:\Program Files\Accessories\WORDPAD.EXE"')
pad = g.find_window(class_name="WordPadClass")
time.sleep(0.5)
text = g.find_window(class_name="RichEdit20A", parent=pad.hwnd)
u.SendMessageA(text.hwnd, WM_SETTEXT, 0, "First")
end = u.SendMessageA(text.hwnd, 0x0E, 0, 0).value   # WM_GETTEXTLENGTH
u.SendMessageA(text.hwnd, EM_SETSEL, end, end)
u.SendMessageA(text.hwnd, EM_REPLACESEL, 1, " second")
assert get_text(text.hwnd) == "First second"
u.SendMessageA(text.hwnd, EM_SETMODIFY, 0, 0)
u.PostMessageA(pad.hwnd, WM_CLOSE, 0, 0)
```

Quirks:

- `EM_SETSEL` with -1, -1 selects everything here, so `EM_REPLACESEL` then replaces the document.
  Use the text length.
- Save As ignores the extension. `C:\DOC.RTF` was written as a Word 6 file by default.
- `AfxControlBar42` titles change between runs. Match toolbars by id.

## Minesweeper

`C:\WINDOWS\WINMINE.EXE`. A 16-bit program with no child windows.

| Item | Value |
| --- | --- |
| Class | `Minesweeper` |
| First `rect` | `(76, 36, 236, 275)` |
| Client area | Starts at `rect` + (3, 41) |
| First cell | Client (12, 55), then 16 pixels each |

| Level | Board | Mines | Client size |
| --- | --- | --- | --- |
| Beginner | 8 x 8 | 10 | 152 or 154 x 195 |
| Intermediate | 16 x 16 | 40 | 280 x 323 |
| Expert | 30 x 16 | 99 | 504 x 323 |

Menu ids are New 510, Beginner 521, Intermediate 522, Expert 523, Custom 524, Marks 527, Color 529,
Best Times 528, Exit 512.

Posted clicks in client coordinates work on the main window. A left click opens a cell, and
`WM_RBUTTONDOWN` (0x204) with `WM_RBUTTONUP` (0x205) flags one.

```python
g.spawn(r"C:\WINDOWS\WINMINE.EXE")
game = g.find_window(class_name="Minesweeper")
u.PostMessageA(game.hwnd, WM_COMMAND, 522, 0)       # Intermediate
time.sleep(0.4)
client = struct.unpack("<4i", u.GetClientRect(game.hwnd, Out(16)).buffers[0])
assert client[2:] == (280, 323)
spot = lparam(20, 63)
u.PostMessageA(game.hwnd, 0x204, 2, spot)
u.PostMessageA(game.hwnd, 0x205, 0, spot)
g.sync(game.hwnd)
```

Quirks:

- Read the mines with the [`XYZZY` cheat](win32-recipes.md#read-minesweepers-mines).
- Each level change moves the window up 2 pixels.
- The game saves to `C:\WINDOWS\WINMINE.INI` when it exits: `Difficulty`, `Height`, `Width`,
  `Mines`, `Mark`, `Color`, `Xpos`, `Ypos`, `Time1` to `Time3`, `Name1` to `Name3`.
- A best time opens a `#32770` box titled `Congratulations`, with Edit 602 and OK 1. Then a `Best
  Times` box follows.
- Cells can be read with `GetPixel` on a client DC. A closed cell is `0xC0C0C0` inside.

## Solitaire

`C:\WINDOWS\SOL.EXE`. 16-bit.

| Item | Value |
| --- | --- |
| Class | `Solitaire` |
| First `rect` | `(22, 22, 619, 456)` or `(0, 0, 597, 434)` |
| Client area | Starts at `rect` + (6, 44), and measures 585 x 384 |
| Child | `Stat`, the status bar with score and time |

Menu ids are Deal 1000, Undo 1001, Deck 1002, Options 1003, Exit 1004, Help Topics 65535, About
2000.

The stock is near client (40, 50). A real click on it draws a card. See
[Deal Solitaire by mouse](win32-recipes.md#deal-solitaire-by-mouse). The Alt+Shift+2 win cheat had no
effect.

## FreeCell

`C:\WINDOWS\FREECELL.EXE`. 16-bit. It opens with no game dealt.

| Item | Value |
| --- | --- |
| Class | `FreeWClass` |
| First `rect` | `(44, 44, 684, 524)` |
| Client size | 632 x 434 |

Menu ids are New Game 102, Select Game 103, Restart 107, Statistics 105, Options 109, Undo 116,
Exit 108, Help Topics 106, About 101.

```python
g.spawn(r"C:\WINDOWS\FREECELL.EXE")
game = g.find_window(class_name="FreeWClass")
u.PostMessageA(game.hwnd, WM_COMMAND, 102, 0)
g.sync(game.hwnd)
```

## Hearts

`C:\WINDOWS\MSHEARTS.EXE`. 16-bit. It starts with a network dialog in front of the game.

| Window | Class | Notes |
| --- | --- | --- |
| Start dialog | `#32770`, title `The Microsoft Hearts Network` | Name is Edit 201. Radio buttons connect 202, dealer 203. OK 1, Quit 2. |
| Game | `AfxFrameOrView`, the same title | `rect` `(66, 66, 606, 546)`, client 534 x 436, child `Afx:0:0:732:0`. |

Menu ids are New Game 102, Options 128, Sound 124, Score 125, Exit 103.

```python
g.spawn(r"C:\WINDOWS\MSHEARTS.EXE")
start = g.find_window(class_name="#32770")
name = g.find_window(class_name="Edit", parent=start.hwnd)
u.SendMessageA(name.hwnd, WM_SETTEXT, 0, "art98")
g.find_window(class_name="AfxFrameOrView")
u.PostMessageA(start.hwnd, WM_COMMAND, 2, 0)        # Quit
```

## Character Map

`C:\WINDOWS\CHARMAP.EXE`. 16-bit.

| Item | Value |
| --- | --- |
| Class | `MyDlgClass` |
| Title | `Character Map` |
| First `rect` | `(14, 54, 553, 281)` |
| Font box | `ComboBox`, id 105, 34 fonts |
| Characters to copy | `Edit`, id 104 |
| Buttons | Close 101, Copy 102, Select 103 |
| Grid | `CharGridWClass`, id 108 |

To change font, select the string and tell the dialog it changed. Copy puts the Edit's text on the
clipboard.

```python
g.spawn(r"C:\WINDOWS\CHARMAP.EXE")
chart = g.find_window(class_name="MyDlgClass")
fonts = next(c for c in g.windows(chart.hwnd) if c.class_name == "ComboBox")
assert u.SendMessageA(fonts.hwnd, 0x14D, -1, "Wingdings").signed >= 0   # CB_SELECTSTRING
u.PostMessageA(chart.hwnd, WM_COMMAND, 105 | 1 << 16, fonts.hwnd)       # CBN_SELCHANGE
g.sync(chart.hwnd)

box = g.find_window(class_name="Edit", parent=chart.hwnd)
u.SendMessageA(box.hwnd, WM_SETTEXT, 0, "abc")
u.PostMessageA(chart.hwnd, WM_COMMAND, 102, 0)      # Copy
g.sync(chart.hwnd)
u.PostMessageA(chart.hwnd, WM_COMMAND, 101, 0)      # Close
```

## Command Prompt

`command.com` or `C:\COMMAND.COM`. Add `/k <command>` to run something and stay, or `/c <command>`
to run and close.

| Item | Value |
| --- | --- |
| Class | `tty` |
| Title | `MS-DOS Prompt` |
| First `rect` | `(22, 22, 594, 381)`, or a cascade position |
| Children | `ttyGrab` id 2, `ToolbarWindow` id 1, `ComboBox` id 3 |
| Process | `C:\WINDOWS\SYSTEM\WINOA386.MOD` |

Only real keys reach it. `WM_CHAR` and `keybd_event` do nothing, and the text inside can't be read
with `WM_GETTEXT`.

```python
g.spawn("command.com")
box = g.find_window(class_name="tty")
time.sleep(1)
u.SetForegroundWindow(box.hwnd)
time.sleep(0.3)
for key in ("d", "i", "r", "ret"):
    vm.send_keys(key)
    time.sleep(0.15)
time.sleep(0.5)
for key in ("e", "x", "i", "t", "ret"):
    vm.send_keys(key)
    time.sleep(0.15)
time.sleep(0.8)
assert not u.IsWindow(box.hwnd)
```

Quirks:

- Output has to go to a file to reach the host. See
  [Run a DOS command](win32-recipes.md#run-a-dos-command).
- `WM_CLOSE` closes it silently.
- Alt+Enter through `vm.send_keys` did not switch to full screen.
- Its process id is that of `WINOA386.MOD`, not `COMMAND.COM`.

## Media Player

`"C:\Program Files\Windows Media Player\MPLAYER2.EXE"`. It plays uncompressed AVI. There are no video
files on the image, so copy one in. See [Video](win32-recipes.md#video).

| Item | Value |
| --- | --- |
| Class | `Media Player 2` |
| Title | `Windows Media Player`, then `<Name> - Windows Media Player` |
| First `rect` | `(280, 196, 574, 625)` |
| Child | `ToolbarClass` |
| Arguments | `/play <file>`, `/close` to exit at the end |
| Time to open a clip | About 2 s |

Menu ids are Open 3009, Close 3022, Exit 3008.

Quirks:

- A 4 s clip played at the right speed. With `/play /close` the player closed 5 s after `spawn`.
- `winmm` MCI plays the same file without the player, in an `AVIWnd` window. The clip's own size
  decides the window.
- The older `C:\WINDOWS\MPLAYER.EXE` opens with a `#32770` prompt, `Media Player settings have been
  changed`, in front of its `MPlayer` window. `WM_CLOSE` does not close it, so end its process.
- Audio is deferred. No clip with sound was tried.

## Message box

`MessageBoxA` from `user32.dll`, class `#32770`. The scene's `Dialog` calls it on a guest thread
with `ACALL`, because it blocks. All boxes are windows of the one agent process, so several can
have the same title.

| Part | Notes |
| --- | --- |
| Icon slot | A `Static` with style `& 0x1F == 3` and id 10 (`0xa`). `STM_SETICON` (`0x170`) with a handle from `shell32.ExtractIconA(0, dll, index)` replaces the picture, then repaint. The static doesn't copy the handle: destroy it only after the box is gone. |
| Text | A `Static` with id `0xffff`. Stock size 111 x 15 at client x 62. It clips to its rectangle, so `MoveWindow` it before `SetWindowTextA` with more lines. |
| Buttons | `Button`. Stock size 75 x 23, 6 apart, 11 above the bottom edge. `EnableWindow(button, 0)` greys one at once. |
| Resize | `SetWindowPos(box, 0, 0, 0, w, h, 0x2 \| 0x4)` changes the frame only. The children stay where they were, and the box grows right and down. |
| Close | Yes/No boxes ignore `WM_CLOSE`. Post `WM_COMMAND` (`0x111`) with 7 (`IDNO`) to close one. |

Icons that were seen in a real box: `shell32.dll` 11 (CD), 13 (globe), 15 (computer), 16 (printer)
in `C:\WINDOWS\SYSTEM`, `main.cpl` 0 (mouse), `modem.cpl` 0 (telephone) and `user.exe` 0
(flag). The full table is in the [Scene API](scene-api.md#dialog). The CD drive is `D:`: see
[Desktop colour and wallpaper](scene-api.md#desktop-colour-and-wallpaper).

## Screensavers

Run a saver with `"<path>" /s`. See [Screensavers](win32-recipes.md#screensavers). All are 32-bit,
with class `WindowsScreenSaverClass`, title `Screen Saver` and a window the size of the screen. All
but the Channel saver exit on mouse movement.

| Saver | File | Size | Notes |
| --- | --- | --- | --- |
| Blank Screen | `C:\WINDOWS\SYSTEM\Blank Screen.scr` | 9.7 KB | Solid black. Nothing moves. |
| Mystify Your Mind | `C:\WINDOWS\SYSTEM\Mystify Your Mind.scr` | 21.5 KB | |
| 3D Maze | `C:\WINDOWS\SYSTEM\3D Maze.scr` | 478 KB | Switches to 640 x 480 while running. |
| Flying Windows | `C:\WINDOWS\SYSTEM\Flying Windows.scr` | 14.8 KB | |
| 3D Flying Objects | `C:\WINDOWS\SYSTEM\3D Flying Objects.scr` | 203 KB | |
| 3D Pipes | `C:\WINDOWS\SYSTEM\3D Pipes.scr` | 161 KB | |
| 3D Text | `C:\WINDOWS\SYSTEM\3D Text.scr` | 121 KB | |
| 3D Flower Box | `C:\WINDOWS\SYSTEM\3D Flower Box.scr` | 94 KB | |
| Flying Through Space | `C:\WINDOWS\SYSTEM\Flying Through Space.scr` | 16.4 KB | Few pixels change: about 35 a second. |
| Curves and Colors | `C:\WINDOWS\SYSTEM\Curves and Colors.scr` | 16.9 KB | |
| Scrolling Marquee | `C:\WINDOWS\SYSTEM\Scrolling Marquee.scr` | 18.9 KB | |
| Channel Screen Saver | `C:\WINDOWS\Channel Screen Saver.SCR` | 92 KB | Mouse movement alone did not close it within 0.6 s. A key press did. |

3D Maze takes about 0.27 s to show its window, and the others less. The agent answers `PING` in
about 5 ms and `SYNC` in 6 to 16 ms while any of them runs.

## Others

Each of these opened on the guest. Beyond that, they have not been explored.

| Program | File | Class | Format |
| --- | --- | --- | --- |
| Explorer | `C:\WINDOWS\EXPLORER.EXE` | `ExploreWClass`, title `Exploring - Art98 (C:)` | 32-bit |
| Registry Editor | `C:\WINDOWS\REGEDIT.EXE` | `RegEdit_RegEdit` | 32-bit |
| File Manager | `C:\WINDOWS\WINFILE.EXE` | `WFS_Frame` | 16-bit |
| Task Manager | `C:\WINDOWS\TASKMAN.EXE` | `MSTaskSwWClass` | 32-bit |

A new Explorer window joins the running shell's process, so its `pid` differs from what `spawn`
returned. `GetMenu` on it returns nothing, because its menu is a toolbar.
