# Commands and the work directory

The `art98` command is `core/art98/cli.py`. Run it with `uv run art98`, from a source
checkout: it finds `guest/build` relative to the source file, so an installed wheel
would not find it.

This page covers `doctor`, `setup`, `ping`, `up` and `serve`. For `art98 render`, see
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
docker                   /usr/bin/docker (for `art98 up` and the container backend)

The local backend needs the missing tools. Install them with one of:
  Fedora          sudo dnf install mingw32-gcc
  Debian, Ubuntu  sudo apt install gcc-mingw-w64-i686
Or skip them: `art98 up` runs QEMU and setup in a container, and the host then needs only ffmpeg.
```

| Exit code | Meaning |
|-----------|---------|
| 0 | Everything in `HOST_TOOLS` was found |
| 1 | Something is missing. It prints a `dnf` and an `apt` command for it |

It looks up each tool with `shutil.which` and nothing more. It does not check
versions or whether `guest/build` exists. The package names come from
`HOST_TOOLS` and `DEBIAN_PACKAGES` in `builder.py`. On Debian 12 and older, `7z` comes from
`p7zip-full` rather than `7zip`. A missing `docker` doesn't change the exit code. Its line then
suggests `podman-docker`, which provides `docker` on a Podman host.

`i686-w64-mingw32-gcc`, `make` and `as` are only needed to build `guest/`. If
`guest/build/` already holds `agent.exe` and `mbr.bin`, `setup` runs without them,
though `doctor` still reports them missing.

## art98 setup

Builds the image in four steps: `vm`, `setup`, `init_api`, `ready`. See
[stages.md](stages.md) for what each does. The code is `setup/art98_setup/`,
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
| `--from STEP` | None | Redo `vm`, `setup`, `init_api` or `ready`, and everything after it. See [what `--from` needs](stages.md#what---from-needs) |
| `--watch` | Off | Show the VM's screen in a window, with `-display gtk` instead of `-display none`. Needs a graphical session and a QEMU built with GTK. `ART98_WATCH_DISPLAY` replaces `gtk`, which is how `art98 up --watch` gets VNC |

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
| `--backend NAME` | `ART98_BACKEND`, else `local` | `local` runs QEMU on the host. `container` runs it in the art98 container, on a copy of the disk. `render` takes the same flag |

The tick count is about 54,400 on every run, since each run restores the same
moment. The full output is on the [landing page](README.md#quick-path-on-the-host).

It prints `error: <message>` to stderr and exits with 1 when the image is missing:

| Message | Cause |
|---------|-------|
| `work/image.json not found; run art98 setup first` | No finished image in that directory. With `--backend container` it says `art98 up` |
| `no image localhost/art98:latest; run art98 up to build it` | With `--backend container`: the container image hasn't been built. `ART98_IMAGE` names another |
| `the stage container exited ...` | With `--backend container`: the container stopped. The message ends with the last lines it printed |

`render` prints the same messages. Anything else fails with a traceback:

| Error | Cause |
|-------|-------|
| `QemuError: QEMU exited with status 1; see work/qemu.log` | QEMU could not start. The log has the reason. A common one is `Failed to get "write" lock`, when another VM is using the image |
| `BridgeTimeout` | The agent did not answer within 30 seconds |

## art98 up

From your disc and key to a working desktop, with QEMU and setup in the container. The host
needs Docker, Python and ffmpeg. The code is
[setup/art98_setup/up.py](../../setup/art98_setup/up.py).

```bash
uv run art98 up --iso /path/to/win98se.iso
```

1. Builds the image `localhost/art98:latest` if it is missing, or always with `--rebuild`.
2. Copies `agent.exe`, `view.exe` and `mbr.bin` out of the image into `guest/build`
   if `view.exe` isn't there, since scenes send `VIEW.EXE` to the guest from the host.
3. If `image.json` is missing from the work directory, takes the key from `ART98_PRODUCT_KEY`
   or asks for it without echo, and runs `art98 setup` in the container with the disc
   mounted read-only. The key goes in a private file, mode 0600, mounted read-only at
   `/run/secrets/art98_key`, and the file is deleted when setup ends. A resumed setup asks for
   the key again.
4. Boots a stage in the container and pings the agent.

| Flag | Default | Effect |
|------|---------|--------|
| `--iso PATH` | None | Your disc image. Needed only while setup isn't done |
| `--work PATH` | `work` | The work directory, mounted at `/work` in the container |
| `--watch` | Off | Show setup's screen over VNC on `127.0.0.1:PORT`, with no password. Loopback only |
| `--vnc-port PORT` | 5998 | The host port for `--watch` |
| `--rebuild` | Off | Build the image even if it exists. The build asks Docker's CLI for `--load` and fails if the engine's image isn't the one just built |
| `--disk-mb N` | 2047 | As for `setup` |

art98 calls only `docker`. On a Podman host, install `podman-docker`, which provides it. Files
the container writes in `work/` are yours on any engine. On a rootless one the container's root
is you. On rootful Docker the image's entry point,
[entry.py](../../core/art98/container/entry.py), sees from `/proc/self/uid_map` that its root is
the host's, and switches to the uid and gid the host passed before running art98.

## art98 serve

Runs inside the container, as the image's default command. It makes a run copy of the disk in
`/work/runs`, restores `ready`, waits for the agent and serves the host until the host's control
connection closes. You don't run it by hand: `boot(backend="container")` starts a container
running it. The protocol is in [the container design](../design/container.md#art98-serve-in-the-container).

| Flag | Default | Effect |
|------|---------|--------|
| `--work PATH` | `/work` | The mounted work directory |
| `--port N` | 7598 | TCP port inside the container |
| `--unix PATH` | None | Listen on this Unix socket instead, in a folder the host mounted. Screenshots can then be written into that folder |
| `--token-file PATH` | `/run/secrets/art98_token` | The token every connection must send first |
| `--vnc` | Off | Show the screen on VNC port 5900 in the container |
| `--ready-timeout S` | 60 | How long to wait for the agent after the restore |

## Environment variables

| Variable | Read by | Effect |
|----------|---------|--------|
| `ART98_PRODUCT_KEY` | `cmd_setup`, `art98 up` | The product key when `--key` is not given. In the container, setup reads `/run/secrets/art98_key` when neither is there |
| `ART98_BACKEND` | `session.boot`, `render`, `ping` | `container` (the default) or `local` |
| `ART98_ENGINE` | `art98.container.host.Engine`, `doctor` | The binary to run instead of `docker`. It only names the command: art98 drives it the same way |
| `ART98_HOST_UID`, `ART98_HOST_GID` | `art98.container.entry` | Set by the host on every container it runs. On a rootful engine the container switches to them, so `work/` stays yours |
| `ART98_IMAGE` | `art98.container.host` | The image name, `localhost/art98:latest` by default |
| `ART98_TRANSPORT` | `ContainerStage` | `unix` (the default on Linux) or `tcp` (the default elsewhere): how the host reaches the container. See [timing](../design/container.md#timing) |
| `ART98_WATCH_DISPLAY` | `Setup._config` | The QEMU display for `--watch`, `gtk` by default. `art98 up --watch` sets it to VNC |
| `ART98_TEST_WORK` | `test_stage.py` | The prepared work directory the stage tests boot |
| `XDG_RUNTIME_DIR` | `VM.__init__`, `ContainerStage` | Where each VM's temporary folder for its QMP and serial sockets goes, and each container stage's socket folder. If unset, Python's default temp directory is used |

`MTOOLS_SKIP_CHECK=1` is not yours to set. Setup sets it for its own mtools calls.

## The work directory

Everything setup makes goes under `--work`. `work/` is in `.gitignore`.

| Path | From | Removed | What it is |
|------|------|---------|------------|
| `state.json` | Every step | | Finished steps. See [how steps are tracked](stages.md#how-steps-are-tracked) |
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

`image.json` holds the absolute path of `golden.qcow2`. If that file is gone, `boot()` and
`private_stage()` use the file of the same name beside `image.json`, so a work directory can
be moved whole, and one prepared in the container (which records `/work/golden.qcow2`) works
on the host.

QEMU holds a write lock on the disk, so one work directory can run one VM at a time.
A second `boot()` fails with `Failed to get "write" lock` in `qemu.log`. `art98 render`
avoids this by working on a throwaway copy under `work/runs/`. To do the same from your
own script, give each VM its own directory:

1. Copy `golden.qcow2` into a new folder. `cp --reflink=auto` makes this instant on
   btrfs.
2. Copy `image.json` next to it.
3. Set `disk` in the copy to the absolute path of the new `golden.qcow2`.
4. Pass the new folder to `boot()`.

Each copy is a full installed Windows with your key in it, so keep it as private as the original.

`art98 ping` and `boot("work")` write to `work/golden.qcow2` itself, so the file's time
and size change. That is expected. The snapshot inside is not touched, and the next
`boot()` restores it.
