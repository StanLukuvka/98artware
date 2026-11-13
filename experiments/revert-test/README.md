# Revert test

Throwaway scripts from the first step of the state MVP: can art98 revert the desktop and apply a
state by hand, quickly and the same way every time? The results are at the end of this page,
and the design they led to is in [State and action](../../docs/design/state-and-action.md#test-results). These are kept so the test can be
run again. They aren't part of art98 and have no tests.

Since the VM service these run on local QEMU, not the container; findings above are from the container backend.

Every script works on a private copy of the image, under `work/runs` (or `/dev/shm` for
`disk.py`), and deletes it on exit. Run them from the repository root:

```bash
. .tools/env.sh
```

```bash
uv run python -u experiments/revert-test/probe.py out/probe
```

| Script | What it checks |
| --- | --- |
| `probe.py OUT` | Sections A to E: the same state 10 times (`N=3` for fewer), state A then B then A, revert leaves nothing behind, revert after a display change, and revert with a call still open. `TRACE=1` prints each step's time |
| `disk.py btrfs\|shm default\|unsafe` | Whether the disk path or QEMU's cache mode changes copy, read and launch times |
| `surface.py OUT` | When the screenshot colours and the pointer change. Needs `uv run --with pillow` |
| `warm.py OUT` | Set from `ready`, then from a baseline saved after Notepad and Paint ran once |
| `warm_new_file.py OUT` | The same, copying to a file name the warm baseline doesn't already have |
| `stray.py OUT` | The stray pixels: 10 Sets from `ready` and 10 from a warm baseline, each screenshot taken after the Set and again 1 s later. `REDRAW=1` repaints the windows after placing them |
| `stray_order.py OUT` | When the stray pixels appear: placing Notepad or Paint first, with a screenshot after each step and after repainting Notepad |

A state here is Notepad at (60, 60, 300, 200), Paint opening a 57 KB BMP at (300, 140, 420, 340),
and the pointer at (400, 500).

Each script has a watchdog that exits after a fixed time, so a stuck run can't hold the VM forever.
If one is killed anyway, look in `work/runs` for a `render-*` copy and delete it.

Timings depend heavily on how busy the host is. Note the CPU pressure from `/proc/pressure/cpu`
next to any figure.

## Results, moved from the design page on 2026-11-13

The text below was cut out of `docs/design/state-and-action.md` (sections "Test results" and "Stray
pixels, explained") and is kept as it was written, with one change: the last sentence of the stray
pixels section was out of date and now says what the code does.

### Test results

Run on 2026-11-07 on a private copy of the image, with throwaway scripts. The state was Notepad and
Paint placed by hand, Paint opening a 57 KB BMP, and the pointer placed last.

**Set works.** It repeats, and a revert leaves nothing behind.

| Check | Result |
| --- | --- |
| Same state, repeated | 13 of 13 screenshots identical across two runs, then 3 of 4 on a warm baseline |
| State A, state B, state A | Identical to the first A |
| Revert after windows, a file and a display change | Same desktop as the baseline, with windows and display mode gone |
| Revert with a call still open | The bridge keeps working. The open call never finishes and waits for its timeout |

**Speed depends mostly on how busy the host is.** The disk made no difference: btrfs, tmpfs and
`cache=unsafe` all took the same time. Figures are the median for a whole Set.

| Host CPU pressure | `ready` today | Warm baseline |
| --- | --- | --- |
| About 30% | 10.3 s | Not measured |
| About 2 to 6% | 3.1 s | 1.7 s |
| Under 1% | 2.0 s, from 2 runs | 1.6 s |
| Under 0.4%, 2026-11-08 | 1.6 s, and 1.8 s with the repaint | 1.25 s, with or without the repaint |

**A warm baseline beats the 2 s target.** A revert also throws away the guest's disk cache, so
every launch is cold. Launching Notepad and Paint once before saving the snapshot cut Paint from
0.83 s to 0.49 s on a quiet host. The windows are closed again before the save, and the resulting
state matched the one from `ready`, apart from the stray pixels below. This changes how the
baseline is made, so it's a decision, not a test result.

**Decided 2026-11-08: the MVP uses `ready` as it is.** A warm baseline is only added if Set misses
the 2 s target. If it is added, the first choice is a `warm` snapshot made at the start of each run
on the private copy, so setup, `ready` and today's scenes don't change. Two costs come with any warm
baseline. Running the apps once leaves traces: the window cascade moves on (Notepad then opens at
(116, 110) instead of (68, 66)), and closing Paint likely writes its settings and recent files to
the registry, which isn't checked. Saving the snapshot also takes time, which hasn't been measured.
Reading the program files once, without running them, might warm the disk cache without the
traces. That is untested.

**Differences found:**

- **Pointer and colours.** On a fresh boot, the first pointer move turns the pointer on and shifts
  the colours (white 255 becomes 248, teal 123 becomes 120). The memory is the same, so this looks
  like QEMU switching how it draws, though that cause is inferred. It already affects today's
  scenes, in the frames before the first pointer move. After a revert it's always in the second
  form, so Sets are consistent with each other. Reverting once right after boot would make every
  frame consistent. That revert was dropped. A `SetCursorPos` nudge in `Pointer.attach`
  (`actions/pointer.py`) now settles the first frame instead; see
  [first-frame](../first-frame/README.md).
- **Stray pixels.** In one run, 1 Set in 4 differed by 8 pixels at Notepad's left edge, on the end
  of the "My Documents" label. Run 2's stall wasn't real: the watchdog fired during normal slow work
  and it didn't happen again. The pixels are explained below.

### Stray pixels, explained

Run on 2026-11-08 on a private copy, at under 0.4% CPU pressure, with `stray.py` and
`stray_order.py`.

The odd Set out was the clean one. A Windows 98 frame's outer column is light grey (216 in the
screenshot) and the next one is white (248), as Paint's frame shows. Usually, Notepad's outer column
at x = 60 is white in rows 118 to 123. Those are the text pixels of the "My Documents" label, drawn
into Notepad's 4-pixel sizing frame (x 60 to 63). The client edge at x = 64 is never touched.

| Run | Label pixels in Notepad's frame |
| --- | --- |
| 10 Sets from `ready` | 10 of 10 |
| 10 Sets from a warm baseline | 8 of 10 |
| Screenshot again 1 s later | No change, so this isn't a screenshot taken too early |
| Notepad placed, Paint not moved yet | 0 of 8 |
| Then Paint moved away | 8 of 8 |
| Paint placed first, then Notepad | 0 of 8 |
| Notepad repainted after both are placed | 0 of 8 |
| Both windows repainted back to front, from `ready` and from warm | 20 of 20 screenshots identical, and warm matches `ready` exactly |

Paint opens at (0, 0, 275, 400), on top of the desktop label and of Notepad's new left frame. When
Paint moves away, the desktop and Notepad both repaint the area it uncovered. The desktop draws its
label into Notepad's frame as well. Notepad's frame is usually painted first, so the label ends up
on top. On the warm baseline the order sometimes flips, which is why that run looked like 1 in 4.
Which part of Windows 98 lets the desktop paint there is inferred, not proven. `SYNC` doesn't fix
it, because it waits for pending repaints and doesn't ask for new ones.

This isn't specific to a Set. Any move of a window off another window can leave these pixels on
the lower window's frame. Dragging a window now repaints it each frame (`Win.repaint_if_moved`); see
[host-checks](../host-checks/README.md).

**Fix:** Apply ends by repainting every window the state placed, back to front, before the final
sync. Checking rects alone wouldn't catch the stray pixels, so done-when 1 compares screenshots.

**What this changes:**

- Revert must fail open calls straight away, not leave them waiting for a timeout.
- The documented `put_file`, `get_file` and app launch times are quiet-host figures. A Set figure
  should be quoted with the host load.
- Apply ends with a back-to-front repaint of its windows. With it, Sets match pixel for pixel.
