# P2: CD drive, medium change after loadvm, wallpaper (local backend)

Run on 2026-11-11, host QEMU 10.2.2 (TCG, pentium3, cirrus, 800x600 at 16 bpp), local backend, `private_stage`, no `savevm`.
Script: `probe_cd.py` (`. .tools/env.sh && .venv/bin/python experiments/dialog-storm/probe_cd.py OUTDIR [section ...]`;
sections `query drive detect wallpaper getwp blank color revert`). The ISO is built with `pycdlib` (level 1, `/WALL0001.BMP;1`,
`WALL0002.BMP` 960 KB, `SMALL001.BMP` 160x120; ISO 2.51 MB). Everything below also ran with P0 and P1 active on the host, so
`/proc/pressure/cpu` "some avg10" is noted per timing (range 1.3 to 9.4 during the runs; timings did not visibly follow it).

## G1: GO (local backend)

Drive exists after `loadvm`, the medium is seen at once with no AutoPlay or Explorer window, the wallpaper shows, times are tiny.
The container backend is P3's job.

## Exact calls that worked

QMP (all via `vm.qmp.execute`):

    query-block                                     # ide1-cd0: removable, tray_open False, no "inserted"; qdev /machine/unattached/device[5]
    blockdev-change-medium device="ide1-cd0" filename=<iso> format="raw" read-only-mode="read-only" force=True
    blockdev-open-tray device="ide1-cd0" force=True               # eject
    blockdev-remove-medium id=<qdev from query-block>             # id only, qdev path read at run time
    blockdev-close-tray device="ide1-cd0"

Note: the qdev path measured here is `device[5]` (the plan text said `device[4]`, which is `ide0-hd0` here). Read it at run time, as D8 says.
The other devices: `ide0-hd0` (device[4]), `floppy0` (device[14]).

Guest (bridge): `kernel32.GetLogicalDrives`, `GetDriveTypeA("D:\\")` == 5, `GetFileAttributesA("D:\\WALL0001.BMP")`,
`advapi32.RegOpenKeyExA(0x80000001, "Control Panel\\Desktop", 0, 2, Out(4))` + `RegSetValueExA` for `TileWallpaper`/`WallpaperStyle`
(REG_SZ), then `user32.SystemParametersInfoA(0x14, 0, "D:\\WALL0001.BMP", fWinIni)` (returns 1), then `bridge.sync()`.
`SetSysColors(1, pack("<I", 1), pack("<I", r | g<<8 | b<<16))`.

## Findings

1. After boot and after an explicit `loadvm ready`: `ide1-cd0` exists, `tray_open False`, no `inserted`, `type unknown`. The guest already lists `D:` as DRIVE_CDROM (5) with the tray empty (A: 2, C: 3, D: 5).
2. CD drive letter: **D:**. No new drive letter after insert.
3. Insert after `loadvm`: no error. `blockdev-change-medium` takes 1 ms (cpu 1.3 to 9.4).
   Detect: the very first `GetFileAttributesA("D:\\WALL0001.BMP")` after the QMP return succeeds (attrs 0x1), 30 to 56 ms (that is one bridge round-trip), no `last_error`, 1 poll, over 25+ runs.
4. **G2 (detection): no polling needed.** A single access with no delay after insert works (0.0 s: 40 ms, ok), and the same after 0.1/0.5/1/3 s delays; never "not ready". Windows 98 sees the swap on its own. The plan's forced access loop is harmless and returns on poll 1; keep the cap but it is never used.
5. Windows after insert (visible top-level, before and after 3 s): only `Shell_TrayWnd` and `Progman`, identical. No AutoPlay, no Explorer window, no dialog. Screenshot `drive_after_insert.png` shows nothing new.
6. Wallpaper, `SystemParametersInfoA(0x14, 0, path, fWinIni)`, 800x600 BMP (1.44 MB), centre, stock desktop:

   | fWinIni | call ms | sync ms | visible |
   |---|---|---|---|
   | 0 | 289 | 33 | yes |
   | 2 | 264 | 31 | yes |
   | 3 | 547 | 8 | yes |

   (cpu avg10 3.3 to 3.8.) 640x500 (960 KB) centred: 415 ms, desktop colour visible around it, correct. Tile (160x120): 345 ms.
7. **G3 (stretch): works.** Registry `TileWallpaper="0"`, `WallpaperStyle="2"` with the 160x120 BMP fills the screen (visible in `wp_stretch_160x120.png`; pixel (400,300) = (112,80,200) matches BMP (80,60)). `STYLES` may keep `stretch`. Centre (`"0","0"`) and tile (`"1","0"`) verified too (tile pixels equal BMP at x%160, y%120 within quantisation). Registry written before the SPI call, as planned.
8. **G8 (read-back): does not work.** `SystemParametersInfoA(0x73, 260, Out(260), 0)` returns 0 with last_error 0 and an empty buffer, both before and after a set, for fWinIni 0 and 3; with uiParam 0 the same; the W form returns 0 with last_error 120 (not implemented). So `wallpaper_path` is dropped and `check_state` verifies by pixel only. (My `RegQueryValueExA` read of `Wallpaper` failed with 234 because the size buffer was zeroed; not pursued.)
   Known pixel (guest `GetPixel` on the screen DC / screendump / BMP value), 800x600 centred gradient `r=x*255//799, g=y*255//599, b=128`, display is 16 bpp so values differ by up to 8:
   (790,560): (255,240,136) / (255,239,132) / (252,238,128); (10,10): (0,0,136) / (0,0,132) / (3,4,128); (400,300): (128,128,136) / (123,123,132) / (127,127,128).
   Compare with a tolerance of about 12 per channel. On a stock desktop do not use (790,590): that is the taskbar (192,192,192). On a blank desktop (790,590) is fine.
9. **G6 (blank desktop + wallpaper): icons and taskbar do NOT come back.** After `blank(guest)` then the SPI call (fWinIni 3 and 0): `check_blank` returns `[]`, taskbar not visible and not enabled, icons not visible, desktop not enabled, only `Progman` listed, screenshot is the full-screen wallpaper. No `rehide_icons` needed.
   Stock desktop + colour change (200,10,30) + 640x500 wallpaper: icons and taskbar stay, wallpaper centred inside the red (the red is dithered on 16 bpp), icon labels keep their teal boxes (`wp_stock_colour_640x500.png`).
10. Colour byte order: **COLORREF = r | g<<8 | b<<16** (as in the plan). Set (200,10,30) -> packed 0x1e0ac8; `GetSysColor(1)` = 0x1e0ac8; screendump (790,590) on a blank desktop = (192,8,24) (16 bpp quantised from 200,10,30), guest `GetPixel` (200,16,32). Packing reversed (b | g<<8 | r<<16) gives (24,8,192).
11. Revert, 5 runs each:
    - (a) insert, detect, `loadvm ready` WITHOUT eject: no QMP error, loadvm 36 to 53 ms. Afterwards QEMU still has the medium (`inserted`), tray closed, and the **guest still reads `D:\WALL0001.BMP` although the snapshot had an empty drive** (5/5, last_error 0). Inserting again over it works (6 to 11 ms detect). So no error, but host and guest are out of step silently: a state that wants no disc would still see the old one. That is why D7 ejects.
    - (b) eject, `loadvm`, insert again, 5 cycles in a row: all fine. After eject+loadvm QEMU has no medium, tray closed, the guest file is gone (`GetFileAttributesA` fails), `D:` still DRIVE_CDROM. Per cycle: eject 1 to 2 ms, loadvm 53 to 63 ms, insert 1 ms, detect 30 to 48 ms; eject+revert+insert+detect total 103 to 155 ms.
12. No stray VM left; `work/runs` empty afterwards.

## Surprises

- The measured qdev is `/machine/unattached/device[5]`, not `[4]`.
- The guest reads a stale medium after loadvm without eject, instead of failing.
- `SPI_GETDESKWALLPAPER` is dead on this image, so the pixel is the only wallpaper check.
