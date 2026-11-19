# Taskbar probe

Can a scene hide parts of the taskbar, and what undoes it? Run 2026-11-19 on the stock desktop
through the service (`art98 vm start`, then `probe_taskbar.py OUTDIR`). It took 4 s; CPU
pressure `avg10` was 0.01 at the start and 0.00 at the end.

## The taskbar's children (Win98 SE, 800x600)

| Class | Rect | What it is |
| --- | --- | --- |
| `Button` | 2,576 to 56,598 | Start |
| `ReBarWindow32` | 60,576 to 713,598 | holds quick launch and the window buttons |
| `ToolbarWindow32` (in the rebar) | 69,576 to 138,598 | quick launch |
| `MSTaskSwWClass` (in the rebar) | 153,576 to 709,598 | the window buttons |
| `SysTabControl32` (in the above) | zero size | not the visible buttons; `TCM_GETITEMCOUNT` reads 0 even with Notepad open |
| `TrayNotifyWnd` | 717,576 to 798,598 | the tray (volume icon) |
| `TrayClockWClass` (in the tray) | 737,578 to 798,598 | the clock, frozen at 9:00 AM by the revert |

## Results

`ShowWindow(hwnd, SW_HIDE)` on each part, then `IsWindowVisible` and a screenshot:

| Part hidden | Hides | After `set_colour` | New window opened | After revert |
| --- | --- | --- | --- | --- |
| `MSTaskSwWClass` | every window button | stays hidden | stays hidden, no button | shown |
| `ReBarWindow32` | quick launch and the buttons | stays hidden | stays hidden | shown |
| `TrayClockWClass` | the clock; the tray keeps its width, empty | stays hidden; the tray shrinks to the icon | (not tried) | shown |
| `TrayNotifyWnd` | the whole tray; one etched line stays at x=713 | **shown again** | stays hidden | shown |

- The clock stays hidden after 65 s of guest time, so the minute tick doesn't re-show it.
- The `set_colour` broadcast re-shows the tray every time, even when it is hidden again
  before a second colour change. Anything that hides the tray must hide it again after a
  colour change.
- Every part reads back with `IsWindowVisible`, so unlike the wallpaper, `get_state` can
  capture these.
- A revert restores all of them; the `ready` snapshot is untouched.

## What this means for the API

- `buttons=False` (hide `MSTaskSwWClass`) keeps every window off the taskbar, including ones
  opened later. A per-window `taskbar=False` on `Win` isn't needed.
- `quick_launch=False` would hide the `ToolbarWindow32` in the rebar (probed on its own in the
  second probe below).
- `clock=False` hides `TrayClockWClass`; `tray=False` hides `TrayNotifyWnd` and must be
  applied again after `Backdrop` or any other colour change.

Per-window options (owner windows, `WS_EX_TOOLWINDOW`) were dropped from the probe; hiding
the buttons area covers that.

## Second probe: the open points from the requirements (2026-11-20)

`probe_taskbar_2.py`, then a short follow-up on display modes. Each case starts from a revert.
CPU pressure `avg10` was 0.00 at the start and 0.56 at the end of the main run (9 s).

| Question | Result |
| --- | --- |
| 1. Quick launch alone (`ToolbarWindow32`) | Hides cleanly with Notepad open. Its band's grip stays; the window buttons don't move (153 to 709 before and after). It stays hidden after `set_colour`. |
| 7. Settle the tray after hiding the clock | `SendMessageA(Shell_TrayWnd, WM_SIZE, 0, 0)` shrinks the tray to its icon at once (717 to 778 on the left edge), the same as a colour change. `WM_SETTINGCHANGE` to the taskbar does too. Doing nothing leaves the empty frame. |
| 8. Wallpaper broadcast | `set_wallpaper("", "center")` leaves the buttons, clock and tray hidden. |
| 8. Display mode change | The hidden parts stay hidden. See the note below about the taskbar not moving. |
| 9. Other resolutions | 640x480 and 1024x768 at 16-bit: the parts hide and read back the same. 1280x1024 at 16-bit isn't offered by the driver. |
| 4. Icons on stock | `ShowWindow(icons, SW_HIDE)` hides them, and `set_colour` keeps them hidden (its `was_hidden` re-hide). |
| 4. Pointer on stock | `hide_pointer` right after a revert hides the arrow on the stock desktop too (checked by screenshot after a move). |

**Taskbar after a display mode change.** A `set_display_mode(..., persist=False)` on the reverted
VM leaves the taskbar where it was, even 15 s later. At 1024x768 it floats at its 800x600 height
(top 572), and at 640x480 it's off the bottom of the screen. The screen also wasn't fully
repainted right after the change. This is how a state's `display` behaves today, separate from the
taskbar options; it needs its own look.
