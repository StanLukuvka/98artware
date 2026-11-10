# Revert test

Throwaway scripts from the first step of the state MVP: can art98 revert the desktop and apply a
state by hand, quickly and the same way every time? The results and what they mean are in
[the design](../../docs/design/state-and-action.md#test-results). These are kept so the test can be
run again. They aren't part of art98 and have no tests.

Every script works on a private copy of the image, under `work/runs` (or `/dev/shm` for
`disk.py`), and deletes it on exit. Run them from the repository root:

```bash
. .tools/env.sh
```

```bash
uv run python -u artware_experiments/revert-test/probe.py out/probe
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
