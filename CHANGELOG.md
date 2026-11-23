# Changelog

All notable changes to art98 are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and art98 uses
[semantic versioning](https://semver.org/). Before 0.1.0 the work was logged in
[build history](docs/archive/build-history.md).

## [Unreleased]

A scene's sections can be rendered alone, and every window a scene sees is now a prop. A scene
written for 0.2.0 needs edits; see "Changed" and "Removed".

### Added

- `art98 render FILE --section NAME` renders one section from the state a full render captured at
  its boundary, into `<Scene>-<NAME>.mp4`. The captures are in
  `<scene file stem>.<Scene>.sections/` beside the scene's file, and a stale one is refused. See
  [Sections](docs/scenes/scene-api.md#sections).
- `Scene.section(name, method)` plays one named section, and `render(..., section=)` takes the
  same name.
- `Scene.get_state(path)` writes the desktop as a state file, from the props. It captures
  `Picture` and `Notepad` windows, and refuses the other programs for now.
- A Notepad state can have a `text` file, put in the Edit control once the window is up.
- A state's `stack` lists windows back to front (z-order) and a Notepad's `selection` restores the
  caret or selected text; `get_state` writes both.
- `Scene.add(prop, id=...)` names a prop, and `Scene.prop(id)` finds any prop on stage by id, not
  only one a state opened. An id is ASCII letters, digits, `_` and `-`.
- `Scene.check_tracking()`, which runs after every `play`, `wait` and `wait_until` and at the end
  of a run, and `Scene.claim(owner, matches)` for windows a program is handling that the scene
  has no prop for. See [Tracking](docs/scenes/scene-api.md#tracking).
- `Close(window, via=...)` shows the click on the X button or a dialog's button, and ends the
  program on the release without a mouse button event.
- `RightClick(target, menu=False)` for a right click that opens no menu, such as a flag in
  Minesweeper.
- `UntrackedWindow`, `ImplicitClose` and `SectionNotFound` errors.
- `Desktop` sets which parts of the desktop show: `icons`, `pointer`, `taskbar`, `buttons`,
  `quick_launch`, `tray` and `clock`. `Desktop("blank")` and `Desktop("stock")` are its presets,
  so `Desktop("blank", taskbar=True, buttons=False)` is a black desktop with a taskbar. An option that
  is off hides the ones under it (`taskbar` over `buttons`, `quick_launch` and `tray`; `tray` over
  `clock`), and writing one of those gives a warning. The options are applied after every revert
  and survive a colour change. See [Desktop options](docs/scenes/scene-api.md#desktop-options).

### Changed

- A window now ends only through `Close`. A window that goes any other way (the X button, a menu's
  Exit, Alt+F4, a click on a dialog's button) raises `ImplicitClose` at the next check. Use
  `Close(window)`, or `Close(box, via=box.button("Yes"))` in place of `Click(box.button("Yes"))`.
- A screensaver is ended with `Close(saver)`, not `saver.stop()`.
- A visible window that is not the desktop's or a prop's now raises `UntrackedWindow` instead of
  going unnoticed. A menu from `RightClick`, a tooltip from `Hover` and the best-time prompt after
  `Minesweeper.clear` are claimed for you. A window you open another way needs `self.add(...)`,
  or a `with self.claim(...)` block.
- `Scene.remove` on a window does what `Close` does.
- A section capture now goes stale when any host file it was built from changes, and the error
  names that file. A capture written by an earlier build has no file records, so it is refused
  and must be rendered again with a full `art98 render` (breaking). See
  [Sections](docs/scenes/scene-api.md#sections).
- A scene's `desktop` must be a `Desktop`. A string is refused where the class is defined, or at
  `run` for one set on an instance, and the message says what to write. Change
  `desktop = "stock"` to `desktop = Desktop("stock")`, and `desktop = "blank"` (or nothing) to
  `desktop = Desktop()`. `Desktop` comes with `from art98.anim import *`.
- The desktop is resolved once, when `run` starts, and every revert in that run uses the result.
  Changing `self.desktop` during a run raises `UsageError`: set it before `run`. A second `run`
  of the same scene resolves again.

### Removed

- `Scene.pointer_visible`. A scene that sets it, on the class (including through a mixin) or on an instance, is refused with
  a message naming the replacement. The pointer now comes only from the `Desktop`: the blank
  preset hides it and the stock preset shows it. To update a 0.2.0 scene:

  | 0.2.0 | Now |
  |---|---|
  | `desktop = "blank"`, or nothing | `desktop = Desktop()`, or nothing |
  | `desktop = "stock"` | `desktop = Desktop("stock")` |
  | blank with `pointer_visible = True` | `desktop = Desktop(pointer=True)` |
  | stock with `pointer_visible`, either value | `desktop = Desktop("stock")` (it did nothing) |

- `Scene.next_section(name)`. Use `self.section(name, method)`, or `self.cut()` for a clip with no
  state to start from.

### Fixed

- A state's `display` now moves the taskbar to the new bottom edge, and `scene.space` gets the
  work area above it. The mode is written to the registry, as the Display control panel does, and
  the next revert undoes the write. Before, the taskbar stayed at its 800x600 place: mid-screen at
  1024x768, and off the bottom at 640x480.
- `set_display_mode` raises `BridgeError` for a mode that takes effect only after a restart
  (640x480 at 4 bits per pixel), instead of returning as if it had switched.

## [0.2.0] - 2026-11-16

A clean-up release: the containers run from a committed `compose.yaml`, the library is regrouped
into packages, and a review pass hardened the window and program actions. A scene written for
0.1.0 needs a few edits; see "Changed" and "Removed".

### Changed

- The containers run from a committed `compose.yaml` instead of `docker run` commands built in
  Python. `art98 up` runs `docker compose build` and `docker compose run --rm setup`, and
  `art98 vm start`/`stop` run `docker compose up -d --wait`/`down`, one compose project per work
  folder. art98 now needs Docker's compose plugin, or `podman-docker` and `docker-compose` on a
  Podman host (`podman-compose` does not work). Your own settings for the containers (a product
  key file, the disc, VNC) go in a gitignored `compose.override.yaml`; start from
  `compose.override.example.yaml`. See [configuration](docs/setup/config.md#where-each-setting-lives).
- `art98 up` checks the disc and the key before it starts setup, and `--iso` together with a disc
  mounted in `compose.override.yaml` is an error. It says setup usually takes 20 to 30 minutes.
- `[ports] connect` defaults to `127.0.0.1`.
- `art98` parses every command without importing `art98_setup`; `setup` and `up` read the default
  disk size when they run.
- `examples/` is now `recipes/`. Scenes are in `recipes/scenes/`, and modules that scenes import
  are in `recipes/helpers/` (`from helpers.<module> import ...`). The folder is on the path for
  `uv run` and is not part of the wheel.
- `core/art98` is regrouped into packages: `guest/` (bridge, protocol, QEMU, `win32`, disc and
  guest files), `container/` (compose, service, serve and the freshness checks), `output/`
  (recorder and GIF writer) and `actions/` (pointer, keyboard, `window/` and `programs/`). Import
  from the new paths. `Picture` is in `actions/window/`, and `timeline.py` is folded into `Scene`.
- `core/art98/legacy.py` keeps the old module paths (`art98.service`, `art98.win32`), `Scene.fps`
  as `output_fps` and `Settings(source=)` working for the Hermes plugin pinned at 94f0fd3. It is
  the one allowed shim, and `test_legacy.py` pins the VM server's wire exchange.
- `Scene.fps` is now `output_fps`, the frame rate of the finished video. The `clock` setting is gone, because
  the guest always runs on its own clock: delete it from a scene that sets it.
- The state file's desktop `colour` is now `fill_colour`. An old `colour` key fails with a
  message that names the new one.
- The bridge only moves bytes: a garbled frame (`BADFRAME`) fails every open request at once, and
  an integer outside -2**31 to 2**32-1 is refused instead of masked.
- Expected failures raise art98 errors (`Art98Error` and its `UsageError`, `NotFound`,
  `GuestError` and `MissingFile`) instead of bare Python ones, and the CLI prints them as one
  line. A drifted desktop is a `GuestError` (`StateMismatch`).
- The guest-program freshness check compares source digests (`guest/build/sources.sha256`,
  written by `make -C guest`) instead of file times, and the image check uses git commit times
  in a git checkout. A fresh `art98 up` no longer warns that the guest programs are out of date.
  After updating, run `make -C guest` once, or `art98 up --rebuild` on a host with only a
  container engine, so `sources.sha256` exists.
- The renderer checks output suffixes, numbers kept clips by position, and takes `GifOptions`.
  The recorder refuses frames after it is closed. A live stretch that ends more than a frame
  late warns, since guest-timed motion in it plays slower in the video.
- Scene: one reset, one pacer and one name per way of holding; `play` overrides no longer stick.
- Windows, pointer and keyboard (#27 to #30):
  - `Win.refresh` reads the show state first, so a minimized window keeps its last place and
    pending moves are sent on restore. `maximize`, `minimize` and `restore` go through the
    system command path. The drift check skips minimized windows.
  - `Win()` with no command, handle, title or class is a `UsageError`. A missing handle, a window
    that never appears and a missing control or menu are `NotFound` with a plain message (`find`
    waits 15 s).
  - `Hover` takes `hold=` and `travel_time=`, not `run_time=`. `Click`, `Drag`, `Stroke` and
    `DoubleClick` refuse unknown mouse buttons when built. `DoubleClick` presses 0.09 s apart and
    `Click` holds 0.065 s at any `run_time`. `Stroke` refuses `steps_per_frame` below 1.
  - `Keys` and `TypeKeys` refuse unknown key names, typing refuses text outside Windows 1252 and
    normalises line endings, and `Untype` refuses a count below 1.
  - `Picture` and `Notepad` raise `MissingFile` for a missing file.
  - State checks: one check per part, an RGB colour in the mismatch message, the pixel
    tolerance chosen by colour depth, and the sample taken clear of the pointer.
- Programs (#31): `Dialog`, `Notepad`, `Paint`, `Minesweeper` and `Screensaver` raise art98
  errors for bad input and use before they are on stage. `Paint`, `Minesweeper` and `Notepad`
  take `at` and `size` only. `Minesweeper` reads the board size once and `find_mines` returns a
  frozenset. A `Dialog` smaller than the stock box is refused before it is placed.
- Development moves to the `dev` branch; `main` changes only at a release, and `experiments/`
  lives on `dev` only.

### Added

- A client can be handed the VM token instead of reading a token file: `Settings.token` (for a
  program that uses art98 as a library) or the `ART98_TOKEN` environment variable. The token
  file stays the default.
- `ART98_GUEST_BUILD` points art98 at the guest programs when the library is a copy outside
  the checkout, and `tools/vendor_to_hermes.py` makes that copy for the Hermes plugin.
- `Screensaver` can run Scrolling Marquee.
- `SECURITY.md`, which points to private reporting.
- In `experiments/` (on `dev` only): probes for the Windows 98 add-on install path and the
  vmdisp9x free-resolution driver.

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
- Dead settings and parameters: `icount_shift`, `audio_wav` (the audio backend is always
  `none`), `Bridge.move_window` (use `win32.place_window`) and the `timeline.py` module.

### Fixed

- `recipes/scenes/hello.py` and its copies in the scene docs place Notepad clear of the desktop icons.
- `Dialog.remove()` closes Yes/No and Abort/Retry/Ignore boxes, which ignore the title bar's close,
  by pressing their No or Abort button. The custom icon is destroyed only after the box has gone.
- `Screensaver.stop` moves the pointer towards the middle of the screen, so it works near the edges,
  and puts the pointer back afterwards.
- `Minesweeper.find_mines` restores the desktop and the pointer even when the read fails.
- A wallpaper check reads one BMP header and allows one pixel of slack for stretch and centre.
- Setup and the CI tests: the Windows 98 boot record now comes from syslinux's `mbr.bin`; CI
  builds `guest/` and still runs when the runner cannot install ffmpeg.

### Known limits

- The colour depth is fixed (16-bit); a state's colours show the 5-6-5 rounding.
- Resolutions are fixed to the four Cirrus modes. Wider displays are only probed in `experiments/`.
- An image prepared before `guest/call_proxy/agent.c` changed warns "the prepared image was
  built before the agent changed; scenes run the old AGENT.EXE". Scenes still run on the old
  agent. To get the new one, run `art98 setup --from vm`, which is a full reinstall.
- A `test_qemu.py` run leaves one `art98-*` socket folder in `$XDG_RUNTIME_DIR`.
- The `ready` step writes `UserPreferencesMask`, but Windows 98 reads `UserPreferencemask`, so
  the setting has no effect. Fixing it changes the image.
- Setup was run on one OEM disc only, and `--from setup` and `--from init_api` still fail after
  a finished build (use `--from vm`).
- Agent bugs on hold: frames over 16384 bytes are truncated, an oversize `#` line is dropped, an
  `ERR` after an `ACALL`'s `OK` is dropped, and a failed `CreateThread` is not handled.
- Host bugs on hold: pending async calls are not failed when the agent sends `! CRASH`,
  `_read_loop` only catches `OSError`, and a failed `load_snapshot` leaves QEMU in `restore-vm`.
- A guest reboot ends the VM. Video only; audio is deferred. `--section` is not built, and Paint,
  Minesweeper and `Dialog` cannot be opened from a state file.
- Timings in the docs are for a quiet host. A busy host can be several times slower, with the
  same frames.

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

[0.2.0]: https://github.com/StanLukuvka/98artware/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/StanLukuvka/98artware/releases/tag/v0.1.0
