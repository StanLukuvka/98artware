# Stray pointer on the blank desktop (T1.4 probe)

Is a pointer drawn on `desktop = "blank"` where none should be? Which of the three candidate causes
in the roadmap (M1d) is it?

```bash
. .tools/env.sh
.venv/bin/python experiments/stray-pointer/probe.py WORK_COPY OUT_DIR
```

`WORK_COPY` is a copy of a prepared work dir (the release-check image, `runs/` left out), never the
repo's `work/`. Each case plays a Scene through `Scene.run` on a private host stage
(`art98.session.stage`, a reflink copy of the disk, deleted on exit), recording lossless FFV1. The
first 12 frames are decoded with ffmpeg and every non-black pixel is boxed. Nothing writes the base
image or a snapshot; no QEMU was started outside `stage`. The probe did not change `core/`.

CPU pressure (`some`): avg10 0.00 to 0.41 at the start of runs, 0.04 to 0.33 at the end of the last
run (totals 253727634 to 254346053 across the 18:5x run). Frames were identical in every run
(the 4 earlier runs gave the same boxes).

## Idle scene, 0.3 s (9 frames), blank desktop

| case | pointer_visible | first non-black frame | pixels, box |
| --- | --- | --- | --- |
| idle (attach only) | False | none in 9 | none |
| pointer placed at (799, 599) | False | none | none |
| `guest.sync()` after attach | False | none | none |
| one `SetCursorPos` to the same spot + `sync()` | False | none | none |
| idle | True | frame 0 (and all 9) | 58 px, x 401-408, y 302-317 |
| placed at (799, 599) | True | none | none (arrow hangs off the screen) |
| same-spot `SetCursorPos` | True | frame 0 (and all 9) | 58 px, same box |

The pointer starts at (400, 300) (`cursor_after_attach`). The 58 px box is the arrow (8x16), hotspot
at its top left. With `pointer_visible = False` frame 0 is pure black in every variant, so neither a
swap after the revert (candidate 1) nor a first frame before the first move (candidate 2) leaves a
pointer. The `True` rows are the documented behaviour, not a bug.

## The scenes from the release check

I could not tell which scenes showed it, so I ran both named ones, scanning every frame for the exact
arrow pixels (a 58 px template cut from the idle-visible clip):

- `recipes/scenes/mvp` (`pointer_visible` unset, two Pictures): no arrow in any of the 257 frames.
- `recipes/scenes/blank_start` (`pointer_visible = True`, state pointer (400, 540)): the arrow is in every
  frame it is not hidden behind a window, from frame 0 (box x 401-408, y 542-557) through the
  glide and the drag. Frames 45-50 of clip 1 match no arrow because it is over the Notepad.
  This is the pointer the scene asked for.

## A program's own cursor (candidate 3)

Pointer hidden (`pointer_visible = False`), a program window at (200, 100, 500x400), the pointer at A
(400, 300) for 3 frames, then at B (480, 340) for 3; frames 1 and 4 are compared around both spots:

| program | px differing near the pointer | box |
| --- | --- | --- |
| Notepad (edit area, would be an I-beam) | 0 | none |
| Paint (canvas, pencil tool) | 33 at A and 33 at B | x 400-406, y 294-300 at A; x 480-486, y 334-340 at B |

Notepad shows nothing: the system I-beam is one of the swapped shapes. Paint draws its own pencil
cursor (a 7x7 px box up and right of the hotspot, from Paint's own resource, not a system shape) and
`hide_pointer` cannot remove it. That matches the `hide_pointer` docstring (desktop.py:273-275).

Crops (8x, nearest) were kept outside the repo, not under `experiments/stray-pointer/`:
- `own-paint-f1.png`, `own-paint-f4.png`: Paint's pencil, pointer hidden.
- `idle-visible-f0.png`: the arrow when `pointer_visible = True`, frame 0.
- `blank_start-01-f0.png`: the arrow in the first frame of `recipes/scenes/blank_start`.

## Conclusion

Candidate 3. Candidates 1 and 2 do not reproduce: on a blank desktop with the pointer hidden, no
frame from frame 0 on has a non-black pixel, with or without a move, a sync or a same-spot
`SetCursorPos`. What shows is (a) the arrow in scenes that set `pointer_visible = True`
(`recipes/scenes/blank_start`), by design, and (b) a program's own cursor, shown by Paint on its canvas.
`recipes/scenes/mvp` shows no pointer. Not tested: other programs with own cursors (Minesweeper, Picture
dialogs), and the wait/hourglass cursor while a program starts.

## Recommended fix

Nothing in `Pointer.attach` or `blank()` needs to change, so there is no hot fix at pointer.py:29,
setstate.py:281-289 or desktop.py:23-26; do not re-issue `SetCursorPos` after `hide_pointer`.
Minimal and honest: document it.
1. desktop.py:273-275: say it plainly that Paint's tools (pencil and so on) draw their own cursor over
   the canvas, so a `blank` scene with Paint shows a cursor wherever the pointer is on the canvas.
2. docs (coordinator): a line in docs/scenes/ for blank scenes with Paint: keep the pointer off the
   canvas (`Glide` away, or a start pointer outside the canvas) when no cursor is wanted.
3. If a hidden cursor over a Paint canvas is wanted later, that is a new feature (an option on Paint,
   changing its window class cursor via `SetClassLongA` or hooking `WM_SETCURSOR`), untested here and
   out of scope for 0.1.1.
Size S as a docs fix. For a determinism check on the unchanged code, render the blank scene twice and
compare `framemd5` of frame 0 (the idle frames here are identical across 5 runs).
