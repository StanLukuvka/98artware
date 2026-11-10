# Status

Last updated 2026-11-10. This page says what exists, what was done, and what is still open, so
work can pick up from here.

## What exists

| Part | State | Docs |
| --- | --- | --- |
| VM preparation | Built. `art98 prep` turns a Windows 98 SE disc into `work/golden.qcow2` with a `ready` snapshot, with no input | [Part 1](prep/README.md) |
| Bridge and agent | Built. `AGENT.EXE` proxies any Win32 call over COM1 using a framed protocol | [Bridge](actions/bridge.md), [Instruction set](actions/instruction-set.md) |
| Scene API and renderer | Built. `Scene`, props, animations, `art98 render`. The program classes are parked, unexported | [Part 2](actions/README.md) |
| Examples | `examples/mvp`, `hello.py`, `showcase.py` and the gallery scenes | [Gallery](actions/gallery.md) |
| Diagrams | Six architecture diagrams with editable `.drawio` files | [Diagrams](diagrams/README.md) |
| States and actions | The MVP is built: state files, `set_state`, picture windows and `Teleport`. Named actions aren't built | [Design](design/state-and-action.md), [States](actions/scene-api.md#states) |
| Recorder | `FrameRecorder`, one file per render. A `Recorder` with `cut()` is specified, not built | [Recorder](design/state-and-action.md#recorder) |

Audio is deferred. art98 is video only.

## What was done

1. **Prep tool and bridge.** Built and run against the real disc. First commit, `9f926fa`.
2. **Manim mapping plan.** A separate session mapped Manim's tools to Windows 98 actions in
   [MANIM_MAPPING_PLAN.md](MANIM_MAPPING_PLAN.md), and a second pass reviewed it in
   [MANIM_MAPPING_REVIEW.md](MANIM_MAPPING_REVIEW.md). Only a first slice of it is built.
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
   [experiments/revert-test](../experiments/revert-test/README.md).
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
    `set_state` and `self.prop`, the sample in `examples/mvp`, and their docs and tests. All five
    done-when checks pass. A Set with two windows and an image takes 1.45 s. See
    [MVP results](design/state-and-action.md#mvp-results). Committed in `24e8803`.
11. **Program classes parked, 2026-11-10.** `Notepad`, `Paint`, `Minesweeper`, `Screensaver` and
    `Dialog` still work and are tested, but `art98.anim` no longer exports them. Scenes import
    them from `art98.anim.apps`, which lists them in `PARKED`. Each program comes back later as
    its own action class, starting from that code.

## What is open

### Next

[After the MVP](design/state-and-action.md#after-the-mvp): the
[recorder](design/state-and-action.md#recorder) with clips, then each program as its own action
class.

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

### Docs that are out of date

- `put_file`, `get_file` and app launch times in the README, [bridge.md](actions/bridge.md),
  [win32-recipes.md](actions/win32-recipes.md) and the `put_file` docstring are quiet-host
  figures. On a busy host they can be several times slower.
- On a fresh boot, frames before the first pointer move have no pointer and slightly brighter
  colours. This affects today's scenes and isn't documented.
- Moving a window off another one can leave desktop label pixels in the lower window's frame.
  Today's scenes probably show this. It isn't checked or documented in Part 2.

### Smaller decisions

- Prep writes `UserPreferencesMask`, but Windows 98 reads `UserPreferencemask`, so the setting has
  no effect. Fixing it changes the image. See [image.md](prep/image.md).
- `art98 prep --from install` and `--from patch` fail after a finished build, because
  `install.img` is gone. The workaround is `--from disk`.

## Working notes

- Set up QEMU in each shell with `. .tools/env.sh`.
- `work/` is gitignored and holds the images, which contain the product key in clear text.
  Never commit or push anything from it, including the copies under `work/runs`.
- To stop a stray VM, kill it by its PID. `pkill -f qemu-system-i386` can match the shell that
  runs it.
- Timings depend on host load, so note `/proc/pressure/cpu` next to any figure.
