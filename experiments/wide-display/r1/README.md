# R1 / R2 results (2026-11-13)

Script: `probe.py` (`std`, `std32`, `r2`). Host QEMU 10.2.2 (`.tools`), 20 CPUs, a service VM (pid 2227188, not mine) ran throughout.
Copy of `~/art98-release-check/98artware/work` golden.qcow2 + image.json in `$XDG_RUNTIME_DIR/art98-probe-*` (removed). The copy's
image.json records `"disk": "/work/golden.qcow2"` (container path); every probe rewrote `config.disk` and called `safe_boot.check_vm` / `check_stage` first.
Screenshots: `/tmp/claude-1000/-home-admin-Documents-scripts-manim-windows/ddcfe38a-03cf-4cda-aa40-2829402d4c51/scratchpad/r1/` (not in the repo).
PSI = `/proc/pressure/cpu` "some" line. My own boot raises it (the probe VM is a busy TCG thread), so figures marked (boot) are not a quiet baseline.

## R1: `vga="std"`, cold boot (loadvm None)
- Boots: yes. argv has `-vga std`; `-machine pc-i440fx-10.2` from image.json accepted by QEMU 10.2.2.
- Sequence (std32 run, sampled every ~10 s): t0 640x480 "Guest has not initialized the display (yet)"; 720x400 text mode with SeaBIOS
  "Booting from Hard Disk... Starting Windows 98..." (std32-002); 640x480 desktop. Desktop reached at t<=62 s in the std runs, t<=55 s in std32
  (t is seconds after `vm.start()`; the first std run saw the desktop already at t=11 s, the next two at ~22-55 s: boot time varies with host load).
- No "New Hardware Found" dialog, no setup prompt in any shot. `bridge.windows()` after boot shows no visible window except `Shell_TrayWnd` and `Progman`.
  The 10 s sampling could miss a short dialog; the window list at the end shows none left open.
- Display: 640x480, 16 colours (`GetDeviceCaps`: HORZRES 640, VERTRES 480, BITSPIXEL 1, PLANES 4, NUMCOLORS 16), i.e. Win98 Standard VGA. Final PNG has 14 distinct colours.
  Icons and taskbar render normally; desktop teal is (87,168,168).
- Agent: connects. `Bridge.connect` then `PING` answered at t=22 s (std), t=55 s (std32). First PING in the std32 run failed until then ("no reply to PING"), so
  the agent starts by itself on the cold-booted copy.
- `EnumDisplaySettingsA(None, 0, devmode)` returns 0 with last_error 0: **the mode list is empty** (not even 640x480x16). `set_display_mode` would raise "no display mode".
  (Calling with -1 for current settings was not conclusive in the script, which reads `current` only if the call succeeds; it did not appear in the output.)
  So the only usable info is GetDeviceCaps above.
- `-global VGA.vgamem_mb=32` (extra_args): accepted by QEMU, boots the same way; same 640x480 16-colour Standard VGA; no visible difference. It only matters once a driver can use the memory.
- Screendump time, 100 calls on std at 640x480 (PSI near the end of boot, 17-31 some avg10):
  - std: png 12.1 ms/call (1.21 s), ppm 4.4 ms (0.44 s). PSI before `avg10=23.92`, after `27.20`. (earlier run: png 9.9 ms, ppm 1.5 ms, PSI avg10=21.83.)
  - std32: png 11.7 ms, ppm 4.3 ms. PSI avg10=31.88 / 31.72.
  Screendump is cheap (ppm 1.5-4.4 ms). Sizes above 640x480 cannot be measured on std yet: no driver.

## R2: frame cost, Cirrus control (`stage()` on a copy; `set_display_mode(..., persist=False)`)
Frame = `bridge.sync()` + `vm.screenshot(ppm)` + `read_bytes()` (what `Recorder._capture` does). Start mode 800x600x16.

| size | frame (sync+ppm+read) | sync only | ppm dump only | png dump only | ppm size |
| --- | --- | --- | --- | --- | --- |
| 800x600 | 5.5 ms | 4.9 ms | 2.3 ms | 6.9 ms | 1.44 MB |
| 1024x768 | 5.7 ms | 4.8 ms | 2.5 ms | 12.5 ms | 2.36 MB |

PSI "some" avg10 during these: 13.55 (800x600), 8.49 (1024x768); each of 100 calls ran in 0.2-1.3 s total. The frame cost grows ~4% (5.5 -> 5.7 ms) from 800x600 to 1024x768;
only PNG dumps get noticeably slower (6.9 -> 12.5 ms). Sync dominates a ppm frame. Not a bottleneck at either size; 1280x720 and 1920x1080 are untested (need a driver).
Caveat: sync returned ~4.9 ms on a still desktop; real scenes with repaints cost more. `sync` was not measured under motion.

## Blocks for R3 (driver install from release assets)
- A driver is needed that lists modes; with no driver the guest runs Standard VGA 640x480x16c and `EnumDisplaySettingsA` returns nothing, so `set_display_mode` cannot work until the vmdisp9x INF is installed.
- Install route: the agent connects on a cold std boot (`put_file` works at ~100-190 KB/s per its docstring), so I1 (files via `put_file` + `DevicePath`) is available; keys via `vm.send_keys` is the I2 fallback.
- No dialog to dismiss on the std boot, but PnP may raise "New Hardware Found" once the driver files are present; R3 must watch for it.
- The release assets must be downloaded to an empty `$P/dl/` (not done here; no network step in R1/R2).
- A saved `ready` snapshot of the Cirrus machine cannot be loaded into a std machine: untested (R5), and R1 always cold-booted.
- Host noise: PSI was 13-32% for much of the session (service VM + my boot), so timings above are upper bounds.
