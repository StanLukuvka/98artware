# R3b results (2026-11-13): making Windows enumerate PCI so vmdisp9x binds to `-vga std`

Script: `r3b.py` (`prep`, `drive`, `observe`; reuses `../r3/r3.py` helpers). Probe dir (deleted 2026-11-14): `/home/admin/art98-release-check/probes/r3b-20261113-2142`
(`shots/` 174 screenshots, logs `prep.out drive*.out obs*.out`, `cmd1.txt` = the command log of route A, `obs-std-221418.json` = the final std dump).
Disk: reflink copy of `~/art98-release-check/98artware/work/golden.qcow2` (cold boots only, no loadvm), driver files from R3's `ext/` put in `C:\DRIVERS\VMDISP` by `put_file` on a cirrus boot (`prep`). Every boot via `safe_boot.check_vm`, one VM at a time.
`/proc/pressure/cpu` some avg10 during all boots: 0.00-0.86 (quiet host; logged on every shot line).
Three unclean VM stops (probe killed with a dialog open: SIGINT to my own driver, once `kill` of my own orphaned QEMU pid); the following boots showed no ScanDisk in the screenshots I looked at.

## Verdict
**YES. A script-less in-guest step brings up PCI: route (a), Add New Hardware > System devices > "PCI bus" (Standard system devices).** After it, plus removing the dead root-enumerated Cirrus device, a cold `-vga std` boot ends with `Enum\PCI` present, vmdisp9x ("QEMU STD VGA PCI Adapter") driving the display, 800x600x16 and **58 modes** in `EnumDisplaySettingsA`. Route (b) and (c) were not needed. Nothing was changed in prep; QEMU flags were as the image uses them, `-vga std` only where noted.

Chain that worked (all in the guest, all on one copy):
1. cirrus boot: Add New Hardware > No (do not search) > System devices > (Standard system devices) > **PCI bus** > Finish. Windows immediately finds and installs the PCI devices from its own INFs (MACHINE2.INF etc., no Win98 CD asked): 82441FX host bridge, 82371SB PCI-ISA bridge, 82371SB bus-master IDE, plus "IO read data port for ISA Plug and Play enumerator" and "IRQ Holder for PCI Steering". Restart prompt, QEMU exits (`-no-reboot`).
2. cold `-vga std` boot (first after step 1): wizard "Standard PCI Graphics Adapter (VGA)" (VEN_1234&DEV_1111). The default search picks MSDISP.INF; **"Specify a location: C:\DRIVERS\VMDISP" picks vmdisp9x INF ("QEMU STD VGA PCI Adapter", C:\DRIVERS\VMDISP\VMDISP9X.INF)**. Restart prompt, again at the next boot.
3. cold std boot: desktop at 640x480x4, no dialog, but the new device has **Code 12 (cannot find free I/O range)**: the Cirrus root device (`Enum\Root\*PNP0905`, Code 24) still holds the VGA ports (3B0-3BB, 3C0-3DF) in BootConfig. Device Manager > select "Cirrus Logic" > Delete > OK removes it (`Enum\Root\*PNP0905` and `Class\Display\0000` gone); restart.
4. cold std boot: 800x600 at once, Windows finds "Plug and Play Monitor" (DDC) -> wizard from MONITOR.INF, Finish; agent then answers.
5. next cold std boot: no dialogs, agent up at 11 s, desktop 800x600x16. (Screenshots below.)

## 1. Diagnosis (cirrus boot, before any change)
- `HKLM\Enum` = INFRARED, Root, HTREE, Network, MONITOR, ESDI, SCSI, FLOP; `Enum\BIOS` and `Enum\PCI` empty (they exist empty after the first boot here; R3 saw them missing), no `*PNP0A03` anywhere in `Enum\Root`.
- `Enum\Root\*PNP0C00\0000`: DeviceDesc "Plug and Play BIOS", Class System, DetFunc `*:DETECTBUS`, NoSetupUI 1, PnPBIOSVer 0x10 (v1.0), PnPStrucOffset set, Driver `System\0002` (bios.vxd, MACHINE.INF PNPBIOS_DRV, 4-23-1999), ConfigFlags all zero. **No disabled/problem flag in the registry**.
- Device Manager (by connection, `shots/e3.png`): PnP BIOS has a yellow warning, **Code 24 ("not present, not working properly, or does not have all the drivers installed")**. Settings tab: only "Disable NVRAM / ESCD updates" (`e4.png`); Driver tab: Microsoft 4-23-1999 (`e5.png`). So bios.vxd loads but finds no PnP BIOS node list, hence no BIOS-enumerated devices (no `*PNP0A03`). The QEMU build's SeaBIOS image contains the `$PnP` header string; it is apparently not enough for Win98 to enumerate.
- `Class\System\0000-0010`: Processor support, SWENUM, PnP BIOS (0002), PIC, DMA, CMOS, timer, speaker, FPU, System board, APM. No PCI bus entry.
- Cirrus root device `*PNP0905` (DXCIRRUS.INF, `Display\0000`, ChipType CL-GD5446) works on cirrus (800x600x16, modes 640x480x4/8/16/24 ...).
- Screenshots: `d0-desktop.png`, `d1-sysdm.png`, `d2/d3`, `e1.png`-`e5.png` (Device Manager and PnP BIOS properties).

## 2. Routes
- **(a) PCI bus via Add New Hardware: works.** `f1.png`-`g3.png` (wizard path: `f7` hardware types, `f9` System devices, `g1` model list, `g2` "PCI bus" selected, `g3` Finish); `g4.png` first new device (82441FX), `g7.png` driver from MACHINE2.INF, `j4/k4/k6/l1.png` IDE controller, `l1.png` restart prompt.
  Detail: the wizard's Next/Back behaviour needs keyboard (QMP has no absolute pointer on this VM: `input-send-event abs` -> "Input handler not found"); `Enter` = Next on the default button, `shift tab` + `Enter` for Back; type-ahead `s` in the hardware list landed on SBP2, use arrow keys.
- (b) not tried (not needed). Note the PnP BIOS device keeps Code 24 after route (a); PCI is enumerated by the new "PCI bus" root device, not through the BIOS.
- (c) not tried.

## 3. Final display state (cold `-vga std`, `obs-std-221418.json`, `drive4-std-fixed.out`)
- `Class\Display\0001`: DriverDesc "QEMU STD VGA PCI Adapter", MatchingDeviceId `PCI\VEN_1234&DEV_1111`, InfPath `JHROBO~1.INF`, DevLoader `*vdd`; `[DEFAULT]` drv qemumini.drv, minivdd qemumini.vxd.
- `Enum\PCI` has 82441FX (1237), PIIX3 ISA (7000), PIIX3 IDE (7010), Cirrus 5446 (1013:00B8, from the cirrus boot), QEMU STD VGA (1234:1111, `Driver=DISPLAY\0001`), IRQHOLDER. `Enum\BIOS` empty.
- `GetDeviceCaps`: HORZRES 800, VERTRES 600, **BITSPIXEL 16, PLANES 1**, NUMCOLORS -1. Current mode 800x600x16.
- `EnumDisplaySettingsA` list: 58 modes. (w x h; bits-per-pixel 4: 640x480, 800x600.) At **8, 16, 24 and 32 bpp each: 640x480, 800x600, 1024x768, 1152x864, 1280x720, 1280x800, 1280x960, 1280x1024, 1400x1050, 1600x900, 1600x1200, 1680x1050, 1920x1080, 1920x1200** (14 sizes x 4 depths + 2). This is R4's first glimpse: 16:9 sizes 1280x720, 1600x900, 1920x1080 are in the list (enumerated only; not switched here).
- Files: `C:\WINDOWS\SYSTEM\qemumini.drv` 15534 B, `qemumini.vxd` 21123 B (R3 looked in SYSTEM\VMM32 and missed it), `vmdisp9x.dll` 39936 B, `vmhal9x.dll` 386048 B. `SYSTEM.INI [boot] display.drv=pnpdrvr.drv`, `[boot.description] display.drv=QEMU STD VGA PCI Adapter`, `[386Enh] display=*vdd,*vflatd`.
- Screenshots: `t7.png` (desktop 640x480x4 after step 2, Code 12), `v1.png`-`v6.png` (Device Manager: PCI bus now present; QEMU adapter Code 12; Resources tab: no conflicting device listed), `w1-w3.png` (removing Cirrus Logic), `x1.png`/`y*.png` (monitor wizard at 800x600), `z1.png` (desktop 800x600), `obs-std-221418-final.png`.

## 4. `-vga cirrus` afterwards (same copy, `obs5-cirrus-cold.out`, `drive5-cirrus.out`)
- Boots to the desktop, agent up at 22 s, 800x600x16. First cirrus boot after the changes shows a "System Settings Change, restart" prompt that blocks the agent (`obs4-cirrus-restartprompt.out`) (Windows installs "Cirrus Logic 5446 PCI" from the already-present PCI device); after one restart it is quiet.
- Now `Class\Display\0000` = "Cirrus Logic 5446 PCI" (`PCI\VEN_1013&DEV_00B8`), modes: 640x480x4; 640/800/1024/1280x1024 at 8 and 16 bpp (800x600, 1024x768 too at 24; no 1280x1024x24). BITSPIXEL 16.
- **Colours are wrong on cirrus now**: icons render greenish (folder yellow -> green, IE blue -> teal; `obs-cirrus-222116-final.png`, `cir1.png`); the desktop teal is unchanged. Likely a 16 bpp format (565/555) mismatch with the PCI Cirrus driver; not investigated. The copy is therefore effectively std-only for art98; do not treat the cirrus result as clean.

## 5. QEMU flag note (recorded, not applied)
- Everything worked with `-vga std` and no other flag change (`machine pc-i440fx-10.2`, tcg, pentium3, 128 MB, `-no-reboot`). The 58-mode list is longer than the Cirrus 4 sizes; the extra modes presumably come from the std VGA's EDID/VBE list (`-device VGA,edid=on,xres=,yres=` would pin a preferred size; `-vga std` vbe_size / `vgamem_mb` raises the usable memory: 16 MB default covers 1920x1200x32 (9 MB)). Not tried.
- No QEMU flag was needed for PCI itself: the "no PCI" state was Windows-side (PnP BIOS Code 24, no `*PNP0A03` root device), not a QEMU-side lack of a PCI bus (the devices are enumerated as soon as the PCI bus device exists).

## 6. What an add-on install script would need (summary for the plan)
1. Install the "PCI bus" system device (the wizard used MACHINE.INF; which `Enum\Root` key it creates was not inspected) and get the PCI devices installed from MACHINE2.INF etc. A reboot.
2. Bind vmdisp9x INF to `PCI\VEN_1234&DEV_1111` (wizard needed "Specify a location"; a default search found only MSDISP.INF, so `DevicePath` alone is not enough, or the INF must be copied/registered into `C:\WINDOWS\INF` first; not tested).
3. Delete the stale `Enum\Root\*PNP0905` Cirrus device (it held 3B0-3DF), reboot.
4. Accept the monitor wizard (MONITOR.INF) or pre-install it; every one of these needs a reboot and, with an unanswered "System Settings Change" box, the agent never starts. So the install must run on a cirrus+agent boot where the driver for each is in `C:\WINDOWS\INF` and ideally unattended (`rundll32 setupapi,InstallHinfSection` / `devcon`-like) rather than through the wizard. **Not done here: scripting any of the wizard steps; all steps were driven by keystrokes in the UI.**

## Not done
- Route (b)/(c), and a scripted (no-wizard) version of steps 1-4, e.g. `rundll32 setupapi.dll,InstallHinfSection` for the PCI bus entry and a registry-only removal of `Enum\Root\*PNP0905`.
- Switching the display with `ChangeDisplaySettings` into a 16:9 mode (R4); only enumeration.
- Cirrus colour mismatch not investigated.
- Where the `PCI\VEN_1234&DEV_1111` match failed in the default INF search (MSDISP.INF won over DevicePath) was not tested (DevicePath was reset by Windows to `C:\WINDOWS\INF` during PCI installs; the copy's `Software\Microsoft\Windows\CurrentVersion\DevicePath` reads `C:\WINDOWS\INF` in every post-step-1 dump).

## Golden mtimes (unchanged)
before: `2026-11-06 16:33:29.007260943 +1100 work/golden.qcow2`; `2026-11-12 01:34:13.301846608 +1100 /home/admin/art98-release-check/98artware/work/golden.qcow2`
after:  identical (`golden-mtimes-after.txt` in the probe dir; the probe dir's `golden-mtimes-before.txt` was taken at copy time). Not touched: art98-vm, the repo `work/`, the R3 probe dir (read only).
