# Troubleshooting

Start with the error message. [stages.md](stages.md) lists the messages for each
step. When the VM is involved, these show what happened:

| Where | What it shows |
|-------|---------------|
| `work/shots/` | The newest `install*`, `init_api*`, `harden*` or `reboot*` PNG is the last screen, at most 30 seconds old |
| `work/qemu.log` | Why QEMU would not start. Appended across runs, so read the end |
| `--watch` | The live screen |
| `C:\SETUPLOG.TXT`, `DETLOG.TXT` | Setup's own logs. On a failed install, read them from `work/install.img` with `mtype -i "work/install.img@@32256" ::SETUPLOG.TXT`. Set `MTOOLS_SKIP_CHECK=1` first |

The logs are fine to paste into an issue, but don't share the disk itself: it is an installed
copy of Windows.

## Setup quirks the tool handles

These come from running a Windows 98 SE OEM disc. The reasons are the ones given in
the code and in `docs/archive/MANIM_MAPPING_PLAN.md` section 2.7.

| Quirk | Why it matters | What setup does | Where |
|-------|----------------|----------------|-------|
| `JO.SYS` on the boot floppy | It is the disc's startup menu. `IO.SYS` runs it before `CONFIG.SYS`, and after a timeout it boots the hard disk, so Setup never starts | Deletes it | `patch_floppy` |
| Setup writes no MBR | Only the partition's boot sector is written, and a blank MBR will not boot | Supplies `guest/boot_record/mbr.S` | `build_mbr` |
| mtools rejects the geometry | It refuses images that are not a textbook floppy or disk | Sets `MTOOLS_SKIP_CHECK=1` | `_mtools_env` |
| OEM first-boot wizard | OEM media ignores the answer file's request to skip it. Four pages: name, licence, product key, finish. Name and key are filled in from the answer file | Presses through it, with `alt+a` on page two for "I accept the Agreement" | `WIZARD_PAGES`, `_answer_setup_wizard` |
| Logon prompt | Appears once on the first real boot and waits forever | Presses Enter. A blank password means it never comes back | `_answer_setup_prompts` |
| Workgroup page | Setup asks for a workgroup unless the answer file gives one, and Windows refuses one with the computer's name | `Workgroup="WORKGROUP"`, computer `art98`, `Display=0` | `render_msbatch` |
| `NoPrompt2Boot` | Microsoft's table and sample disagree on what `1` means | Follows the sample | `render_msbatch` |
| Warm reboot freeze | Windows hangs on its logo after a reset in the same QEMU process | `-no-reboot`, and a new VM per boot | `VMConfig`, `setup.py` |
| `ExitWindowsEx` never replies | A plain call would block the bridge until it timed out | Uses `acall`, then waits for QEMU to exit | `_reboot` |
| Blinking caret | A dialog waiting forever still changes the screen | The stall rule watches the disk instead | `_wait_for_agent` |
| Modern toolchains | They build files that fail on 98 with a vague error | Links without the mingw CRT, and checks the result on the host | `guest/Makefile`, `pecheck` |

## The stall rule

**A stall means no disk writes for 20 minutes**; screen changes don't count. `STALL_LIMIT` is `20 * 60`.

Every `SHOT_INTERVAL`, 30 seconds, `_wait_for_agent` reads the modified time of the
disk file on the host. When it changes, the timer resets. When it has not changed for
20 minutes, setup raises:

```
no disk writes for 20 minutes during install2; see .../shots/install2-0049.png, or rerun with --watch to see the VM
```

The screenshot named in the message is usually the answer. Look for a dialog. If the
guest looks busy instead, 20 minutes of no disk writes on a slow host is possible but
was not seen here: the longest part of Setup kept writing throughout.

Other limits apply at the same time:

| Limit | Constant | Value |
|-------|----------|-------|
| One boot of `setup` | `INSTALL_TIMEOUT` | 3 hours, so a very bad run could last far longer in total |
| Number of boots | `SETUP_BOOTS` | 8 |
| Waiting for the agent in `init_api` and `ready` | Literal in `_require_agent` | 15 minutes |
| One wizard page | `WIZARD_PAGE_TIMEOUT` | 2 minutes |
| Windows shutting down | `SHUTDOWN_TIMEOUT` | 5 minutes |
| A ready agent after `HELLO` | `wait_ready` default | 60 seconds |

The wait for a quiet screen in `ready` has no limit. See [ready](stages.md#ready).

## Recovering from a failed step

Fix the cause, then:

| Failed in | Do this | Why |
|-----------|---------|-----|
| `vm` | `art98 setup --iso ... ` again, with a key | Both parts rerun and start clean. A `state.json` with only the old names (`media`, `disk`) counts as nothing done, see [the step names](stages.md#how-steps-are-tracked) |
| `setup` | `art98 setup --from vm` | A plain rerun boots Setup again over the partly installed disk. `--from vm` starts from a blank one. It needs the ISO and a key |
| `init_api` | `art98 setup` again | `install.img` is still there |
| `ready` | `art98 setup` again | It boots `golden.qcow2` again, and `install.img` is still there |
| `--from setup` or `--from init_api` after a finished build | `art98 setup --from vm` | `install.img` is gone, and `state.json` was already shortened |

Common causes:

| Symptom | Cause | Fix |
|---------|-------|-----|
| Traceback ending in `QemuError: QEMU exited with status 1` | See `work/qemu.log` | Usually a lock, or a missing file |
| `Failed to get "write" lock` in `qemu.log` | Another VM has that disk open, possibly left over from a crash | Stop it. Check with `pgrep -a qemu-system`. See [several VMs](cli.md#moving-the-image-and-running-several-vms) |
| `FileNotFoundError` for `mbr.bin` | The guest was not built | `make -C guest` |
| `image.json not found` | No finished image in `--work` | Check `--work`, or finish `art98 setup` |
| `guest speaks protocol N, host M` | The agent on the image is older or newer than the Python code | Rebuild the agent and redo the install, see below |
| Snapshot fails to load after a QEMU upgrade | The image's device state doesn't match the new QEMU | Rebuild from `vm` |
| `unexpected windows on the desktop` | Something opened at startup | See `shots/ready.png`, deal with its cause, then `--from ready` |

To put a new `agent.exe` on the image, rebuild it and redo the install:

```bash
make -C guest
```

```bash
uv run art98 setup --from vm --iso /path/to/win98se.iso
```

### Windows rejected the product key

You see `Windows rejected the product key`, and the log printed `answering the first-boot
wizard` a second time. `shots/product-key.png` shows the wizard on its Product Key page with
the key filled in. A good install answers the wizard once, so setup stops at the second pass
instead of pressing through it until the 3-hour limit.

The key is written to `MSBATCH.INF` on the disk in the `vm` step, and a resume skips that step,
so rerunning as it is reuses the bad key. Start again from `vm` with the right key:

```bash
uv run art98 setup --from vm --iso /path/to/win98se.iso --key XXXXX-XXXXX-XXXXX-XXXXX-XXXXX
```

`art98 up` has no `--from`, and running it again as it is reuses the bad key. Delete
`work/state.json`, run `art98 up --iso ...` again and type the right key at the prompt.

## QEMU only

art98 works only with QEMU. It depends on QMP for screenshots, keys and snapshots, on a
Unix socket as COM1, and on `-no-reboot`.

The binary is `qemu-system-i386`, the constant `QEMU_BINARY`. It can't be set with a
flag, but it is found on `PATH`.

### Unpacked tools

You don't have to install the tools system-wide. If you can't, you can unpack the
packages into a folder, add its `bin` to `PATH`, and set `LD_LIBRARY_PATH` to its
libraries. QEMU also needs `-L` pointing at its firmware, so a small wrapper script
named `qemu-system-i386` works best.

Don't unpack into `/tmp`. It is cleared when the host reboots, and every tool in it goes
with it. Setup would then fail with a missing program, or `doctor` would report it
missing, even though nothing about the image changed.

Keep one QEMU version for the life of an image: see [the snapshot](image.md#the-snapshot).
`image.json` pins the machine version, not the QEMU build.

The sockets live in `XDG_RUNTIME_DIR`, or the temp directory. Each VM makes its own
folder and removes it on a clean exit, so a crashed run can leave an `art98-*` folder
behind. It is safe to delete once that VM has gone.

### Reboots end the VM

A guest reboot ends the QEMU process. This is on purpose, see
[`-no-reboot`](image.md#hardware). During setup it is handled. In your own scripts:

- The bridge reports the link closing, and the session is over.
- Stop the VM with `art98 vm stop`, then start it with `art98 vm start`. It restores the
  snapshot, so a reboot does not keep anything from the session.
- To keep changes across a reboot, you need a cold boot without `-loadvm`, the way
  the `ready` step does it, on a private copy of the image.
- Call `ExitWindowsEx` with `acall`, since it never replies.

## On a busy host

When the host is under CPU pressure, a render is slower but gives the same video. Measured on a
20-CPU host with 28 busy loops running, on host QEMU (before the VM service), with `recipes/scenes/blank_start/blank_start.py`
(3 clips, 263 frames). The pressure column is `some avg10` from `/proc/pressure/cpu`, before, during
(min to max) and after the render.

| Run | Pressure before / during / after | Wall time | Frames | `put_file` total | `BridgeTimeout` |
| --- | --- | --- | --- | --- | --- |
| quiet | 0.01 / 0.01 / 0.00 | 3.8 s | 263 | 0.46 s | none |
| quiet again | 4.4 / 3.6 / 2.95 | 3.6 s | 263 | 0.42 s | none |
| busy 1 | 40.8 / 42.1 to 45.1 / 45.1 | 20.9 s | 263 | 6.04 s | none |
| busy 2 | 45.1 / 45.8 to 47.3 / 46.9 | 17.9 s | 263 | 4.07 s | none |

What to expect:

- At pressure about 45, a render takes about 5 times as long, and `put_file` about 10 times
  (the 57 KB picture went from 0.43 s to 3.7 to 5.7 s).
- The frame and clip counts are the same as on a quiet host. The recorder is driven by frames, not
  by the clock.
- No `BridgeTimeout` fired. The guest's `sync` gives up on a window after 500 ms without saying so,
  so a slow window can show up only as a longer call (0.80 s at worst here).
- Frames are not bit for bit equal, but two quiet renders differ the same way. The causes are
  Notepad's blinking caret and the encoder, not the load.
- Note `/proc/pressure/cpu` next to any timing you quote. The figures in other docs are quiet-host
  figures.

Details: [host-checks](https://github.com/StanLukuvka/98artware/blob/dev/experiments/host-checks/README.md).

## A different disc

Setup has run on one Windows 98 SE OEM disc. Anything else may need changes. Look at
these first.

| Part | Depends on | Change if |
|------|------------|-----------|
| `boot_floppy_image` | El Torito with floppy emulation, one default entry | The disc is no-emulation, or has several boot images |
| `extract_setup_files` | A `WIN98` folder with `SETUP.EXE` and `PRECOPY1.CAB` | The disc's layout differs |
| `patch_floppy` | `HIMEM.SYS` on the floppy. `JO.SYS` is optional | The floppy is laid out differently |
| `render_msbatch` | US locale and keyboard: `L0409`, `KEYBOARD_00000409` | The disc is localised |
| `OPTIONAL_COMPONENTS` | English names from the disc's INF files | The disc is localised. Setup ignores unknown names silently, so check the result |
| `WIZARD_PAGES` | Four pages, with `alt+a` for "I accept" | Page count or accelerator keys differ. A localised disc will likely differ |
| `setup_wizard_showing` | A 640x480 screen with exact colours at five points: `(10,10)` and `(20,470)` blue `(0,0,255)`, `(300,70)` navy `(0,0,168)`, `(300,360)` grey `(192,199,200)` | The wizard looks different |
| `WIZARD_HEADING` | The heading area at `(220, 92)` to `(560, 118)` | The dialog sits elsewhere |
| `logon_prompt_showing` | A 640x480 screen: `(10,10)` and `(20,470)` teal `(0,128,128)`, `(300,72)` navy `(0,0,128)`, `(300,245)` grey `(192,192,192)` | The logon dialog differs. Also if a network client is installed, since the prompt changes |
| `--key` | Always required by `vm` | The disc takes no key |

A retail disc may not show the wizard at all. That is fine: the check only fires when
those pixels match, and no keys are sent otherwise.

If a prompt isn't recognised, setup doesn't know it is there. It sees no disk writes and
stops after 20 minutes. To find the new values:

1. Run with `--watch`, or open the newest PNG in `work/shots/`.
2. Read the colours at those coordinates from `work/shots/probe.ppm` with the screen on
   show.
3. Update the checks in `setup/art98_setup/builder.py`, and the matching test screens in
   `setup/tests/test_setup.py`.

`--from vm` then reruns the install.

Windows 98 first edition, Windows 95 and Windows ME have not been tried.
