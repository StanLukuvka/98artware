# Changelog

All notable changes to art98 are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and art98 uses
[semantic versioning](https://semver.org/). Before 0.1.0 the work was logged in
[build history](docs/archive/build-history.md).

## [Unreleased]

### Removed

- `art98 vm start --vnc`, `art98 up --watch` and `art98 up --vnc-port`, and the `[ports] bind`,
  `vnc` and `setup_vnc` keys. Published ports are on `127.0.0.1` only; turn VNC on in
  `compose.override.yaml` (`ART98_VNC: "1"` and a port), as `compose.override.example.yaml`
  shows. An `art98.toml` that still has the keys stops with an error: delete them.
- The `[vm] container` key, `work/vm.cid` and the `art98.work` label check. compose names the
  container `art98-<hash8>-vm-1`, one project per work folder, so two work folders can each run
  a VM, and art98 finds it by its project. Delete `container` from your `art98.toml` if you
  copied it. A stopped `art98-vm` container from before is no longer used: remove it with
  `docker rm art98-vm`, and delete `work/vm.cid` if it is there.

### Added

- A client can be handed the VM token instead of reading a token file: `Settings.token` (for a
  program that uses art98 as a library) or the `ART98_TOKEN` environment variable. The token
  file stays the default.
- `ART98_GUEST_BUILD` points art98 at the guest programs when the library is a copy outside
  the checkout, and `tools/vendor_to_hermes.py` makes that copy for the Hermes plugin.

### Changed

- The containers run from a committed `compose.yaml` instead of `docker run` commands built in
  Python. `art98 up` runs `docker compose build` and `docker compose run --rm setup`, and
  `art98 vm start`/`stop` run `docker compose up -d --wait`/`down`, one compose project per work
  folder. art98 now needs Docker's compose plugin, or `podman-docker` and `docker-compose` on a
  Podman host (`podman-compose` does not work). Your own settings for the containers (a product
  key file, the disc, VNC) go in a gitignored `compose.override.yaml`; start from
  `compose.override.example.yaml`. See [configuration](docs/setup/config.md#where-each-setting-lives).
- `art98 up` checks the disc and the key before it starts setup, and `--iso` together with a disc
  mounted in `compose.override.yaml` is an error.
- `[ports] connect` defaults to `127.0.0.1`.
- `examples/` is now `recipes/`. Scenes are in `recipes/scenes/`, and modules that scenes import are in
  `recipes/helpers/` (`from helpers.<module> import ...`). The folder is on the path for `uv run`
  and is not part of the wheel.
- The guest-program freshness check compares source digests (`guest/build/sources.sha256`,
  written by `make -C guest`) instead of file times, and the image check uses git commit times
  in a git checkout. A fresh `art98 up` no longer warns that the guest programs are out of date.
  After updating, run `make -C guest` once, or `art98 up --rebuild` on a host with only a
  container engine, so `sources.sha256` exists.
- `art98 up` says setup usually takes 20 to 30 minutes.
- Development moves to the `dev` branch; `main` changes only at a release, and
  `experiments/` lives on `dev` only.

### Fixed

- `recipes/scenes/hello.py` and its copies in the scene docs place Notepad clear of the desktop icons.

## [0.1.0] - 2026-11-11

The first release. It is a git tag and a GitHub release. There is no wheel and no sdist: art98
runs from a checkout with `uv run`.

### What works

- `art98 setup` and `art98 up` turn a Windows 98 SE disc image into a prepared VM image with a
  `ready` snapshot, with no input. `art98 up` does it inside a container.
- `art98 vm start` runs one long-lived VM container. `art98 render` and `art98 ping` attach to it,
  one at a time. `art98 vm stop` removes it.
- A scene is a Python file. The scene API has props, animations, sections, `cut()` and a recorder
  that waits for Windows to finish drawing before each frame. Output is MP4, with an optional GIF.
- Hand-written JSON states for the starting desktop, with a colour, a wallpaper, windows and
  pictures. A blank start gives a black, empty screen.
- Programs as action classes: Notepad, Paint, Minesweeper, the screensaver and `Dialog`.
- `art98 doctor`, `art98.toml` for names, ports and the work folder, and clear one-line errors.
- Setup stops with `Windows rejected the product key` when Windows refuses the key, instead of
  pressing through the first-boot wizard's Product Key page for hours.
- Docs for setup, the scene API, the design and the repo. Examples and a gallery of GIFs.

### What you need

- Linux. Other systems are untried.
- Docker, or Podman with the `podman-docker` package.
- Python 3.11 or newer, [uv](https://docs.astral.sh/uv/) and ffmpeg.
- Your own Windows 98 SE disc image and product key. art98 ships no Windows files. Running
  setup accepts the Windows licence agreement on your behalf.
- About 3 GB of free disk space and 20 to 40 minutes for the one-time install.

### Known limits

- Setup was run on one OEM disc only. A different disc is the likeliest first failure.
- After a finished build, `art98 setup --from setup` and `--from init_api` fail because
  `install.img` is gone. Use `--from vm`.
- Agent bugs on hold: frames over 16384 bytes are truncated, an oversize `#` line is dropped, an
  `ERR` after an `ACALL`'s `OK` is dropped, and a failed `CreateThread` is not handled.
- Host bugs on hold: pending async calls are not failed when the agent sends `! CRASH`,
  `_read_loop` only catches `OSError`, and a failed `load_snapshot` leaves QEMU in `restore-vm`.
  The truncation and the crash handling are the ones a scene author can trigger.
- A guest reboot ends the VM.
- `--section` is not built. Paint, Minesweeper and `Dialog` cannot be opened from a state file.
- Timings in the docs are for a quiet host. A busy host can be several times slower, with the
  same frames.
- The `UserPreferencesMask` prep setting is written under the wrong name, so it has no effect on
  stock scenes.
- Video only. Audio is deferred.

See [status](docs/status.md) for the open work.

[0.1.0]: https://github.com/StanLukuvka/98artware/releases/tag/v0.1.0
