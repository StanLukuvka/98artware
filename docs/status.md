# Status

Last updated 2026-11-13, for release 0.1.0. This page says what works, what is open and which
bugs are on hold. The dated build diary is in [build history](archive/build-history.md); release
notes are in the [changelog](../CHANGELOG.md).

## What works

| Part | State | Docs |
| --- | --- | --- |
| VM preparation | Built. `art98 setup` turns a Windows 98 SE disc into `work/golden.qcow2` with a `ready` snapshot, with no input. Four steps: vm, setup, init_api, ready | [Part 1](setup/README.md) |
| Bridge and agent | Built. `AGENT.EXE` proxies any Win32 call over COM1 using a framed protocol | [Bridge](scenes/bridge.md), [Instruction set](scenes/instruction-set.md) |
| Scene API and renderer | Built. `Scene`, props, animations, `art98 render`, and `Backdrop` for the desktop colour | [Part 2](scenes/README.md) |
| Examples | `recipes/scenes/blank_start` (the proof scene: a Picture and a Notepad, three sections), `recipes/scenes/mvp`, `hello.py`, `showcase.py` and the gallery scenes | [Gallery](scenes/gallery.md) |
| Diagrams | Nine diagrams and the Manim comparison, with editable `.drawio` files | [Diagrams](diagrams/README.md) |
| States and sections | The MVP is built: state files, `set_state`, picture windows and `Teleport`. `Scene.next_section(name)` is built, on top of `cut()`. The `--section` option is not | [Design](design/state-and-action.md), [States](scenes/scene-api.md#states) |
| Recorder | Built: `Recorder`, with `cut()` to start a new clip during a run, `clips` to list them, and a join into the output. Clips are kept beside the output as MP4 | [Recorder](design/state-and-action.md#recorder), [Clips](scenes/scene-api.md#clips) |
| Programs | Notepad, Dialog, Paint, Minesweeper and Screensaver, one file each in `actions/programs/`. Only Picture and Notepad can be opened from a state. Notepad (`notepad.py`) opens a text file or an empty window and checks its title; Windows 98 drops a trailing `.txt` from the title. `Dialog` (`dialog.py`) is a real message box with icons, a size, greyed buttons and changeable text | [Programs](design/programs.md), [Dialog](scenes/scene-api.md#dialog) |
| Desktop colour and wallpaper | Built. `Backdrop` and a state's `desktop` (colour, wallpaper, style). A wallpaper reaches the guest on a CD in drive D: | [Colour and wallpaper](design/state-and-action.md#desktop-colour-and-wallpaper) |
| CLI and checks | Errors from `art98` print one clean line, not a traceback. Warnings say when the image or guest programs are older than the code (`freshness.py`). `art98 doctor` works on a host that has only a container engine and ffmpeg. CI runs `ruff check`, `ruff format --check` and the unit tests on Python 3.11 and 3.13 on each push and pull request (`.github/workflows/tests.yml`) | [CLI](setup/cli.md) |
| Container | Built: the VM service in `core/art98/container/`, `art98 up` and the Dockerfile in `setup/`. `art98 up` builds the image and runs setup, then stops; `art98 vm start` runs one long-lived VM container that `render` and `ping` attach to. Tested on rootful Docker 29.9 and rootless Podman. Tested from scratch: about 23 minutes, and its image renders the same frames as the host-built one | [Container](design/container.md) |

Audio is deferred. art98 is video only.

## What is open

### Next

In order, from the layer review of 2026-11-11. See also
[Not built, on purpose or not yet](design/decisions.md#not-built-on-purpose-or-not-yet).

1. **Other programs.** New programs (Calculator and the rest) go in `actions/programs/`, one
   file each, subclassing `Win`. Paint, Minesweeper and `Dialog` are not state apps yet.
2. **`--section`.** Render one section of a scene, on top of `next_section`.

### Leftovers from the dialog storm

- `RemoteVM` has no `disc_state()`. Only the local `VM` has it, and no art98 code calls it.
  Delete it or give `RemoteVM` one.
- `bmp_pixel` decodes 24-bit and 8-bit BMPs only. For any other depth the wallpaper pixel
  check is skipped. (A `lazy:` marker in the code.)
- A `Cascade` helper, and desktop icons and tray in a state, are not built.

### Known bugs, on hold

These were found while writing the docs. They are on hold. The truncation and the crash
handling are the ones a scene author can trigger.

| Where | Bug |
| --- | --- |
| Agent | Frames over 16384 bytes are truncated |
| Agent | An oversize `#` line is dropped |
| Host | An `ERR` sent after an `ACALL`'s `OK` is dropped |
| Agent | A failed `CreateThread` isn't handled |
| Host | Pending async calls aren't failed when the agent sends `! CRASH` |
| Host | `_read_loop` only catches `OSError` |
| Host | A failed `load_snapshot` leaves QEMU in its `restore-vm` state |
| Tests | Each `test_qemu.py` run leaves one `art98-*` socket folder in `$XDG_RUNTIME_DIR`: a test VM isn't closed |

### Docs that are out of date

- `put_file`, `get_file` and app launch times in the README, [bridge.md](scenes/bridge.md),
  [win32-recipes.md](scenes/win32-recipes.md) and the `put_file` docstring are quiet-host
  figures. On a busy host they can be several times slower.

### Smaller decisions

- The `ready` step writes `UserPreferencesMask`, but Windows 98 reads `UserPreferencemask`, so the setting has
  no effect. Fixing it changes the image. See [image.md](setup/image.md). `blank` turns the
  same effects off at run time, so it only matters for stock scenes. This and the other prep
  options for a blank snapshot are listed in
  [Blank start](design/blank-start.md#prep-changes-not-made).
- `art98 setup --from setup` and `--from init_api` fail after a
  finished build, because `install.img` is gone. The workaround is `--from vm`.

## Working notes

House rules for working on the repo are in [AGENTS.md](../AGENTS.md#rules). When running the VM tests
from a worktree, point `ART98_TEST_WORK` at a prepared work folder.
