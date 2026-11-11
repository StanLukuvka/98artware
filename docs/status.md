# Status

Last updated 2026-11-11. This page says what exists, what was done, and what is still open, so
work can pick up from here.

## What exists

| Part | State | Docs |
| --- | --- | --- |
| VM preparation | Built. `art98 setup` (alias `prep`) turns a Windows 98 SE disc into `work/golden.qcow2` with a `ready` snapshot, with no input. Four steps: vm, setup, init_api, ready | [Part 1](setup/README.md) |
| Bridge and agent | Built. `AGENT.EXE` proxies any Win32 call over COM1 using a framed protocol | [Bridge](scenes/bridge.md), [Instruction set](scenes/instruction-set.md) |
| Scene API and renderer | Built. `Scene`, props, animations, `art98 render`. Notepad is a program in `actions/programs/notepad.py`. The other program classes are parked, unexported | [Part 2](scenes/README.md) |
| Examples | `examples/blank_start` (the proof scene: a Picture and a Notepad, three sections), `examples/mvp`, `hello.py`, `showcase.py` and the gallery scenes | [Gallery](scenes/gallery.md) |
| Diagrams | Seven diagrams and the Manim comparison, with editable `.drawio` files | [Diagrams](diagrams/README.md) |
| States and sections | The MVP is built: state files, `set_state`, picture windows and `Teleport`. `Scene.next_section(name)` is built, on top of `cut()`. The `--section` option is not | [Design](design/state-and-action.md), [States](scenes/scene-api.md#states) |
| Recorder | Built: `Recorder`, with `cut()` to start a new clip during a run, `clips` to list them, and a join into the output. Clips are kept beside the output as MP4 | [Recorder](design/state-and-action.md#recorder), [Clips](scenes/scene-api.md#clips) |
| Programs | Notepad is the first program, in `actions/programs/notepad.py`. It opens a text file or an empty window and checks its title. Windows 98 drops a trailing `.txt` from the title | [Programs](design/programs.md) |
| CLI and checks | Errors from `art98` print one clean line, not a traceback. Warnings say when the image or guest programs are older than the code (`freshness.py`). `art98 doctor` works on a host that has only a container engine and ffmpeg. CI runs the unit tests on each push (`.github/workflows/tests.yml`) | [CLI](setup/cli.md) |
| Container | Built: the backend in `core/art98/container/`, `art98 up` and the Dockerfile in `setup/`. `art98 up` builds the image, runs setup in it and pings; `ART98_BACKEND=container` or `--backend container` runs a stage in it. The default backend is still `local`. Tested from scratch: about 25 minutes, and its image renders the same frames as the host-built one | [Container](design/container.md) |

Audio is deferred. art98 is video only.

## What was done

1. **Setup tool and bridge.** (Called the prep tool then.) Built and run against the real disc. First commit, `9f926fa`.
2. **Manim mapping plan.** A separate session mapped Manim's tools to Windows 98 actions in
   [MANIM_MAPPING_PLAN.md](archive/MANIM_MAPPING_PLAN.md), and a second pass reviewed it in
   [MANIM_MAPPING_REVIEW.md](archive/MANIM_MAPPING_REVIEW.md). Only a first slice of it is built,
   and both are archived.
3. **Scene API and docs.** Four sessions ran in parallel: the action API, the prep docs, the
   bridge docs and the diagrams. Their work was checked, corrected and committed together with
   the gallery GIFs in `a1531ea`.
4. **State and action design.** Today a scene can only run from `ready` to its end. The design
   adds hand-written JSON states for a static starting desktop, with actions in free Python on
   top. It was reviewed from a Manim maintainer's point of view and updated. The terms, goal,
   decisions, lifecycle diagram and MVP are in [the design](design/state-and-action.md).
5. **Revert test.** The first MVP step, run on a private copy. Set repeats and a revert leaves
   nothing behind. A Set takes 1.6 to 2.0 s on a quiet host, and 10 s on a busy one. Details are
   under [Test results](design/state-and-action.md#test-results), and the scripts are in
   [artware_experiments/revert-test](../experiments/revert-test/README.md).
6. **Stray pixels explained.** The odd Set out was the clean one. Usually Paint moving away leaves
   the "My Documents" label's pixels in Notepad's frame. Repainting the windows back to front at the
   end of Apply made 20 of 20 Sets identical, from `ready` and from a warm baseline. See
   [Stray pixels, explained](design/state-and-action.md#stray-pixels-explained).
7. **Warm baseline decided.** The MVP uses `ready` as it is. A warm baseline is only added if Set
   misses 2 s, and then preferably per run on the private copy.
8. **Recorder specified.** `Recorder` replaces `FrameRecorder` and can cut to a new clip during a
   run. See [Recorder](design/state-and-action.md#recorder).
9. **MVP narrowed, 2026-11-10.** All programs are out of the MVP, Paint included. Each will be its
   own action class later. The MVP has one window kind, a small art98 picture viewer (`VIEW.EXE`)
   that shows a BMP. Windows can be moved, teleported, closed and opened. See
   [Picture window](design/state-and-action.md#picture-window).
10. **MVP built, 2026-11-10.** `VIEW.EXE` and `Picture`, `Teleport`, state files, `Session.revert`,
    `set_state` and `self.prop`, the sample in `artware_experiments/set_state`, and their docs and tests. All five
    done-when checks pass. A Set with two windows and an image takes 1.45 s. See
    [MVP results](design/state-and-action.md#mvp-results). Committed in `24e8803`.
11. **Program classes parked, 2026-11-10.** `Notepad`, `Paint`, `Minesweeper`, `Screensaver` and
    `Dialog` still work and are tested, but `art98.anim` no longer exports them. Scenes import
    them from `art98.anim.apps`, which lists them in `PARKED`. Each program comes back later as
    its own action class, starting from that code.
12. **Blank start, 2026-11-10.** An audit found nothing that pops up on its own after a restore.
    Scenes now start on a black screen with no icons, taskbar, Start menu or pointer
    (`Scene.desktop = "blank"`, `pointer_visible`), made at run time by `art98/desktop.py`
    after each revert. The snapshot isn't changed. The older demos are pinned to
    `desktop = "stock"`. See [Blank start](design/blank-start.md).
13. **Container, 2026-11-10.** QEMU 10.2.2, setup and the guest programs moved into a Podman or
    Docker image, then all in `98artware_container/`. The existing `ready` snapshot restores in it
    unchanged. The container relays the agent's protocol to the host and serves screenshots,
    keys and reverts on a JSON channel, over a Unix socket on Linux and loopback TCP elsewhere.
    The host keeps `Bridge`, `FrameRecorder` and ffmpeg. A recorded frame takes 6.8 to 7.0 ms
    through the container against 5.6 to 6.3 ms locally. The suite passes on both backends, and
    the MVP scene renders through the container. A from-scratch `art98 up` took about 25
    minutes on a quiet host, and its image renders the MVP scene with all 257 frames identical
    to the host-built image's. Doctor and the guides now give Debian and Ubuntu package names
    too. See [Container](design/container.md).
14. **`actions.py` split, 2026-11-10.** It's now `anim/pointer.py`, `anim/keys.py` and
    `anim/window.py`, and `Teleport` moved from `picture.py` to `window.py`. The programs a
    state can open are listed once, in `setstate.py`, and `scene.py` sets up the pointer in
    one place. Nothing a scene imports changed.
15. **Cleanup and naming, 2026-11-11.** Each duplicated guest read (work area, screen size,
    pointer, window rect) now has one helper, and `Win._find` holds the one wait-for-window loop
    (`bd2c56c`). A named part of a scene is now a **section**, Manim's word, and "action" means
    an action class: one kind of thing on screen and the verbs that drive it. A plan to split
    the package into clearer parts was reviewed and adopted. Its steps are under Next.
16. **Package restructure, 2026-11-11.** Win32 constants and small guest helpers are in
    `win32.py` (`765a8cc`). The building blocks (`Animation` and its groups, rate functions,
    vectors, `Box`, `Prop`, `Spot`) are in `base/`, and the action families in `actions/`:
    `pointer.py`, `keyboard.py` and `window/` (`Win`, its commands, `Menu`, `Picture`).
    `art98.anim` is the entry point scripts import, with the same names (`f4a5e12`). The frame
    recorder is in `recorder.py` (`79a014a`). `Scene` calls `anim/setstate.py` for the desktop
    state and `anim/timeline.py` for the frames (`62b4634`). A scene loads under its own module
    name, so `gallery/typing.py` finds its own folder (`0f39d01`). Scenes are in `examples/`,
    the tools in `tools/`, the revert probes in `experiments/`, and render output goes to the
    ignored `out/` (`5579adc`). The lifecycle and architecture diagrams' PNGs were not
    redrawn.
17. **Recorder with `cut()`, 2026-11-11.** `Recorder` in `recorder.py` replaces `FrameRecorder`.
    `self.cut()` ends a clip between two frames. `render()` keeps the clips as `<stem>-01.mp4`
    and on beside the output and joins them into it by stream copy, or into one lossless
    recording when a GIF is wanted (`keep_clips=False` deletes them). `close()` and `cut()`
    raise `RecorderError` when ffmpeg failed, without hiding the scene's own error, and a screen
    size change inside a clip raises and suggests `cut()`. What the build added to the spec is
    under [As built](design/state-and-action.md#as-built).
18. **Docs, checks and the proof scene, 2026-11-11.** Notepad became the first program in
    `actions/programs/`. `next_section` was built; `--section` was not. Errors from the CLI are
    clean, freshness warnings were added, `art98 doctor` works with only a container engine, and
    CI runs the unit tests. `examples/blank_start` is the proof scene. Two host checks ran. The
    first frames of a stock desktop are settled by a pointer nudge, not a revert
    ([first-frame](../experiments/first-frame/README.md)). A busy host slows a render about 5
    times with the same frames, and a title-bar Drag no longer leaves stray label pixels
    ([host-checks](../experiments/host-checks/README.md),
    [On a busy host](setup/troubleshooting.md#on-a-busy-host)). The docs were corrected to match.

## What is open

### Next

In order, from the layer review of 2026-11-11. See also
[After the MVP](design/state-and-action.md#after-the-mvp).

1. **Rootful Docker test.** The switch to the host's uid in `entry.py` has only run against a
   stand-in uid map.
2. **Default backend.** Decide whether `container` becomes the default instead of `local`.
3. **Other programs.** Paint, Minesweeper and the rest return one at a time, each as a file in
   `actions/programs/` that subclasses `Win`, following the Notepad pilot. `apps.py` and the
   fixed `APPS` list go when the last one is moved.
4. **Gallery and showcase port.** Port the showcase and re-render the gallery.
5. **`--section`.** Render one section of a scene, on top of `next_section`.

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
- `art98 setup --from setup` and `--from init_api` (old names `install` and `patch`) fail after a
  finished build, because `install.img` is gone. The workaround is `--from vm`.

## Working notes

- For the local backend, set up QEMU in each shell with `. .tools/env.sh`. The container
  backend doesn't need `.tools/`.
- The stage tests boot the real image: point `ART98_TEST_WORK` at a prepared work folder when
  running from a worktree. They run on both backends.
- `work/` is gitignored and holds the images: installed copies of Windows, with the product
  key in clear text. Never commit or push anything from it, including the copies under
  `work/runs`.
- To stop a stray VM, kill it by its PID. `pkill -f qemu-system-i386` can match the shell that
  runs it.
- Timings depend on host load, so note `/proc/pressure/cpu` next to any figure.
