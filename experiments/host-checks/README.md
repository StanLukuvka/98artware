# Host checks (M7a busy host, M7b stray label pixels)

Numbers for the docs task (D3). Run on the VM host (20 CPUs, `--work work`), one run at a time.
`art98 vm start` must be running. The numbers below were taken on the local backend (a local QEMU
per render), not the VM service, so they are not directly comparable with service renders.
Videos and frames stay in a scratch dir, none are in the repo. Every timing has
`/proc/pressure/cpu` `some avg10` ("psi") next to it.

```bash
. .tools/env.sh
.venv/bin/python experiments/host-checks/busy_check.py OUT_DIR 2        # M7a: quiet, then 2 busy renders
STRAY_OUT=DIR .venv/bin/art98 render experiments/host-checks/stray_labels.py \
    --work work -o DIR/stray.mp4                                         # M7b (STRAY_NO_REPAINT=1: repaint off)
```

- `timed_render.py` runs `art98 render` with `Bridge.sync` and `put_file` timed (JSON out).
- `busy_check.py` starts `os.cpu_count() + 8` = 28 hogs (`python3 -c "while True: pass"`), each by PID,
  waits for psi > 40, renders, and kills each by PID in a `finally` (no pkill). After both runs: hogs left = none
  (`ps` checked), psi back to 0.00 a minute later. The "quiet again" run used `busy_check.py OUT 0`, which still starts and kills the hogs after the render (no render under them).
- `stray_labels.py` is the M7b scratch scene.

## M7a. `recipes/scenes/blank_start/blank_start.py` on a busy host

Scene: state with a Picture and a Notepad, Glide, TypeWithCursor, a Drag, a Teleport, Close; 3 clips
(`next_section`). No `live`/`wait`. mp4 only. 800x600, 30 fps, libx264 crf 12.

| run | psi avg10 before / during min-max / after | wall | frames (total; clip 1/2/3) | sync calls, total, longest | put_file total | BridgeTimeout |
|---|---|---|---|---|---|---|
| quiet | 0.01 / 0.01 / 0.00 | 3.8 s | 263 (156/76/31) | 166, 0.61 s, 0.017 s | 0.46 s | none |
| quiet again | 4.4 / 3.6 / 2.95 | 3.6 s | 263 | 166, 0.63 s, 0.014 s | 0.42 s | none |
| busy 1 | 40.8 / 42.1-45.1 / 45.1 | 20.9 s | 263 (156/76/31) | 166, 3.43 s, **0.80 s** | 6.04 s | none |
| busy 2 | 45.1 / 45.8-47.3 / 46.9 | 17.9 s | 263 (156/76/31) | 166, 2.37 s, 0.061 s | 4.07 s | none |

"after" is read just after the render, hogs still running (busy) or off (quiet). `avg10` is a 10 s
average, so it lags; right after the kill it still read 46.9.

Busy costs about 5x the wall time. The put_file of the 57 KB flower.bmp went from 0.43 s to 5.7 s / 3.7 s.
Frame and clip counts are identical in all four renders (the recorder is frame-driven).

**sync give-up.** `Bridge.sync(hwnd=0, timeout_ms=500)` sends `SYNC`; the guest agent
(`guest/call_proxy/agent.c`, `verb_sync`/`settle_window`) does `RedrawWindow` then
`SendMessageTimeoutA(WM_NULL, ..., timeout_ms)` per visible top-level window (all of them for hwnd 0),
ignores the result, and always replies OK. So a give-up is silent: no `BridgeTimeout`, no error. The host
only sees the duration. No `BridgeTimeout` fired in any run. Busy run 1 had one `sync()` (call #58, hwnd 0,
one of the 166) that took 0.80 s, and one at 0.11 s; with several windows open that is one window
at or near its 500 ms limit plus the rest, so a give-up on that call cannot be ruled out or confirmed from
the host. Mean `sync()` time: 3.7 ms quiet, 14-21 ms busy. Nothing visible followed (see frames).

**Frames match? Not bit for bit, and not because of load.** Per-frame `framemd5` of the decoded mp4s differs between
quiet and busy, but it also differs between two quiet renders (111 of 263 frames, frames 48-155 and 197-199).
Using ffmpeg `psnr` per frame, the minimum is 45.4 dB in quiet vs quiet again, 45.4 in quiet vs busy 1,
45.4 in quiet vs busy 2, and 45.4 in busy 1 vs busy 2: the worst frame in any pair is the same, so
busy adds nothing over the quiet-to-quiet noise. A moved window would show as far lower PSNR. Causes of the
noise, from looking at frames:

- Notepad's text caret blinks on the guest's clock: frame 1 of quiet shows the caret on "A note on
  a blank desktop.", frame 1 of busy 1 shows it off (max pixel diff 214, the caret). That is the largest
  difference, and it is in a quiet pair too (frames 48-155 are the caret on/off in the typing and drag
  stretch).
- Where the pixels are not the caret, max per-pixel difference is 6-10 levels: x264 at crf 12, whose
  choices depend on the frame sequence once one frame differs.

So: no window moved, no title or content differed, no extra frames, no missing frames. Exact hashes would
need a lossless render and a scene without Notepad's blinking caret; not done.

Reference frames (scratch): quiet `.../scratchpad/m7a/quiet.mp4`, busy `.../scratchpad/m7a/busy1.mp4`,
`busy2.mp4`, second quiet `.../scratchpad/m7a-q2/quiet.mp4`; frame 1 PNGs in `.../scratchpad/fr/` (`quiet-1.png`,
`busy1-1.png`: only the caret differs).

## M7b. Stray label pixels (stock desktop, window moved over the icons)

Scene `stray_labels.py`: `desktop = "stock"`, a Picture at (200,120) and a Notepad at (420,300). After
each move a `Snap` takes a screendump right away (A0), one after `guest.sync()` (A1), then one after a full
`RedrawWindow(RDW_REPAINT_ALL)` of the desktop and every window plus `sync()` (R, the reference). Pixels
in A that differ from R are stale. Moves: Teleport onto the icon column (x 10-20) and off it, and Drag by
the title bar across it and off it. 7 snaps, run with the repaint in `win32.place_window` on, and again with
`win32.repaint_window` turned into a no-op (`STRAY_NO_REPAINT=1`).

| move | A0 and A1 vs R, repaint on | repaint off |
|---|---|---|
| open (no move) | 0 px | 0 px |
| Teleport Picture onto icons | 0 | 0 |
| Teleport Picture off icons | 0 | 0 |
| Teleport Notepad onto icons | 0 (55 once: the taskbar clock ticking) | 0 |
| Drag Notepad across the icons and off (by 300,-150) | **121-151 px**, x 310-318, y 192-347 | 121-151 |
| Drag Picture back over the icons (by -380,60) | 14 px, x 258-259, y 174-191 | 14 |
| Drag Picture off (by 400,100) | 86 px, x 420-426, y 289-436 | 86 |

(the pixel counts for the same drag vary between runs, 121 to 151, so they depend on timing.) psi was
0.0-0.2 throughout. `sync()` right after (A1) does not clear them: A0 and A1 are the same.

What they are: white icon-label text pixels ("Online Services", "Outlook Express", ...) left inside the
window's own frame/client edge, in a column along its left side (look at the left edge of the Notepad
in `s4_note_drag_off_A1.png`; `s4_note_drag_off_R.png` is clean apart from the caret). They show only with
`desktop = "stock"` (the blank desktop has no labels) and only after a Drag by the title bar, where
Windows moves the window itself. They did not appear after a Teleport, with the repaint on or off.

Which API repaints them: `RedrawWindow(hwnd, 0, 0, RDW_REPAINT_ALL)` on the dragged window, which is
`win32.repaint_window`. Calling it alone on the Notepad after the drag changed exactly the 121 stale
pixels (all of them), so the desktop redraw is not needed. Cost: one `repaint_window` call is 3-10 ms
(one request to the guest); redrawing the desktop and both windows plus `sync()` was 27-41 ms. `Win.apply`
already repaints after a move it sends (Teleport, `shift`), but a Drag never goes through `apply`: the
guest moves the window, and `Win.refresh` only reads the rectangle back.

Not fixed. A one-line call would not be enough: it belongs after the drag in `Win.refresh` with a test
for "the real position differs from the one sent" (two lines), and it would only clear the pixels at the
end of the Drag (`Drag.finish` -> `refresh_props`), so any pixels during the drag stay and then pop
away in one frame. Doing it per frame during a Drag means a repaint (3-10 ms) in a pointer action,
which is `actions/pointer.py`, outside the files this task may edit. Mid-drag frames were not analysed
frame by frame. Also untested: whether `repaint_window` matters at all for `Teleport`; with it off,
nothing differed in this scene (a small Picture/Notepad over a label), so it may only matter for resizes.

Frames: `.../scratchpad/m7b-on/s4_note_drag_off_A1.png` (stale), `s4_note_drag_off_R.png` (reference),
`s4_crop_A1.png` / `s4_crop_R.png` (4x crop of the left edge), `snaps.json` (counts); repaint-off run in
`m7b-off/`, second run with the single-window repaint check in `m7b2-on/`, `m7b2-off/`. Prefix:
`/tmp/claude-1000/-home-admin-Documents-scripts-manim-windows/e89aa5f1-6ca6-43c2-bb51-aecb8c0b37cb/scratchpad`.

**After the fix.** `Drag` from a `Win.title_bar` now calls `Win.repaint_if_moved()` once per frame and at `finish`
(one `GetWindowRect` read; `repaint_window` only if the rectangle changed). Same scene, repaint on, psi 0.00
before and after: the three drags (s4-s6) are **0 px** stale in A0 and A1 (was 121-151, 14, 86). Teleports 0.
s3 shows 30 px at x 17-18, y 345-359 before any drag: the Notepad caret blink, not a stray label.
Frames (scratch, prefix as above): `m7b-fix/mid.png` (mid second Picture drag), `m7b-fix/end.png`, `m7b-fix/snaps.json`.
