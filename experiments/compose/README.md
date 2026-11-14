# Compose probe: can compose replace art98's hand-built `docker run`?

Question: can a committed `compose.yaml` (a long-lived `vm` service and a one-shot `setup`
service behind a profile) do what `setup_argv` (`art98 up`) and `service.start` (`art98 vm start`)
did by hand, on both engines, with a user's own `compose.override.yaml` for local config?

**Answer: yes, on both engines, with three things to know** (below, under "What this changes").
The change built on it is the `refactor/compose` branch; this page is the evidence.

2026-11-14, one Fedora 44 host, 20 CPUs.

| Engine | How it was run | Versions |
|---|---|---|
| Rootful Docker | `env -u DOCKER_HOST sg docker -c 'docker compose ...'` | Docker 29.9.3, compose plugin v5.7.1 |
| Rootless Podman | `podman compose ...`, which hands over to the same docker-compose v5.7.1 plugin; also `docker compose` with `DOCKER_HOST` at the Podman socket | Podman 5.8.9 |
| `podman-compose` 1.6.0 | `podman-compose ...` | checked last, see below |

`/proc/pressure/cpu` `some avg10` was 0.0 to 2.6 next to every timing below (avg10 is a 10 s
window, so it misses shorter bursts). Nothing from `work/` was copied; the probes ran in a scratch
folder outside the repo, and only the end-to-end runs used the prepared image.

## Files

- `probe.compose.yaml`: a `vm` and a `setup` service on the real `localhost/art98:latest` image,
  with the entry point replaced by a short Python script, so nothing boots Windows. `vm` drops to
  the host user the way `art98.container.entry` does, prints its uid and the token it was given,
  writes a file in `/work`, sleeps 3 s, then listens on `/run/art98/serve.sock` (or TCP 7598 when
  the socket folder is not mounted). `setup` prints its uid, the key it was given and whether the
  disc is mounted, and writes a file in `/work`.
- `probe.tcp.yaml`: the TCP variant, merged on top with `-f`.
- `probe.override.yaml`: what a user would put in `compose.override.yaml`: a VNC port, a disc
  mount and the key from a file.

Rerun: copy the three files to an empty folder outside the repo as `compose.yaml`,
`compose.tcp.yaml` and `compose.override.yaml`; add `work/`, `sock/`, a `token` file, a `key.txt`
and an empty `fake.iso`; export `ART98_HOST_UID=$(id -u) ART98_HOST_GID=$(id -g)`; then run the
commands named below in that folder.

## Results

| # | Check | Rootful Docker | Rootless Podman |
|---|---|---|---|
| 1 | Token secret, `file:` source, read at `/run/secrets/art98_token` | Yes | Yes |
| 2 | Key secret, `environment: ART98_PRODUCT_KEY` source (`ART98_PRODUCT_KEY=... compose run --rm setup`) | Yes | Yes |
| 3 | Key secret with `file:` in the override instead | Only with `!override` (plain merge: `file\|environment attributes are mutually exclusive`) | Same |
| 4 | Override auto-merged: VNC port on `vm`, disc mount on `setup`, key file | Yes; `compose port vm 5900` gave `127.0.0.1:5911` | Yes |
| 5 | `security_opt: [label=disable]` bind mounts under SELinux, `init: true` | Yes | Yes |
| 6 | Files the container writes in `work/` and the socket folder owned by the user (uid 1000) | Yes: entry drops to 1000 from `ART98_HOST_UID`/`GID` | Yes: container root is the host user, entry stays root |
| 7 | Healthcheck + `up -d --wait` as the readiness gate | Yes. `start_interval: 1s` is honoured: healthy 5.9 s after start for a 3 s sleep | Yes, but **`start_interval` is ignored**: with `interval: 30s` the wait took 30.9 s; `5s` gave 6.3 s and `2s` 5.7 s |
| 8 | A missing key secret | `environment variable "ART98_PRODUCT_KEY" required by secret ... is not set`, exit 1, and **a `setup-run-*` container is left in `Created`** | Same text, same leftover |
| 9 | TCP variant (`-f compose.yaml -f compose.tcp.yaml -f compose.override.yaml`): `volumes: !override`, loopback port, TCP healthcheck | Yes, `127.0.0.1:7598` | Yes |
| 10 | Build through compose (`build:` on `vm`, real `setup/Dockerfile`) | Yes, 62 s with no layer cache, image stored | Yes, 70 s, image stored in Podman (buildx's `buildkit` container builds it and loads it) |
| 11 | `compose --dry-run run --rm setup` | Creates nothing; stops at `interactive run is not supported in dry-run mode` | Same |

Two things that did not work, and the design that avoids them:

- **A TCP profile.** A second service `vm-tcp` (`extends: vm`, `profiles: [tcp]`) cannot share the
  container name: `container name "art98probe-vm" is already in use by service` as soon as both are
  in the model. So the TCP choice is a second committed file, `compose.tcp.yaml`, that art98 adds
  with `-f`. Because `-f` turns off compose's own override lookup, art98 then adds
  `compose.override.yaml` itself when it exists.
- **`podman-compose` 1.6.0.** It parses `!override` and starts `vm`, but `run --rm setup` printed
  `missing services [setup]` (it does not enable a profile for a service named on `run`), and it
  has no `--wait`. art98 needs the docker-compose plugin; `podman compose` uses it when it is
  installed, as here.

## What this changes

1. **The prompt stays as a fallback, in the wrapper.** Compose cannot prompt, and a missing key
   leaves a container behind (8). So `art98 up` reads the resolved config first
   (`compose --profile setup config --format json`): a `file:` key must exist; an `environment:`
   key comes from `ART98_PRODUCT_KEY`, else the prompt, and is passed to compose in its
   environment, never on a command line. The disc is checked the same way.
2. **A key file in the override needs `!override`** (3). `compose.override.example.yaml` shows it.
3. **The healthcheck interval is 5 s**, because Podman ignores `start_interval` (7). Docker still
   checks every second while starting. The check is `test -S` on the socket (or a TCP connect),
   which is enough because serve only listens once the guest agent has answered.

Also seen: compose leaves out an inactive profile's services and secrets from `config`, so the
key check needs `--profile setup`; and `down` without the profile does not remove a leftover
`setup-run-*` container (another reason to check the key first).

## End to end, through compose, on the prepared image

The branch's `art98 vm start`, `art98 ping`, `art98 render recipes/scenes/hello.py Hello`,
`art98 vm status` and `art98 vm stop`, run from a scratch folder whose `art98.toml` names a
separate container (`art98-compose-probe`), an image built from the branch through compose, and
the existing `work/`.

| Engine | `vm start` | render | Video | cpu avg10 |
|---|---|---|---|---|
| Rootless Podman (`docker` CLI, `DOCKER_HOST` at the Podman socket) | 6.0 s | 3.8 s | 800x600, 211 frames | 0.00 to 0.01 |
| Rootful Docker | 2.4 s | 3.6 s | 800x600, 211 frames | 0.00 to 0.30 |

Also checked live: a second `vm start` says `already running`; `vm stop` twice says `stopped
<id>` then `nothing to stop`; no file in `work/` newer than the run is owned by anyone but uid
1000; with a VNC override (`ART98_VNC: "1"`, `127.0.0.1:5911:5900`) `vm status` shows
`vnc: 127.0.0.1:5911` and the port answers `RFB 003.008` (Podman, Unix socket); with
`ART98_TRANSPORT=tcp` and the same override, Docker published only `127.0.0.1:7598` and
`127.0.0.1:5911`, and `ping` answered.

An old container named `art98-vm` from the `docker run` days blocks the default name:
`vm start` fails with the engine's own `the container name "art98-vm" is already in use ... You
have to remove that container`. `docker rm art98-vm` once fixes it.

Later, in review: a fixed `container_name` also stops a second work folder's project from
starting its VM, since container names are global to the engine. So `compose.yaml` has no
`container_name`; compose names the VM `art98-<hash8>-vm-1`, and the old `art98-vm` no longer
gets in the way.
