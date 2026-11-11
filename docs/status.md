# Status

Last updated 2026-11-11, for release 0.1.0. This page says what works, what is open and which
bugs are on hold. The dated build diary is in [build history](archive/build-history.md); release
notes are in the [changelog](../CHANGELOG.md).

## What works

| Part | State | Docs |
| --- | --- | --- |
| VM preparation | Built. `art98 setup` turns a Windows 98 SE disc into `work/golden.qcow2` with a `ready` snapshot, with no input. Four steps: vm, setup, init_api, ready | [Part 1](setup/README.md) |
| Bridge and agent | Built. `AGENT.EXE` proxies any Win32 call over COM1 using a framed protocol | [Bridge](scenes/bridge.md), [Instruction set](scenes/instruction-set.md) |
| Scene API and renderer | Built. `Scene`, props, animations, `art98 render`. Every program (Notepad, Dialog, Paint, Minesweeper, Screensaver) is in `actions/programs/`, and `Backdrop` sets the desktop colour. Paint, Minesweeper and Screensaver are there too | [Part 2](scenes/README.md) |
| Examples | `examples/blank_start` (the proof scene: a Picture and a Notepad, three sections), `examples/mvp`, `hello.py`, `showcase.py` and the gallery scenes | [Gallery](scenes/gallery.md) |
| Diagrams | Seven diagrams and the Manim comparison, with editable `.drawio` files | [Diagrams](diagrams/README.md) |
| States and sections | The MVP is built: state files, `set_state`, picture windows and `Teleport`. `Scene.next_section(name)` is built, on top of `cut()`. The `--section` option is not | [Design](design/state-and-action.md), [States](scenes/scene-api.md#states) |
| Recorder | Built: `Recorder`, with `cut()` to start a new clip during a run, `clips` to list them, and a join into the output. Clips are kept beside the output as MP4 | [Recorder](design/state-and-action.md#recorder), [Clips](scenes/scene-api.md#clips) |
| Programs | Notepad is the first program, in `actions/programs/notepad.py`. It opens a text file or an empty window and checks its title. Windows 98 drops a trailing `.txt` from the title. `Dialog` (`actions/programs/dialog.py`) is a real message box with icons, a size, greyed buttons and changeable text. It is not in a state | [Programs](design/programs.md), [Dialog](scenes/scene-api.md#dialog) |
| Desktop colour and wallpaper | Built. `Backdrop` and a state's `desktop` (colour, wallpaper, style). A wallpaper reaches the guest on a CD in drive D: | [Colour and wallpaper](design/state-and-action.md#desktop-colour-and-wallpaper) |
| CLI and checks | Errors from `art98` print one clean line, not a traceback. Warnings say when the image or guest programs are older than the code (`freshness.py`). `art98 doctor` works on a host that has only a container engine and ffmpeg. CI runs the unit tests on each push (`.github/workflows/tests.yml`) | [CLI](setup/cli.md) |
| Container | Built: the VM service in `core/art98/container/`, `art98 up` and the Dockerfile in `setup/`. `art98 up` builds the image and runs setup, then stops; `art98 vm start` runs one long-lived VM container that `render` and `ping` attach to. Tested on rootful Docker 29.9 and rootless Podman. Tested from scratch: about 25 minutes, and its image renders the same frames as the host-built one | [Container](design/container.md) |

Audio is deferred. art98 is video only.

## What is open

### Next

In order, from the layer review of 2026-11-11. See also
[After the MVP](design/state-and-action.md#after-the-mvp).

1. **Other programs.** New programs (Calculator and the rest) go in `actions/programs/`, one
   file each, subclassing `Win`. Only Picture and Notepad are in the fixed `APPS` list of state
   apps; Paint and Minesweeper are not in a state yet.
2. **Gallery and showcase port.** Port the showcase and re-render the gallery.
3. **`--section`.** Render one section of a scene, on top of `next_section`.

### Leftovers from the dialog storm

- `RemoteVM` has no `disc_state()`. Only the local `VM` has it, and no art98 code calls it.
  Delete it or give `RemoteVM` one.
- `bmp_pixel` decodes 24-bit and 8-bit BMPs only. For any other depth the wallpaper pixel
  check is skipped. (A `lazy:` marker in the code.)
- Fixed: `art98 up --rebuild` with Docker CE's CLI at the Podman socket left the image
  unchanged (buildx `docker-container` builder, result only in the build cache, exit 0).
  `build_image` now passes `--load` where the CLI has it and fails with a message unless the
  engine's image has the ID the build wrote with `--iidfile`.
- A `Cascade` helper, `Dialog` as a state `app`, and desktop icons and tray in a state are not built.

### Known bugs, on hold

These were found while writing the docs. Fixing them was started, then paused for the design
work. None of them block the MVP. (`AsyncCall.wait()` was listed here as waiting forever. It
doesn't: with no timeout it uses the bridge's, 10 s by default, and raises `BridgeTimeout`.)

| Where | Bug |
| --- | --- |
| Agent | Frames over 16384 bytes are truncated |
| Agent | An oversize `#` line is dropped |
| Agent | An `ERR` sent after an `ACALL`'s `OK` is dropped |
| Agent | A failed `CreateThread` isn't handled |
| Host | Pending async calls aren't failed when the agent sends `! CRASH` |
| Host | `_read_loop` only catches `OSError` |
| Host | A failed `load_snapshot` leaves QEMU in its `restore-vm` state |
| Tests | Each `test_qemu.py` run leaves one `art98-*` socket folder in `$XDG_RUNTIME_DIR`: a test VM isn't closed |

### Docs that are out of date

- `put_file`, `get_file` and app launch times in the README, [bridge.md](scenes/bridge.md),
  [win32-recipes.md](scenes/win32-recipes.md) and the `put_file` docstring are quiet-host
  figures. On a busy host they can be several times slower.
- Resolved: on a fresh boot, stock-desktop frames before the first pointer move had no pointer
  and brighter colours. One `SetCursorPos` nudge in `Pointer.attach` fixes it. See
  [first-frame](../experiments/first-frame/README.md) and [Blank start](design/blank-start.md#the-first-frame).
- Resolved: dragging a window by its title bar on the stock desktop left desktop label pixels in
  its frame. `Win.repaint_if_moved` now repaints the moved window each frame, and the check shows
  0 stale pixels. See [host-checks](../experiments/host-checks/README.md).
- Resolved: the busy-host timings are now measured. At CPU pressure about 45 a render takes about
  5 times as long and `put_file` about 10 times, with the same frames and no timeout. See
  [On a busy host](setup/troubleshooting.md#on-a-busy-host). The quiet-host figures in the other
  pages are still quiet-host figures.

### Smaller decisions

- The `ready` step writes `UserPreferencesMask`, but Windows 98 reads `UserPreferencemask`, so the setting has
  no effect. Fixing it changes the image. See [image.md](setup/image.md). `blank` turns the
  same effects off at run time, so it only matters for stock scenes. This and the other prep
  options for a blank snapshot are listed in
  [Blank start](design/blank-start.md#prep-changes-not-made).
- `art98 setup --from setup` and `--from init_api` fail after a
  finished build, because `install.img` is gone. The workaround is `--from vm`.

## Working notes

- Host QEMU (`. .tools/env.sh` if you keep a local build) is for `test_qemu.py`, host
  `art98 setup` and `boot_local` experiments only. Renders and the VM tests use the VM service
  and need no `.tools/`.
- The VM tests boot the real image: point `ART98_TEST_WORK` at a prepared work folder when
  running from a worktree.
- `work/` is gitignored and holds the images: installed copies of Windows, with the product
  key in clear text. Never commit or push anything from it, including the copies under
  `work/runs`.
- To stop a stray VM, kill it by its PID. `pkill -f qemu-system-i386` can match the shell that
  runs it.
- Timings depend on host load, so note `/proc/pressure/cpu` next to any figure.
