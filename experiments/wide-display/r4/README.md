# R4 results (2026-11-14): display modes with vmdisp9x on `-vga std`

Script `r4.py` (`table`, `table-persist`, `persist`, `modes`, `vga32`, `taskbar`, `taskbar2`, `raw`). Probe dir (deleted 2026-11-14): `/home/admin/art98-release-check/probes/r4-20261114-0105` (`vm/` = copy of R3c runA; `*.json`/`*.out` per phase, `shots/`).
Start: `loadvm ready` (std, vmdisp9x, 800x600x16, 58 modes), agent up at once. Host QEMU 10.2.2, one VM at a time, every boot via `safe_boot.check_vm`, no network. `/proc/pressure/cpu` some avg10 was 0.00-0.6 throughout (host quiet; per-row values in the json files).
Switch = `bridge.set_display_mode(w,h,d)` itself (default `persist=True`); rc read by wrapping `user32.ChangeDisplaySettingsA`. Screendump size polled until it equals the mode.

## Q1 mode table (persist=True, from `table-persist.json`)
| mode | rc | switch s | dialog | GetDeviceCaps after | dump size | taskbar/looks right | agent up |
|---|---|---|---|---|---|---|---|
| 1280x720x16 | 0 | 0.28 | none | 1280x720x16 | 1280x720 | yes, Shell_TrayWnd (-2,692,1282,722) | yes |
| 1280x720x32 | 0 | 0.36 | none | 1280x720x32 | 1280x720 | yes (tray rect right; bar is grey 192 at 32 bpp) | yes |
| 1920x1080x16 | 0 | 0.25 | none | 1920x1080x16 | 1920x1080 | yes, tray at y=1052 | yes |
| 1920x1080x32 | 0 | 0.39 | none | 1920x1080x32 | 1920x1080 | yes (viewed: clean, icons, Start, clock) | yes |
| 1600x900x16 | 0 | 0.23 | none | 1600x900x16 | 1600x900 | yes | yes |
| 1024x768x16 | 0 | 0.18 | none | 1024x768x16 | 1024x768 | yes | yes |
| 800x600x16 (back) | 0 | 0.17 | none | 800x600x16 | 800x600 | yes | yes |
Dump matched the mode within 0.01 s of the call returning. No "restart?" box, no 15 s test box, no garbage. Windows listing shows only Progman and Shell_TrayWnd resized.

**Taskbar finding (coordinator's note confirmed): `persist=False` (CDS flags 0) never moves the taskbar.** Same 7 modes with `persist=False` (`table.json`, `shots/<mode>.png`): resolution, caps and dump all change correctly, but `Shell_TrayWnd` stays at its 800x600 rect (-2,572,802,602), so in every larger mode the bar sits at y~600 and spans only x<=800; at 1024x768 the screenshot has no bar at all at the bottom. Only 800x600 looks right. Not fixed by: waiting 10 s, broadcasting WM_DISPLAYCHANGE, SPI_SETWORKAREA, SetWindowPos on the tray, a posted WM_DISPLAYCHANGE to the tray (`taskbar.json`, `taskbar2.json`). Fixed by `persist=True` (CDS_UPDATEREGISTRY), immediately, and it also holds on a following non-persist switch only until that switch (a non-persist switch after a persist run leaves the tray where it was). `ChangeDisplaySettingsA(NULL,0)` drops back to the registry mode. Probable cause: the shell re-lays out the taskbar only when the registry mode changes (Win98 explorer path); cause not proven. Consequence: `setstate.py:61` (`persist=False`) would leave a wrong taskbar and work area on vmdisp9x; use `persist=True`. (Not tested on Cirrus; on Cirrus the blank desktop hides the bar.) The 960x540 non-persist switch also left the tray behind.

## Q2 persist (`persist-a.json`, `persist-b.json`)
- CDS_UPDATEREGISTRY: writes `Config\0001\Display\Settings` Resolution `1280,720`, BitsPerPixel `16`. After a clean ExitWindowsEx reboot (cold boot, no loadvm) the VM came up 1280x720x16, agent at 12 s, no dialog, tray correct. **Survives a reboot: yes.**
- Mode set (non-persist, 1024x768x16) just before `savevm m1024`, new process `loadvm m1024`: agent up at once, GetDeviceCaps and dump 1024x768x16, desktop sane. **Survives savevm/loadvm: yes** (device state in the snapshot). The tray was still at the previous (1280x720) position, since the switch was non-persist: same taskbar issue.

## Q3 frame cost (100 calls each; frame = sync + ppm dump + read; `table.json`, repeat in `table-persist.json`)
| size | frame ms | sync ms | ppm ms | ppm size | png ms |
|---|---|---|---|---|---|
| 800x600 | 5.2-5.9 | 5.0 | 3.0 | 1.44 MB | 5.0-6.0 |
| 960x540 (n=30) | 6.0 | 4.8 | 3.3 | 1.56 MB | 5.9 |
| 1280x720x16 | 9.9-10.0 | 5.0 | 4.2 | 2.76 MB | 8.8-9.4 |
| 1920x1080x16 | 15.1 | 5.0 | 7.8-8.2 | 6.22 MB | 19.4-20.2 |
| 1920x1080x32 | 15.0-15.2 | 5.0 | 7.9 | 6.22 MB | 18.5-20.4 |
(ppm is 24-bit whatever the depth. PSI some avg10 0.00-0.18 during these.) About 100 frames per second headroom at 1080p; sync dominates at 800x600. Cost scales with pixels, not a bottleneck. Sync was measured on a still desktop only.
**vgamem**: default 16 MB is enough for 1920x1080x32 (switch ok, dump 1920x1080, clean screenshot, taskbar right). With `-global VGA.vgamem_mb=32` (`vga32.json`): same 58 modes (max 1920x1200x32 either way), same frame cost (14.6 ms), nothing gained. No change needed.

## Q4 non-listed mode, 960x540 (`modes.json`, `raw.json`)
- `bridge.set_display_mode(960,540,16)` rejects it ("guest has no 960x540x16 display mode"); that check is art98's own list walk.
- **The driver itself does not reject**: `ChangeDisplaySettingsA` with a hand-built DEVMODE (no list lookup, flags 0) for 960x540x16 and for 1000x700x16 returned 0 and the screen really switched (caps and dump 960x540 / 1000x700). So a non-listed mode is reachable at run time with no INF/registry/reboot, if the bridge skips the list check (not changed here; core untouched). Taskbar needs the persist flag as above (not re-tested on raw modes).
- INF-style route: `Class\Display\0002\MODES\<bpp>\<w>,<h>` (default value empty, keys `4,8,16,24,32`, 14 sizes under `16`). Creating `MODES\16\960,540` and `MODES\32\960,540` through the registry made 960x540 appear in `EnumDisplaySettings` **immediately without a reboot** (58 -> 60 modes after, count after reboot 60, both depths), and `set_display_mode(960,540,16)` then worked (0.31 s, dump 960x540, frame 6.0 ms). So "freely" works at run time by a registry write (or the raw call); `vesamode.exe` is on the guest (`C:\WINDOWS\INF`, 50 KB) but was not used.

## Golden mtimes (unchanged; `golden-mtimes-before.txt`/`-after.txt`)
`2026-11-06 16:33:29.007260943 +1100` repo `work/golden.qcow2`; `2026-11-12 01:34:13.301846608 +1100` clone `work/golden.qcow2`. Only the probe dir copy was booted; R3c, art98-vm, `work/` untouched.

## Not done
Raw 1000x700 persist/reboot; 2560x1440 and larger; vesamode runtime insert; non-persist taskbar fix (none found); Cirrus comparison of the taskbar issue.
