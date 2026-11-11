# Blank start

A scene starts on a black, empty 800 x 600 screen: no wallpaper colour, icons, taskbar or
pointer. Nothing appears that the scene didn't put there. This page says what can pop up on its
own, how the blank screen is made, and what is still open.

The code is [`art98/desktop.py`](../../core/art98/desktop.py). A scene uses it through
`Scene.desktop`, described in the [Scene API](../scenes/scene-api.md#scene).

## What can pop up on its own

An audit on 2026-11-10 restored `ready` on a private copy and looked for anything that could
appear without the scene asking. It found nothing.

- **Idle soak.** 12 minutes idle, with a screenshot each minute and the window list read every
  15 s. No window appeared. Eight processes run: KERNEL32, MSGSRV32, SPOOL32, MPREXE, mmtask,
  EXPLORER, AGENT and SYSTRAY.
- **Startup entries** only run at boot, and a restore doesn't boot. The Run keys hold only the
  agent and SystemTray.
- **Scheduled tasks.** `Tune-up Application Start.job` is on the image, but Task Scheduler
  (`mstask`) isn't running, so it can't fire.
- **Tips, Windows Update, ScanDisk and Active Desktop** are all off or inactive.
- **Tooltips** only come up while the pointer hovers over something that has one.

Not checked: a clean reboot, daylight-saving prompts, and idling for longer than 12 minutes.

## How the blank screen is made

`blank(guest)` runs right after every revert, for each scene whose `desktop` is `"blank"`, the
default. Each step changes memory only, so the `ready` snapshot stays as it is and the next revert
undoes it all. None of it needs Explorer restarted. It takes about 0.4 s.

| Step | Call | Notes |
| --- | --- | --- |
| Black background | `SetSysColors` with `COLOR_DESKTOP` = black | Shows because the image has no wallpaper. |
| No icons | `ShowWindow(SysListView32, SW_HIDE)` | A desktop refresh (F5, or command `0x7103`) shows them again. |
| No taskbar | `ShowWindow(Shell_TrayWnd, SW_HIDE)` | The tray and Quick Launch go with it. It stays hidden through a settings change and the mouse at the bottom edge. |
| No Start menu | `EnableWindow(Shell_TrayWnd, FALSE)` | Without this, the Windows key and Ctrl+Esc open the Start menu over the black. |
| No desktop menu | `EnableWindow(Progman, FALSE)` | Without this, a right-click on the black opens the desktop menu. |
| Full work area | `SPI_SETWORKAREA` to the whole screen | A maximized window covers all 800 x 600. `scene.screen` measures the whole screen. The desktop space is read after this step, so `scene.space` has the whole screen too. |
| No interface effects | `SPI_SETMENUANIMATION`, `SPI_SETCOMBOBOXANIMATION`, `SPI_SETLISTBOXSMOOTHSCROLLING`, `SPI_SETGRADIENTCAPTIONS`, `SPI_SETHOTTRACKING`, all off | Their timing comes from the guest's clock. Prep was meant to turn them off; see [below](#prep-changes-not-made). |
| No pointer | Every system pointer shape swapped for an empty one with `SetSystemCursor` | `ShowCursor(FALSE)` doesn't hide it on Windows 98. Skipped when `pointer_visible` is True. |

`blank` then reads everything back except the pointer and raises `DesktopError` listing what
didn't take.

### The pointer is chosen once per desktop

A scene sets `pointer_visible` and can't switch it partway through. Swapping the shapes again
after the first swap was tested on the real image, and Windows 98 kept drawing the old shape until
the pointer moved to a new spot and stayed there. Moving it away and back didn't help, even with
a 300 ms pause, and nor did `SetCursor`, `WM_SETCURSOR` or reloading the shapes with
`SPI_SETCURSORS`. Since every revert brings the stock pointer back, the choice is applied fresh
after each one, and that first swap has always shown at once.

A program that sets its own pointer shape, such as Paint's tools, still shows that shape.

### Checked on the real image

A scene run on a private copy, 2026-11-10, CPU pressure `some avg10` 0.00 to 0.33 throughout:

- the first frame is 480,000 black pixels, and the work area is `(0, 0, 800, 600)`;
- after a pointer glide, the Windows key, Ctrl+Esc and a right-click on the desktop, the
  screen is still all black;
- after `set_state` with two picture windows, everything outside the windows is black;
- a maximized window covers the whole screen, and the desktop stays blank after a window
  closes;
- with `pointer_visible = True`, only the arrow shows, before and after `set_state`.

## The first frame

On a stock desktop, a fresh boot shows brighter, pointerless frames until the first pointer move. The blank desktop hides this. It is settled by one `SetCursorPos` nudge in `Pointer.attach`, not by a revert after boot. See [first-frame](../../experiments/first-frame/README.md).

## Prep changes not made

These would make the snapshot itself start closer to blank. Each changes the `ready` step and
needs the snapshot rebuilt, so none is done without the owner's go-ahead.

- Fix the name `UserPreferencesMask`. Windows 98 reads `UserPreferencemask`, so today the menu
  and gradient effects are still on in the snapshot, and `blank` turns them off at run time.
  Takes effect on a cold boot.
- `Policies\Explorer\NoDesktop=1` hides the icons. Takes effect when Explorer restarts.
- `Control Panel\Colors\Background="0 0 0"` makes the background black. Takes effect at logon.
- Delete `Tune-up Application Start.job`, in case Task Scheduler ever runs.
- `verify_desktop` in the `ready` step expects a visible `Shell_TrayWnd`, so it would need to
  change along with these.
