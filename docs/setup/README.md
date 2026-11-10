# Part 1: preparing the VM

`art98 setup` (`art98 prep` still works as an alias) turns your Windows 98 SE disc image into a desktop that restores to
the same state every time. It runs Setup with no input, cleans up the result, and
saves a QEMU snapshot called `ready`. Everything else in art98 starts from that
snapshot.

This part covers the setup tool, `setup/`. To drive the finished desktop, see
[Part 2](../scenes/README.md).

![How the host, QEMU and the guest fit together](../diagrams/system-overview.png)

## What it produces

| File | What it is |
|------|------------|
| `work/golden.qcow2` | The installed disk, with the snapshot `ready` inside it. About 415 MB on disk, 2 GB virtual |
| `work/image.json` | The `VMConfig` that created the snapshot. `boot()` reads it, and the snapshot only loads on the same hardware |
| `work/state.json` | The steps that have finished |
| `work/shots/ready.png` | What the desktop looked like when the snapshot was saved |

![The prepared desktop at 800x600](../assets/prep/ready-desktop.png)

The desktop is Windows 98 SE at 800x600 in 16-bit colour, with screensavers,
system sounds and power saving off, and `C:\ART98\AGENT.EXE` already running.
[image.md](image.md) lists what is on it.

## What you need

- **A Windows 98 SE disc image and product key of your own.** The disc must boot
  from an emulated floppy and hold a `WIN98` folder. The tool was run on one OEM
  disc only, see [what a different disc needs](troubleshooting.md#a-different-disc).
- **Docker and ffmpeg**, for the [container path](#quick-path-in-a-container).
  The container holds QEMU 10.2.2, mtools, 7-Zip and the guest programs, so the host needs
  nothing else. art98 calls only `docker`. On a Podman host, install `podman-docker`, which
  provides that command.
- **Or, for the [local path](#quick-path-on-the-host), Linux with these tools.**
  `art98 doctor` checks them.

  | Tool | Fedora package | Debian and Ubuntu package | Used for |
  |------|----------------|---------------------------|----------|
  | `qemu-system-i386` | `qemu-system-x86` | `qemu-system-x86` | Running the VM |
  | `qemu-img` | `qemu-img` | `qemu-utils` | Converting the disk to qcow2 |
  | `mcopy` and the rest of mtools | `mtools` | `mtools` | Editing the FAT floppy and disk from the host |
  | `7z` | `7zip` | `7zip` (`p7zip-full` on Debian 12 and older) | Unpacking the disc |
  | `ffmpeg` | `ffmpeg` | `ffmpeg` | Not used by `setup`. Scenes need it to encode video |
  | `make`, `as` | `make`, `binutils` | `make`, `binutils` | Building `mbr.bin` |
  | `i686-w64-mingw32-gcc` | `mingw32-gcc` | `gcc-mingw-w64-i686` | Building `agent.exe` |

  The `ready` snapshot only loads on the QEMU machine type that saved it, so an image made
  with one QEMU version may not restore on another. The container pins the version.
- **Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).** art98 has no
  runtime Python dependencies.
- **About 3 GB of free disk space during the build**, and 40 minutes. The raw
  install disk is 2 GB, and it exists next to the qcow2 until the `ready` step deletes it.

KVM is not used. See [why TCG](image.md#hardware).

## Licence

Nothing from Microsoft is in this repository. You supply the disc and the key.

**Running `art98 setup` accepts the Windows 98 licence agreement on your behalf.** The
answer file sets `ShowEula=0`, and on OEM discs that show the agreement anyway,
setup selects "I accept the Agreement" by keystroke. Only run it with a disc and
key you are licensed to use.

Do not share `golden.qcow2`: it is an installed copy of Windows 98. It also holds your key
in clear text, see [the key on the image](image.md#your-product-key-is-on-the-image).

## Quick path in a container

One command builds the image, runs setup in the container and checks the result:

```bash
uv run art98 up --iso /path/to/win98se.iso
```

It asks for your product key without echoing it, or reads `ART98_PRODUCT_KEY`. Setup takes
25 to 40 minutes, depending on host load: about 25 on a quiet one. Add `--watch` and point a VNC viewer at `127.0.0.1:5998` to see the screen.
If setup stops, run the same command again: it resumes, and asks for the key again, since
nothing keeps it between runs. Running `up` again once everything is done only boots the
desktop and pings the agent.

Then render through the container:

```bash
ART98_BACKEND=container uv run art98 render examples/mvp/mvp.py
```

`--backend container` on `render` or `ping` does the same for one command. The default backend
is still `local`. See [the container design](../design/container.md) for how it works.

### By hand

`art98 up` runs these. Build the image from the repository root:

```bash
docker build -t localhost/art98:latest -f setup/Dockerfile .
```

Put the key in a private file, typed without echo. `docker run` has no secrets outside swarm,
so the file is mounted read-only where setup looks for it:

```bash
read -rs KEY && (umask 077 && printf %s "$KEY" > "$XDG_RUNTIME_DIR/art98_key") && unset KEY
```

Run setup, with `work/`, the disc and the key mounted. `ART98_HOST_UID` and `ART98_HOST_GID`
make the files setup writes in `work/` yours on rootful Docker. Rootless engines ignore them,
since their root is you already:

```bash
docker run --rm --init --security-opt label=disable -v "$PWD/work:/work" -e ART98_HOST_UID=$(id -u) -e ART98_HOST_GID=$(id -g) -v /path/to/win98se.iso:/media/win98.iso:ro -v "$XDG_RUNTIME_DIR/art98_key:/run/secrets/art98_key:ro" localhost/art98:latest setup --work /work --iso /media/win98.iso
```

Then delete the file, since the key is in the finished image:

```bash
rm "$XDG_RUNTIME_DIR/art98_key"
```

A stage container runs `art98 serve`, which needs a token in `/run/secrets/art98_token` and
waits for the host to connect. `art98.container.host` starts those for you. Which file does what is in
[the container design](../design/container.md#the-image).

## Quick path on the host

Install the tools:

```bash
sudo dnf install qemu-system-x86 qemu-img mtools 7zip ffmpeg make binutils mingw32-gcc
```

On Debian or Ubuntu:

```bash
sudo apt install qemu-system-x86 qemu-utils mtools 7zip ffmpeg make binutils gcc-mingw-w64-i686
```

Build the two files that go on the Windows disk, `guest/build/agent.exe` and
`guest/build/mbr.bin`:

```bash
make -C guest
```

Check the host:

```bash
uv run art98 doctor
```

Give setup your key without leaving it in your shell history:

```bash
read -rs ART98_PRODUCT_KEY && export ART98_PRODUCT_KEY
```

Build the image. This takes about 40 minutes and needs no input:

```bash
uv run art98 setup --iso /path/to/win98se.iso
```

Check that it works:

```bash
uv run art98 ping
```

`ping` restores the snapshot and prints what is running in the guest:

```
guest tick count: 54390
0xff0f5f99 C:\WINDOWS\SYSTEM\KERNEL32.DLL
0xffff8b21 C:\WINDOWS\SYSTEM\MSGSRV32.EXE
0xffff8319 C:\WINDOWS\SYSTEM\SPOOL32.EXE
0xffff91cd C:\WINDOWS\SYSTEM\MPREXE.EXE
0xfffff38d C:\WINDOWS\SYSTEM\mmtask.tsk
0xffffdc1d C:\WINDOWS\EXPLORER.EXE
0xfffe4865 C:\ART98\AGENT.EXE
0xfffe4025 C:\WINDOWS\SYSTEM\SYSTRAY.EXE
```

If a step fails, fix the cause and see
[recovering from a failed step](troubleshooting.md#recovering-from-a-failed-step).

## What happens

Setup runs four steps in order, named after the path from a blank machine to a
scriptable desktop: VM, setup, init api, ready. Each one is recorded in
`work/state.json`. Builds made with the old five stage names (`media`, `disk`,
`install`, `patch`, `harden`) still count as done, and `--from` accepts those names too.

![The four setup steps, their inputs and their outputs](../diagrams/prep-pipeline.png)

| Step | Old stages | Time on the two full runs logged | Result |
|------|------------|---------------------------------|--------|
| `vm` | `media`, `disk` | 1 s, then 0 to 9 s | Setup files unpacked, boot floppy patched, raw disk with Setup, the answer file and the agent on it |
| `setup` | `install` | 2083 s and 2268 s | Windows installed |
| `init_api` | `patch` | 1 to 2 s, plus one extra boot | `MSDOS.SYS` edited, disk converted to qcow2, the agent seen answering |
| `ready` | `harden` | 78 s and 106 s | Settings applied, snapshot saved |

The extra boot in `init_api` is new, so the logged times do not include it.

This is Setup running, from file copy to the first desktop, with one frame every
few minutes:

![Time-lapse of Windows 98 Setup running under setup](../assets/prep/install-timelapse.gif)

## The rest of this part

| Page | Covers |
|------|--------|
| [stages.md](stages.md) | Each step: inputs, outputs, what happens inside, how it fails, what `--from` redoes |
| [cli.md](cli.md) | `art98 doctor`, `setup`, `ping`, `up` and `serve`, every flag, environment variables, the work directory |
| [image.md](image.md) | What is on the finished image, every setting and why, the snapshot, the VM hardware |
| [troubleshooting.md](troubleshooting.md) | Setup quirks, the stall rule, recovery, other discs |

Audio is deferred. art98 is video only for now, though the VM keeps its Sound
Blaster.
