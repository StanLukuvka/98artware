# Taskbar after a display mode change

Why a state's `display` left the taskbar at its 800x600 rect, and what moves it. Run 2026-11-20
on the stock desktop through the service, with a revert before every case. Start the VM with
`uv run art98 vm start`. Each probe takes the output folder and, optionally, a work folder:

```bash
PYTHONPATH=experiments/display_taskbar .venv/bin/python experiments/display_taskbar/probe_display.py OUTDIR
```

| Probe | Took | CPU pressure `avg10`, start to end |
| --- | --- | --- |
| `probe_display.py`: flags and nudges at 1024x768x16 | 22 s | 0.09 to 0.72 |
| `probe_modes.py`: every driver mode with `CDS_UPDATEREGISTRY` | 6 s | 0.02 to 0.01 |
| `probe_set.py`: `Scene.set_state` to 640x480 and 1024x768 | 1 s | 0.00 to 0.00 |

## What moves the taskbar

Stock at 800x600x16: taskbar -2,572 to 802,602, work area 0,0 to 800,572.

`ChangeDisplaySettingsA` to 1024x768x16, then the nudge, then `sync`. Readings were also taken
3 s later and didn't change:

| Flags | Nudge | Taskbar | Work area |
| --- | --- | --- | --- |
| 0 | none | -2,572 to 802,602 | 0,0 to 1024,740 |
| 0 | `WM_DISPLAYCHANGE` sent to `Shell_TrayWnd` | unchanged | unchanged |
| 0 | `WM_DISPLAYCHANGE` broadcast (`SendMessageTimeoutA`) | unchanged | unchanged |
| 0 | `WM_SIZE` sent to `Shell_TrayWnd` | unchanged | **0,0 to 1024,768** (worse) |
| 0 | `WM_SETTINGCHANGE` with `SPI_SETWORKAREA` sent to `Shell_TrayWnd` | unchanged | unchanged |
| 1 (`CDS_UPDATEREGISTRY`) | none | **-2,740 to 1026,770** | 0,0 to 1024,740 |

- With flags 0, Windows moves the work area, but Explorer leaves the taskbar where it was.
  Explorer on Win98 seems to treat a mode change that isn't in the registry as temporary, like a
  game's full-screen switch, and doesn't lay out the taskbar again. No message we tried
  changes that.
- With flags 0 the screen outside the old 800x600 area was also left unpainted, with stray
  lines over the old desktop. With `CDS_UPDATEREGISTRY` the whole screen repaints, so no extra
  repaint is needed.
- `Progman` and the icon list follow the new screen either way.

## Every mode with `CDS_UPDATEREGISTRY`

| Mode | Result | Taskbar | Work area |
| --- | --- | --- | --- |
| 640x480x16 | 0 | -2,452 to 642,482 | 0,0 to 640,452 |
| 1024x768x16 | 0 | -2,740 to 1026,770 | 0,0 to 1024,740 |
| 800x600x8 | 0 | -2,572 to 802,602 | 0,0 to 800,572 |
| 1024x768x8 | 0 | -2,740 to 1026,770 | 0,0 to 1024,740 |
| 640x480x24 | 0 | -2,452 to 642,482 | 0,0 to 640,452 |
| 640x480x8 | 0 | -2,452 to 642,482 | 0,0 to 640,452 |
| 1280x1024x8 | 0 | -2,996 to 1282,1026 | 0,0 to 1280,996 |
| 640x480x4 | **1** (`DISP_CHANGE_RESTART`) | mode stays 800x600x16 | |

640x480x4 also returns 1 with flags 0. `set_display_mode` used to accept that silently, and now
raises. A revert after a persisted change brings back 800x600x16 and the stock taskbar.

## The fix

`apply_state` calls `set_display_mode(..., persist=True)`. The registry write is part of the VM
state, so the next revert undoes it, just as it undoes `set_wallpaper`'s registry write.
`probe_set.py` through `Scene.set_state` reads taskbar -2,452 to 642,482 and
`scene.work_area` 0,0 to 640,452 at 640x480, and -2,740 to 1026,770 and 0,0 to 1024,740 at
1024x768. The screenshots show the whole screen repainted.

## Not fixed here

At 1024x768x16 the desktop and taskbar are cross-hatched with stray pixels. `GetPixel` in the
guest reads them too, for example (136, 40, 16) between teal pixels, so they're in the guest's
framebuffer and not added by the screenshot. It happens with flags 0 as well, and 1024x768x8 is
clean. It looks like a Cirrus driver issue at that mode.
