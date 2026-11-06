# 98artware

Script animations with a real Windows 98 desktop as the medium. See
[PLAN.md](PLAN.md) for the creative direction. This repository currently holds
the two foundations: a tool that prepares the VM, and a bridge that drives it.

```
Host: Python                                   Guest: Windows 98 SE in QEMU
  your script                                    Explorer, Notepad, dialogs...
  art98.Bridge  ---- COM1, framed text ------->  AGENT.EXE: Win32 call proxy
  art98.VM      ---- QMP: frames, snapshots -->  the VM's hardware
```

## Setup

```bash
sudo dnf install qemu-system-x86 qemu-img mtools 7zip ffmpeg make binutils mingw32-gcc
```

```bash
make -C guest
```

```bash
uv run art98 doctor
```

## 1. Prepare the image

You need your own Windows 98 SE disc image and product key. Nothing here
supplies them. Running `prep` accepts the Windows 98 licence agreement on your
behalf: the answer file asks to skip it, and OEM discs that show it anyway get
"I accept" selected by keystroke.

```bash
uv run art98 prep --iso /path/to/win98se.iso --key XXXXX-XXXXX-XXXXX-XXXXX-XXXXX
```

Add `--watch` to see the screen. Progress is saved after each stage, so rerunning
resumes, and `--from STAGE` repeats a stage and everything after it.

| Stage | What happens |
|-------|--------------|
| `media` | Checks the agent can load on 98, unpacks `WIN98`, pulls the boot floppy from the disc and points it at Setup |
| `disk` | Makes a raw disk with a boot record and FAT32, copies in the setup files, answer file and agent |
| `install` | Runs Setup until the agent says hello, starting a new VM each time Setup reboots, then shuts down. Answers the OEM first-boot wizard and the logon prompt by watching the screen. Screenshots go to `work/shots/` |
| `patch` | Edits `MSDOS.SYS` offline and converts the disk to qcow2 |
| `harden` | Over the bridge: applies registry settings, empties the Run keys, sets 800x600x16, reboots, checks the desktop is clean, saves snapshot `ready` |

The result is `work/golden.qcow2` and `work/image.json`.

## 2. Drive it

```python
from art98 import Out, boot

with boot("work") as stage:
    guest = stage.bridge
    guest.spawn("notepad.exe")
    notepad = guest.find_window(class_name="Notepad")

    # Any exported Win32 function works, from any DLL.
    guest.user32.SetWindowPos(notepad.hwnd, 0, 100, 80, 400, 300, 0x14)
    guest.user32.SetCursorPos(200, 200)
    rect = guest.user32.GetWindowRect(notepad.hwnd, Out(16)).buffers[0]

    # Anything that blocks goes on its own guest thread.
    dialog = guest.acall("user32", "MessageBoxA", 0, "hello", "98", 0)

    stage.vm.screenshot("frame.png")
```

Every `boot()` restores the same snapshot, so nothing carries over between runs.

Arguments map as follows: `int` is a dword, `str` a pointer to an ANSI string,
`bytes` an in/out buffer, and `Out(n)` a zeroed out buffer. Buffers come back in
`result.buffers`, which is how structs reach the host.

Things that need a callback or a local loop have their own methods: `windows`,
`find_window`, `processes`, `spawn`, `sync`, `move_window`, `put_file`, `get_file`,
`set_display_mode`.

Use `move_window` rather than a bare `SetWindowPos`, since moves leave stale
pixels along the window frame until it is repainted.

A guest reboot ends the VM, because Windows freezes on its logo after a warm
reset in the same QEMU process. Start a new one with `boot()` afterwards.
`ExitWindowsEx` never replies, so call it with `acall`.

### Frames

`stage.record("out.mp4")` gives a recorder whose `frame()` waits for the guest to
repaint and then captures, so a video comes out the same on a slow host as on a
fast one. [examples/hello.py](examples/hello.py) is a complete scene.

`live(seconds)` records something that moves by itself, such as a screensaver.
It follows the host's clock and skips the sync, so that stretch does depend on
host speed. [examples/showcase.py](examples/showcase.py) uses both: it draws in
Paint with the mouse, clears a Minesweeper board, and runs 3D Pipes.

Serial runs at about 11 KB/s, which is plenty for commands and slow for files
(`put_file` manages about 3 KB/s). Larger assets should go on the disk during
`prep`.

## Tests

```bash
uv run --group dev pytest
```

| Suite | Runs against |
|-------|--------------|
| `test_protocol`, `test_bridge`, `test_prep` | Python alone, with mtools for the disk tests |
| `test_qemu` | Real QEMU with no Windows: boot chain, QMP, snapshots |
| `test_agent_wine` | The real `agent.exe` under Wine, with a pty as COM1 |

The QEMU and Wine suites skip themselves if those tools are missing. They can't
stand in for real Windows 98, so the findings from real runs are below.

## Measured on real Windows 98

From a Windows 98 SE OEM disc, on QEMU 10.2.2 with software emulation:

| What | Result |
|------|--------|
| Full `prep`, blank disk to snapshot, no input | About 40 min |
| Snapshot restore to a working agent | About 1 s |
| `PING` round trip | About 5 ms |
| `SYNC` plus one frame capture | About 6.5 ms |
| `examples/hello.py`, 210 frames | Under 3 s |
| `examples/showcase.py`, 1731 frames | About 34 s |
| 3D Pipes under TCG, launched with `/s` | About 37 new frames per second |
| Guest clock against host | 5004 ms over 5 s |
| Screenshots | Include the mouse pointer |
| Installed extras | Games, Character Map, 11 screensavers, sound schemes. Screensavers are in `C:\WINDOWS\SYSTEM` with long names, such as `3D Pipes.scr` |

Setup quirks that `prep` handles, in case another disc behaves differently:

- The disc's boot floppy holds `JO.SYS`, a startup menu that defaults to the hard
  disk, so it is deleted.
- OEM discs ignore the request to skip the first-boot wizard (name, licence,
  product key, finish). The name and key come from the answer file, and prep
  presses through the pages. It recognises the wizard by pixels on a 640x480
  screen, so a retail or localised disc may need new markers.
- Setup asks for a workgroup unless the answer file gives one, and it can't match
  the computer name.
- The logon prompt appears once. A blank password stops it coming back.

A stall means no disk writes for 20 minutes. Screen changes don't count, because
a blinking caret looks like progress while a dialog waits forever.

## Deferred

Audio. art98 is video only for now, though the VM keeps its Sound Blaster.

## Not yet proven on Windows 98

- The Wine suite against the final agent. It needs a Wine prefix on this machine.
