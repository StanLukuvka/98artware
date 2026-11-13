# Drift audit (does the host's model of the screen match the guest?)

Does the host's picture of the guest drift from the real guest as actions run? Two kinds of drift:

- **A. Position drift.** The host keeps a rect for each window prop and a pointer position. Is that
  the same as `GetWindowRect` and `GetCursorPos` in the guest?
- **B. Pixel drift.** Is the frame the recorder would encode the same as the screen after a forced
  full repaint (`RedrawWindow` with `RDW_REPAINT_ALL` on every visible top-level window, then a
  sync)? A difference is a stale or wrongly layered pixel that a fresh paint would not have.

```bash
. .tools/env.sh
OUT=/path/outside/the/repo
.venv/bin/python experiments/drift/probe_drift.py $OUT 5                      # RUNS=5 per scene
.venv/bin/python experiments/drift/probe_drift.py $OUT 5 typing storm         # only these scenes
.venv/bin/python experiments/drift/summarize.py $OUT                          # reads $OUT/drift.jsonl
```

The probe attaches to the running VM service (`art98 vm start`), so the engine is whatever the VM
runs in; for real Docker start the VM with `env -u DOCKER_HOST sg docker -c 'art98 vm start'`. There is
no backend argument any more. `probe_drift.py` writes `OUT/drift.jsonl` and `OUT/diffs/`. Each run
starts by attaching, which reverts to the snapshot; no other snapshot is saved and no frame is
encoded. `experiments/stray-pixels/repro.py` is a separate experiment with its own commands. Scenes:
`motion`, `drag`, `typing`, `menus` (the gallery scenes, 10 fps), `storm` (`DialogStorm`, 24 fps) and
`cmds` (Maximize, Restore, Teleport, Minimize). At every frame, A and B are read, and the plain sync,
the read-back and the forced repaint are timed.

The same checks run as VM tests: `core/tests/test_stage.py::test_no_drift[<scene>]` (A at every frame
of the six scenes above plus short `paint`, `minesweeper` and `picture` scenes; B on `typing`,
`storm`, `paint`, `minesweeper` and `picture`), with the shared code in `core/tests/drift_check.py`.
A failure names the prop, the frame and both rects, and B saves both screendumps.

**History.** Everything below was measured on 2026-11-11, before the VM service replaced the backends
(`local`, `container` as Podman or Docker, `--backend`). The tables are kept as they were; the
commands that produced them no longer exist.

Run on the VM host (20 CPUs), 2026-11-11, one backend at a time. Host CPU pressure
(`/proc/pressure/cpu`, `some`) was 0.00 to 0.18 avg10 throughout (0.00 to 0.01 avg60 at the start of
each backend run; the stray-pixel runs started at 0.00 to 0.51 avg10, 0.00 to 0.12 avg60). Nothing
else heavy was running, so the timings are quiet-host figures.

## Result A and B: nothing drifts after the fixes

5 runs per scene and backend (a run is 11 to 73 frames, so a few seconds; the full probe took 2m20s
local, 2m28s Podman, 2m30s Docker, none scaled down). "Frames off" is the number of frames with at
least one difference, out of all frames.

| scene | frames per backend | A: frames off (local / Podman / Docker) | B: frames differ (local / Podman / Docker) |
|---|---|---|---|
| motion | 270 | 0 / 0 / 0 | 0 / 0 / 0 |
| drag | 165 | 0 / 0 / 0 | 0 / 0 / 0 |
| typing | 365 | 0 / 0 / 0 | 0 / 0 / 0 |
| menus | 220 | 0 / 0 / 0 | 0 / 0 / 0 |
| storm | 135 | 0 / 0 / 0 | 0 / 0 / 0 |
| cmds | 55 | 0 / 0 / 0 | 0 / 0 / 0 |

Every storm phase (cascade, pair, typing, colour, wallpaper) is also 0 in A and B on all three
backends. Raw B diffs existed (57 of 1210 frames local, 65 Podman, 72 Docker), and every one was the
Notepad caret blinking between the two screendumps or the taskbar clock ticking. `summarize.py`
discards those two (a diff of at most 3 x 20 px, or inside the tray at x >= 690, y >= 572) after
looking at the saved screendumps, and nothing else was left.

Limits: the probe sees what its scenes do. It does not see a drift that needs a different action
(a program the scenes don't open), and a repaint that fixes a pixel the same way the frame had it
is not a difference. Five runs per scene gives "0 of 5", which is a rate under about 45 % at 95 %
confidence per run, but the per-frame counts (55 to 365 frames per cell, 1210 per backend) are
what carry the claim; a drift that hit one run in five would have shown.

## Stray pixels after `set_colour`

`experiments/stray-pixels/repro.py`: revert, blank desktop, teal, the 11 `DialogStorm` boxes, then
`set_colour` to dark red; compare the frame with a back-to-front forced repaint. 20 runs per cell.
`PRE=1` removes the final `repaint_all` from `set_colour` (the pre-fix behaviour).

| backend | before (`PRE=1`): runs differ | pixels | after: runs differ | cpu psi avg10 at start / end |
|---|---|---|---|---|
| local | 20/20 | 380 or 395 | 0/20 | 0.00 / 0.00 (before), 0.51 / 0.02 (after) |
| Podman | 20/20 | 380 or 395 | 0/20 | 0.00 / 0.00 (before), 0.02 / 0.00 (after) |
| Docker | 20/20 | 380 or 395 | 0/20 | 0.00 / 0.51 (before), 0.00 / 0.00 (after) |

Before the fix every run differed, on every backend, always in the box area (bbox
(84, 227)-(407, 400), or from x = 60 in 39 of 60 runs): the caption text of a box repainted late is
drawn over the box in front of it. It is not a race: a later `sync` does not clear it, only a
back-to-front repaint does. After the fix 0 of 60.

Two corrections to the repro made on the way: `PRE=1` was in the docstring but not in the code
(it now replaces `repaint_all` with a plain sync), and the repro's own forced repaint walked the
windows front to back, so it re-created the very pixels it was looking for (380 px in 20 of 20
fixed runs). It now goes back to front, as `win32.repaint_all` does.

## Cost per frame

Median / p95 in ms, from the same runs (`summarize.py`). Plain sync is `Bridge.sync()` as the
recorder does it. Read-back is `GetWindowRect` per window prop (or `GetCursorPos` for the pointer),
per call; a frame with N props costs N times that. Forced repaint is a `RedrawWindow` on every visible
top-level window plus a sync. Host CPU pressure avg10 (median over the frames) was 0.0 to 0.1 for
every row.

| scene (top-level windows) | backend | plain sync | read-back, per prop | forced repaint + sync |
|---|---|---|---|---|
| motion (3) | local | 5.0 / 7.7 | 3.3 / 5.2 | 40.5 / 46.3 |
| motion (3) | Podman | 7.1 / 8.0 | 4.9 / 5.3 | 40.8 / 46.3 |
| motion (3) | Docker | 7.0 / 7.9 | 4.8 / 5.3 | 40.8 / 47.3 |
| typing (3) | local | 4.1 / 5.6 | 3.8 / 5.2 | 40.4 / 46.0 |
| typing (3) | Podman | 4.0 / 7.0 | 4.5 / 5.3 | 40.7 / 50.8 |
| typing (3) | Docker | 4.1 / 4.8 | 4.3 / 5.3 | 40.7 / 50.3 |
| storm (10, max 12) | local | 5.7 / 6.7 | 4.7 / 5.0 | 53.8 / 97.1 |
| storm (10, max 12) | Podman | 5.7 / 6.6 | 4.9 / 5.2 | 66.6 / 96.6 |
| storm (10, max 12) | Docker | 5.9 / 7.6 | 4.9 / 5.1 | 66.8 / 111.2 |
| cmds (2) | local / Podman / Docker | 5.1 / 5.0 / 5.1 | 3.4 / 3.4 / 4.5 | 25.4 / 25.3 / 22.4 |

(drag and menus are like motion and typing: 40 to 42 forced repaint on all three.) The three
backends cost the same within a millisecond or two. A forced repaint is about 8 times a plain sync
in a 3-window scene and 10 to 12 times in the storm; at 24 fps that would be 1.6 s of host time per
second of video for the storm. A read-back of every prop is 3 to 5 ms each.

## What was fixed, and where

- `core/art98/desktop.py:147` (`set_colour`): ends with `repaint_all`, so the frame after
  `Backdrop` is the one a fresh paint draws. `core/art98/win32.py:86` (`repaint_all`): repaints
  every visible top-level window back to front, then syncs. Cured the stray pixels above.
- `core/art98/actions/window/commands.py:22` (`_SysCommand.act`): `self.target.refresh()` after
  Minimize, Maximize and Restore, since Windows moves and sizes the window itself. The `cmds`
  scene is 0 of 55 on every backend.
- `core/art98/actions/window/win.py:174` (`Win.corner`) sets `spot.window = self` (and `:163` for
  `Win.title_bar`), which `Drag.__init__` reads at `core/art98/actions/pointer.py:184`, so a Drag
  from a resize corner reads the size back while Windows does it. `drag` is 0 of 165.

## What still drifts

Nothing that the probe could find, on any backend. Not covered, and worth knowing:

- Blinking and ticking things (the Notepad caret, the taskbar clock) change between any two
  screendumps. They are not drift, but they are why two renders of a scene with a caret are not
  byte-identical in general (the dialog storm has no caret, and its three renders are identical).
- Scenes the probe didn't run: Paint, Minesweeper, Screensaver, Picture. (Paint, Minesweeper and Picture now have short scenes in `test_no_drift`; Screensaver still has none.) They draw themselves and
  could leave something stale after a move the way a Backdrop did.
- Container image: `art98 render` warns that `localhost/art98:latest` is older than the checkout.
  Only QEMU and `serve` run in it, and the actions run on the host, so the numbers here do not
  depend on it. It was not rebuilt.
- One Docker stage failed once at start-up (`/run/secrets/art98_token` was a directory inside the
  container), on a run that was repeated successfully straight after. It left a root-owned
  `art98-secret-*` folder in `/run/user/1000`. Not investigated.

## Recommendation

Do not add a per-frame read-back or a per-frame forced repaint to the recorder: it would cost 4 to
5 ms per prop or 25 to 67 ms per frame to guard against something that 1210 frames per backend did
not show. Keep the cheap, targeted fixes: a repaint at the end of anything that broadcasts to every
window (`set_colour` today; a future `set_wallpaper` or theme change would be the same), a
`refresh()` after anything Windows moves, and the plain sync per frame. Re-run `probe_drift.py` when
a new program or action is added, and add a scene for it to `SCENES`. If one ever shows a stale
pixel, the first thing to try is `repaint_all` at the end of that action, not a per-frame check. No
guest agent change is proposed.

## Dialog storm across backends

`art98 render recipes/scenes/dialog_storm/dialog_storm.py DialogStorm --backend {local,container}` (Podman,
Docker via `env -u DOCKER_HOST sg docker -c`), 126 frames, `ffmpeg -f framemd5` of each: the three
frame lists are identical (local = Podman = Docker), and so are the five section clips byte for
byte. Render time 5.1 s local, 5.8 s Podman, 6.9 s Docker, CPU pressure 0.00. This was not so
before `set_colour` repainted (the stray pixels above differed run to run).
