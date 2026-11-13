# Changelog

All notable changes to art98 are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and art98 uses
[semantic versioning](https://semver.org/). Before 0.1.0 the work was logged in
[build history](docs/archive/build-history.md).

## [Unreleased]

### Added

- A client can be handed the VM token instead of reading a token file: `Settings.token` (for a
  program that uses art98 as a library) or the `ART98_TOKEN` environment variable. The token
  file stays the default.
- `ART98_GUEST_BUILD` points art98 at the guest programs when the library is a copy outside
  the checkout, and `tools/vendor_to_hermes.py` makes that copy for the Hermes plugin.

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
