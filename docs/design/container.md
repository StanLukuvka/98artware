# Container

Built on the `container` branch, 2026-11-10, and tested from scratch.
The Windows 98 VM moves into a Podman or Docker container. The host keeps Python and ffmpeg and
needs nothing else. One command goes from your disc image and product key to a desktop ready to
render. [What was built](#what-was-built) at the end lists where the build differs from the plan.

```bash
uv run art98 up --iso ~/isos/win98se.iso
```

## Why

Today the VM runs on QEMU 10.2.2 from Fedora 44, unpacked by hand into `.tools/`. Nothing records
that build, and the `ready` snapshot only loads on the QEMU machine type that saved it
(`pc-i440fx-10.2`). A container pins QEMU, firmware and tools in one image that anyone can rebuild,
on any Linux distribution, and later on macOS or Windows through Docker Desktop or Podman machine.

QEMU runs the guest in software (TCG), so the container needs no `/dev/kvm` and no extra
privileges.

## Large files and the key

None of them go into the image. The image holds only programs, so it can be rebuilt, shared or
pushed without leaking anything.

| What | Size | How it gets in |
| --- | --- | --- |
| Disc image (ISO) | about 650 MB | Bind-mounted read-only, for `up` and `setup` only. |
| Product key | | A Podman secret, read by setup from `/run/secrets/art98_key`. `docker run` has no secrets outside swarm, so Docker gets a private file mounted read-only at the same path. |
| `work/` | about 1.6 GB here | Bind-mounted read-write. It keeps the existing `golden.qcow2` and its `ready` snapshot. |
| Run copies | 416 MB each, mostly shared | Made inside the mounted `work/runs` with `cp --reflink=auto`, so on btrfs or XFS they cost almost nothing. Elsewhere it is a full copy. |

Why not the other ways:

- `COPY` of the ISO bakes 650 MB into an image layer, and it stays in the layer even if a later
  step deletes it.
- A build `ARG` or `ENV` with the key is saved in the image history (`podman history`), so anyone
  with the image can read it.
- An environment variable at `run` time shows in `podman inspect`. A secret doesn't.

`work/` still holds the finished disk, an installed copy of Windows with the key in it, as it
does today. It is mounted, never copied, and `Containerfile.dockerignore` lists it so a build can't pick it up by
accident.

## The image

Everything for the container lives in its own folder,
[98artware_container/](../../98artware_container/README.md): the `Containerfile`, its ignore
file, the package `art98_container` (`serve.py` for inside, `host.py` for the host) and its
tests. The rest of art98 reaches it only through `session.boot(backend="container")` and the
`up` and `serve` commands.

`98artware_container/Containerfile` is built from the repository root, in two stages:

1. **Build.** `fedora:44` with `mingw32-gcc`, `binutils` and `make` runs `make -C windows_handlers`
   and produces `agent.exe`, `view.exe` and `mbr.bin`. The host no longer needs a cross-compiler.
2. **Run.** `fedora-minimal:44` with `qemu-system-x86-core-10.2.2-1.fc44` and `qemu-img` of the
   same version, plus `mtools`, `7zip` and `python3`, then the two art98 packages and the guest
   programs from stage 1.

Fedora 44's release repository is frozen, so pinning the exact package version keeps the same
build available. It's the build that saved the current `ready` snapshot, so that snapshot should
load in the container with no new setup run. Checking this is the first step below.

## Who runs what

```
host                                  container (one per stage)
----                                  -------------------------
scene.py, art98.anim                  art98 serve
Bridge (client half, unchanged)  ──▶  relay  ──▶ COM1 socket ──▶ QEMU ──▶ agent.exe
RemoteVM: screenshot, keys, revert ─▶ control ─▶ QMP
FrameRecorder + ffmpeg  ◀── PPM frames ──┘
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

On start it makes the run copy, starts QEMU with `-loadvm ready`, and waits for the agent to
answer a ping. It then listens on port 7598 inside the container, or with `--unix PATH` on a
Unix socket. Each connection starts with two lines:

1. a token, which the host generates for each stage and passes in as a secret. A wrong token
   gets `error wrong token` and the connection closes;
2. the channel, `agent` or `control`.

serve answers `ok`, or `error <reason>`. The host waits for that line, because a rootless port
forward accepts a connection before anything listens behind it and then hangs up.

- **agent** relays bytes both ways between the connection and the agent's serial socket,
  untouched. QEMU's serial socket takes one client, so a new agent connection replaces the old
  one.
- **control** takes JSON lines, one request and one reply each:

  | Request | Reply |
  | --- | --- |
  | `{"op": "screenshot", "format": "ppm"}` | `{"ok": true, "size": N}`, then N raw bytes |
  | the same with `"shared": true`, on a Unix socket | `{"ok": true, "file": "frame.ppm"}`, written into the shared folder |
  | `{"op": "save_snapshot", "snapshot": "warm"}` | `{"ok": true}`. It saves into the run copy, which goes with the stage |
  | `{"op": "send_keys", "keys": ["alt", "f"], "hold_ms": 80}` | `{"ok": true}` |
  | `{"op": "revert", "snapshot": "ready"}` | `{"ok": true}` |
  | `{"op": "pause"}`, `{"op": "resume"}` | `{"ok": true}` |
  | `{"op": "quit"}` | `{"ok": true}`, then the container exits |

  Errors come back as `{"ok": false, "error": "..."}` and are raised as `QemuError` on the host.

The first control connection owns the stage, and a second one is refused. When it drops,
`serve` quits QEMU, deletes the run copy and exits. If no control connection arrives within
120 s of the guest being ready, it does the same. The container runs with `--rm` and `--init`,
so it goes too, and the SIGTERM from `podman stop` reaches serve. A crashed host script can't
leave a VM running. Only a SIGKILL of the container leaves its run copy in `work/runs`.

### On the host

- `art98_container/host.py`: `Engine` finds `podman`, else `docker`, or `ART98_ENGINE`.
  `ContainerStage` runs the container, finds where serve listens, and connects. `RemoteVM` has
  the methods the scene layer uses on `VM`: `screenshot`, `send_keys`, `load_snapshot`,
  `save_snapshot`, `pause`, `resume`, `close`.
- `session.boot(work, backend=...)`: `"local"` is today's path, `"container"` the new one.
  `ART98_BACKEND` picks the default, which is still `"local"`. The suite now passes on both, so
  switching is the owner's call.
- `session.stage(work, backend=...)` boots on a throwaway copy. The local backend copies the
  disk under `work/runs` itself; the container makes its own. `render` uses it.
- `revert`, `FrameRecorder` and every scene are unchanged: they only see `Session.vm` and
  `Session.bridge`.

On Linux the host makes a private folder under `$XDG_RUNTIME_DIR` (mode 0700) and mounts it at
`/run/art98`, and serve listens on `/run/art98/serve.sock`. Elsewhere, or with
`ART98_TRANSPORT=tcp`, the port is published as `-p 127.0.0.1::7598`, a random host port on
loopback only. The agent runs any Win32 call it's given, so the link must never be reachable
from the network, and the token stops other local users from connecting.

`work/` is mounted with `--security-opt label=disable`, so SELinux doesn't need the files in it
relabelled.

### `art98 up`, on the host

1. Builds the image if it isn't there.
2. Reads the key from `ART98_PRODUCT_KEY`, or asks for it without echo, and stores it as the
   secret `art98_key`.
3. If `work/image.json` is missing, runs `art98 setup` in the container with the ISO mounted:
   about 40 minutes, resumable like today. `--watch` shows the screen through VNC on
   `127.0.0.1:5998` (`--vnc-port`), since GTK can't open from inside a container. Setup reads
   `ART98_WATCH_DISPLAY` for that. After a finished setup the secret is deleted, since the key
   is in the image by then. If setup stops early the secret stays, so a rerun doesn't ask again.
4. Copies the guest programs out of the image into `windows_handlers/build` if they aren't
   there, since scenes send `VIEW.EXE` to the guest from the host.
5. Boots one stage and pings the agent, to show it works.

Running `art98 up` again skips what's done. Everything in it can also be run by hand with
`podman build` and `podman run`, written out in the setup guide.

## Steps

1. **Image.** The Containerfile and its ignore file. Check the QEMU version inside, then
   restore `ready` from the existing `work/` in the container and ping the agent. If the snapshot
   doesn't load, stop: making a new one changes the `ready` image and needs the owner's go-ahead.
2. **Stage.** `art98 serve`, `container.py` and the `boot` backend. Tests against a fake
   server, with no VM, plus a real test marked `container`.
3. **Timing.** Frames are 1.44 MB each. Measure a 300-frame recording through the rootless
   port forward against the local backend, noting `/proc/pressure/cpu`. If the forward is too
   slow, switch the transport to a Unix socket in a mounted folder (Linux only), keeping TCP for
   other hosts.
4. **Up.** `art98 up` and setup in the container, tested from scratch on a separate work folder
   (`work-container/`), so the current `work/` and its snapshot are never touched.
5. **Docs.** The setup guide, the README, `status.md` and the tour. `.tools/` and `env.sh`
   become optional, kept only for the local backend.

## Timing

300 frames recorded with `FrameRecorder.frame()` (sync, capture, write to ffmpeg) on the
existing `work/`, two rounds each. `/proc/pressure/cpu` read some avg10 0.00 before and after
every run.

| Backend | 300 frames | Per frame | Sync | Capture | ffmpeg write |
| --- | --- | --- | --- | --- | --- |
| local | 1.68 to 1.89 s | 5.6 to 6.3 ms | 2.3 to 2.8 ms | 2.3 to 2.6 ms | 0.9 ms |
| container, TCP through the rootless port forward | 2.90 to 3.03 s | 9.7 to 10.1 ms | 5.1 to 5.2 ms | 3.6 to 3.8 ms | 1.0 ms |
| container, Unix socket, frames sent on it | 2.69 to 2.77 s | 9.0 to 9.2 ms | 4.5 to 4.7 ms | 3.5 ms | 0.9 ms |
| container, Unix socket, frames in the shared folder | 2.05 to 2.10 s | 6.8 to 7.0 ms | 3.0 to 3.1 ms | 2.9 ms | 0.9 ms |

Sync time is not network latency. A bare ping takes 5.0 ms both inside the container and on the
host, because the agent answers on its own polling period, so a frame that fits in one period
costs about one period. Sending the 1.44 MB frame over the socket pushed each frame into a
second period, and the port forward added a little more. Writing the frame into the shared folder
brings the container within about 10% of local, so that is the default on Linux. TCP stays for
Docker Desktop and Podman machine, where a Unix socket can't cross the VM boundary. A boot takes
about 0.3 s in the container against 0.1 s locally.

## What was built

Where the build differs from, or adds to, the plan above:

- The handshake answers `ok` or `error <reason>`, so the host can tell a refused connection from
  a guest still booting.
- The Unix socket and shared-folder screenshots on Linux, from [Timing](#timing).
  `ART98_TRANSPORT` picks `unix` or `tcp`.
- A `save_snapshot` op, for the revert-test experiments. It only touches the run copy.
- A 120 s limit for the first control connection, so a host that dies before connecting still
  ends the stage.
- serve handles SIGTERM, and stages run with `--init`. Python as PID 1 ignored SIGTERM, so
  `podman stop` had to fall back to SIGKILL.
- The per-stage token is a Podman secret named `art98_token_<stage>`. It is removed as soon as
  the container exists, and the container keeps its mounted copy.
- `image.json` records an absolute disk path. A work folder prepared in the container records
  `/work/golden.qcow2`, one prepared on the host records the host path. Both backends now fall
  back to the file of that name beside `image.json` (`session.image_disk`).
- The image is `localhost/art98:latest` (`ART98_IMAGE`), 385 MB. The guest programs built in it
  are byte for byte the ones built on the host.
- The ignore file is `98artware_container/Containerfile.dockerignore`, so the container's files
  stay in one folder. Docker BuildKit finds it beside the Containerfile; Podman gets it with
  `--ignorefile`. Besides `work/`, `.tools/`, `.venv/`, `*.mp4` and `*.iso` it leaves out
  `.git/`, `.claude/`, `*.qcow2`, `*.img` and `windows_handlers/build/`. A probe build
  confirmed a decoy `work/`, `.iso` and `.qcow2` don't reach the build context.
- The code is its own package, `art98_container` in `98artware_container/`, not modules of
  `art98`, at the owner's request.

Checked:

- the image builds;
- `qemu-system-i386 --version` in it is 10.2.2 (`qemu-10.2.2-1.fc44`), with default machine
  `pc-i440fx-10.2`;
- the existing `ready` snapshot restores in the container on a run copy in `work/runs` (agent
  ready in 0.11 s, revert 0.05 s);
- the suite passes with `ART98_BACKEND` set to `local` and to `container`;
- the MVP scene renders through the container;
- `art98 up` on the existing `work/` skips setup, boots and pings;
- VNC answers on loopback for a stage booted with a display;
- `art98 up` from scratch on an empty `work-container/`, with the key typed at the prompt:
  setup 1326 s, init_api 13 s, ready 55 s, about 25 minutes end to end with `/proc/pressure/cpu`
  at 0.00 throughout. The key secret was removed afterwards and no container was left behind.
  The stage tests pass on the new image on both backends;
- the new image renders the MVP scene frame for frame the same as the old host-built `work/`:
  0 of 257 frames differ.

Not yet checked: real Docker. The `docker` on the build host is Podman's shim.

## Not in this design

- VMs on another machine. Only a published port on loopback is covered; across a network the
  link would need TLS.
- Audio, which is still deferred.
- Moving `FrameRecorder` into the container. It stays on the host, where the planned recorder
  changes will happen.
- Switching the default backend to `container`. The suite passes on both, so it can be done
  whenever the owner wants.
