# Container

The Windows 98 VM runs in a Docker container. The host keeps Python and ffmpeg and
needs nothing else. How the containers run is written down in [compose.yaml](../../compose.yaml),
and art98 calls only `docker compose`; on a Podman host the `podman-docker` and `docker-compose`
packages provide that command, and art98 never asks which engine is behind it. One command goes from your
disc image and product key to a prepared image, and `art98 vm start` runs the VM.
[The VM service](#the-vm-service) explains the split.

```bash
uv run art98 up --iso ~/isos/win98se.iso
```

## Why

Why the VM is in a container: [decision 5](decisions.md#5-qemu-in-a-container-python-the-recorder-and-ffmpeg-on-the-host). The `ready` snapshot only loads on the QEMU
machine type that saved it, `pc-i440fx-10.2`, so the image pins
`qemu-system-x86-core-10.2.2-1.fc44`. The same image runs on any Linux distribution, and later on
macOS or Windows through Docker Desktop.

QEMU runs the guest in software (TCG), so the container needs no `/dev/kvm` and no extra
privileges.

## Large files and the key

None of them go into the image. The image holds only programs, so it can be rebuilt and shared.

| What | Size | How it gets in |
| --- | --- | --- |
| Disc image (ISO) | about 650 MB | Bind-mounted read-only, for `up` and `setup` only. |
| Product key | | The compose secret `art98_key`, a file mounted read-only at `/run/secrets/art98_key`, where setup reads it. It comes from `ART98_PRODUCT_KEY` or the prompt, or from a key file named in the gitignored `compose.override.yaml`. Windows 98 product keys are public and reusable, so this is about keeping the image and the repository clean, not about secrecy. |
| `work/` | about 1.6 GB here | Bind-mounted read-write. It keeps the existing `golden.qcow2` and its `ready` snapshot. |
| Run copies | 416 MB each, mostly shared | Made inside the mounted `work/runs` with `cp --reflink=auto`, so on btrfs or XFS they cost almost nothing. Elsewhere it is a full copy. |

A `COPY` of the ISO would keep 650 MB in a layer even after a later step deletes it. The key goes
in a mounted file, not a build `ARG` or `ENV`, so it is never in `docker history` or
`docker inspect`. The real secret is the VM token, a file too: see [The VM service](#the-vm-service).

`work/` stays private because it holds the finished disk, an installed copy of Windows 98. It is
mounted, never copied, and `.dockerignore` lists it so a build can't pick it up by accident.

## The image

The container code is split by job:

| File | Job |
| --- | --- |
| [compose.yaml](../../compose.yaml) | The `vm` and `setup` services: build, mounts, secrets, healthcheck, commands |
| [compose.tcp.yaml](../../compose.tcp.yaml) | On top of it for the tcp transport: the loopback port instead of the socket folder |
| [compose.override.example.yaml](../../compose.override.example.yaml) | A start for your own `compose.override.yaml`: the key file, the disc, VNC |
| [core/art98/container/compose.py](../../core/art98/container/compose.py) | The compose project name, files and `ART98_*` variables art98 passes it |
| [setup/Dockerfile](../../setup/Dockerfile) | The image, built with the repository root as its context |
| [.dockerignore](../../.dockerignore) | What stays out of that context: `work/` above all |
| [setup/art98_setup/up.py](../../setup/art98_setup/up.py) | `art98 up`: builds the image, runs setup in it, copies the guest programs out |
| [core/art98/container/serve.py](../../core/art98/container/serve.py) | `art98 serve`, inside the container: boots `ready` on a run copy and relays the agent and a control channel |
| [core/art98/container/entry.py](../../core/art98/container/entry.py) | The image's entry point: on a rootful engine, switch to the host's uid, then run the CLI |
| [core/art98/container/host.py](../../core/art98/container/host.py) | On the host: `Engine`, `open_channel` and `RemoteVM` |
| [core/art98/service.py](../../core/art98/service.py) | The VM service: `start`, `stop`, `status` and `attach`, which every render uses |
| [core/art98/settings.py](../../core/art98/settings.py) | `art98.toml`: names, ports and the work folder, with their defaults |
| [core/tests/test_container.py](../../core/tests/test_container.py), [test_stage.py](../../core/tests/test_stage.py) | serve and the host side on a fake VM; the real VM through the service (`test_stage.py`, with `art98 vm start` running) |
| [setup/tests/test_up.py](../../setup/tests/test_up.py) | `up`'s setup run and the image build, without an engine |

Building images is setup's job, and running the VM is core's. `art98.service` starts one
long-lived container from the image, and each render attaches to it with `art98.attach()`.
`art98.session.boot_local()` is QEMU on this host, for experiments only.

`setup/Dockerfile` is built from the repository root, in two stages:

1. **Build.** `fedora:44` with `mingw32-gcc`, `binutils` and `make` runs `make -C guest`
   and produces `agent.exe`, `view.exe` and `mbr.bin`. The host no longer needs a cross-compiler.
2. **Run.** `fedora-minimal:44` with `qemu-system-x86-core-10.2.2-1.fc44` and `qemu-img` of the
   same version, plus `mtools`, `7zip` and `python3`, then the two art98 packages and the guest
   programs from stage 1.

Fedora 44's release repository is frozen, so pinning the exact package version keeps the same
build available. It's the build that saved the current `ready` snapshot, so that snapshot should
Fedora 44's release repository is frozen, so pinning the exact package version keeps the same
build available. It's the build that saved the current `ready` snapshot, so that snapshot loads in
the container with no new setup run.

The image is `localhost/art98:latest` (`ART98_IMAGE`), 385 MB. Its guest programs are byte for
byte the ones built on the host. `.dockerignore` leaves out `work/`, `.tools/`, `.venv/`, `.git/`,
`.claude/`, `guest/build/`, `*.mp4`, `*.iso`, `*.qcow2` and `*.img`; a probe build confirmed a decoy
`work/`, `.iso` and `.qcow2` don't reach the build context.

## Who runs what

```
host                                  container (one per vm start)
----                                  -------------------------
scene.py, art98.anim                  art98 serve
Bridge (client half, unchanged)  ──▶  relay  ──▶ COM1 socket ──▶ QEMU ──▶ agent.exe
RemoteVM: screenshot, keys, revert ─▶ control ─▶ QMP
Recorder + ffmpeg       ◀── PPM frames ──┘
```

On Linux the two channels run over a Unix socket in a folder the host mounts into the container,
and QEMU writes each screenshot straight into that folder. Elsewhere they run over TCP on
loopback and the frame bytes follow the reply. See [Timing](#timing).

The container is the bridge between the host and the VM. It owns QEMU and the run copy of the
disk, and it relays the agent's protocol out to the host. The host keeps the client half:
`bridge.py`, which tracks request ids, events and timeouts, stays as it is; only the socket it
connects to changes. Why a relay: [decision 5](decisions.md#5-qemu-in-a-container-python-the-recorder-and-ffmpeg-on-the-host).

### `art98 serve`, in the container

On start it makes the run copy under `work/runs/vm-*`, starts QEMU with `-loadvm ready`, and waits for the agent to
answer a ping. It then listens on port 7598 inside the container, or with `--unix PATH` on a
Unix socket. Each connection starts with two lines:

1. the token from `work/vm.token` (or `[vm] token_file`), which `art98 vm start` makes once
   and compose mounts as the secret at `/run/secrets/art98_token`. A wrong token
   gets `error wrong token` and the connection closes;
2. the channel: `agent`, `control` or `status`.

serve answers `ok`, or `error <reason>`. The host waits for that line, because a rootless port
forward accepts a connection before anything listens behind it and then hangs up.

- **agent** relays bytes both ways between the connection and the agent's serial socket,
  untouched. QEMU's serial socket takes one client, so a new agent connection replaces the old
  one. It is refused unless a control connection is open.
- **control** takes JSON lines, one request and one reply each:

  | Request | Reply |
  | --- | --- |
  | `{"op": "screenshot", "format": "ppm"}` | `{"ok": true, "size": N}`, then N raw bytes |
  | the same with `"shared": true`, on a Unix socket | `{"ok": true, "file": "frame.ppm"}`, written into the shared folder |
  | `{"op": "insert_disc", "size": N}`, then N raw bytes | `{"ok": true}`. An ISO of at most 64 MiB |
  | `{"op": "eject_disc"}` | `{"ok": true}` |
  | `{"op": "save_snapshot", "snapshot": "warm"}` | `{"ok": false, "error": "save_snapshot is not served"}`. The `ready` snapshot can't be overwritten through the service |
  | `{"op": "send_keys", "keys": ["alt", "f"], "hold_ms": 80}` | `{"ok": true}` |
  | `{"op": "revert", "snapshot": "ready"}` | `{"ok": true}` |
  | `{"op": "pause"}`, `{"op": "resume"}` | `{"ok": true}` |

  Errors come back as `{"ok": false, "error": "..."}` and are raised as `QemuError` on the host.

One control connection owns the VM; a second gets `busy: the control channel is held by another
client`. Release is described under [The VM service](#the-vm-service). A render that crashed or was
killed releases the VM when its socket closes.

The `status` channel answers one JSON line with `busy`, `paused`, `snapshots` and `started_at`,
then closes. It takes no lock and asks QEMU nothing, so it is safe during a render.

serve runs until `art98 vm stop` or until QEMU dies. The VM outlives the host script and stays
paused until `vm stop`. The container has `init: true`: `vm stop` runs `compose down`, which sends
SIGTERM through init, serve deletes its run copy on the way out, and then the container is
removed. A container that crashed during `vm start` has its last 20 log lines printed before it
is taken down. Only a SIGKILL of the container leaves its run copy in
`work/runs/vm-*`, and the next `vm start` deletes it.

### On the host

- `art98/container/host.py`: `Engine` runs `docker`, or the binary `ART98_ENGINE` names, and
  `open_channel` opens the token handshake. `art98/container/compose.py` puts `compose`, the
  project and the files in front of each command. `RemoteVM` has the methods the scene layer uses on
  `VM`: `screenshot`, `send_keys`, `load_snapshot`, `insert_disc`, `eject_disc`, `pause`, `resume`,
  `close`. `close` releases the VM; it does not stop it.
- `art98/service.py`: `start`, `stop` and `status` for the container, and `attach`, which a render
  uses to take the VM for one run. See [the VM service](#the-vm-service).
- `image.json` records an absolute disk path (`/work/golden.qcow2` when prepared in the container).
  The VM service and `boot_local()` fall back to the file of that name beside `image.json`
  (`session.image_disk`).
- `session.boot_local(work)` and `session.stage(work)` are QEMU on this host, for experiments only.
  No render path uses them.
- `revert`, the recorder and every scene are unchanged: they only see `Session.vm` and
  `Session.bridge`.

On Linux the host makes a private folder under `$XDG_RUNTIME_DIR/art98/` (mode 0700), compose
mounts it at `/run/art98`, and serve listens on `/run/art98/serve.sock`. Elsewhere, or with
`ART98_TRANSPORT=tcp`, art98 adds `compose.tcp.yaml`, which publishes `127.0.0.1:<control>:7598`,
a fixed host port on loopback only. The agent runs any Win32 call it's given, so the link must
never be reachable from the network, and the token stops other local users from connecting. A
client in another container attaches through a port the user adds in `compose.override.yaml`
on an address that container can reach, such as the `docker0` gateway, and is given only the
token file ([how](../setup/config.md#attach-from-another-container)).

The healthcheck passes once the socket (or port) exists, and serve listens only after the guest
agent has answered, so `compose up --wait` is the readiness gate. It checks every 5 s, and every
second while starting on Docker; Podman ignores `start_interval`.

`work/` is mounted with `security_opt: [label=disable]`, so SELinux doesn't need the files in it
relabelled.

### Who owns what the container writes

The container runs as its root, and what that root is depends on the engine. Under a rootless
one (Podman, rootless Docker) it is you, so files in `work/` come out yours. Under rootful Docker
it is the host's real root, and they would come out root's. `--user $(id -u)` is no fix: under
rootless Podman that uid maps to a subordinate id that can't write your files.

So the decision is made inside the container, and the host never asks which engine it has.
art98 passes `ART98_HOST_UID` and `ART98_HOST_GID` (your uid and gid) to compose, which sets
them on every container. The image's
entry point, [entry.py](../../core/art98/container/entry.py), reads `/proc/self/uid_map`. The
identity map, `0 0 4294967295`, means the container shares the host's user namespace, so it
drops to that uid and gid (`setgroups([])`, `setgid`, `setuid`) and sets `HOME=/tmp` before
running art98. Any other map means a rootless engine, and nothing changes. It also stays put
when it isn't root, or when the host passed nothing or root. The secret files are the host
user's and mode 0600, so they stay readable after the switch.

### `art98 up`, on the host

It builds the image with `compose build vm` if it isn't there (or with `--rebuild`), copies
the guest programs out, and runs setup with `compose run --rm setup`. It fails if the engine
holds no image under the name after the build: Docker CE's CLI against a Podman socket used to
leave it in a buildx cache. Before the run it reads compose's resolved config and checks the disc
and the key, because compose stops only after it has made the container, and leaves it behind.
A key that is not in a file comes from `ART98_PRODUCT_KEY` or a prompt, and reaches compose in
its environment, so a rerun asks for it again. The other steps are in
[art98 up](../setup/cli.md). `up` stops before starting the VM and prints `art98 vm start`.

## The VM service

The VM is one long-lived container, not a stage booted for each render. The split:

- `art98 up` builds the image and prepares `work/`, then stops and prints `art98 vm start`.
- `art98 vm start` runs `compose up -d --wait vm`: one container, `art98-vm` by default, in the
  compose project `art98-<hash8>` of the work folder, so `down` never touches another checkout's
  VM. It writes `work/vm.token` first (mode 0600, kept between starts). The VM is left paused at
  `ready`.
- `art98 render` and `art98 ping` attach to the running VM. Without one they fail at once and say
  to run `art98 vm start`. `--wait S` waits for a busy VM.
- `art98 vm stop` runs `compose down`: it stops the container, removes it and deletes the run copy.
- `art98 vm status` reads the `status` channel and the engine. It takes no lock.

**The lock.** The control connection is the lock. The first one wins, and the others are refused
as busy. The `status` channel is lock-free.

**Attaching**, in order: `status` (the VM must be up with a `ready` snapshot; a busy VM is busy),
then the control channel (the lock), then the agent channel. Then the VM is resumed, reverted to
`ready` (eject, then `loadvm`), and pinged. The revert comes before the ping, so a guest hung by a
killed render is fixed first. `art98 ping` skips the revert.

**Releasing**, in order: drop the agent relay, eject the disc, pause the VM, and free the lock
last. The client's close waits until the lock is free, so the next attach can't race the cleanup.
Freeing the lock last fixes a release race that the VM tests found; `test_serve.py` covers it.

**A lost client and a VNC viewer.** See [Configuration](../setup/config.md#transport-and-a-lost-client).
The probes are in [experiments/vm-service](https://github.com/StanLukuvka/98artware/blob/dev/experiments/vm-service/README.md): the run copy
stayed flat over 30 renders, and the next attach worked about 0.05 s after a `kill -9`. A view-only
VNC viewer did not change the frames. A normal viewer sends input and was not tested; it would
change the frames. See [configuration](../setup/config.md#vnc).

## Timing

300 frames, each a sync, a capture and an ffmpeg write, on the existing `work/`, two rounds each.
`/proc/pressure/cpu` read some avg10 0.00 before and after every run. "Host QEMU" is QEMU run on
the host, measured before renders moved to the VM service.

| Backend | 300 frames | Per frame | Sync | Capture | ffmpeg write |
| --- | --- | --- | --- | --- | --- |
| host QEMU | 1.68 to 1.89 s | 5.6 to 6.3 ms | 2.3 to 2.8 ms | 2.3 to 2.6 ms | 0.9 ms |
| container, TCP through the rootless port forward | 2.90 to 3.03 s | 9.7 to 10.1 ms | 5.1 to 5.2 ms | 3.6 to 3.8 ms | 1.0 ms |
| container, Unix socket, frames sent on it | 2.69 to 2.77 s | 9.0 to 9.2 ms | 4.5 to 4.7 ms | 3.5 ms | 0.9 ms |
| container, Unix socket, frames in the shared folder | 2.05 to 2.10 s | 6.8 to 7.0 ms | 3.0 to 3.1 ms | 2.9 ms | 0.9 ms |

Sync time is not network latency. A bare ping takes 5.0 ms both inside the container and on the
host, because the agent answers on its own polling period, so a frame that fits in one period
costs about one period. Sending the 1.44 MB frame over the socket pushed each frame into a
second period, and the port forward added a little more. Writing the frame into the shared folder
brings the container within about 10% of host QEMU, so that is the default on Linux. TCP stays for
Docker Desktop, where a Unix socket can't cross the VM boundary. A boot takes
about 0.3 s in the container against 0.1 s locally.
In the revert test, `loadvm ready` in a running VM took 0.06 to 0.2 s and kept the bridge
connected. Capture over serial would take about 3 s per frame, against about 6.5 ms through QMP,
so capture stays outside the guest.

## The CD drive

A scene's wallpaper goes to the guest on a disc, not through `put_file`. The host builds a small
ISO 9660 level 1 disc (`disc.py`, 8.3 capital names) and sends it on the serve channel: a JSON header line with the size (`insert_disc`, at most 64 MiB), then the raw bytes. Serve puts it in the guest's CD drive, `D:`, with QMP. There is no AutoPlay and no Explorer window. After the insert the scene polls every 50 ms and gives up after 2 s; the first read succeeded at once in every run. `eject_disc` takes no
bytes. A revert sends `eject_disc` first, because `loadvm` doesn't remove QEMU's medium; a
session that never inserted a disc never sends it, so an older container image still works. On
Podman, real Docker and host QEMU, at CPU pressure avg10 1.3 to 2.0, an insert took 5 to 8 ms, the guest saw it in 60 to
110 ms, setting a 1.44 MB wallpaper took 0.5 to 0.8 s and a revert with an eject took 75 to 145 ms
(a quiet-host set is in [Scene API](../scenes/scene-api.md)). A revert's eject opens the tray with force, removes the medium and closes the tray. The drive's QEMU id is read from `query-block` each time, because it was `device[5]` on one host and `device[4]` in the plan.
`RemoteVM` has no `disc_state()`, which the host-side `VM` class has. See
[README-p3](https://github.com/StanLukuvka/98artware/blob/dev/experiments/dialog-storm/README-p3.md).

## What was built

The build notes and the lists of checks, with their dates, are in
[build history](../archive/build-history.md#container-build-plan-and-as-built-notes). The
measured results that still hold:

- The image builds, with QEMU 10.2.2 (`qemu-10.2.2-1.fc44`) and default machine `pc-i440fx-10.2`.
  The existing `ready` snapshot restores in the container on a run copy in `work/runs`: agent ready
  in 0.11 s, revert 0.05 s.
- From scratch, `art98 up` on an empty work folder took setup 1326 s, init_api 13 s and ready 55 s,
  about 23 minutes, with `/proc/pressure/cpu` at 0.00. The container-built image renders the MVP
  scene with 0 of 257 frames different from the host-built one.
- On rootful Docker 29.9.3 (Fedora 44, CPU pressure some avg10 under 0.5), `art98 up` on the
  existing `work/` built the image in about 30 s. No file in `work/` or `guest/build` came out
  owned by root, and `recipes/scenes/blank_start` gave 0 of 263 frames different from a host QEMU render.
  Two host QEMU renders can differ from each other, only in the blinking Notepad caret (a 2 x 15 px
  box), which depends on timing. The stage suite passed in the container (18 passed).

## Not in this design

- VMs on another machine. Only a published port on loopback is covered; across a network the
  link would need TLS.
- Audio, which is still deferred.
- Moving the recorder into the container. It stays on the host.
