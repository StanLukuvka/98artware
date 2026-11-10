# Status

Last updated 2026-11-11. This page says what exists, what was done, and what is still open, so
work can pick up from here.

## What exists

| Part | State | Docs |
| --- | --- | --- |
| VM preparation | Built. `art98 setup` (alias `prep`) turns a Windows 98 SE disc into `work/golden.qcow2` with a `ready` snapshot, with no input. Four steps: vm, setup, init_api, ready | [Part 1](setup/README.md) |
| Bridge and agent | Built. `AGENT.EXE` proxies any Win32 call over COM1 using a framed protocol | [Bridge](scenes/bridge.md), [Instruction set](scenes/instruction-set.md) |
| Scene API and renderer | Built. `Scene`, props, animations, `art98 render`. The program classes are parked, unexported | [Part 2](scenes/README.md) |
| Examples | `examples/mvp`, `hello.py`, `showcase.py` and the gallery scenes | [Gallery](scenes/gallery.md) |
| Diagrams | Seven diagrams and the Manim comparison, with editable `.drawio` files | [Diagrams](diagrams/README.md) |
| States and sections | The MVP is built: state files, `set_state`, picture windows and `Teleport`. Sections aren't built | [Design](design/state-and-action.md), [States](scenes/scene-api.md#states) |
| Recorder | `FrameRecorder`, one file per render. A `Recorder` with `cut()` is specified, not built | [Recorder](design/state-and-action.md#recorder) |
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

## What is open

### Next

In order, from the layer review of 2026-11-11. See also
[After the MVP](design/state-and-action.md#after-the-mvp).

1. **Restructure the package**, one commit each, with the tests passing between. Nothing a
   scene imports changes: `art98.anim` and `art98.anim.apps` keep working.
   1. `win32.py`: the Win32 constants and small helpers, moved without changes. Raw
      `guest.user32` stays first-class, and `Bridge.move_window`, `find_window` and
      `set_display_mode` stay.
   2. Move the building blocks (`Animation` and its groups, rate functions, vectors, `Box`,
      `Prop`, `Spot`) out of `anim/` into a package below the actions, so `anim/` is only the
      public entry point. Short modules stay at the old paths for the tests that import them.
   3. Split `session.py` into the session and the recorder.
   4. Split `scene.py` into its desktop half (`set_state`, the blank start, the props on
      stage) and its timeline half (`play`, `pause`, `live`). `Scene` stays the one class a
      script uses.
   5. Move the top-level folders: `examples/` for maintained scenes, `experiments/` for
      throwaway work, `tools/` for `check_docs.py` and `render_all.py`, and a gitignored `out/`.
      Docs links, tests and script paths move in the same commit. Fix `cli._load_scene` here: it
      registers a scene module by file name, so a scene file named like a standard module (such
      as `gallery/typing.py`) finds state files in the wrong folder.
2. **The [recorder](design/state-and-action.md#recorder) with `cut()`.** It moves
   `FrameRecorder` out of `session.py`. Its open questions were
   [decided](design/state-and-action.md#recorder-decisions) on 2026-11-10: one GIF from joined lossless
   clips, clips kept as MP4, the `close()` exit-code fix included, and a size change inside a
   clip raises.
3. **Sections:** `next_section` and `--section`.
4. **Program classes:** a one-page design, then a Notepad pilot. Each program becomes a file
   in `actions/programs/` that subclasses `Win`, made when its pilot starts. The base is `Prop`,
   with hooks for a name used in state files, a check of its state entry, and opening or
   adopting a window from a state. Those replace the fixed `APPS` list and the `"picture"`
   special case in `state.py`. `apps.py` stays whole until then.
5. **Port the showcase** and re-render the gallery.
6. **Container follow-ups.** Try real Docker, rootful above all: the switch to the host's uid
   in `entry.py` has only run against a stand-in uid map. Then decide whether `container`
   becomes the default backend.

Two bugs on hold below sit on the `set_state` path, the failed `load_snapshot` and the pending
async calls on `! CRASH`. They may be worth taking off hold.

### Known bugs, on hold

These were found while writing the docs. Fixing them was started, then paused for the design
work. None of them block the MVP.

| Where | Bug |
| --- | --- |
| Agent | Frames over 16384 bytes are truncated |
| Agent | An oversize `#` line is dropped |
| Agent | An `ERR` sent after an `ACALL`'s `OK` is dropped |
| Agent | A failed `CreateThread` isn't handled |
| Host | Pending async calls aren't failed when the agent sends `! CRASH` |
| Host | `AsyncCall.wait()` waits forever by default |
| Host | `_read_loop` only catches `OSError` |
| Host | A failed `load_snapshot` leaves QEMU in its `restore-vm` state |
| Host | `FrameRecorder.close` doesn't check ffmpeg's exit code |
| Tests | Each `test_qemu.py` run leaves one `art98-*` socket folder in `$XDG_RUNTIME_DIR`: a test VM isn't closed |

### Docs that are out of date

- `put_file`, `get_file` and app launch times in the README, [bridge.md](scenes/bridge.md),
  [win32-recipes.md](scenes/win32-recipes.md) and the `put_file` docstring are quiet-host
  figures. On a busy host they can be several times slower.
- On a fresh boot, frames before the first pointer move have no pointer and slightly brighter
  colours. This affects stock scenes and isn't documented.
- Moving a window off another one can leave desktop label pixels in the lower window's frame.
  Today's scenes probably show this. It isn't checked or documented in Part 2.

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
