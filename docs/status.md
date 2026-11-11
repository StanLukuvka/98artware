# Status

Last updated 2026-11-11. This page says what exists, what was done, and what is still open, so
work can pick up from here.

## What exists

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
| Container | Built: the backend in `core/art98/container/`, `art98 up` and the Dockerfile in `setup/`. `art98 up` builds the image and runs setup, then stops; `art98 vm start` runs the VM in the container. Tested on rootful Docker 29.9 and rootless Podman. Tested from scratch: about 25 minutes, and its image renders the same frames as the host-built one | [Container](design/container.md) |

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
    its own action class, starting from that code. (`Dialog` came back in item 19.)
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
14. **`actions.py` split, 2026-11-10.** It's now `actions/pointer.py`, `actions/keyboard.py` and
    `actions/window/`, and `Teleport` moved from `picture.py` to `commands.py`. The programs a
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

19. **Dialog storm, 2026-11-11.** `Dialog` is out of parked: it is in `art98.anim` with `size`,
    `disabled`, `set_message` and `icon`. `Backdrop` sets the desktop colour, and a state's
    `desktop` sets a colour and a wallpaper, which goes to the guest on a CD. The scene is
    `examples/dialog_storm` (GIF in the [gallery](scenes/gallery.md#dialog-storm)); its probes
    are in [experiments/dialog-storm](../experiments/dialog-storm/README-p0.md). What they found:
    - **Icons.** `STM_SETICON` on the box's icon slot works and draws 32 x 32. Seven custom
      icons, each seen in a real box: computer `shell32.dll` 15, printer `shell32.dll` 16, mouse
      `main.cpl` 0, telephone `modem.cpl` 0, cd `shell32.dll` 11, globe `shell32.dll` 13, flag
      `user.exe` 0 (all under `C:\WINDOWS\SYSTEM`). The icon static's id is 10, not 20. The
      static doesn't copy the icon, so it is destroyed only when the box is removed.
    - **Size and text.** Resizing the frame leaves the children alone, so the buttons and the
      text are laid out again. A size under the stock box is refused. A text static clips to its
      rectangle, so `set_message` moves it to fit. Yes/No boxes ignore `WM_CLOSE`.
    - **Colour.** `SetSysColors(COLOR_DESKTOP)` is right on the stock desktop for teal, dark red,
      red and white. The 16-bit screen rounds 128 to 120 and 255 to 248, so checks use the
      rounded colour or a tolerance. On a blank desktop the call shows the icons again, so
      `Backdrop` hides them again.
    - **CD.** The guest already has a CD drive, `D:`, empty. A disc goes in in 1 to 8 ms, the
      guest sees it in 40 to 110 ms, and setting a 1.4 MB wallpaper takes 0.3 to 0.8 s. The
      first read after the insert always worked (25+ runs); one bounded check (50 ms polls, 2 s)
      stays. No AutoPlay window. Same on the local backend, rootless Podman and Docker.
    - **Stretch.** `center`, `tile` and `stretch` all work. The wallpaper call does not bring
      icons or the taskbar back. The wallpaper path can't be read back, so one pixel is checked.
    - **Revert-eject rule.** `loadvm` restores the guest's empty tray but not QEMU's medium, so
      a revert must eject first (open tray with force, remove medium, close tray; 75 to 145 ms
      on the container). `Session.revert` does it only when it inserted a disc. The drive's qdev
      id differs between hosts (`device[5]` here), so it is read from `query-block`.
    - **Timings.** The proof scene renders in 4.8 s local, 6.0 s on Podman and 6.4 s on Docker,
      126 frames at 24 fps, pixel for pixel the same on every engine. Host CPU pressure was near zero.
    - **Same-title boxes.** The first version took any visible box whose title matched, so a
      new `Dialog` could attach to an older one. A `Dialog` now ignores windows that existed
      before its call.
20. **Programs unparked, 2026-11-11.** `Paint`, `Minesweeper` and `Screensaver` are action
    classes in `actions/programs/` (`paint.py`, `minesweeper.py`, `screensaver.py`), exported
    from `art98.anim`. `anim/apps.py` and `PARKED` are gone, with no old import path left.
21. **Drift audit, 2026-11-11.** Does the host's model of the screen drift from the guest? Position
    (the host's window rects and pointer against `GetWindowRect` and `GetCursorPos`) and pixels
    (the frame against a forced full repaint), on local, Podman and Docker, 5 runs of 6 scenes,
    1210 frames per backend: no drift in either, once three fixes were in. `set_colour` ends with
    a back-to-front `repaint_all` (before: 60 of 60 runs left 380 to 395 stray pixels in the box
    area; after: 0 of 60), `Minimize`, `Maximize` and `RestoreWindow` refresh the rect, and a
    resize-corner Spot carries its window so a Drag reads the size back. The dialog storm renders
    frame for frame identical on all three backends (`framemd5`), and its GIF was regenerated. A
    per-frame read-back (3 to 5 ms per prop) or forced repaint (25 to 67 ms) was measured and is
    not recommended. See [experiments/drift](../experiments/drift/README.md).

22. **VM service, 2026-11-11.** The VM is no longer booted for each render. `art98 vm start` runs
    one long-lived container, paused at `ready`. `art98 render` and `art98 ping` attach to it, and
    `art98 up` stops after setup and prints `art98 vm start`. The control connection is the lock: a
    second render gets `busy`, or waits with `--wait`. Release drops the relay, ejects the disc and
    pauses the VM, and frees the lock last, which fixes a release race the VM tests found. VM tests
    11 of 11 on Podman and on real Docker. Probes in `experiments/vm-service`: the run copy stayed at
    414 to 415 MiB over 30 renders (512 KiB written per render in one series); a render killed with `kill -9`
    recovered in about 0.05 s; a view-only VNC viewer gave the same frames as none. Removed:
    the backend switch (its flag and its environment variable), and the `quit` and `save_snapshot`
    wire ops.
    Over TCP a vanished client now frees the lock within about a minute (TCP keepalive, item 26).
    See [Container](design/container.md#the-vm-service) and [Configuration](setup/config.md).
23. **Desktop space, 2026-11-11.** Screen, work area, taskbar and metrics are read once per
    `prepare_desktop` into `scene.space`. Placement is checked before a size is sent. See
    [Desktop space](scenes/scene-api.md#desktop-space).
24. **Fresh desktop per scene, 2026-11-11.** Every scene now starts from `ready`, also when
    several scenes render in one attach. `Session.fresh` is set by `revert()`; `Scene.run` reverts
    unless the session is fresh, forgets the last run's props, and clears the flag before it
    touches the guest. A state scene right after attach reverts once, not twice; a mid-scene
    `set_state` still reverts. VM test: `core/tests/test_stage_scenes.py` (Paint, Minesweeper,
    then a state scene in one attach).
25. **Scene line in render errors, 2026-11-11.** A guarded render error raised from the scene
    file now ends with `(scene.py:LINE, in func)`, from the innermost frame in that file.
    `ART98_TRACE=1` still prints the full traceback.
26. **Clients in another container, 2026-11-11.** Three `art98.toml` keys: `[vm] transport`
    (`tcp`/`unix`; `ART98_TRANSPORT` still wins), `[vm] token_file` (default `<work>/vm.token`;
    outside `work/` it is mounted read-only into the VM container) and `[ports] connect` (the host
    a client dials; default `bind`, or `127.0.0.1` for a wildcard `bind`). A client needs only its
    `art98.toml` and the token file, never `work/`. TCP keepalive on both ends (idle 20 s, 3 probes
    10 s apart). Checked from a second Docker container over the docker0 gateway: `art98 ping` and
    an attach with revert. Probe: `experiments/vm-service/probe_container_client.sh`.

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
- `test_state_with_wallpaper` runs on the local backend only. The container path is covered by
  rendering a wallpapered state on both engines.

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
