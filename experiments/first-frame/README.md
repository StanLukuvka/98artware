# First frame (M2b)

Does a fresh boot show a different first frame from a settled one, so that a revert right after boot
(M2.2) would be worth it? The idea was that the first frames are brighter and have no pointer yet.

```bash
. .tools/env.sh
.venv/bin/python experiments/first-frame/probe.py OUT_DIR
```

The probe runs on a private copy of the image (`art98.session.stage`, a `cp --reflink` under
`work/runs`, deleted on exit). It only does `loadvm ready`; it never saves a snapshot and never
writes the base image. Frames stay in `OUT_DIR` (default a temp dir), not in the repo.

Frames, each with the blank desktop (pointer allowed) and a Notepad at (200, 100, 400x300), the pointer
set to (400, 500) and `sync()` before the screenshot:

- A: straight after boot, no revert.
- B: after `revert()`, `blank()` and the same window.
- C: B's desktop after 1.5 s more, a settled reference.

Each is shot again with the pointer at (150, 450); the pixels that change near the two pointer
positions say whether a pointer is drawn. The window is a Notepad, not a Picture (no scene here, and
the pixels are the same for this question).

## Result 1: after a pointer move (3 runs, identical)

The first version of the probe moved the pointer before frame A, so it only showed that a frame after
a pointer move is the same with or without a revert (A, B and C: mean RGB 55.940, 55.963, 57.411 for
A and B; 30 px differ from C, all a Notepad caret blink; pointer drawn in all). That is not the
reported case.

## Result 2: raw frames, nothing moved (3 runs, identical)

Raw frames: no `blank`, no window. A0 right after boot, A1 after `bridge.sync()`, A2 after one
`SetCursorPos` to (400, 500), B0 after `revert()` with no pointer move. The pointer starts at (400, 300).

| | A0 | A1 | A2 | B0 |
| --- | --- | --- | --- | --- |
| mean RGB | 11.123, 126.676, 126.595 | same as A0 | 10.825, 123.533, 123.454 | same as A2 |
| desktop colour at (5, 5) | 0, 123, 123 | | 0, 120, 120 | 0, 120, 120 |
| diff px vs A2, all | 479291 | 479291 | | 210 |
| diff px vs A2, outside the pointer boxes | 474489 | 474489 | | 0 |

- A0 and A1 are brighter over the whole frame and have no pointer (their pointer-box pixels are one
  flat colour). The first `SetCursorPos` turns both on: brightness drops and the pointer is drawn.
- `sync()` does not fix it. A0 equals A1.
- B0, a revert with no move, already has the settled brightness and a pointer at its start position.
  Its 210 diff pixels are only the two pointer boxes (the pointer at (400, 300) in B0, at (400, 500) in A2).
- Candidates that need no revert: `SetCursorPos` to the spot the pointer is already at, and a 1 px step
  and back. Both give a frame identical to B0 (0 px, same mean), in all 3 runs.

## Result 3: what a real no-state scene records

`Scene.run` -> `_start_desktop()` -> `prepare_desktop()` (`blank()` only for `desktop="blank"`) -> `calibrate()`,
then `Pointer.attach`. `Pointer.attach` only reads the position (`cursor_pos`); `Pointer.apply` sends
`SetCursorPos` only when the wanted position differs from the read one. So nothing moves the pointer
before the first frame, and a scene that never moves it never does. The renderer only opens the recorder
and calls `scene.run`.

I ran a scene that only waits 1 s through `Scene.run` on a private stage with a lossless recording and
compared frame 1 with frame 20 (scratch script, outside the repo):

| desktop | mean RGB, frame 1 | frame 20 | diff px |
| --- | --- | --- | --- |
| `stock` | 11.123, 126.676, 126.595 | same | 0 |
| `blank` + `pointer_visible` | 0.031 each | same | 0 |
| `blank` | 0.000 each | same | 0 |

The `stock` clip has the A0 look (bright, no pointer) from its first frame to its last. A move later in
a scene flips it mid-clip. So the report is real, but only for `desktop="stock"`. The default blank
desktop is black, so the brightness does not show, and `blank()` leaves the pointer drawn when
`pointer_visible` is true and hidden otherwise.

## Verdict

The earlier "nothing to fix" was wrong: the first probe moved the pointer before frame A. On a stock
desktop the first frames of a fresh boot are brighter and pointerless until the first pointer move, and
a revert fixes that (B0 equals A2 bar the pointer position). On the default blank desktop it does not
show. A cheaper fix than a revert is one `SetCursorPos` to the current position before recording; it
gives the same frame as B0. Decision for the coordinator; M2.2 is not re-added here.

CPU pressure (`some`): the first probe version ran at avg10 0.00. The last runs, with another worker
active, started at avg10 2.53, 1.39 and 0.93 and ended at 1.70, 0.93 and 0.51 (totals 19669256 to
19686475, 19687253 to 19711002, 19712300 to 19728602). Frames were identical every run.
