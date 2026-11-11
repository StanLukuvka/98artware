# Container

Built on the `container` branch, 2026-11-10, and tested from scratch.
The Windows 98 VM moves into a Docker container. The host keeps Python and ffmpeg and
needs nothing else. art98 calls only `docker`; on a Podman host the `podman-docker` package
provides that command, and art98 never asks which engine is behind it. One command goes from your disc image and product key to a prepared image, and
`art98 vm start` runs the VM. [The VM service](#the-vm-service) explains the split. [What was built](#what-was-built) at the end lists where the build differs from the plan.

```bash
uv run art98 up --iso ~/isos/win98se.iso
```

## Why

Today the VM runs on QEMU 10.2.2 from Fedora 44, unpacked by hand into `.tools/`. Nothing records
that build, and the `ready` snapshot only loads on the QEMU machine type that saved it
(`pc-i440fx-10.2`). A container pins QEMU, firmware and tools in one image that anyone can rebuild,
on any Linux distribution, and later on macOS or Windows through Docker Desktop.

QEMU runs the guest in software (TCG), so the container needs no `/dev/kvm` and no extra
privileges.

## Large files and the key

None of them go into the image. The image holds only programs, so it can be rebuilt, shared or
pushed without leaking anything.

| What | Size | How it gets in |
| --- | --- | --- |
| Disc image (ISO) | about 650 MB | Bind-mounted read-only, for `up` and `setup` only. |
| Product key | | A private file, mode 0600, mounted read-only at `/run/secrets/art98_key`, where setup reads it. `docker run` has no secrets outside swarm. The file is deleted when setup ends, so a resumed setup asks again. |
| `work/` | about 1.6 GB here | Bind-mounted read-write. It keeps the existing `golden.qcow2` and its `ready` snapshot. |
| Run copies | 416 MB each, mostly shared | Made inside the mounted `work/runs` with `cp --reflink=auto`, so on btrfs or XFS they cost almost nothing. Elsewhere it is a full copy. |

Why not the other ways:

- `COPY` of the ISO bakes 650 MB into an image layer, and it stays in the layer even if a later
  step deletes it.
- A build `ARG` or `ENV` with the key is saved in the image history (`docker history`), so anyone
  with the image can read it.
- An environment variable at `run` time shows in `docker inspect`. A mounted file's contents don't.

`work/` still holds the finished disk, an installed copy of Windows with the key in it, as it
does today. It is mounted, never copied, and `.dockerignore` lists it so a build can't pick it up by
accident.

## The image

The container code is split by job:

| File | Job |
| --- | --- |
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
load in the container with no new setup run. Checking this is the first step below.

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
`bridge.py`, which tracks request ids, events and timeouts, stays as it is and just connects over
TCP instead of a Unix socket.

Why a relay and not a remote procedure call for every `Bridge` method: the agent protocol already
carries ids, rows, events and a checksum, so passing it through needs no new format. Every scene,
prop and test keeps working against the same class. An RPC layer would need remote handles for
async calls, event forwarding and its own error mapping, and would repeat all of that.

### `art98 serve`, in the container

On start it makes the run copy under `work/runs/vm-*`, starts QEMU with `-loadvm ready`, and waits for the agent to
answer a ping. It then listens on port 7598 inside the container, or with `--unix PATH` on a
Unix socket. Each connection starts with two lines:

1. a token, which the host generates for each stage and passes in as a secret. A wrong token
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

One control connection owns the VM at a time. A second one is refused with `busy: the control
channel is held by another client`. When the owner goes away, serve cleans up in this order: drop
the agent relay, eject the disc, pause the VM, and only then free the slot. A client that connects
during the cleanup is refused, so it never has its relay dropped or its disc ejected by the
previous owner. A render that crashed or was killed releases the VM when its socket closes.

The `status` channel answers one JSON line with `busy`, `paused`, `snapshots` and `started_at`,
then closes. It takes no lock and asks QEMU nothing, so it is safe during a render.

serve runs until `art98 vm stop` or until QEMU dies. The VM outlives the host script and stays
paused until `vm stop`. The container has `--init` and no `--rm`: `vm stop` sends SIGTERM through
`--init`, serve deletes its run copy on the way out, and then the container is removed. A crashed
container keeps its logs for `docker logs`. Only a SIGKILL of the container leaves its run copy in
`work/runs/vm-*`, and the next `vm start` deletes it.

### On the host

- `art98/container/host.py`: `Engine` runs `docker`, or the binary `ART98_ENGINE` names, and
  `open_channel` opens the token handshake. `RemoteVM` has the methods the scene layer uses on
  `VM`: `screenshot`, `send_keys`, `load_snapshot`, `insert_disc`, `eject_disc`, `pause`, `resume`,
  `close`. `close` releases the VM; it does not stop it.
- `art98/service.py`: `start`, `stop` and `status` for the container, and `attach`, which a render
  uses to take the VM for one run. See [the VM service](#the-vm-service).
- `session.boot_local(work)` and `session.stage(work)` are QEMU on this host, for experiments only.
  No render path uses them.
- `revert`, the recorder and every scene are unchanged: they only see `Session.vm` and
  `Session.bridge`.

On Linux the host makes a private folder under `$XDG_RUNTIME_DIR/art98/` (mode 0700) and mounts it at
`/run/art98`, and serve listens on `/run/art98/serve.sock`. Elsewhere, or with
`ART98_TRANSPORT=tcp`, the port is published as `-p <bind>:<control>:7598`, by default `-p 127.0.0.1:7598:7598`, a fixed host port on
loopback only. The agent runs any Win32 call it's given, so the link must never be reachable
from the network, and the token stops other local users from connecting. A client in another
container attaches by setting `bind` to an address that container can reach, such as the
`docker0` gateway, and is given only the token file
([how](../setup/config.md#attach-from-another-container)).

`work/` is mounted with `--security-opt label=disable`, so SELinux doesn't need the files in it
relabelled.

### Who owns what the container writes

The container runs as its root, and what that root is depends on the engine. Under a rootless
one (Podman, rootless Docker) it is you, so files in `work/` come out yours. Under rootful Docker
it is the host's real root, and they would come out root's. `--user $(id -u)` is no fix: under
rootless Podman that uid maps to a subordinate id that can't write your files.

So the decision is made inside the container, and the host never asks which engine it has.
The host passes `-e ART98_HOST_UID=$(id -u) -e ART98_HOST_GID=$(id -g)` on every run. The image's
entry point, [entry.py](../../core/art98/container/entry.py), reads `/proc/self/uid_map`. The
identity map, `0 0 4294967295`, means the container shares the host's user namespace, so it
drops to that uid and gid (`setgroups([])`, `setgid`, `setuid`) and sets `HOME=/tmp` before
running art98. Any other map means a rootless engine, and nothing changes. It also stays put
when it isn't root, or when the host passed nothing or root. The secret files are the host
user's and mode 0600, so they stay readable after the switch.

### `art98 up`, on the host

1. Builds the image if it isn't there (or with `--rebuild`). It passes `--load` when `docker build` has it, since Docker CE's CLI against a Podman socket otherwise leaves the result in a buildx cache, and it fails if the engine's image isn't the ID the build reported.
2. Reads the key from `ART98_PRODUCT_KEY`, or asks for it without echo, and writes it to a
   private file to mount at `/run/secrets/art98_key`.
3. If `work/image.json` is missing, runs `art98 setup` in the container with the ISO mounted:
   about 40 minutes, resumable like today. `--watch` shows the screen through VNC on
   `127.0.0.1:5998` (`[ports] setup_vnc`, or `--vnc-port`), since GTK can't open from inside a container. Setup reads
   `ART98_WATCH_DISPLAY` for that. The key file is deleted when setup ends, finished or not, so
   a rerun asks for the key again.
4. Copies the guest programs out of the image into `guest/build` if they aren't
   there, since scenes send `VIEW.EXE` to the guest from the host.
5. Stops here and prints `art98 vm start`. The VM is started by that command, not by `up`.

Running `art98 up` again skips what's done. Everything in it can also be run by hand with
`docker build` and `docker run`, written out in the setup guide.

## The VM service

The VM is one long-lived container, not a stage booted for each render. This replaced the stage
that every render booted, on 2026-11-11. The split:

- `art98 up` builds the image and prepares `work/`, then stops and prints `art98 vm start`.
- `art98 vm start` starts one container, `art98-vm` by default, from the image. It carries the
  label `art98.work=<work folder>`, and writes `work/vm.token` (mode 0600, kept between starts)
  and `work/vm.cid`. The VM is left paused at `ready`.
- `art98 render` and `art98 ping` attach to the running VM. Without one they fail at once and say
  to run `art98 vm start`. `--wait S` waits for a busy VM.
- `art98 vm stop` stops the container, removes it and deletes the run copy.
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

**A lost client.** The Unix socket, the default on Linux, frees the lock as soon as the client's
process dies. Over TCP, both ends turn on keepalive (20 s idle, then 3 probes 10 s apart), so a
client that vanishes without closing its connection frees the lock in about a minute. Until
2026-11-11 such a client kept the lock until `vm stop` and `vm start`.

**Probes.** On real Docker and Podman, in [experiments/vm-service](../../experiments/vm-service/README.md):
the run copy's size stayed flat over 30 renders; a render killed with `kill -9` left the next attach
working, in about 0.05 s; a view-only VNC viewer did not change the frames. A normal viewer sends
input and was not tested; it would change the frames. See [configuration](../setup/config.md#vnc).

## Steps

1. **Image.** The Dockerfile and its ignore file. Check the QEMU version inside, then
   restore `ready` from the existing `work/` in the container and ping the agent. If the snapshot
   doesn't load, stop: making a new one changes the `ready` image and needs the owner's go-ahead.
2. **Stage.** `art98 serve`, `container.py` and the `boot` backend (replaced on 2026-11-11 by [the VM service](#the-vm-service)). Tests against a fake
   server, with no VM, plus a real test marked `container`.
3. **Timing.** Frames are 1.44 MB each. Measure a 300-frame recording through the rootless
   port forward against QEMU on the host, noting `/proc/pressure/cpu`. If the forward is too
   slow, switch the transport to a Unix socket in a mounted folder (Linux only), keeping TCP for
   other hosts.
4. **Up.** `art98 up` and setup in the container, tested from scratch on a separate work folder
   (`work-container/`), so the current `work/` and its snapshot are never touched.
5. **Docs.** The setup guide, the README, `status.md` and the tour. `.tools/` and `env.sh`
   become optional, kept for setup on the host and for experiments.

## Timing

300 frames recorded with `FrameRecorder.frame()`, since replaced by `Recorder` (sync, capture,
write to ffmpeg), on the existing `work/`, two rounds each. Measured before the VM service, so
"host QEMU" is QEMU run on the host, which renders no longer do. `/proc/pressure/cpu` read some avg10 0.00 before and after
every run.

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

## The CD drive

A scene's wallpaper goes to the guest on a disc, not through `put_file`. The host sends the
ISO on the serve channel: a JSON header line with the size (`insert_disc`, at most 64 MiB), then the raw bytes. Serve puts it in the guest's CD drive with QMP. `eject_disc` takes no
bytes. A revert sends `eject_disc` first, because `loadvm` doesn't remove QEMU's medium; a
session that never inserted a disc never sends it, so an older container image still works. On
Podman, real Docker and host QEMU, an insert took 5 to 8 ms, the guest saw it in 60 to
110 ms, setting a 1.44 MB wallpaper took 0.5 to 0.8 s and a revert with an eject took 75 to 145 ms
(CPU pressure avg10 1.3 to 2.0). The drive's QEMU id is read from `query-block` each time.
`RemoteVM` has no `disc_state()`, which the host-side `VM` class has. See
[README-p3](../../experiments/dialog-storm/README-p3.md).

## What was built

Where the build differs from, or adds to, the plan above:

- The handshake answers `ok` or `error <reason>`, so the host can tell a refused connection from
  a guest still booting.
- The Unix socket and shared-folder screenshots on Linux, from [Timing](#timing).
  `ART98_TRANSPORT` picks `unix` or `tcp`.
- A `save_snapshot` op, for the revert-test experiments. It only touched the run copy. Removed on
  2026-11-11 with the VM service: serve refuses it now.
- A 120 s limit for the first control connection, so a host that dies before connecting still
  ends the stage. Removed on 2026-11-11: the VM now stays up until `art98 vm stop`.
- serve handles SIGTERM, and stages run with `--init`. Python as PID 1 ignored SIGTERM, so
  `docker stop` had to fall back to SIGKILL.
- The token is `work/vm.token`, mode 0600, kept between starts and mounted with `work/`. On
  2026-11-11 this replaced the per-stage token file. `[vm] token_file` can put it elsewhere, and
  then it is mounted read-only on its own.
- On 2026-11-11 the two engine paths became one. art98 calls only `docker`, with Podman behind
  `podman-docker`. Both secrets are mounted files on every engine, and the container decides who
  owns what it writes ([above](#who-owns-what-the-container-writes)). Podman secrets, and the
  resume that reused the stored key, went with it.
- `image.json` records an absolute disk path. A work folder prepared in the container records
  `/work/golden.qcow2`, one prepared on the host records the host path. The VM service and `boot_local()` both fall
  back to the file of that name beside `image.json` (`session.image_disk`).
- The image is `localhost/art98:latest` (`ART98_IMAGE`), 385 MB. The guest programs built in it
  are byte for byte the ones built on the host.
- The ignore file is `.dockerignore` at the repository root, the build context, where
  `docker build` reads it by itself. Besides `work/`, `.tools/`, `.venv/`, `*.mp4` and `*.iso` it leaves out
  `.git/`, `.claude/`, `*.qcow2`, `*.img` and `guest/build/`. A probe build
  confirmed a decoy `work/`, `.iso` and `.qcow2` don't reach the build context.
- The code was first its own package, `art98_container` in `98artware_container/`. On
  2026-11-11 it was split by job: the backend moved into core as `art98.container`, and `up`
  and the Dockerfile into setup.

The checks below were run before the VM service. Then `art98 up` booted and pinged, and the
backend was a switch set by an environment variable. Both changed on 2026-11-11, see
[the VM service](#the-vm-service). The results stand for the code they ran on.

Checked:

- the image builds;
- `qemu-system-i386 --version` in it is 10.2.2 (`qemu-10.2.2-1.fc44`), with default machine
  `pc-i440fx-10.2`;
- the existing `ready` snapshot restores in the container on a run copy in `work/runs` (agent
  ready in 0.11 s, revert 0.05 s);
- the suite passes with the backend switch (since removed) set to `local` and to `container`;
- the MVP scene renders through the container;
- `art98 up` on the existing `work/` skips setup, boots and pings;
- VNC answers on loopback for a stage booted with a display;
- `art98 up` from scratch on an empty `work-container/`, with the key typed at the prompt:
  setup 1326 s, init_api 13 s, ready 55 s, about 25 minutes end to end with `/proc/pressure/cpu`
  at 0.00 throughout. The key secret was removed afterwards and no container was left behind.
  The stage tests pass on the new image, on host QEMU and in the container;
- the new image renders the MVP scene frame for frame the same as the old host-built `work/`:
  0 of 257 frames differ.

Checked on real rootful Docker (29.9.3, Fedora 44) on 2026-11-11, `/proc/pressure/cpu` some avg10
under 0.5 throughout:

- `art98 up` on the existing `work/` built the image in about 30 s, skipped setup, booted and
  pinged;
- no file in `work/` or `guest/build` came out owned by root or anyone but the user, so the
  switch to the host's uid works;
- `doctor` reports both host QEMU and the container usable, and the stage suite passes in the
  container (18 passed);
- the proof scene `examples/blank_start` renders frame for frame the same as a host QEMU render:
  0 of 263 frames differ. Two host QEMU renders can differ from each other, but only in the
  blinking Notepad caret (a 2 x 15 px box), which depends on timing;
- no container was left behind.

After this the default backend became `container`. The switch itself was removed on 2026-11-11.

## Not in this design

- VMs on another machine. Only a published port on loopback is covered; across a network the
  link would need TLS.
- Audio, which is still deferred.
- Moving the recorder into the container. It stays on the host; `Recorder`, which replaced
  `FrameRecorder`, was built there.
