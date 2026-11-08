# State and action design

Status: proposal for review. Nothing here is built.

Today a scene runs from start to finish on the `ready` snapshot. art98 can't put Windows 98
into a chosen state, so reaching one point in a scene means playing everything before it, on
camera. This design adds static starting states and named actions, and leaves actions as free
as they are now. Where Manim already has the idea, this follows Manim.

![Life of an animation .py](scene-lifecycle.png)

## Goal

**Any scene starts from a hand-written static state, and its actions can do anything from
there.**

1. Set gives the same starting desktop every time.
2. Part of a scene can be recorded again without recording the rest.
3. Actions have no limits and produce no JSON.
4. Only the backend knows about QEMU.

Not in scope: capturing an action's result as a state, saving a snapshot per action, matching
memory byte for byte, audio, running on real hardware, and moving frame capture into the guest.

## Terms

| Term | Meaning |
| --- | --- |
| **Baseline** | The clean desktop we always revert to. Today that's `ready`. |
| **State** | A hand-written JSON file describing a static starting desktop. |
| **Set** | Revert to the baseline and apply a state, off camera. In code, `set_state()`. |
| **Action** | A named section of `construct()`, marked with `next_section`. |
| **Animation** | A building block an action uses, like `Glide` or `Stroke`. |
| **Clip** | The video file one action writes. |
| **Scene** | A state plus the actions that run on it, recorded. |
| **Backend** | Whatever provides revert and capture. Today that's QEMU. |

"Stage" keeps its meaning in prep only. "Snapshot" only means the VM feature behind the baseline.

Manim users may read "state" as `save_state`, so the docs should say early that a state here is
a desktop. `anim/actions.py` holds pointer and keyboard animations, which now clashes with the
new meaning of action, so it becomes `anim/input.py`.

## Decisions

| Decision | Why |
| --- | --- |
| A state is static and hand-written | Not every action result can be described, and forcing it would limit what actions can do |
| A state is stored as JSON | It can be written by hand, and it covers wallpaper, icons and tray, which props can't |
| A state can open a file | A finished drawing can start the next scene, without saving an action's result |
| Actions are sections of `construct()` | Manim's `next_section` already does this, and a list of method names would be a second system |
| Actions can chain | Each one picks up where the last ended |
| Each action writes its own clip | Part of a scene can be recorded again, and clips are host files with no tie to the VM |
| A finished run holds the desktop | You can try more actions without a restart |
| A failed run holds the desktop too | The most useful evidence is the live desktop where it failed |
| Every restart takes the same path | A run never continues from a half-finished desktop |

An animation is a Python script, so it's arbitrary code. As with Manim, art98 doesn't decide how
many states or output files one script uses. Set is an ordinary call, and the rest is up to the
script.

## A state file

```json
{
  "version": 1,
  "desktop": {
    "wallpaper": {"file": "assets/clouds.bmp", "sha256": "..."},
    "icons": {"My Computer": [8, 8], "Recycle Bin": [8, 80]},
    "tray": ["volume"]
  },
  "windows": [
    {
      "id": "canvas",
      "app": "paint",
      "rect": [10, 10, 640, 480],
      "show": "normal",
      "focus": true,
      "open": {"file": "assets/flower.bmp", "sha256": "..."}
    }
  ],
  "pointer": [400, 300]
}
```

- Anything a state leaves out stays as it is on the baseline.
- `windows` are listed back to front, so the last one is on top.
- `open` is optional. Without it, a program starts in its default state: blank Paint, an
  untitled Notepad, a new Minesweeper game.
- Files sit beside the state and are referenced by path and hash, never embedded in the JSON.
- One Python schema defines the fields, and a state is validated on load. Unknown fields fail.
- `app` maps to a prop class such as `Paint`, through a small registry.
- States are always written with fixed key order, so diffs stay clean and hashes are stable.

The schema starts small, with windows and pointer. Other fields join once they pass their tests.

## A scene

```python
class PaintFlower(Scene):
    state = "states/state_1.json"

    def construct(self):
        canvas = self.prop("canvas")

        self.next_section("action_paint_1")
        self.play(...)

        self.next_section("action_paint_2")
        self.play(...)
```

```bash
uv run art98 render flower.py PaintFlower --section action_paint_2
```

`self.prop("canvas")` returns the prop for that window `id`. `Win(hwnd=...)` can already take
hold of an existing window, but each app prop also needs adopting properly: see Paint under
"Not proven yet".

`state` is optional. Without one, a scene starts on the baseline, so scenes written today keep
working. Actions keep the animations and raw `self.guest` access they have now.

## How it runs

| State in the diagram | What it does |
| --- | --- |
| Loading | Imports `scene.py`, then validates the JSON and the file hashes |
| Reverting | Returns the desktop to the baseline (see Backend) |
| Applying | Copies the state's files to the guest, then applies the JSON through the bridge |
| Checking | Reads back what the state describes, and fails on a difference |
| Ready | `STATE_1` is on screen and no frames have been written |
| Action N | Runs one action and writes its clip, with its own ffmpeg |
| Encoding | Joins the clips into one file, and fails if ffmpeg did |
| Holding | Keeps the VM up and opens a Python prompt |
| Failed | Keeps the VM up at the failure, with the log and last frame |
| Restarting | Drops the unfinished clip, keeps finished ones, and returns to Loading |

Checking only covers what the state describes. Anything else on the desktop is ignored.

### Holding

Holding opens a Python prompt where `self` is the live scene. Anything typed there runs as a new
action with its own clip. This is the same idea as Manim's `interactive_embed`. A file can't do
this job, because the variables from `construct()` only exist in the running process.

Clips made this way are previews. They may differ from a clean run, so the final output should
come from a full run. Failed opens the same prompt, without the new clip.

### Recording part of a scene

With `--section action_3`, actions 1 and 2 run first with capture off, action 3 records, and the
result is joined with the clips already on disk.

- **Capture off is not free.** Manim can skip an animation in one step. Here, earlier actions must
  still make their real mouse moves and clicks, and `Hover`, other live animations and keypresses
  still take real time. Only the screenshots are saved. A later `fast_forward()` hook on
  animations could jump window moves to their end, but pointer actions would still replay.
- **Reuse is your call.** art98 can't tell whether an edit to `construct()` changed an earlier
  action. A full render ignores old clips, and only `--section` reuses them.
- **Later clips can go stale.** If action 3 ends differently, clip 4 starts with a visible jump.

## Backend

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

## Not proven yet

Each of these needs a test on the real image before the schema is final.

| Item | Risk |
| --- | --- |
| Icon positions | Another program owns them, and Windows 98 has refused some calls that reach into other programs' windows |
| Tray | Adding icons is likely. Removing another program's icon is unproven |
| Wallpaper | Likely easy, but the bitmap must reach the guest first |
| Window order and focus | Taskbar order follows the order windows opened, so it may not match the JSON |
| Opening files | Titles change, and Paint may not show the image at the expected zoom or size |
| Paint with an opened file | `canvas_size` assumes a blank canvas, so canvas positions and `resize_canvas` would be wrong. `ready()` must also run on an adopted window |
| Copying files | `put_file` ran at about 90 KB/s on a quiet host and about 12 KB/s on a busy one, so a 1.4 MB wallpaper could take 15 s or far longer on every Set. If that's too slow, assets could go on a read-only disc attached by the backend |
| Stray pixels | One Set in 4 differed by 8 pixels at Notepad's left edge, where it covers a desktop icon label. See "Test results" |
| Capture off | Some actions depend on real time, so a run with capture off may differ from a recorded one |
| Clock and randomness | A new Minesweeper board differs each run unless these are fixed |

## Test results

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

**A warm baseline beats the 2 s target.** A revert also throws away the guest's disk cache, so
every launch is cold. Launching Notepad and Paint once before saving the snapshot cut Paint from
0.83 s to 0.49 s on a quiet host. The windows are closed again before the save, and the resulting
state matched the one from `ready`, apart from the stray pixels below. This changes how the
baseline is made, so it's a decision, not a test result.

**Differences found:**

- **Pointer and colours.** On a fresh boot, the first pointer move turns the pointer on and shifts
  the colours (white 255 becomes 248, teal 123 becomes 120). The memory is the same, so this looks
  like QEMU switching how it draws, though that cause is inferred. It already affects today's
  scenes, in the frames before the first pointer move. After a revert it's always in the second
  form, so Sets are consistent with each other. Reverting once right after boot would make every
  frame consistent.
- **Stray pixels.** In one run, 1 Set in 4 differed by 8 pixels at Notepad's left edge, on the end
  of the "My Documents" label, and the state from `ready` showed the same 8 pixels. It looks like
  a repaint timing issue, but the cause isn't confirmed. Checking rects wouldn't catch it. Run 2's
  stall wasn't real: the watchdog fired during normal slow work and it didn't happen again.

**What this changes:**

- Revert must fail open calls straight away, not leave them waiting for a timeout.
- The documented `put_file`, `get_file` and app launch times are quiet-host figures. A Set figure
  should be quoted with the host load.
- Done-when 1 still needs the stray pixels explained.

## MVP

**A script can jump the desktop to a state it chose, as many times as it likes, and record from
there.** The baseline already exists, so the MVP is the path from Loading to Ready, plus a
restart. That path is the biggest unknown, and everything else builds on it.

### In

| Part | What it covers |
| --- | --- |
| Display | `"display": [800, 600, 16]`, using `set_display_mode`. A switch takes 65 to 150 ms with no reboot, but only modes the driver offers work |
| Windows | Notepad, Paint and any `command`, each with `id`, `rect`, `show` and an order |
| Images | `open` on a Paint window, with a BMP copied to the guest first |
| Pointer | Placed last, because focus may need a click on a title bar |
| Revert | `loadvm ready` in the running VM, kept as one plain function |
| Set | `set_state(path)`, usable any number of times. Each call is a hard cut |
| Check | Display, each window's rect and order, and the pointer |
| Scene | `state`, `set_state()` and `self.prop()` |

Moving, opening and closing windows on camera needs nothing new. The existing animations do
that, starting from the state.

```python
class Mvp(Scene):
    state = "states/two_windows.json"

    def construct(self):
        notes = self.prop("notes")
        self.play(notes.animate.shift(200 * RIGHT), run_time=2)
        self.play(Close(notes))

        self.set_state("states/gallery.json")
        self.pause(1)
        self.play(self.prop("picture").animate.shift(100 * DOWN), run_time=2)
```

### Out, for now

Wallpaper, icons and tray. Sections, clips and `--section`. Holding, Failed with a live VM, the
Python prompt and Stop. The backend interface, Notepad text, Minesweeper, and the agent bug fixes.

### Done when

1. Setting the same state 10 times gives matching screenshots. Any difference gets explained.
2. Set takes under 2 s for a state with two windows and a small image. The real figure goes in
   the docs either way.
3. A bad file, a missing window or a wrong position stops with a clear error.
4. The sample scene renders, jumping between two states.
5. Existing scenes and tests still pass.

### Order

1. Test revert and a hand-applied state in a throwaway script on a private copy. Done: it passed,
   apart from the stray pixels. See "Test results".
2. Make `put_file` check the written count.
3. Add the schema and loader.
4. Add revert, apply and check.
5. Add `state`, `set_state()` and `self.prop()` to `Scene`.
6. Add the sample scene and tests, then record the results.

## After the MVP

1. **Actions and clips.** `next_section`, one clip per action, capture off and `--section`.
2. **More of the desktop.** Wallpaper, icons and tray, each after its test.
3. **Backend.** Move start, revert, capture and keys behind one interface.
4. **Run control.** Holding and Failed with the Python prompt, and Stop. `render()` closes the VM
   on exit today, so this needs restructuring.
5. **Docs.** Update Part 2, rename `anim/actions.py`, and port the showcase as the proof.

The agent bug fixes are separate work. Nothing here depends on them.
