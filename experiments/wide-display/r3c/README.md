# R3c results (2026-11-13/14): unattended install of the vmdisp9x QEMU driver

Script: `r3c.py` (`run RUNDIR`, `check RUNDIR`, `dump ...`), `refs/*.png` (title-bar masks for the two dialogs seen before the agent is up).
Probe dir (kept): `/home/admin/art98-release-check/probes/r3c-20261113-2311` (`runA/`, `runB/` = two fresh copies of the clone's `golden.qcow2`, each with `run.out`, `result.json`, `check.json`, `shots/`; `ref/` + `hklm.diff` = the early registry diff, not extended after the scope change; `scratch/`, `t3/` = development copies).
Driver files: R3's `ext/` read only. Every boot through `safe_boot.check_vm`, one VM at a time, no network, nothing run on the host.

## Verdict: PASS, twice, no human input
Start: fresh copy, Cirrus `ready` (booted with `loadvm ready`). End: cold `-vga std` boot quiet (agent up at 12 s, no dialog), `Class\Display\0002` "QEMU STD VGA PCI Adapter" (`Enum\PCI\VEN_1234&DEV_1111` -> `DISPLAY\0002`, `VMDISP9X.INF`), BITSPIXEL 16, 800x600x16, 58 modes incl. 1280x720 and 1920x1080 (at 8/16/24/32 bpp), `Enum\MONITOR\RHT1234` present. `savevm ready` then `loadvm ready` on a new process: agent up at once, same verify passes, desktop screenshot `runA/shots/loadvm-ready.png`. (`savevm ready` replaced the inherited tag: `snapshots()` = `['ready']`, answers plan probe A1's question for this QEMU.)

| | run A | run B |
|---|---|---|
| install (boot 1 start to quiet agent after boot 3) | 324 s | 309 s |
| total incl. final clean reboot, quiet wait, verify, savevm | 369 s | 353 s |
| VM boots | 4 (cirrus loadvm, std, std, final std) | 4 |
| reboots (ExitWindowsEx or accepted restart) | 3 | 3 |
| dialogs on the final clean boot | 0 (agent 12 s) | 0 (agent 12 s) |
| modes / caps | 58, 800x600x16 | 58, 800x600x16 |
| keystrokes sent | 6 (1 Yes + 5 Enter) | 6 |
| `/proc/pressure/cpu` some avg10 at start / end | 0.40 / 0.00 | 0.00 / 0.00 |
Dialog logs are identical (same counts per dialog kind). Host quiet (avg60 0.0-0.5) throughout.

## Unattended steps, in order (all inside `install(ctx)`)
1. file: `ctx.put` the 13 binaries to `C:\WINDOWS\INF` and to `C:\WIN98` (Windows' own source path), and `VMDISP9X.INF` to `C:\WINDOWS\INF` (~20 s). No `DevicePath` change needed.
2. command (setupapi through the bridge, no registry written by hand): `SetupDiCreateDeviceInfoA("Root\System\0000", System class)`, `SetupDiSetDeviceRegistryPropertyA(HARDWAREID="*PNP0A03")`, `SetupDiRegisterDeviceInfo` (async call, it blocks). Windows itself then opens the Add New Hardware Wizard for "PCI bus". DEVIATION from the coordinator's "drive the wizard with keystrokes": this replaces the manual System devices > PCI bus list navigation. It is the same wizard and the same result (R3b: `Enum\Root\System\0000`, `Class\System\0011`), created by Windows, not by me.
3. button clicks by title through the agent (`PostMessage BM_CLICK` on Next/Finish; window title and page text read first; no keystrokes): the PCI bus wizard, then Windows finds and installs 82441FX, PCI-ISA bridge, bus-master IDE, "Cirrus Logic 5446 PCI" the same way (3 to 8 pages each, ~100 s total, no CD asked; files come from `C:\WIN98`). "New Hardware Found" progress boxes close themselves. "System Settings Change" (restart) boxes are answered "No" here (button by title), the engine reboots itself.
4. registry: one delete, `RegDeleteKey Enum\Root\*PNP0905` (the dead root Cirrus). Nothing else deleted.
5. command: `ExitWindowsEx` -> cold `-vga std` (this is where `[image.vm]` vga applies).
6. boot 2 (std, no agent yet): PnP finds the PCI devices left, picks `VMDISP9X.INF` from `C:\WINDOWS\INF` by its exact hardware ID (MSDISP.INF did not win; no "Specify a location" fallback needed), copies the driver files with no "Insert Disk" thanks to `C:\WIN98`, then "System Settings Change". **keystroke** (Enter = Yes), detected by the title bar text (exact white-pixel mask of the title on the screendump, since the agent is not up). The VM exits (`-no-reboot`).
7. boot 3 (std, 800x600 now): the DDC "Plug and Play Monitor" wizard, again before the agent is up: **keystrokes**, 5 x Enter, each one only after the "Add New Hardware Wizard" title bar is matched on screen. Then the agent starts, nothing else is on screen.
8. engine tail: final clean reboot (cold std) -> agent at 12 s, no dialog -> `wait_quiet` (30 s) -> `verify` -> `savevm ready` (QEMU paused, as the plan's step 5).

Keystroke steps: only 6 per run, all in the two boots where no agent exists (restart box after the display driver, monitor wizard). Everything in the Cirrus session (the long part) uses agent title checks and button messages.

## What I learned, short (the registry diff was stopped at the scope change)
- R3b's disk vs fresh: the PCI bus device is `Enum\Root\System\0000` (HardwareID `*PNP0A03`, Driver `System\0011` = pci.vxd), `Enum\Root\*PNP0600` (root IDE) is replaced by the PCI IDE (`Enum\PCI\VEN_8086&DEV_7010`, `Class\hdc`), `Enum\Root\*PNP0905` and `Class\Display\0000` gone, `Class\Display\0001` vmdisp9x with 56 MODES keys, `Enum\MONITOR\RHT1234` + `Class\Monitor\0001`, `OtherDevicePath=C:\WINDOWS\INF\OTHER`, files `qemumini.drv/vxd`, `vmdisp9x.dll`, `vmhal9x.dll`, `vmhal486.dll`, `pci.vxd`, `pcimp.pci`, `isapnp.vxd` in SYSTEM. (`hklm.diff`, `ref/*`.) Not used by the script.
- Win98 SE source path is `C:\WIN98` (cabs are there; `SourcePath`); a third-party INF in `INF\` asks for its disk there, so the driver binaries must also sit in `C:\WIN98`.
- `rundll32 setupx.dll,InstallHinfSection PCI_DRV` only copies files (no AddReg), so it is not a route to the PCI bus.
- `regedit /e` works through the agent (`spawn` + poll `processes`); `command.com /c` needs the full path `C:\WINDOWS\COMMAND.COM`.

## Still manual or fragile
- Pre-shell dialogs (restart box after the display driver; monitor wizard) are matched by exact white-pixel title masks (640x480x4 and 800x600x16 renderings of the bold title). Another video mode or font setting would not match: the install would wait 900 s then fail with `unknown`. The matcher needs Pillow and numpy (probe only); an engine version needs a stdlib PPM reader (`screendump format=ppm`) and a pure-Python matcher. The reference masks were cut from a scratch run's screenshots.
- Enter as "Next/Finish" in the wizard relies on the default button; it worked all 10 times.
- The wizards were never asked about their subject while the agent was down; the monitor identity is inferred from `Enum\MONITOR\RHT1234` appearing, not from page text.
- setupapi usage is `lazy:`: struct bytes hand-packed (SP_DEVINFO_DATA, 28 B), `Root\System\0000` fixed name, one run on this image only.
- `C:\WINDOWS\INF` and `C:\WIN98` keep the 13 unzipped driver files (unused ones too: boxv/vesa/vmws/tray3d). Not cleaned up.
- Cirrus is left in a half state (Cirrus 5446 PCI installed, root Cirrus deleted): the copy is std-only, as in R3b. Wrong-colour Cirrus behaviour from R3b was not re-tested.
- `Class\Display\0000` (old Cirrus) remains; harmless.
- Install time ~5.5 min, dominated by the PCI wizards (~100 s) and three cold boots (TCG).

## lazy: markers in r3c.py
Two: numpy/PIL import in `title_on_screen` (engine needs a stdlib reader), and the fixed `Root\System\0000` device name / hand-packed SP_DEVINFO_DATA in `install`.

## Golden mtimes (unchanged)
before and after (identical, `golden-mtimes-*.txt` in the probe dir):
`2026-11-06 16:33:29.007260943 +1100 work/golden.qcow2` (repo)
`2026-11-12 01:34:13.301846608 +1100 /home/admin/art98-release-check/98artware/work/golden.qcow2` (clone)
Not touched: art98-vm, the repo `work/`, the R3/R3b probe dirs (R3b's disk copied for the registry diff only, never booted in place; its copy `ref/R` booted for the dump).
