# Commands and the work directory

The `art98` command is `core/art98/cli.py`. Run it with `uv run art98`, from a source
checkout: it finds `guest/build` relative to the source file, so an installed wheel
would not find it.

This page covers `doctor`, `setup`, `vm`, `ping`, `up`, `serve` and a short `render` section. For
the GIF options of `art98 render`, see [the scene API](../scenes/scene-api.md#command-line). Settings for these commands live in
[art98.toml](config.md).

## art98 doctor

Checks that the host tools are on `PATH`. It has no flags.

```bash
uv run art98 doctor
```

```
qemu-system-i386         missing (only `art98 setup` on the host needs it)
qemu-img                 missing (only `art98 setup` on the host needs it)
mcopy                    /usr/bin/mcopy
7z                       /usr/bin/7z
ffmpeg                   /usr/bin/ffmpeg
make                     /usr/bin/make
as                       /usr/bin/as
i686-w64-mingw32-gcc     /usr/bin/i686-w64-mingw32-gcc
/dev/kvm                 not used: Windows 98 runs under software emulation
docker                   /usr/bin/docker (for `art98 up` and `art98 vm`)

The VM is usable (run `art98 up` first). `art98 setup` on the host needs: qemu-system-i386, qemu-img
```

This is a host that has `docker` and `ffmpeg` but no host QEMU. The last line is one of four
summaries: everything usable, only the host path usable, only the container path usable, or
nothing usable. When nothing is usable it also prints an install command per system.

| Exit code | Meaning |
|-----------|---------|
| 0 | At least one path works: every tool in `HOST_TOOLS` is found (host `setup`), or `ffmpeg` and the engine are found (`art98 up`, `art98 vm`) |
| 1 | Neither path works. It prints a `dnf` and an `apt` command for the missing tools |

It looks up each tool with `shutil.which` and nothing more. It does not check
versions or whether `guest/build` exists. The package names come from
`HOST_TOOLS` and `DEBIAN_PACKAGES` in `builder.py`. On Debian 12 and older, `7z` comes from
`p7zip-full` rather than `7zip`. The engine is `docker`, or the command `ART98_ENGINE` names. If it is missing, its line
suggests `podman-docker` and `docker-compose`, which provide `docker compose` on a Podman host,
and the exit code can become 1. It does not check that the compose plugin is installed.

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
| `--key KEY` | `ART98_PRODUCT_KEY` | Your product key. `art98 setup` never prompts for it. Only `vm` needs it, and it is used when the answer file is written. `--key` wins over the variable |
| `--work PATH` | `[vm] work` | The work directory, relative to where you run the command. Created if missing |
| `--disk-mb N` | 2047 | Size of the Windows disk. Only the `vm` step reads it, and it rounds down to whole cylinders. Only the default has been run |
| `--from STEP` | None | Redo `vm`, `setup`, `init_api` or `ready`, and everything after it. See [what `--from` needs](stages.md#what---from-needs) |
| `--watch` | Off | Show the VM's screen in a window, with `-display gtk` instead of `-display none`. Needs a graphical session and a QEMU built with GTK. `ART98_WATCH_DISPLAY` replaces `gtk`. `ART98_VNC=1` turns it on too, which is how the `setup` service in `compose.override.yaml` gets VNC |

Steps that are already done don't need their flags. Resuming at `setup` needs
neither `--iso` nor a key.

`--watch` is stored as `"display": "gtk"` in `image.json`. It has no effect later,
because `art98 vm start` always sets the display itself.

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
[setup] done in 1294s
[init_api] starting
[init_api] done in 13s
[ready] starting
[ready] done in 59s
Ready: /home/you/98artware/work
```

| Exit code | Meaning |
|-----------|---------|
| 0 | All steps are done. It prints `Ready: <work directory>` |
| 1 | It failed. `SetupError`, `QemuError` and `BridgeError` print one `error: <message>` line to stderr. `ART98_TRACE=1` adds the traceback |
| 1 | `PEError` and a plain `FileNotFoundError` are not caught: they print a Python traceback |

[stages.md](stages.md) lists the messages for each step.

## art98 vm

The VM runs in one long-lived container. `art98 vm start` starts it and leaves the VM paused
at `ready`. `art98 render` and `art98 ping` attach to it, and `art98 vm stop` removes it. Nothing
boots the VM during a render.

```bash
uv run art98 vm start
uv run art98 render recipes/scenes/mvp/mvp.py -o mvp.mp4
uv run art98 vm stop
```

### art98 vm start

Runs `docker compose up -d --wait vm`: the `vm` service of [compose.yaml](../../compose.yaml),
in the compose project `art98-<hash8>` of this work folder, so the container is named
`[vm] container` (`art98-vm` by default) and runs `[vm] image`. Before that it writes
`work/vm.token` (or the file `[vm] token_file` names), mode 0600, made once and reused, which
compose mounts as a secret. `--wait` returns once the healthcheck sees serve listening; then
art98 checks the `ready` snapshot and the guest agent, and leaves the VM paused.

On Linux the VM listens on a Unix socket in a folder art98 makes and compose mounts. With the
tcp transport art98 adds [compose.tcp.yaml](../../compose.tcp.yaml), which publishes
`127.0.0.1:[ports] control` instead. Your `compose.override.yaml` is added last, when it
exists, for VNC and anything else of your own.

| Flag | Default | Effect |
|------|---------|--------|
| `--work PATH` | `[vm] work` | The work folder |

To see the screen over VNC, turn it on in `compose.override.yaml`: see [VNC](config.md#vnc).

If this work folder's `vm` container is already running and answers, `start` prints
`already running` and does nothing. A stopped or stale one is taken down first.

```
the VM is up and paused; render with `art98 render`
```

| Message | Cause |
|---------|-------|
| `work/image.json not found; run art98 up` | No prepared image in that folder |
| `no image localhost/art98:latest; run art98 up to build it` | The image is not built. `[vm] image` or `ART98_IMAGE` names another |
| `the container image is older than the code; run art98 up --rebuild` | The image holds an older copy of `core/art98` than the checkout |
| `the VM has no ready snapshot; run art98 up ...` | The image's disk has no `ready` snapshot |
| `the VM did not start: <compose's last line>` | `compose up` failed, or the healthcheck did not pass within 120 s. The message ends with the last 20 lines of the container's log, and the project is taken down |
| `... the container name "art98-vm" is already in use ...` | A container of that name that compose did not make, such as one from an art98 before compose. Remove it once with `docker rm art98-vm` |

### art98 vm status

Prints the state of the running VM. It takes no lock, so it is safe during a render.

```
up since 2026-11-11T09:00:00Z
state: paused
ready snapshot: yes
vnc: 127.0.0.1:5900
```

`state` is `busy` while a render holds the VM, `paused` between renders, and `running` otherwise.
`vnc` is `off` unless `compose.override.yaml` publishes the VNC port. If the image is older than the code,
a warning follows. With no VM it prints `down: the VM is not running; run art98 vm start`.

Exit code: 0 when the `ready` snapshot is there, 1 when the VM is down or has no `ready`.

### art98 vm stop

Runs `docker compose down` for this work folder's project: the container stops with a 20
second grace period, so the VM's run copy is deleted on the way out, and is removed. It also
deletes the socket folder, and keeps the token file.

It acts only on this work folder's compose project, so it never touches another checkout's VM.
With no container it prints `nothing to stop`.

| Flag | Default | Effect |
|------|---------|--------|
| `--work PATH` | `[vm] work` | The work folder |

## art98 render

Plays a scene on the running VM and writes the video. It attaches to the VM, reverts it to
`ready`, plays the scene, and ends by pausing the VM again. The scene options are in
[the scene API](../scenes/scene-api.md#command-line).

| Flag | Default | Effect |
|------|---------|--------|
| `--work PATH` | `[vm] work` | The work folder |
| `--wait S` | 0 | If the VM is busy, retry for up to `S` seconds, then fail with `busy`. Only "busy" is retried |

Errors:

| Message | Cause |
|---------|-------|
| `the VM is not running (nothing answers on <socket>); run art98 vm start` | No VM is running for this work folder |
| `the VM is busy: another render holds it` | A render holds the VM. Use `--wait S` |
| `the guest agent did not answer after the revert; run art98 vm stop then art98 vm start` | The guest hangs. Restart the VM |

An art98 error raised from a line of the scene file ends with the innermost such line:
`error: <message> (scene.py:LINE, in func)`. One with no scene line, such as a bad `state` file
named as a class attribute, prints without it. Other Python errors print the usual traceback.
`ART98_TRACE=1` prints the full traceback for every error.

## art98 ping

Attaches to the running VM, without the revert, and prints the guest's tick count and process
list. The desktop is as the last render left it. Its close pauses the VM again. Use it to check
that the VM answers.

```bash
uv run art98 ping
```

| Flag | Default | Effect |
|------|---------|--------|
| `--work PATH` | `[vm] work` | The work folder |
| `--wait S` | 0 | As for `render` |

Right after `art98 vm start`, the tick count is about 54,400, the moment the snapshot was saved.
It then moves on with each render.

Errors are as for [render](#art98-render).

## art98 up

From your disc and key to a prepared image, with QEMU and setup in the container. The host
needs Docker, Python and ffmpeg. It stops after setup and prints `art98 vm start`: it does not
start a VM. The code is
[setup/art98_setup/up.py](../../setup/art98_setup/up.py).

```bash
uv run art98 up --iso /path/to/win98se.iso
```

1. Builds the image `localhost/art98:latest` if it is missing, or always with `--rebuild`.
2. Copies `agent.exe`, `view.exe` and `mbr.bin` out of the image into `guest/build`
   if `view.exe` isn't there, since scenes send `VIEW.EXE` to the guest from the host.
3. If `image.json` is missing from the work directory, runs `docker compose run --rm setup`,
   the `setup` service of [compose.yaml](../../compose.yaml), with the disc mounted read-only.
   First it reads compose's resolved config and checks the disc and the key are there, since
   compose would stop half way and leave a container behind. The disc is `--iso`, or the one
   `compose.override.yaml` mounts. The key is the key file `compose.override.yaml` names; else
   `ART98_PRODUCT_KEY`; else a visible prompt. compose mounts it read-only at
   `/run/secrets/art98_key`. A key from the prompt goes to compose in its environment, never on
   a command line, and is not kept, so a resumed setup asks again.
4. Stops here and prints `art98 vm start`. Start the VM with that command.

| Flag | Default | Effect |
|------|---------|--------|
| `--iso PATH` | None | Your disc image. Needed only while setup isn't done, and only if `compose.override.yaml` does not mount one. Giving both is an error |
| `--work PATH` | `[vm] work` | The work directory, mounted at `/work` in the container |
| `--rebuild` | Off | Build the image even if it exists, with `docker compose build vm`. It fails if the engine does not hold the image afterwards |
| `--disk-mb N` | 2047 | As for `setup` |

To watch the install over VNC, turn it on for the `setup` service in `compose.override.yaml`
(see [VNC](config.md#vnc)) and point a view-only viewer at `127.0.0.1:5998`.

art98 calls only `docker compose` (or `ART98_ENGINE compose`). On a Podman host, install
`podman-docker` and `docker-compose`, which provide it; `podman-compose` does not work, since
it cannot run a service that is behind a profile. Files
the container writes in `work/` are yours on any engine. On a rootless one the container's root
is you. On rootful Docker the image's entry point,
[entry.py](../../core/art98/container/entry.py), sees from `/proc/self/uid_map` that its root is
the host's, and switches to the uid and gid the host passed before running art98.

## art98 serve

Runs inside the container, as the image's default command, for as long as the VM runs. It makes
a run copy of the disk in `/work/runs/vm-*`, restores `ready`, waits for the agent and serves the
host until `art98 vm stop`. You don't run it by hand: `art98 vm start` starts a container running
it. The protocol is in [the container design](../design/container.md#art98-serve-in-the-container).

| Flag | Default | Effect |
|------|---------|--------|
| `--work PATH` | `/work` | The mounted work directory |
| `--port N` | 7598 | TCP port inside the container |
| `--unix PATH` | None | Listen on this Unix socket instead, in a folder the host mounted. Screenshots can then be written into that folder |
| `--token-file PATH` | `/run/secrets/art98_token` | The token every connection must send first |
| `--vnc` | Off, or on when `ART98_VNC` is set | Show the screen on VNC port 5900 in the container |
| `--ready-timeout S` | 60 | How long to wait for the agent after the restore |

## Environment variables

| Variable | Read by | Effect |
|----------|---------|--------|
| `ART98_PRODUCT_KEY` | `cmd_setup`, `art98 up` | The product key when `--key` is not given. In the container, setup reads `/run/secrets/art98_key` when neither is there |
| `ART98_ENGINE` | `art98.container.host.Engine`, `doctor` | The binary to run instead of `docker`, such as `podman`. It only names the command: art98 runs `ART98_ENGINE compose` the same way |
| `ART98_HOST_UID`, `ART98_HOST_GID` | `art98.container.entry` | Passed by art98 to compose, which sets them on every container. On a rootful engine the container switches to them, so `work/` stays yours |
| `ART98_VNC` | `art98 serve`, `art98 setup` | Set to `1` (in `compose.override.yaml`) to turn on `serve --vnc` or `setup --watch` |
| `ART98_IMAGE`, `ART98_CONTAINER`, `ART98_WORK`, `ART98_TOKEN_PATH`, `ART98_SOCKET_DIR`, `ART98_CONTROL_PORT`, `ART98_ISO`, `ART98_DISK_MB` | `compose.yaml` | Set by art98 from `art98.toml` and the flags when it runs compose. Don't set them yourself, except `ART98_IMAGE` |
| `ART98_IMAGE` | `art98.settings` | The image name. Overrides `[vm] image` in [art98.toml](config.md), `localhost/art98:latest` by default |
| `ART98_TRANSPORT` | `art98.container.host.transport_name` | `unix` (the default on Linux) or `tcp` (the default elsewhere): how a client reaches the VM service. Overrides `[vm] transport` in [art98.toml](config.md#keys). See [timing](../design/container.md#timing) |
| `ART98_WATCH_DISPLAY` | `Setup._config` | The QEMU display for `--watch`, `gtk` by default. compose.yaml sets it to VNC in the container |
| `ART98_TRACE` | `art98.cli` | Set to `1` to get the full Python traceback instead of the one-line `error:` message |
| `ART98_TEST_WORK` | `test_stage.py` | The prepared work directory the stage tests boot |
| `ART98_TEST_WINEPREFIX` | `test_agent_wine.py` | A Wine prefix to reuse, so the Wine tests skip creating a new one |
| `ART98_TOKEN_FILE` | `art98 serve` (`read_token`) | The token file, when `--token-file` is not given. The default is `/run/secrets/art98_token` |
| `XDG_RUNTIME_DIR` | `VM.__init__`, `art98.service` | Where each VM's temporary folder for its QMP and serial sockets goes, and the VM service's socket folder. If unset, Python's default temp directory is used |

`MTOOLS_SKIP_CHECK=1` is not yours to set. Setup sets it for its own mtools calls.

## The work directory

Everything setup makes goes under `--work`. `work/` is in `.gitignore`.

| Path | From | Removed | What it is |
|------|------|---------|------------|
| `state.json` | Every step | | Finished steps. See [how steps are tracked](stages.md#how-steps-are-tracked) |
| `media/win98/` | `vm` | | Setup files from your disc. Microsoft's files, so keep them out of anything you publish |
| `boot.img` | `vm` | | Patched boot floppy |
| `AUTOEXEC.BAT`, `CONFIG.SYS` | `vm` | | Scratch copies of what went on the floppy. No key in them, and nothing reads them again |
| `install.img` | `vm` | End of `ready` | Raw disk. An installed copy of Windows: never share it |
| `MSBATCH.INF` | `vm` | Same stage | Answer file, with your key. Left behind only if the copy to the disk fails |
| `MSDOS.SYS` | `init_api` | Same stage | Edited copy |
| `golden.qcow2` | `init_api` | | The prepared disk and, after `ready`, the snapshot. An installed copy of Windows: never share it |
| `image.json` | `ready` | | `VMConfig` as JSON |
| `qemu.log` | Every VM | | QEMU's stdout and stderr. Appended, never cleared |
| `shots/install<boot>-<n>.png` | `setup` | | One frame every 30 seconds |
| `shots/init_api-<n>.png`, `shots/harden-<n>.png`, `shots/reboot-<n>.png` | `init_api`, `ready` | | The same, while waiting for the agent. May be absent if it starts within 30 seconds |
| `shots/probe.ppm` | `setup`, `init_api`, `ready` | | Last frame checked for prompts |
| `shots/ready.png` | `ready` | | The desktop in the snapshot |
| `shots/wizard.png`, `shots/shutdown.png` | On failure | | The screen when the wizard or a shutdown got stuck |
| `vm.token` | `art98 vm start` | Kept by `vm stop` | The token every connection sends first. Mode 0600. See [config](config.md#files-the-vm-uses) |
| `runs/` | `art98 vm start` (`vm-*`), and experiments (`render-*`) | `vm-*` at `vm stop`; `render-*` at the end of its run | Private copies of the image. Not made by `setup`. A killed container can leave a `vm-*` copy; the next `vm start` deletes it |

`shots/` is never cleared. Numbers restart with each run and overwrite old files, so a
shorter run leaves later frames from an earlier run in place. Check the times when
reading them.

### Moving the image, and running several VMs

`image.json` holds the absolute path of `golden.qcow2`. If that file is gone, `boot_local()` and
`private_stage()` use the file of the same name beside `image.json`, so a work directory can
be moved whole, and one prepared in the container (which records `/work/golden.qcow2`) works
on the host.

QEMU holds a write lock on the disk, so one work directory can run one VM at a time.
A second QEMU on the same disk fails with `Failed to get "write" lock` in `qemu.log`. The VM
service avoids this: `art98 vm start` runs the VM on a throwaway copy under `work/runs/vm-*`, and
a second `start` for the same folder finds the running VM. To run your own QEMU on the image,
give it its own directory (for experiments, with `boot_local()`):

1. Copy `golden.qcow2` into a new folder. `cp --reflink=auto` makes this instant on
   btrfs.
2. Copy `image.json` next to it.
3. Set `disk` in the copy to the absolute path of the new `golden.qcow2`.
4. Pass the new folder to `boot_local()`.

Each copy is a full installed Windows: never share it.

`setup` and `boot_local("work")` write to `work/golden.qcow2` itself, so the file's time
and size change. That is expected. The snapshot inside is not touched, and the next
`boot_local()` restores it. The VM service never writes to it: it runs on a copy.
