# Build history

The dated build diary, moved out of [status.md](../status.md) for the 0.1.0 release. It is kept
as it was written, so it uses old terms such as "backend" and `FrameRecorder`. For what is true
now, read [status.md](../status.md) and the [changelog](../../CHANGELOG.md).

1. **Setup tool and bridge.** (Called the prep tool then.) Built and run against the real disc. First commit, `9f926fa`.
2. **Manim mapping plan.** A separate session mapped Manim's tools to Windows 98 actions in
   [MANIM_MAPPING_PLAN.md](MANIM_MAPPING_PLAN.md), and a second pass reviewed it in
   [MANIM_MAPPING_REVIEW.md](MANIM_MAPPING_REVIEW.md). Only a first slice of it is built,
   and both are archived.
3. **Scene API and docs.** Four sessions ran in parallel: the action API, the prep docs, the
   bridge docs and the diagrams. Their work was checked, corrected and committed together with
   the gallery GIFs in `a1531ea`.
4. **State and action design.** Today a scene can only run from `ready` to its end. The design
   adds hand-written JSON states for a static starting desktop, with actions in free Python on
   top. It was reviewed from a Manim maintainer's point of view and updated. The terms, goal,
   decisions, lifecycle diagram and MVP are in [the design](../design/state-and-action.md).
5. **Revert test.** The first MVP step, run on a private copy. Set repeats and a revert leaves
   nothing behind. A Set takes 1.6 to 2.0 s on a quiet host, and 10 s on a busy one. Details are
   under [Test results](../../experiments/revert-test/README.md#test-results), and the scripts are in
   [artware_experiments/revert-test](../../experiments/revert-test/README.md).
6. **Stray pixels explained.** The odd Set out was the clean one. Usually Paint moving away leaves
   the "My Documents" label's pixels in Notepad's frame. Repainting the windows back to front at the
   end of Apply made 20 of 20 Sets identical, from `ready` and from a warm baseline. See
   [Stray pixels, explained](../../experiments/revert-test/README.md#stray-pixels-explained).
7. **Warm baseline decided.** The MVP uses `ready` as it is. A warm baseline is only added if Set
   misses 2 s, and then preferably per run on the private copy.
8. **Recorder specified.** `Recorder` replaces `FrameRecorder` and can cut to a new clip during a
   run. See [Recorder spec](#recorder-spec).
9. **MVP narrowed, 2026-11-10.** All programs are out of the MVP, Paint included. Each will be its
   own action class later. The MVP has one window kind, a small art98 picture viewer (`VIEW.EXE`)
   that shows a BMP. Windows can be moved, teleported, closed and opened. See
   [Picture window](#picture-window-spec).
10. **MVP built, 2026-11-10.** `VIEW.EXE` and `Picture`, `Teleport`, state files, `Session.revert`,
    `set_state` and `self.prop`, the sample in `artware_experiments/set_state`, and their docs and tests. All five
    done-when checks pass. A Set with two windows and an image takes 1.45 s. See
    [MVP results](#mvp-plan-and-results). Committed in `24e8803`.
11. **Program classes parked, 2026-11-10.** `Notepad`, `Paint`, `Minesweeper`, `Screensaver` and
    `Dialog` still work and are tested, but `art98.anim` no longer exports them. Scenes import
    them from `art98.anim.apps`, which lists them in `PARKED`. Each program comes back later as
    its own action class, starting from that code. (`Dialog` came back in item 19.)
12. **Blank start, 2026-11-10.** An audit found nothing that pops up on its own after a restore.
    Scenes now start on a black screen with no icons, taskbar, Start menu or pointer
    (`Scene.desktop = "blank"`, `pointer_visible`), made at run time by `art98/desktop.py`
    after each revert. The snapshot isn't changed. The older demos are pinned to
    `desktop = "stock"`. See [Blank start](../design/blank-start.md).
13. **Container, 2026-11-10.** QEMU 10.2.2, setup and the guest programs moved into a Podman or
    Docker image, then all in `98artware_container/`. The existing `ready` snapshot restores in it
    unchanged. The container relays the agent's protocol to the host and serves screenshots,
    keys and reverts on a JSON channel, over a Unix socket on Linux and loopback TCP elsewhere.
    The host keeps `Bridge`, `FrameRecorder` and ffmpeg. A recorded frame takes 6.8 to 7.0 ms
    through the container against 5.6 to 6.3 ms locally. The suite passes on both backends, and
    the MVP scene renders through the container. A from-scratch `art98 up` took about 25
    minutes on a quiet host, and its image renders the MVP scene with all 257 frames identical
    to the host-built image's. Doctor and the guides now give Debian and Ubuntu package names
    too. See [Container](../design/container.md).
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
    under [As built](#as-built).
18. **Docs, checks and the proof scene, 2026-11-11.** Notepad became the first program in
    `actions/programs/`. `next_section` was built; `--section` was not. Errors from the CLI are
    clean, freshness warnings were added, `art98 doctor` works with only a container engine, and
    CI runs the unit tests. `examples/blank_start` is the proof scene. Two host checks ran. The
    first frames of a stock desktop are settled by a pointer nudge, not a revert
    ([first-frame](../../experiments/first-frame/README.md)). A busy host slows a render about 5
    times with the same frames, and a title-bar Drag no longer leaves stray label pixels
    ([host-checks](../../experiments/host-checks/README.md),
    [On a busy host](../setup/troubleshooting.md#on-a-busy-host)). The docs were corrected to match.

19. **Dialog storm, 2026-11-11.** `Dialog` is out of parked: it is in `art98.anim` with `size`,
    `disabled`, `set_message` and `icon`. `Backdrop` sets the desktop colour, and a state's
    `desktop` sets a colour and a wallpaper, which goes to the guest on a CD. The scene is
    `examples/dialog_storm` (GIF in the [gallery](../scenes/gallery.md#dialog-storm)); its probes
    are in [experiments/dialog-storm](../../experiments/dialog-storm/README-p0.md). What they found:
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
    not recommended. See [experiments/drift](../../experiments/drift/README.md).

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
    See [Container](../design/container.md#the-vm-service) and [Configuration](../setup/config.md).
23. **Desktop space, 2026-11-11.** Screen, work area, taskbar and metrics are read once per
    `prepare_desktop` into `scene.space`. Placement is checked before a size is sent. See
    [Desktop space](../scenes/scene-api.md#desktop-space).
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

## Moved from the design pages, 2026-11-13

The sections below were cut out of `docs/design/` in the 2026-11-13 docs review and are kept as they
were written, so they use old terms such as "backend", `FrameRecorder` and "the owner". Each
heading says where its text came from. Where a design page kept a short stub, it links here.


### Recorder spec

From `state-and-action.md`, section "Recorder" (Before, Change, Recorder decisions, As built).

Status: spec decided 2026-11-10, built 2026-11-11 in `core/art98/recorder.py`. See
[As built](#as-built) for what the build added to the spec. The API is in
[bridge.md](../scenes/bridge.md#recorder) and [scene-api.md](../scenes/scene-api.md#clips).

#### Before

`FrameRecorder` in `session.py` wrote one file per render. `render()` opens it around
`scene.run()`, and a scene sees it as `self.video`. Frames are taken when the script asks, never
on a timer:

- `frame(hold=1)` waits for the guest to repaint (`SYNC`), takes a QMP `screendump`, and writes
  `hold` copies to ffmpeg. `play()` calls it once per step, and `pause()` once with a long hold.
- `live(seconds)` takes frames on the host clock without the repaint wait, for things that move
  by themselves.
- Video time is frames over fps, so a slow host makes the same video as a fast one.

It can't be changed during a run: one file, one fps, and `close()` doesn't check ffmpeg's exit code.

#### Change

`Recorder` replaces `FrameRecorder`. A scene reaches it as `self.recorder`, and `self.video`
stays as another name for it. The only new control is cutting to a new clip.

| Member | What it does |
| --- | --- |
| `frame(hold=1)`, `live(seconds, stop_condition=None)` | As today |
| `cut(path=None)` | Closes the current clip, fails if its ffmpeg failed, and starts the next one. It returns the closed clip's path. Without `path`, clips are named `<stem>-01<suffix>`, `<stem>-02<suffix>` and so on |
| `path` | The clip being written now |
| `clips` | Finished clips, in order |
| `count`, `total` | Frames in this clip, and in all clips so far. `Scene.time` uses `total` |
| `close()` | Closes the last clip and fails if its ffmpeg failed |
| `join(output)` | Joins the clips into one file. Every clip uses the same codec settings, so this is a stream copy |

- A cut falls between two frames, so no frame is lost or repeated.
- A scene that never cuts writes one file, exactly as today, with no join.
- With cuts, `render()` keeps the clips beside the output and joins them into it.
- `set_state()` doesn't cut. A script that wants one clip per state calls `cut()` after it.
- `next_section` will call `cut()` with the section name, and `--section` builds on `clips`.

Checking ffmpeg's exit code touches one of the host bugs on hold (`FrameRecorder.close`). `cut()`
needs it to know a clip finished, so the recorder work would include that fix.

Not in this change: pausing capture, cropping or following a window, and real-time capture.

#### Recorder decisions

Decided 2026-11-10: the owner took all four recommendations below. Sizes come from re-encoding `hello.mp4` and
`showcase.mp4`, the two demo videos in the repository: H.264 at CRF 12 is about 10 to 14 KB a
second, and lossless FFV1 about 1.5 to 2.2 MB a second, 150 times more.

**1. A GIF once a render is cut.** Today a GIF is made from one lossless recording (FFV1), because
H.264's 4:2:0 colour smears 1-pixel coloured text, and the MP4 is then encoded from that same
recording.

*Decided:* when a GIF is wanted, every clip is recorded lossless, the clips are joined by
stream copy into one lossless recording, and the GIF and MP4 are made from it, exactly as today.
The render still makes one GIF. A GIF per clip isn't made: each would get its own palette, so
colours would shift from one to the next. `--section` can add per-clip GIFs later, where a
shifted palette doesn't matter.

**2. Whether clips are kept after the join.**

*Decided:* keep them, since cutting is something a scene asks for and sections will build
on the clips. They're kept as H.264 MP4, named `<stem>-01.mp4` and so on beside the output, even
when the output is only a GIF. When the clips were recorded lossless, each is encoded to MP4 at
the end and the lossless one deleted, so a kept clip costs what the MP4 output costs. A scene that
never cuts leaves no clips, as today. `render(..., keep_clips=False)` deletes them after the join.

**3. Whether the `close()` exit-code bug is in scope.**

*Decided:* yes. `cut()` can't say a clip is finished without it, and the fix is small:
`close()` waits for ffmpeg and raises if it failed. One rule goes with it: when the scene itself
raised, `close()` still closes ffmpeg but doesn't replace the scene's error with its own.

**4. A state that changes the screen size.** Not in the original list. A state's `display` can
switch the guest to another size partway through a render. Frames reach ffmpeg as PPM images,
and ffmpeg scales every frame to the first frame's size by default, so today the stretch after the
change is probably resized without warning. That hasn't been tried. With clips, two clips of
different sizes can't be joined by stream copy.

*Decided:* the recorder checks the size of each frame. If the size changes inside a clip,
it raises and suggests `cut()` before the `set_state` that changes it. If clips of different
sizes are joined, the join fails with the sizes in the message. Scaling is left to the scene's
author, outside art98.

#### As built

Built 2026-11-11 as specified, with these additions:

- `Scene.cut(path=None)` wraps `self.recorder.cut`, so a script writes `self.cut()`.
- Each clip's ffmpeg starts at the clip's first frame. A cut with nothing recorded since the last
  one closes nothing, makes no empty file, and returns `None`. So `set_state` then `cut()` at the
  very start of a scene is harmless. A `path` given to such a cut names the clip to come.
- The first clip is written at the output's name and renamed to `<stem>-01` by the first cut,
  so a scene that never cuts is unchanged. A clip the scene named still takes a number, so
  `cut()`, `cut("intro.mp4")`, `cut()` gives `-01`, `-02`, `intro.mp4`, `-04`.
- A lossless recorder writes every clip as `.mkv`, whatever suffix it was given, since FFV1
  doesn't go in MP4. In a GIF render the kept MP4 of a clip the scene named is that name with
  `.mp4`.
- ffmpeg's error output goes to a log per clip, and the `RecorderError` quotes it. When the
  scene raised, a recorder failure is added to the scene's error as a note.
- `render()` raises `RecorderError` if the scene recorded no frames. `keep_clips` is a Python
  argument only: `art98 render` has no flag for it.
- `Recorder` and `RecorderError` are exported from `art98`. The name `FrameRecorder` is gone.

Checked with a copy of `examples/mvp/mvp.py` that calls `self.cut()` right after
`set_state("states/gallery.json")`, rendered with `-o mvpcut.mp4 --gif mvpcut.gif` on both
backends: `mvpcut-01.mp4` has 152 frames, `mvpcut-02.mp4` 105, and the joined `mvpcut.mp4` 257,
the same count as the uncut scene. The GIF has 128 frames at 15 fps. Both backends wrote files of
the same sizes. `/proc/pressure/cpu` some avg10 was 0.00.

### Picture window spec

From `state-and-action.md`, section "Picture window". The facts only this section had are now in [Programs](../design/programs.md#picture).

Status: built, 2026-11-10.

The MVP's only window. Windows 98 has no small image viewer, and Paint brings its own tools,
canvas and quirks, so art98 ships a tiny one.

- **Program.** `guest/picture_viewer/view.c` builds `VIEW.EXE` with the agent's toolchain, using only functions
  Windows 98 has. It came out at 4 KB.
- **Command line.** `VIEW.EXE <x> <y> <width> <height> "<title>" ["<image.bmp>"]`. Each window is
  its own process, and it opens where the state wants it, so nothing moves on screen first.
- **Window.** A normal window: title bar, minimise, maximise and close buttons, a sizing frame
  and a taskbar button. Its class is `Art98View`.
- **Contents.** A BMP drawn at 1:1, centred, with the rest of the client area grey. With no image,
  the window is plain grey. An image bigger than the window is cropped. Scaling and other formats
  are out for now.
- **Getting there.** A revert removes everything copied since `ready`, so `VIEW.EXE` and each
  image are copied again when they're missing. Each file goes in `C:\ART98\F<7 hex of its
  sha256>\`, so one `GetFileAttributesA` call tells whether the right file is there. Putting the
  viewer in the setup tool instead would change the image, so that needs a decision.
- **Prop.** `Picture(Win)`, with `title`, `image`, `at` and `size`. The image is checked on the
  host when the prop is made. Windows 98's `LoadImage` crashes inside 16-bit code on a BMP that's
  cut short, so the viewer can't catch it. The host check stops that before the guest is asked,
  and if the viewer crashes anyway, `Picture` sees Windows' crash dialog and fails at once instead
  of waiting 15 s.

On camera, a picture window does what any window does:

| Do | How |
| --- | --- |
| Move | `pic.animate.shift(...)`, as today |
| Teleport | `Teleport(pic, to=...)`, a new `Instant` that places the window in one frame. `run_time=0` on `.animate` already gives the same result |
| Close | `Close(pic)`, as today |
| Open | `self.add(Picture(...))`, as today |

### Backend, the design before the VM service

From `state-and-action.md`, section "Backend". Two measured facts from it are now in [Timing](../design/container.md#timing).

> **Superseded.** This section describes the design before the VM service: a per-render boot with
> `start()` and `-loadvm ready`. Now one long-lived VM container serves each render, which
> attaches, reverts and releases. See [decision 6](../design/decisions.md#6-the-vm-service-one-long-lived-vm-one-render-at-a-time)
> and [Container](../design/container.md#the-vm-service). The table is kept as the original design.

| Call | QEMU today |
| --- | --- |
| `start()` | Make a private copy of the image, then boot it with `-loadvm ready` |
| `revert()` | `loadvm ready` in the running VM |
| `capture()` | QMP `screendump` |
| `send_keys()` | QMP `send-key` |
| `connect()` | COM1 over a unix socket |

The first run calls `start()`. A restart calls `revert()`, which took 0.06 to 0.2 s in the test and
keeps the bridge connected, so it avoids a new QEMU process. `start()` is the fallback if the VM has died.
Python rebuilds its props after any revert, because every window handle changes.

Revert and capture stay outside Windows 98 for now. Revert can't be done reliably from inside.
Capture over serial would take about 3 s per frame, against 6.5 ms now. Mouse input is already in
the guest.

### Resolved rows of "Not proven yet"

From `state-and-action.md`, table "Not proven yet".

| Item | Risk |
| --- | --- |
| Wallpaper | Built. The bitmap reaches the guest on a CD, not by `put_file`. See "Desktop colour and wallpaper" |
| Copying files | `put_file` ran at about 90 KB/s on a quiet host and about 12 KB/s on a busy one, so a 1.4 MB wallpaper could take 15 s or far longer on every Set. That was too slow, so a wallpaper goes on a read-only disc attached by the backend: about 1 s for 1.4 MB |
| Stray pixels | Explained. Moving a window off another one can leave desktop label pixels in the lower window's frame. A repaint at the end of Apply clears them. See "Test results" |

### MVP plan and results

From `state-and-action.md`, sections "MVP" (In, Out, Done when, Order) and "MVP results". The measured results are summarised in [State and action design](../design/state-and-action.md#how-it-runs).

**A script can jump the desktop to a state it chose, as many times as it likes, and record from
there.** The baseline already exists, so the MVP is the path from Loading to Ready, plus a
restart. That path is the biggest unknown, and everything else builds on it.

#### In

| Part | What it covers |
| --- | --- |
| Display | `"display": [800, 600, 16]`, using `set_display_mode`. A switch takes 65 to 150 ms with no reboot, but only modes the driver offers work |
| Windows | Picture windows only, each with `id`, `title`, `at`, `size`, `show` and an order |
| Images | `open` on a picture window, with a BMP copied to the guest first |
| On camera | Move, teleport, close and open a picture window. Only `Teleport` is new |
| Pointer | Placed last, because focus may need a click on a title bar |
| Revert | `loadvm ready` in the running VM, kept as one plain function |
| Set | `set_state(path)`, usable any number of times. Each call is a hard cut, and ends with a repaint of the state's windows |
| Check | Display, each window's title, show state, place, size and order, and the pointer |
| Scene | `state`, `set_state()` and `self.prop()` |

Moving, opening and closing windows on camera use the existing animations, starting from the
state. Teleporting adds one small `Instant`.

```python
class Mvp(Scene):
    state = "states/two_windows.json"

    def construct(self):
        flower = self.prop("flower")
        self.play(flower.animate.shift(200 * RIGHT), run_time=2)
        self.play(Teleport(flower, to=(40, 40)))
        self.play(Close(flower))
        self.add(Picture("Sky", image="assets/sky.bmp", at=(300, 200), size=(320, 240)))

        self.set_state("states/gallery.json")
        self.pause(1)
        self.play(self.prop("picture").animate.shift(100 * DOWN), run_time=2)
```

#### Out, for now

Every program: Paint, Notepad, Minesweeper and any `command`. (All of them have since returned as action classes in `actions/programs/`, one file each.) Icons and tray. (The desktop colour and wallpaper came later: see "Desktop colour and wallpaper".)
Sections, clips and `--section`. Holding, Failed with a live VM, the Python prompt and Stop. The
backend interface, and the agent bug fixes.

#### Done when

1. Setting the same state 10 times gives matching screenshots. Any difference gets explained.
2. Set takes under 2 s for a state with two windows and a small image. The real figure goes in
   the docs either way.
3. A bad file, a missing window or a wrong position stops with a clear error.
4. The sample scene renders, moving, teleporting, closing and opening a picture window, and
   jumping between two states.
5. Existing scenes and tests still pass.

#### Order

All done, 2026-11-10.

1. Test revert and a hand-applied state in a throwaway script on a private copy. It passed, and
   the stray pixels are explained. See "Test results".
2. Make `put_file` check the written count.
3. Build `VIEW.EXE`, the `Picture` prop and `Teleport`, and test them by hand on a private copy.
4. Add the schema and loader.
5. Add revert, apply and check.
6. Add `state`, `set_state()` and `self.prop()` to `Scene`.
7. Add the sample scene and tests, then record the results.

#### MVP results

Run on 2026-11-10 on private copies, with host CPU pressure (some, avg10) between 0.02 and 1.6%.

| Done when | Result |
| --- | --- |
| 1. Same state 10 times | 10 of 10 screenshots identical, for both sample states |
| 2. Set under 2 s | Two windows and a 57 KB image: median 1.45 s (1.18 to 1.61). One window and an image: median 0.97 s (0.75 to 1.27) |
| 3. Clear errors | A bad file lists every problem before the desktop is touched. A window Windows won't make (`"size": [40, 20]`) stops with `size [40, 20] wanted, the guest has [112, 27]`. A cut-short image fails on the host. Unit tests cover a missing window, the wrong order, title, show state, display and pointer |
| 4. Sample scene | `examples/mvp/mvp.py` renders in 7.7 s, moving, teleporting, closing and opening a picture window, then jumping to a second state |
| 5. Nothing broken | 199 tests pass (32 skip without QEMU set up), all 32 doc samples render, and so do `hello.py`, `showcase.py` and the gallery scenes |

What it's made of:

- `Session.revert()` fails every open call and async call at once (`Bridge.abandon`), then
  reverts and pings.
- `art98.state` loads and checks a state file. `art98.anim.setstate` applies it back to front and
  checks it. Maximizing happens as each window opens, because it activates the window, and
  minimized windows are left out of the order check, because Windows 98 sends them to the back.
- `Scene.set_state()` forgets the old props, so one used after a Set fails with "not on stage"
  instead of driving a stale handle. Adding it again opens a new window.

Found on the way:

- The revert winds the guest's clock back to the snapshot's time, so the taskbar clock can go back
  a minute at a Set.
- Copying the files again is a large part of a Set: about 60 KB per Set for the sample.

### After the MVP, the open-item list

From `state-and-action.md`, section "After the MVP". Items 1, 2 and 6 are built. Open work is in [status](../status.md#next).

1. **Sections and clips.** The recorder above, then `next_section`, one clip per section, capture
   off and `--section`.
2. **Programs.** Each program (Paint, Notepad, Minesweeper and others) becomes its own action
   class. Not designed yet.
3. **More of the desktop.** The colour and the wallpaper are built. Icons and tray remain, each after its test.
4. **Backend.** Move start, revert, capture and keys behind one interface.
5. **Run control.** Holding and Failed with the Python prompt, and Stop. `render()` closes the VM
   on exit today, so this needs restructuring.
6. **Docs.** Update Part 2 and port the showcase as the proof. (`anim/actions.py` is already
   split into `actions/`.)

The agent bug fixes are separate work. Nothing here depends on them.

### Terms, rename history and the decisions table

From `state-and-action.md`, sections "Terms" and "Decisions". The glossary now holds the terms, and [decisions.md](../design/decisions.md) holds the reasons.

## Terms

| Term | Meaning |
| --- | --- |
| **Baseline** | The clean desktop we always revert to. Today that's `ready`. |
| **State** | A hand-written JSON file describing a static starting desktop. |
| **Set** | Revert to the baseline and apply a state, off camera. In code, `set_state()`. |
| **Section** | A named part of `construct()`, marked with `next_section`, as in Manim. |
| **Animation** | A building block a section plays, like `Glide` or `Stroke`. |
| **Action** | A class for one kind of thing on screen and the verbs that drive it, such as `Win` and `Teleport`. Programs come back as action classes. |
| **Clip** | The video file one section writes. |
| **Scene** | A state plus the sections that run on it, recorded. |
| **Backend** | Whatever provides revert and capture. Today that's the VM service, which runs QEMU in a container. |

"Stage" keeps its meaning in the setup tool only (its steps were stages before). "Snapshot" only means the VM feature behind the baseline.

Manim users may read "state" as `save_state`, so the docs should say early that a state here is
a desktop. Until 2026-11-11 this design called a named part of a scene an action. That word now
means action classes, and the parts are sections, which is Manim's word for them. The pointer and
keyboard animations, once in `anim/actions.py`, are in `actions/pointer.py`, `actions/keyboard.py`
and `actions/window/`. Programs now live in `actions/programs/`, one file each (Notepad first).

## Decisions

| Decision | Why |
| --- | --- |
| A state is static and hand-written | Not every result of a scene can be described, and forcing it would limit what scenes can do |
| A state is stored as JSON | It can be written by hand, and it covers wallpaper, icons and tray, which props can't |
| A state can open a file | A finished drawing can start the next scene, without saving a scene's result |
| Sections are parts of `construct()` | Manim's `next_section` already does this, and a list of method names would be a second system |
| Sections can chain | Each one picks up where the last ended |
| Each section writes its own clip | Part of a scene can be recorded again, and clips are host files with no tie to the VM |
| A finished run holds the desktop | You can try more sections without a restart |
| A failed run holds the desktop too | The most useful evidence is the live desktop where it failed |
| Every restart takes the same path | A run never continues from a half-finished desktop |
| ~~Revert once after boot, so the first frame matches~~ | Replaced by one `SetCursorPos` nudge in `Pointer.attach`. It gives the same frame without a second boot step. See [first-frame](../../experiments/first-frame/README.md) |

An animation is a Python script, so it's arbitrary code. As with Manim, art98 doesn't decide how
many states or output files one script uses. Set is an ordinary call, and the rest is up to the
script.

### Container build plan and as-built notes

From `container.md`, sections "Steps" and "What was built", with the "Checked" lists. The facts that are still true are now in [Container](../design/container.md).

#### Steps

1. **Image.** The Dockerfile and its ignore file. Check the QEMU version inside, then
   restore `ready` from the existing `work/` in the container and ping the agent. If the snapshot
   doesn't load, stop: making a new one changes the `ready` image and needs the owner's go-ahead.
2. **Stage.** `art98 serve`, `container.py` and the `boot` backend (replaced on 2026-11-11 by [the VM service](../design/container.md#the-vm-service)). Tests against a fake
   server, with no VM, plus a real test marked `container`.
3. **Timing.** Frames are 1.44 MB each. Measure a 300-frame recording through the rootless
   port forward against QEMU on the host, noting `/proc/pressure/cpu`. If the forward is too
   slow, switch the transport to a Unix socket in a mounted folder (Linux only), keeping TCP for
   other hosts.
4. **Up.** `art98 up` and setup in the container, tested from scratch on a separate work folder
   (`work-container/`), so the current `work/` and its snapshot are never touched.
5. **Docs.** The setup guide, the README, `status.md` and the tour. `.tools/` and `env.sh`
   become optional, kept for setup on the host and for experiments.

#### What was built

Where the build differs from, or adds to, the plan above:

- The handshake answers `ok` or `error <reason>`, so the host can tell a refused connection from
  a guest still booting.
- The Unix socket and shared-folder screenshots on Linux, from [Timing](../design/container.md#timing).
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
  owns what it writes ([above](../design/container.md#who-owns-what-the-container-writes)). Podman secrets, and the
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
[the VM service](../design/container.md#the-vm-service). The results stand for the code they ran on.

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

### Programs rework story

From `decisions.md`, section 9 "Code by layer and by action family", Why, and section 19, Why.

**Why.** Everything used to sit in one `anim/` folder, and programs piled up in one module. A program is added one at a time, so each needs its own place, and the layers make it clear which code talks to the guest. When the programs were reworked, they were parked first and then brought back one by one as action classes, starting with a Notepad pilot.

From section 19: **Why.** art98 is young, and keeping old paths alive costs more than updating the callers. When the VM service was designed, the lean option (fewer settings, one server mode, one module) was picked over a more general one, and features that wait on a number, such as recreating the run copy of the disk, were left until a probe showed a need (it didn't: the run copy stayed the same size over 30 renders). When the programs were reworked, parking them as commented-out code was rejected in favour of keeping them live and tested, and then rebuilding each one properly.
