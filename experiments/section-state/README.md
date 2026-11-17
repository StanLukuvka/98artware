# B0: windows the desktop owns, what appears by itself, and what a check costs

Probe for the section-state plan (`--section` on `set_state`/`get_state`, with every window tracked).
Script: `probe.py`. Run on 2026-11-17 on the `ready` image through the VM service (real Docker,
Cirrus 800x600x16), two full runs, blank then stock desktop, each part after a revert. Nothing
recorded, no snapshot saved. CPU pressure `some avg10` was 0.05 to 0.26 for both runs (quiet
host).

## Q1: the baseline

Visible top-level windows right after the desktop starts (`Scene._start_desktop`):

| Desktop | Visible | All top-level |
| --- | --- | --- |
| blank | `Progman` "Program Manager" | 20 |
| stock | `Progman` "Program Manager", `Shell_TrayWnd` "" | 20 |

The other 18 are hidden. The same hwnds come back after two reverts (`baseline_same_after_reverts`).

## Q2: windows that appear by themselves

After each step, the visible top-level windows minus the baseline:

| Step | New visible windows |
| --- | --- |
| Notepad opened | `Notepad` |
| `Menu(pad, "Edit", "Select All")` finished | `Notepad` (the `#32768` menu is gone again) |
| Pointer resting on the title bar, 2.5 s | `Notepad` |
| Pointer resting at the bottom edge (the taskbar on stock), 2.5 s | `Notepad` |
| Notepad minimized | `Notepad` |
| `Dialog` added | `Notepad`, `#32770` "art98" |
| `Dialog` removed | `Notepad` |
| Notepad removed | none |

Nothing appeared that the scene didn't open, on either desktop. No `IGNORED_CLASSES` list is
needed yet. Not covered: a tooltip from resting on a taskbar button or the clock, since the
probe rested on an empty part of the bar.

## Q3: cost

100 calls each, from the host, per desktop:

| Call | Median ms | p95 ms |
| --- | --- | --- |
| `windows()` (20 rows) | 3.2 to 3.7 | 7.8 to 9.3 |
| one `user32.IsWindow` | 5.0 | 5.3 to 5.5 |

One listing is cheaper than a single `IsWindow`, because each call is a round trip and the
listing is one. **So the check after each `play` should be one `windows()` call.** That covers
untracked windows (visible rows), gone props (all rows), and hwnd reuse (each row's pid and
class), instead of one `IsWindow` per prop. Under the plan's 5 ms bar (median).

## Q4: GetWindowPlacement

`WINDOWPLACEMENT.length` must be set to 44. With a zeroed buffer (`Out(44)`) the call returns 0
and fills nothing, so pass `struct.pack("<I", 44) + bytes(40)` as an in/out buffer.

A Notepad placed at (120, 90) size 360x240:

| Show | `showCmd` | `rcNormalPosition` | `GetWindowRect` |
| --- | --- | --- | --- |
| normal | 1 | 120, 90, 480, 330 | 120, 90, 480, 330 |
| maximized | 3 | 120, 90, 480, 330 | -4, -4, 804, 604 (blank), 576 (stock) |
| minimized | 2 | 120, 90, 480, 330 | 3000, 3000, 3160, 3024 |

`rcNormalPosition` keeps the normal rect in every show state, and equals `GetWindowRect` for a
normal window on both desktops. Both desktops have their work area at (0, 0), so this can't tell
screen coordinates from work-area ones. They are the same for art98's desktops.

# B1 follow-up: what the recipes' gestures leave up

Script: `probe_windows.py`. Run on 2026-11-17 on the `ready` image (stock desktop), with tracking
checks switched off so the scene sees the guest unfiltered. CPU pressure `some avg10` 0.22 to
0.26. "At return" is what a tracking check after that play would see.

| Gesture | At return | Then |
| --- | --- | --- |
| `Hover((768, 587), hold=1.5)` on the clock | `tooltips_class32` "" (Explorer's pid) | gone when the next `Glide` returned |
| `RightClick((640, 300))` on the desktop | nothing | `#32768` up 0.30 s later; gone 9 ms after `Keys("esc")` returned |
| `DoubleClick((38, 22), run_time=0.9)` | nothing | `CabinetWClass` "My Computer" up 0.96 s later; gone 0.45 s after WM_CLOSE |
| `Menu(pad, "Edit", "Select All")`, then `"Time/Date"` | no `#32768` | none |
| Minesweeper `clear()` | `#32770` "Congratulations", Minesweeper's pid | |
| `sign_scoreboard()` | nothing (the table had gone) | |

So a tracking check needs three things:
- a claim on the tooltip from `Hover`;
- a RightClick claim that waits for its menu, which comes after the play;
- a My Computer adoption that waits for the window. `Win("My Computer")` finds it by title, and
  the title is exactly "My Computer".

`Menu` needs nothing.

# B2: get_state round trip

Script: `probe_get_state.py`. Run on 2026-11-17 on the `ready` image (stock desktop). CPU
pressure `some avg10` 0.00. The scene has a maximized Picture (normal rect 40, 40, 320x240), an
Untitled Notepad set to two lines, and the pointer at (500, 400). It is captured with `get_state`,
then a second scene runs `set_state` on the capture, which passed `check_state`, and captures
again.

The two state files are identical apart from their `.files` folder names. The maximized window
keeps its normal `at`/`size`, the title is "Untitled - Notepad", and `text.txt` holds the text
with CRLF line ends.

# B4 follow-up: `--section move` of blank_start, the Notepad Edit control

Scripts: `probe_edit_state.py` (rendered first frames), `probe_hscroll.py` (scroll info). Run on
2026-11-17 on the `ready` image. CPU pressure `some avg10` 2.4 to 4.0.

`--section close` matched the full run frame for frame. `--section move` differed on frame 1, in the
Notepad only, in two ways:

- **Caret.** The full run's typing left it at the start of line 2. A Set puts it at 0. Sending
  `EM_SETSEL` to the typed position fixes this.
- **Horizontal scroll bar.** It is enabled with a thumb in the full run and disabled in a solo run.
  `GetScrollInfo(edit, SB_HORZ)` (min, max, page):

| Path | Range |
| --- | --- |
| desk.json, before typing | 0, 208, 209 |
| after typing "hello from a blank desktop\n" at 0 | 0, 416, 290 |
| the 02-move capture, set with WM_SETTEXT | 0, 208, 209 |
| that, then WM_CHAR "x", backspace, enter, backspace | 0, 216, 217 |

While the text was typed, line 1 was briefly "hello from a blank desktopA note on a blank
desktop.", wider than the view. The Edit control keeps the widest line it has had, and the Enter
didn't shrink it back. That's typing history, not text. WM_SETTEXT and EM_REPLACESEL both
recompute it from the text as it is now, so neither can restore it. Variants Caret, Replace and
Nudge all still differ in the same box (320, 224, 636, 376).

So a capture can't restore the full run's Notepad exactly once text was typed into it. Options
(owner's call): store the scroll range in the state and force it with SetScrollInfo, which only
changes the bar, not the control's own width; or document it as a known limit. Until then, the
plan's B4 VM test uses Picture windows only, as it already said.
