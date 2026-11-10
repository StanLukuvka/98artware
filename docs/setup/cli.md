# Commands and the work directory

The `art98` command is `98artware_core/art98/cli.py`. Run it with `uv run art98`, from a source
checkout: it finds `windows_handlers/build` relative to the source file, so an installed wheel
would not find it.

This page covers `doctor`, `setup` and `ping`. `setup` was called `prep`, and `art98 prep` still works as an alias. For `art98 render`, see
[the scene API](../scenes/scene-api.md).

## art98 doctor

Checks that the host tools are on `PATH`. It has no flags.

```bash
uv run art98 doctor
```

```
qemu-system-i386         /usr/bin/qemu-system-i386
qemu-img                 /usr/bin/qemu-img
mcopy                    /usr/bin/mcopy
7z                       /usr/bin/7z
ffmpeg                   /usr/bin/ffmpeg
make                     /usr/bin/make
as                       /usr/bin/as
i686-w64-mingw32-gcc     missing
/dev/kvm                 not used: Windows 98 runs under software emulation

Install the missing tools with:
  sudo dnf install mingw32-gcc
```

| Exit code | Meaning |
|-----------|---------|
| 0 | Everything in `HOST_TOOLS` was found |
| 1 | Something is missing. It prints a `dnf` command for it |

It looks up each tool with `shutil.which` and nothing more. It does not check
versions or whether `windows_handlers/build` exists. The install hint is always `dnf`. On
other distributions the package names differ.

`i686-w64-mingw32-gcc`, `make` and `as` are only needed to build `windows_handlers/`. If
`windows_handlers/build/` already holds `agent.exe` and `mbr.bin`, `setup` runs without them,
though `doctor` still reports them missing.

## art98 setup

Builds the image in four steps: `vm`, `setup`, `init_api`, `ready`. See
[stages.md](stages.md) for what each does. The code is `98artware_setup/art98_setup/`,
which `art98 doctor` and `art98 setup` import when they run.

```bash
uv run art98 setup --iso /path/to/win98se.iso
```

| Flag | Default | Effect |
|------|---------|--------|
| `--iso PATH` | None | Your disc image. Only the `vm` step reads it |
| `--key KEY` | `ART98_PRODUCT_KEY` | Your product key. Only `vm` needs it, and it is used when the answer file is written. `--key` wins over the variable |
| `--work PATH` | `work` | The work directory, relative to where you run the command. Created if missing |
| `--disk-mb N` | 2047 | Size of the Windows disk. Only the `vm` step reads it, and it rounds down to whole cylinders. Only the default has been run |
| `--from STEP` | None | Redo `vm`, `setup`, `init_api` or `ready`, and everything after it. The old stage names `media`, `disk`, `install`, `patch` and `harden` are accepted and mean the step that holds them. See [what `--from` needs](stages.md#what---from-needs) |
| `--watch` | Off | Show the VM's screen in a window, with `-display gtk` instead of `-display none`. Needs a graphical session and a QEMU built with GTK |

Steps that are already done don't need their flags. Resuming at `setup` needs
neither `--iso` nor a key.

`--key` on the command line is visible in your shell history and to other users in
`ps`. Prefer the variable.

`--watch` is stored as `"display": "gtk"` in `image.json`. It has no effect later,
because `boot()` always sets the display itself.

The steps print progress as they go:

```
[vm] starting
  setup files in /home/you/98artware/work/media
  copying setup files to the disk
[vm] done in 1s
[setup] starting
  running Setup, this takes a while; progress shots in /home/you/98artware/work/shots
  Setup restarted the machine (boot 1)
  answering the first-boot wizard, accepting the license agreement
  Setup restarted the machine (boot 2)
  answering the logon prompt with a blank password
[setup] done in 2083s
[init_api] starting
[init_api] done in 40s
[ready] starting
[ready] done in 78s
Ready: /home/you/98artware/work
```

| Exit code | Meaning |
|-----------|---------|
| 0 | All steps are done. It prints `Ready: <work directory>` |
| 1 | It failed. A `SetupError` prints `error: <message>` to stderr |
| 1 | Any other exception prints a Python traceback. This is what happens with `PEError`, `QemuError`, `BridgeError` and `FileNotFoundError`, which `cmd_setup` does not catch |

[stages.md](stages.md) lists the messages for each step.

## art98 ping

Restores the snapshot, talks to the agent, prints the guest's tick count and process
list, and quits. Use it to check that an image works.

```bash
uv run art98 ping
```

| Flag | Default | Effect |
|------|---------|--------|
| `--work PATH` | `work` | Where to find `image.json` |

The tick count is about 54,400 on every run, since each run restores the same
moment. The full output is on the [landing page](README.md#quick-path).

It fails with a traceback in these cases:

| Error | Cause |
|-------|-------|
| `FileNotFoundError: work/image.json not found; run art98 setup first` | No finished image in that directory |
| `QemuError: QEMU exited with status 1; see work/qemu.log` | QEMU could not start. The log has the reason. A common one is `Failed to get "write" lock`, when another VM is using the image |
| `BridgeTimeout` | The agent did not answer within 30 seconds |

## Environment variables

| Variable | Read by | Effect |
|----------|---------|--------|
| `ART98_PRODUCT_KEY` | `cmd_setup` | The product key when `--key` is not given |
| `XDG_RUNTIME_DIR` | `VM.__init__` | Where each VM's temporary folder for its QMP and serial sockets goes. If unset, Python's default temp directory is used |

`MTOOLS_SKIP_CHECK=1` is not yours to set. Setup sets it for its own mtools calls.

## The work directory

Everything setup makes goes under `--work`. `work/` is in `.gitignore`.

| Path | From | Removed | What it is |
|------|------|---------|------------|
| `state.json` | Every step | | Finished steps. Old stage names in it still count, see [how steps are tracked](stages.md#how-steps-are-tracked) |
| `media/win98/` | `vm` | | Setup files from your disc. Microsoft's files, so keep them out of anything you publish |
| `boot.img` | `vm` | | Patched boot floppy |
| `AUTOEXEC.BAT`, `CONFIG.SYS` | `vm` | | Scratch copies of what went on the floppy. No key in them, and nothing reads them again |
| `install.img` | `vm` | End of `ready` | Raw disk. **Holds your key** |
| `MSBATCH.INF` | `vm` | Same stage | Answer file. **Holds your key.** Left behind only if the copy to the disk fails |
| `MSDOS.SYS` | `init_api` | Same stage | Edited copy |
| `golden.qcow2` | `init_api` | | The prepared disk and, after `ready`, the snapshot. **Holds your key** |
| `image.json` | `ready` | | `VMConfig` as JSON |
| `qemu.log` | Every VM | | QEMU's stdout and stderr. Appended, never cleared |
| `shots/install<boot>-<n>.png` | `setup` | | One frame every 30 seconds |
| `shots/init_api-<n>.png`, `shots/harden-<n>.png`, `shots/reboot-<n>.png` | `init_api`, `ready` | | The same, while waiting for the agent. May be absent if it starts within 30 seconds |
| `shots/probe.ppm` | `setup`, `init_api`, `ready` | | Last frame checked for prompts |
| `shots/ready.png` | `ready` | | The desktop in the snapshot |
| `shots/wizard.png`, `shots/shutdown.png` | On failure | | The screen when the wizard or a shutdown got stuck |
| `runs/` | `art98 render` | Each `render-*` folder at the end of its run | Private copies of the image. Not made by `setup`, and a crash can leave one behind |

`shots/` is never cleared. Numbers restart with each run and overwrite old files, so a
shorter run leaves later frames from an earlier run in place. Check the times when
reading them.

### Moving the image, and running several VMs

`image.json` holds the absolute path of `golden.qcow2`, so moving the directory or
the repository breaks `boot()`. Edit `disk` in `image.json` to match.

QEMU holds a write lock on the disk, so one work directory can run one VM at a time.
A second `boot()` fails with `Failed to get "write" lock` in `qemu.log`. `art98 render`
avoids this by working on a throwaway copy under `work/runs/`. To do the same from your
own script, give each VM its own directory:

1. Copy `golden.qcow2` into a new folder. `cp --reflink=auto` makes this instant on
   btrfs.
2. Copy `image.json` next to it.
3. Set `disk` in the copy to the absolute path of the new `golden.qcow2`.
4. Pass the new folder to `boot()`.

Each copy holds your key, so treat them as you would the original.

`art98 ping` and `boot("work")` write to `work/golden.qcow2` itself, so the file's time
and size change. That is expected. The snapshot inside is not touched, and the next
`boot()` restores it.
