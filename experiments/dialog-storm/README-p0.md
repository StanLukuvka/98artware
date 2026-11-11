# P0 - stock desktop plus `SetSysColors(COLOR_DESKTOP)`

Probe: `experiments/dialog-storm/probe_stock.py OUTDIR` (local backend, private `art98.session.stage`, no snapshot saved, `session.revert()` between colours). Run twice on 2026-11-11, host CPU pressure `some avg10` 0.8 to 11 (see below); no source edits.

Call that works, on the stock `ready` desktop: `guest.user32.SetSysColors(1, struct.pack("<I", 1), struct.pack("<I", r | g << 8 | b << 16))` then `guest.sync()`. `GetSysColor(1)` reads back the same COLORREF for all four colours (808000, 000080, 0000ff, ffffff).

## Findings (stock desktop)

| Check | teal | dark red | red | white |
| --- | --- | --- | --- | --- |
| Desktop fills with the colour | yes | yes | yes | yes |
| Icon label background | transparent: the label sits straight on the new colour, no teal box | same | same | same |
| Label text colour | white | white | white | black (Windows picks it by luminance, so readable) |
| Taskbar, Start button, tray, Quick Launch | unchanged (grey 184), fine | same | same | same |
| Notepad on top | draws normally over it | same | same | same |

- No repaint is needed. The frame after `SetSysColors` + `guest.sync()` already shows the new colour on the whole desktop and under every label. An extra `RedrawWindow(Progman, 0, 0, RDW_REPAINT_ALL)` changed no pixel (`-a` and `-b` shots equal).
- Pixel values are quantised by the 16-bit display: 128 reads back 120, 255 reads 248 (teal frame = (0,120,120), dark red (120,0,0), red (248,0,0), white (248,248,248)). Expect this in any pixel assert (K1/S1 tests).
- The focused icon (My Computer) shows a one-pixel dotted/coloured focus rectangle; its colour is the inverse of the desktop (cyan on red, red on teal). Cosmetic; same as stock Windows.
- Whole taskbar region on a stock desktop was not recoloured by `COLOR_DESKTOP`, as expected (it uses COLOR_BTNFACE).

## Findings (blank desktop)

- `blank()` then `SetSysColors(COLOR_DESKTOP, c)`: the colour fills the whole 800x600 frame (taskbar hidden stays hidden, `IsWindowVisible(taskbar)` = 0).
- PROBLEM: the colour change makes the **desktop icons visible again** (`IsWindowVisible(icons)` = 1 after the call; labels and icons drawn in the frame). `SetSysColors` broadcasts `WM_SYSCOLORCHANGE`, and Explorer's list view re-shows itself, the same effect as the desktop refresh noted in `desktop.py`. `blank()` itself is unaffected because it sets the colour first and hides the icons afterwards.
- Taskbar does not come back; `EnableWindow` states of taskbar and Progman were not re-checked after the call (not needed for the frame).

## Small fix (not applied)

For K1's `Backdrop` (and any later `set_colour`), after `SetSysColors` re-hide the icon list when the desktop is blank: `user32.ShowWindow(icons, SW_HIDE)` with `icons = shell_windows(guest)[2]`, then `guest.sync()`. Tested: `IsWindowVisible(icons)` goes 1 -> 0 and the frame is a clean flat colour for all four colours (`-c` shots). This is the plan's `rehide_icons(guest)`; it is needed for K1, G6. It must be conditional: on a `stock` scene the icons must stay. Simplest rule: only re-hide if `IsWindowVisible(icons)` was 0 before the call (read it first).

Nothing is needed for the stock desktop: no label background, taskbar or repaint fix.

## Timings and load

Per colour (revert + colour + 2 shots, stock adds a Notepad spawn + 2 s sleep): stock 2.6 to 3.1 s, blank 1.0 to 1.2 s. Pressure `/proc/pressure/cpu` `some avg10` at those timings: run 1 stock 5 to 11, blank 4.6 to 5.9; run 2 stock 0.8 to 0.9, blank 0.9 to 1.1 (P1/P2 were running VMs on the host at the same time, so run 1 was busier). Timings are not load-sensitive in a way that matters here.

## Not checked

Scene/`Recorder` frames (used `vm.screenshot` PPM via QMP `screendump`, the same source); `ART98_BACKEND=container`.
