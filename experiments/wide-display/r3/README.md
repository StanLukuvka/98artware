# R3 results (2026-11-13): installing the vmdisp9x QEMU driver by script

Scripts: `unpack.py` (zip-slip-checked extract), `r3.py` (`install`, `observe`, `drive`). Probe dir (deleted 2026-11-14): `/home/admin/art98-release-check/probes/r3-20261113-2041`
(screenshots in `shots/`, logs `install.out obs*.out drive*.out`, `cmd.txt` is the command log of the UI driving).
Zip: sha256 `e0d698a6...1fb23` checked (matches). 17 flat entries, no unsafe path; extracted into an empty dir, nothing run on the host, nothing copied into the repo.
Disk: reflink copy of `~/art98-release-check/98artware/work/golden.qcow2` in the probe dir, booted cold (no loadvm), every boot through `safe_boot.check_vm`.
CPU pressure (`/proc/pressure/cpu` some avg10) during all boots: 0.0-0.9, quiet host. Agent up at ~22 s on the two clean boots.
Host rebooted at 20:58 (SIGTERM to my drive VM at ~20:57), so one unclean VM stop; the next boot showed no ScanDisk screen.

## Verdict
- **I1 (files by `put_file` + `DevicePath` + silent PnP): FAIL.** Not a missing-file or INF problem: this guest has **no PCI enumeration at all**.
- **Root cause:** `HKLM\Enum` holds only INFRARED, Root, HTREE, Network, MONITOR, ESDI, SCSI, FLOP. There is no `Enum\PCI` and no `Enum\BIOS`; the Cirrus adapter is a root-enumerated device (`*PNP0905`, DXCIRRUS.INF, `Class\Display\0000`, "Cirrus Logic"). So `PCI\VEN_1234&DEV_1111` is never presented to PnP and DevicePath never gets consulted. (Probably from the unattended setup / acpi=off; changing it means touching prep, out of scope.)
- **I2 floppy variant not run**; the failure is not about where the files are. A manual route over UI works partly (below), with the files on C: (a floppy would add nothing).
- **Manual UI install (Add New Hardware, Have Disk `C:\DRIVERS\VMDISP`): INF accepted, files copied, driver NOT in use.** Result after a clean reboot and a cold `-vga std` boot: still Standard VGA.

## Evidence
1. install boot (cirrus, 800x600x16, modes 640x480x4/8/16/24 ... listed): 17 files `put_file`d to `C:\DRIVERS\VMDISP` (0.0-4.4 s each, 1.1 MB total), `DevicePath` read back as type 1 (REG_SZ) `C:\WINDOWS\INF` -> `C:\WINDOWS\INF;C:\DRIVERS\VMDISP`, RegFlushKey, ExitWindowsEx reboot (QEMU exits, `-no-reboot`).
2. First cold `-vga std` boot (obs1.out, shot `obs-std-204401-final.png`): desktop at 640x480, no dialog, agent up at 22 s. Class\Display\0000 still "Cirrus Logic"; `Enum\PCI` empty; no `qemumini.*` in SYSTEM; `EnumDisplaySettingsA` list empty; caps HORZRES 640, VERTRES 480, **BITSPIXEL 1, PLANES 4**, NUMCOLORS 16.
3. Second std boot: dialog "Display: Your display adapter is not configured properly. To correct the problem, click OK to start the Hardware Installation wizard." (`obs-std-204546-020-t220.png`, `b1.png`). It blocks the agent (never answers, 420 s). OK opens the Add New Hardware Wizard (`a2.png`). The dialogs came on both later std boots too.
4. Wizard: "Windows will now search for any new Plug and Play devices" -> list shows only "Cirrus Logic" and "Plug and Play BIOS", both with a yellow warning (`d3.png`); Cirrus Logic = "already installed, but has a problem" -> properties: Code 24, not present (`f1.png`). Update Driver with "Specify a location: C:\DRIVERS\VMDISP": "unable to locate an updated driver ... found other drivers" (`h1.png`); the list has only Number Nine Imagine 128 entries (`h2.png`), not vmdisp9x. The INF only matches PCI IDs.
5. Manual: Add New Hardware > No, not in list > No, select from list > Display adapters > Have Disk > `C:\DRIVERS\VMDISP` (`k1.png`) lists QEMU STD VGA PCI Adapter, VBox SVGA/VGA PCI, VESA ISA/PCI, VMware SVGA-II PCI (`k2.png`). Picked QEMU STD, Next, "Plug and Play compatible", "Windows has finished installing the software" (`k3.png`, `k4.png`), Finish, no restart prompt (`k5.png`). New `Enum\Root\DISPLAY\0000` appeared; `C:\WINDOWS\SYSTEM\qemumini.drv` (15534 B) and `vmdisp9x.dll` (39936 B) were copied; `SYSTEM\VMM32\qemumini.vxd` not found there (not searched elsewhere); no OEM*.INF in INF or INF\OTHER.
6. After clean reboot + cold std boot (shot `obs-std-213608-009-t099.png`, then drive5.out dump): same "Display adapter not configured properly" dialog, `Class\Display\0000` still Cirrus Logic / DXCIRRUS.INF, **BITSPIXEL 1, PLANES 4**, 640x480, NUMCOLORS 16, **`EnumDisplaySettingsA` list empty**. So no usable mode list from the driver.
7. **Windows 98 CD:** never asked for. All file copies came from C:\DRIVERS\VMDISP, no "Insert disk" prompt in any shot (the shots are 10-15 s apart, a transient one cannot be excluded).

## UI notes (for any later wizard driver)
- After the Display message box the Add New Hardware Wizard opens with an **inactive, unresponsive window**: `vm.send_keys` and `BM_CLICK` via the agent did nothing until a QMP mouse click (`input-send-event`, abs) activated it; then `ret`, `alt n`, `alt h`, arrow keys work. Typing a path: `shift`+letter qcodes, `shift semicolon` for ":", `backslash`. Pointer is not drawn in screendumps.
- While the Display dialog is open the agent does not start (no Run-key programs until OK is pressed).

## Not done
- True I2 (floppy image as A:); nothing indicates the medium matters.
- A vmdisp9x INF with a root `HKR` hardware ID, or installing from Display Properties > Advanced > Adapter > Change, or finding where PCI enumeration was disabled (any of these is a prep question); "Display Properties" screenshot after install.
- Checking where `qemumini.vxd` went, and the EnumDisplaySettings list with the driver active (R4).

## Golden mtimes (unchanged)
before: `2026-11-06 16:33:29.007260943 +1100 work/golden.qcow2`; `2026-11-12 01:34:13.301846608 +1100 /home/admin/art98-release-check/98artware/work/golden.qcow2`
after:  `2026-11-06 16:33:29.007260943 +1100 work/golden.qcow2`; `2026-11-12 01:34:13.301846608 +1100 /home/admin/art98-release-check/98artware/work/golden.qcow2`
(repo `work/golden.qcow2` and the clone's `work/golden.qcow2`)
