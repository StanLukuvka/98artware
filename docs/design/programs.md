# Programs

A program is a Windows program art98 can open, drive and film: Notepad, the picture window, the
message box (`Dialog`), Paint, Minesweeper and the screensaver. This page says how one is built and
how to add the next. It is read from the code of `Picture`, `Notepad` and `Dialog`; the others
follow the same shape. The state file itself is described in
the [state and action design](state-and-action.md).

## What a program class is

One Python class per program. It starts the program on the guest, finds its window, and holds the
verbs that drive it (`text`, `set_text`, `close`). A scene adds it as a prop, and a state file names
it with `app`.

## Where it lives

The layers are Action, then Window, then programs.

| Layer | Path | What it is |
| --- | --- | --- |
| Action | `core/art98/actions/` | The base: anything the scene can do on screen. |
| Window | `core/art98/actions/window/win.py` | `Win`: start a command, find the window, move, size, close. |
| Programs | `core/art98/actions/programs/` | One file per stock Windows program, `notepad.py`, `paint.py`, `minesweeper.py`, `screensaver.py` and `dialog.py`. |
| art98's own | `core/art98/actions/window/picture.py` | `Picture`, the window for VIEW.EXE. |

A program is one file, or one folder once it needs more than one. Docs, outputs and experiments stay
out of these folders.

## The state hooks

These matter only for a program that can appear in a state file (today `picture` and `notepad`). A scene-only program, such as `Dialog`, needs none of them.

| Hook | Where | What it does |
| --- | --- | --- |
| `from_state(window)` | the class | Builds the prop from one parsed window of a state file. |
| `APPS` | `core/art98/anim/setstate.py` | The one list: `{"picture": Picture, "notepad": Notepad}`. A state's `app` must be a key. |
| title rule | `core/art98/state.py` | The exact title-bar text, used as the default `title` and checked after Set. |

`state.programs()` reads `APPS`, so adding a key there makes the name valid in a state file.

**The title rule.** After Set, the guest's window title must equal the state's `title` exactly.
When the state gives none, `state.py` fills in a default.

| Program | Default title |
| --- | --- |
| `picture` | `Picture` |
| `notepad` | `<file name without .txt> - Notepad`, or `Untitled - Notepad` with no file |
| `dialog` | Not in `APPS`, so it is not in a state and has no title rule. Its title is the one you give it |

The Notepad rule is the function `notepad_title(file)` in `notepad.py`. Confirmed on the real image: Windows 98 Notepad drops a trailing `.txt`
(any case) and keeps other extensions and the case, so `note.txt` shows as
`note - Notepad` and `x.log` as `x.log - Notepad`.

## Dialog

`Dialog` (`actions/programs/dialog.py`) is a program of a different kind: Windows draws the box
itself, from a `MessageBoxA` call on a guest thread of the agent. It has no command line and no
file, so it has no `from_state`. A scene adds it in `construct`. It takes an `icon` (stock, one of
seven custom icons, or a `(dll, index)` pair), `buttons`, `size`, `disabled` and `set_message`.
The options are in the [Scene API](../scenes/scene-api.md#dialog), and the probes behind them are
in [experiments/dialog-storm](https://github.com/StanLukuvka/98artware/blob/dev/experiments/dialog-storm/README-p1.md).

Two things are worth knowing if you build a program like it. Every box is a window of the same
class (`#32770`) from the same process, so a title can't say which box is yours: `Dialog` notes
the windows that exist before its call and takes only a new one. And Windows draws the icon
slot's picture from a handle, which the slot doesn't copy, so the handle is destroyed only when
the box is removed.

## Picture

`VIEW.EXE` (`guest/picture_viewer/view.c`, 4 KB) takes
`VIEW.EXE <x> <y> <width> <height> "<title>" ["<image.bmp>"]`. Each window is its own process, of
class `Art98View`, with a normal frame and a taskbar button. An image bigger than the window is
cropped. If the viewer crashes anyway, `Picture` sees Windows' crash dialog and fails at once
instead of waiting 15 s. Why art98 has its own viewer:
[decision 11](decisions.md#11-a-picture-viewer-of-art98s-own). The options are in the
[Scene API](../scenes/scene-api.md#picture).

## What `app` and `open` mean

| `app` | `open` is | Without `open` |
| --- | --- | --- |
| `picture` | a BMP, checked by `check_bmp` | an empty window |
| `notepad` | a text file, checked by `check_text` | `Untitled - Notepad` |

`open` is `{"file": "...", "sha256": "..."}`. The file sits beside the state and is referenced by
path and hash. A wrong hash fails the load.

## How files reach the guest

`guestfiles.ensure(guest, data, name)` copies the bytes to `C:\ART98\F<7 hex>\<name>`, where the
folder name is the start of the content hash. If that path exists already, nothing is copied. A
revert throws away everything copied since the baseline, so `attach()` calls `ensure` every time
the prop is added.

- `Notepad.attach` copies the text and starts `notepad.exe "<path>"`.
- `Picture.attach` copies VIEW.EXE and the BMP, then starts VIEW.EXE with the position, size, title
  and image path.

## Adding a program

The steps are in [CONTRIBUTING.md](../../CONTRIBUTING.md#adding-a-program): write the class on
`Win`, export it from `actions/programs/__init__.py` and `anim/__init__.py`, document it in the
[Scene API](../scenes/scene-api.md), and test it. `from_state` and `APPS` are optional: add them,
plus the default title and file check in `state.py`, only if the program should be nameable with
`app` in a state file. In `attach()`, copy any file with `guestfiles.ensure` and put the guest path
in `command`.

Does the program need a guest change?

| Program | Guest change | After it |
| --- | --- | --- |
| Stock Windows (`notepad.exe`, `mspaint.exe`) | None. | Nothing to rebuild. |
| art98's own (VIEW.EXE) | Edit the C source in `guest/`. | `make -C guest`, then `art98 up --rebuild` so the container image holds the new build. |

## Worked example: Notepad

A state with one Notepad window:

```json
{
  "version": 1,
  "windows": [
    {
      "id": "note",
      "app": "notepad",
      "at": [320, 140],
      "size": [420, 260],
      "open": {"file": "assets/note.txt", "sha256": "..."}
    }
  ]
}
```

Set does this:

1. The state loads. `app` is in `APPS`. `check_text` runs on `note.txt`. With no `title`, it becomes
   `note - Notepad`.
2. `apply_state` calls `Notepad.from_state(window)` and adds the prop.
3. `attach` copies the text, with CRLF line ends, to `C:\ART98\F<hash>\note.txt` and runs
   `notepad.exe "<that path>"`.
4. `ready` finds the Edit control. The window is moved to `at` and `size`.
5. `check_state` compares the title, position and size. Any difference raises `StateMismatch`.

In a scene, `note.text` reads the Edit control, `note.set_text("...")` replaces it, and
`note.close()` closes Notepad without the save prompt. `Notepad()` with no title takes any
Notepad window on the guest.

## Limits

These are checked on the host, before anything is copied.

| Limit | Value | Why |
| --- | --- | --- |
| Text size | 50,000 bytes | Above this, Windows 98 Notepad offers WordPad instead. |
| Line ends | CRLF | `check_text` rewrites bare LF to CRLF, which Notepad needs. |
| Encoding | cp1252 | Any other byte fails with its position. NUL bytes fail too. |
| Title | no `"`, no control character, no trailing `\`, cp1252 only | It goes on a command line: a trailing `\` would escape the closing quote, and anything outside cp1252 becomes `?`. |
| File name | none of `\ / : * ? " < > |`, no control character, no trailing space or dot, cp1252 only | It goes on a command line and in the guest path; `?` is a wildcard. |
| BMP | `check_bmp` | Header, depth and pixels must all be there, or Windows 98 can crash loading it. |

## Open work

See [status](../status.md#next).
