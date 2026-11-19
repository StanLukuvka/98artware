# Design: desktop options

Requirements: [requirements.md](requirements.md), with the owner decisions of 2026-11-20. Probe
results: `experiments/taskbar/README.md` (both probes). Read before writing: `core/art98/desktop.py`,
`core/art98/anim/scene.py`, `core/art98/anim/setstate.py`, `core/art98/actions/backdrop.py`,
`core/art98/guest/win32.py`, `core/tests/test_desktop.py`, `core/tests/test_anim.py`.

## Overview

A scene sets `desktop` to a preset name (as today) or to a `Desktop` value: one frozen dataclass
in `core/art98/desktop.py`, beside `blank`, with a flat option for each part of the desktop. No new
module. The parts have implicit levels: an option that is off hides the options under it. One pure
function turns the written value into the effective parts and the warnings. One function applies
the parts after every revert, and the same check path reads them back. `"blank"` and `"stock"` are
two presets, and blank applies the same calls in the same order as today.

Nothing here touches prep, the `ready` snapshot or the display-mode path in `apply_state`
(`apply_state` keeps calling `scene.prepare_desktop()`, as it does now).

## 1. The public shape

Exported from `art98.anim`: `Desktop`.

```python
@dataclass(frozen=True)
class Desktop:
    preset: str = "blank"           # "blank" or "stock"
    _: KW_ONLY
    icons: bool | None = None       # None: the preset's value
    pointer: bool | None = None
    taskbar: bool | None = None
    buttons: bool | None = None
    quick_launch: bool | None = None
    tray: bool | None = None
    clock: bool | None = None
```

Rules of writing:

- Every option is `True`, `False` or left out. Left out means the preset's value. The options are
  keyword-only, so `Desktop("stock", False)` is a `TypeError`, not a guess.
- A preset followed by an option is an override (Requirement 2.4). Overriding a preset is not a
  conflict. What is a conflict is in section 2.
- `desktop = "blank"` and `desktop = "stock"` keep working and equal `Desktop("blank")` and
  `Desktop("stock")`. `Scene.desktop` stays `"blank"` by default.
- There is one way to write each part. A misspelled keyword (`Desktop(clok=False)`) is Python's
  `TypeError`, which names the keyword and the author's line (owner decision 1).
- `pointer_visible` keeps working (section 2).

### The levels

The one place that says what sits over what. The code holds it as one dict, `PARENT`, and
everything else (resolution, warnings, apply, check, tests) reads that dict.

| Option | Level | Sits under | Hidden by |
| --- | --- | --- | --- |
| `icons` | 0 | nothing | nothing |
| `pointer` | 0 | nothing | nothing |
| `taskbar` | 0 | nothing | nothing |
| `buttons` | 1 | `taskbar` | `taskbar` |
| `quick_launch` | 1 | `taskbar` | `taskbar` |
| `tray` | 1 | `taskbar` | `taskbar` |
| `clock` | 2 | `tray` | `tray`, `taskbar` |

```python
PARENT = {"buttons": "taskbar", "quick_launch": "taskbar", "tray": "taskbar", "clock": "tray"}
```

An option is *under* every option on its chain, so `clock` is under `tray` and under `taskbar`.
`icons` and `pointer` have no children.

Whole scenes, as the docs will show them:

```python
from art98.anim import *


class NoClock(Scene):
    """The stock desktop with the clock hidden."""

    desktop = Desktop("stock", clock=False)

    def construct(self):
        self.add(Notepad("Untitled - Notepad", at=(80, 60)))
        self.wait(1)
```

```python
from art98.anim import *


class BlankWithTaskbar(Scene):
    """Black desktop, no icons, but a taskbar with no window buttons."""

    desktop = Desktop("blank", taskbar=True, buttons=False)

    def construct(self):
        self.add(Notepad("Untitled - Notepad", at=(80, 60)))
        self.wait(1)
```

```python
from art98.anim import *


class StockNoTaskbarNoPointer(Scene):
    desktop = Desktop("stock", taskbar=False, pointer=False)

    def construct(self):
        self.wait(1)
```

The docs also show the warning, in a `text` block (not a scene), for
`Desktop("stock", tray=False, clock=True)`; see section 2.

The docs examples need a program that exists in the catalogue and a `Notepad` title; the
implementation checks them against `test_anim_docs.py`.

## 2. Resolving the options

### Effective parts

```python
@dataclass(frozen=True)
class Parts:                         # internal, not exported
    icons: bool
    pointer: bool
    taskbar: bool
    buttons: bool
    quick_launch: bool
    tray: bool
    clock: bool
    blank_steps: bool                # the steps that belong to no part (owner decision, question 2)
```

`Parts` holds what the guest will show. A child of an off option is always `False` in `Parts`, so
`Parts` can never describe a clock under a hidden tray. `blank_steps` is true for the `"blank"`
preset only, and stays true when a part is turned back on. It stands for: black desktop colour,
disabled `Progman`, animations, gradient captions and hot tracking off.

The presets are written values, before the levels apply:

```python
PRESETS = {
    "stock": dict(icons=True, pointer=True, taskbar=True, buttons=True, quick_launch=True, tray=True, clock=True),
    "blank": dict(icons=False, pointer=False, taskbar=False, buttons=True, quick_launch=True, tray=True, clock=True),
}
```

Blank's children are on in the preset, so `Desktop("blank", taskbar=True)` shows a full taskbar.
`STOCK` is `Parts` with every part on and `blank_steps=False`, and `resolve_desktop(Desktop("stock"))`
equals it, which lets `apply` return at once.

### The function

```python
def resolve_desktop(value, owner: str, pointer_visible: bool | None) -> tuple[Parts, list[str]]:
    """The effective parts and the warning texts. Raises UsageError."""
```

It is pure: no guest, no warning call. `owner` is `"ClassName.desktop"` for messages.
`pointer_visible` is `None` when the scene never declared it.

1. `value` is a `str`: `Desktop(value)`. A `Desktop`: as is. Anything else:
   `UsageError("Name.desktop 5: use one of blank, stock, or a Desktop(...)")`.
2. Unknown `preset`: `UsageError("Name.desktop 'foo': use one of blank, stock")`. This is the
   text `check_desktop` gives today.
3. Types: each option must be `True`, `False` or `None`, tested with `type(x) is bool`, so `1` and
   `"off"` are refused with
   `UsageError("Name.desktop: tray must be True or False, not 'off'")`.
4. `base` = the preset's written values, with each option that is not `None` replacing its
   preset value.
5. Effective: walk `PARENT`. An option is effective only when `base` has it on and every option
   it sits under is effective. So `Parts.clock = base.clock and base.tray and base.taskbar`.
6. Pointer. `pointer_visible` is the old name for the pointer part:
   - `Desktop.pointer` written: the tree wins. If `pointer_visible` was declared and differs, add
     the pointer warning below.
   - Not written, preset `"blank"`: pointer is `bool(pointer_visible)` (default off), as today.
   - Not written, preset `"stock"`: on. A declared `pointer_visible` is ignored on stock, as
     today, and does not warn.

### The override warning

A written option is *overridden* when `base` has some option it sits under off. Written means
the author gave a value, `True` or `False`. The off option can be off because the author wrote
it or because the preset has it off (the second is a recommendation; see "Decisions for the
owner", decision 1). `resolve_desktop` makes one warning per overridden option, in the order of
the table above.

The off option named in the text is the **highest** one that is off, because that is the one to
change: with `taskbar=False, tray=False, clock=True`, the clock warning names `taskbar`. The text
says where the off value came from, the author (`tray=False`) or the preset (`the "blank" preset`).

```text
Name.desktop: clock=True has no effect, because tray is off (tray=False). Remove clock=True, or write tray=True.
Name.desktop: buttons=False has no effect, because taskbar is off (taskbar=False). Remove buttons=False, or write taskbar=True.
Name.desktop: buttons=False has no effect, because taskbar is off (the "blank" preset). Remove buttons=False, or write taskbar=True.
```

The template is
`{owner}: {option}={value} has no effect, because {parent} is off ({source}). Remove {option}={value}, or write {parent}=True.`
with `{source}` either `{parent}=False` or `the "{preset}" preset`. `{owner}` starts with the
scene class name, as in the `UsageError` texts, so Python's default once-per-message-and-line
filter shows each warning once per class, because two classes never share text.

The override really has no effect. Writing the option `True`, `False` or leaving it out gives the
same `Parts` (a property test, section 6). A child written the same as its effective value
(`Desktop("blank", buttons=False)`) still warns: the setting is dead either way, and the author
most likely forgot `taskbar=True`.

What does not warn:

- A preset alone, and a preset with an override that takes effect: `Desktop("blank",
  taskbar=True, buttons=False)`, `Desktop("stock", clock=False)`.
- A higher option written on: `Desktop("stock", taskbar=True, buttons=False)`.
- `pointer_visible = False` on stock, as today.

The pointer warning is the other one:

```text
Name.pointer_visible = True is ignored, because Desktop(pointer=False) sets the pointer. Remove pointer_visible, or make the two agree.
```

with the actual values filled in. It is built by the same function, from the same inputs.

### Where it runs

`pointer_visible` is "declared" when some class in the scene's MRO other than `Scene` has it in
`vars()`, or the instance has it in `__dict__`. A helper `_desktop_of(scene)` in `scene.py`
collects `scene.desktop` and that value, calls `resolve_desktop`, and returns `(parts, notes)`.

- `check_desktop(scene)` calls it and returns `(parts, notes)`. It raises `UsageError`. It is
  called from `__init_subclass__` with the class and from the start of `run` with the instance
  (the instance may have changed `desktop`). It does not warn.
- **Warnings are raised in `Scene.__init_subclass__`**, once, when the class statement runs:

  ```python
  parts, notes = check_desktop(cls)
  if "desktop" in vars(cls) or "pointer_visible" in vars(cls):
      for note in notes:
          warnings.warn(note, UserWarning, stacklevel=2)
  ```

  Called straight from `__init_subclass__`, `stacklevel=2` is the frame that runs the `class`
  statement: the author's file and the `class` line. (`type.__new__` has no Python frame.) A
  helper would need `stacklevel=3`; the loop stays inline so the count is plain. A subclass that
  inherits both settings does not warn again.
- `UserWarning`, no new category. It shows under default filters in `python scene.py` and in
  `art98 render`, which sets no filters (owner decision, question 10). The warning is seen when
  the script runs, at the `class` line, and the render goes on (Requirement 6.6).
- `prepare_desktop` calls `check_desktop(self)[0]` for the parts. The function is pure and
  cheap, so there is no cache to go stale.

`UsageError` is raised only in `resolve_desktop` (through `check_desktop`), at class definition
and at the start of `run`.

## 3. Applying it

`desktop.blank(guest, pointer)` is replaced by:

```python
def apply_desktop(guest, parts: Parts) -> None:
    """Put the parts in place on a reverted desktop, then check them. Raises DesktopError."""
```

`scene.prepare_desktop` becomes:

```python
def prepare_desktop(self):
    apply_desktop(self.guest, check_desktop(self)[0])
    self.calibrate()
```

Steps, in order. Because `Parts` has a child off whenever its parent is off, a step on a child
runs only inside `if parts.taskbar` (and the clock only inside `if parts.tray`); no check of the
levels is left in `apply`.

1. `if parts == STOCK: return`. Stock with nothing off makes no guest call, as today.
2. `shell_windows(guest)` gives taskbar, desktop, icons. `taskbar_windows(guest, taskbar)` (new,
   beside it) gives `{"buttons", "quick_launch", "tray", "clock"}` handles, 0 for a missing one. It
   uses `FindWindowExA`: rebar under the taskbar, `MSTaskSwWClass` and `ToolbarWindow32` under the
   rebar, `TrayNotifyWnd` under the taskbar, `TrayClockWClass` under the tray. It runs only when
   the taskbar is on and some child is off.
3. `if parts.blank_steps: set_colour(guest, black)`. First, as `blank` does today.
4. `if not parts.icons and icons: ShowWindow(icons, SW_HIDE)`.
5. `if not parts.taskbar`: `ShowWindow(taskbar, SW_HIDE)`, `EnableWindow(taskbar, 0)`.
6. `if parts.blank_steps`: `EnableWindow(desktop, 0)`.
7. `if not parts.taskbar`: the work area becomes the whole screen (`SPI_SETWORKAREA`). It goes
   with `taskbar` off, not with blank, so stock with `taskbar=False` gets it and blank with the
   taskbar on does not (Requirement 3.3, 3.4).
8. `if parts.blank_steps`: the effects off (`for ... in UI_EFFECTS`).
   Steps 3 to 8 are today's order for `blank`: colour, icons, taskbar hide and disable, desktop
   disable, work area, effects. A unit test pins that order for `BLANK`.
9. `if parts.taskbar`, the children that are off, in this order:
   1. clock off and tray on: `ShowWindow(clock, SW_HIDE)`, then
      `SendMessageA(taskbar, WM_SIZE, 0, 0)`. This settles the tray at once to its icon, with
      the same pixels as a colour change (second probe, question 7). It comes before the other
      hides so the message cannot show a part hidden earlier.
   2. buttons off: hide `MSTaskSwWClass`.
   3. quick launch off: hide `ToolbarWindow32`. The band's grip stays and the buttons do not move
      (probe, question 1).
   4. tray off: hide `TrayNotifyWnd`, last.

   Hiding only; the taskbar keeps its size and `work_area` does not change (Requirement 3.5).
10. `if not parts.pointer: hide_pointer(guest)` once, after the revert, as the module notes
    require. This also covers `pointer=False` on stock (probe question 4).
11. `guest.sync()`, then `problems = check_parts(guest, parts)`; raise
    `DesktopError(problems, lead)` when there are any.

For `BLANK` this is exactly today's `blank(guest, pointer=False)`: same calls, same order, one
`sync` at the end, so `test_desktop`'s count of 3 syncs still holds. `pointer_visible = True` on
blank is `replace(BLANK, pointer=True)`, which skips only `hide_pointer`.

### `set_colour` keeps the tray hidden

`set_colour` already re-hides the icons when they were hidden. It gets the same for the tray:

```python
taskbar, _desk, icons = shell_windows(guest)
tray = (
    user32.FindWindowExA(taskbar, 0, TRAY_CLASS, 0).value
    if taskbar and user32.IsWindowVisible(taskbar).value
    else 0
)
hidden = [h for h in (icons, tray) if h and not user32.IsWindowVisible(h).value]
... SetSysColors ...
for h in hidden: user32.ShowWindow(h, SW_HIDE)
```

The tray is looked at only when the taskbar is visible. On blank the taskbar is hidden, so the tray
is not touched: blank's calls in `set_colour` stay as they are, apart from one
`IsWindowVisible(taskbar)`. Buttons, quick launch and the clock stay hidden through a colour change
on their own (probe), so only the tray needs this. The wallpaper broadcast and a display mode
change leave all parts hidden (probe, question 8), so `set_wallpaper` does not change.
`apply_state` is not changed.

## 4. Checking it

`check_blank` is extended and renamed `check_parts(guest, parts) -> list[str]`: one check path, no
copy beside it. Each existing line keeps its exact text. What it reads depends on `parts`:

| Condition | Check, with its message |
| --- | --- |
| icons off | list found and not visible: "the desktop icons are showing", "the desktop icon list wasn't found" |
| taskbar off | not visible, not enabled: the two existing messages; work area equals the screen |
| taskbar on | found and visible: "the taskbar wasn't found" is raised when missing |
| taskbar on, a child | off: not visible, "the taskbar's tray is showing"; on: found, "the taskbar's tray (TrayNotifyWnd) wasn't found". Same for buttons, quick launch, clock |
| `blank_steps` | `Progman` disabled; colour black; the five effects off, as today |

A child of an off parent is not read, because `Parts` has it off and its parent already reads as
hidden: the clock under an off tray, any child under an off taskbar. The pointer is not checked,
as today. Every difference is collected before raising, so `DesktopError` lists them all, one per
line. The lead is "the desktop isn't blank:" when `blank_steps` is true and "the desktop options
didn't take:" otherwise.

## 5. Constants and class names

All in `core/art98/guest/win32.py`, once:

```python
WM_SIZE = 0x0005
TASKBAR_CLASS = "Shell_TrayWnd"
REBAR_CLASS = "ReBarWindow32"
QUICK_LAUNCH_CLASS = "ToolbarWindow32"
BUTTONS_CLASS = "MSTaskSwWClass"
TRAY_CLASS = "TrayNotifyWnd"
CLOCK_CLASS = "TrayClockWClass"
```

`shell_windows` uses `TASKBAR_CLASS` instead of its inline string. `Progman`, `SHELLDLL_DefView`
and `SysListView32` stay where they are: they are not part of this feature. A part is looked up with
`FindWindowExA` on its direct parent; the probe lists the quick launch and the buttons as children
of the rebar. If a VM test finds them deeper, the lookup becomes one recursive helper in
`win32.py`, and nothing else changes.

## 6. Testing

Unit tests, no VM. `FakeGuest` (in `test_anim.py`) records every call in `.calls` and answers
through `do_<Function>` handlers; `DesktopGuest` in `test_desktop.py` is the stand-in for desktop
work. Extend `DesktopGuest`, no new fake, with only what the probes saw:

- `FindWindowExA` finds the rebar, `ToolbarWindow32`, `MSTaskSwWClass`, `TrayNotifyWnd` and
  `TrayClockWClass` under their parents.
- A child's `IsWindowVisible` is true only when it and every ancestor is visible.
- `ShowWindow(SW_HIDE)` hides a part. `SetSysColors` shows the tray again, and nothing else
  (probe table). `SendMessageA(taskbar, WM_SIZE)` is recorded.

`test_desktop.py`:

- Blank and stock unchanged: `BLANK` gives the guest state and the call order of today's test;
  `STOCK` makes no call at all; the syncs count is 3.
- Each part off on stock: buttons, quick launch, tray, clock, icons, pointer, taskbar, alone and in
  one combination. `work_area` read from the guest is unchanged when only children are off.
- Blank with the taskbar on: taskbar visible and enabled, work area as the guest gave it, colour
  still black, `Progman` still disabled, animations off.
- Order: the clock hide and `WM_SIZE` come before the other hides; the tray is hidden last.
- `Backdrop` and `set_colour` with the tray off: the tray is hidden again, and the other parts
  stay hidden; on blank no extra `ShowWindow` appears.
- `set_state` (a Set) re-applies the parts after a revert (use the Scene with a `FakeSession`).
- `DesktopError`: a part that will not hide, and a part not found, each named in a line; two
  problems give two lines.

Scene level, in `test_anim.py` or `test_desktop.py`:

- `desktop = "blank"`/`"stock"` as strings behave as before; `pointer_visible = True` on blank
  gives pointer on; on stock it changes nothing.
- The override warning, with the exact texts of section 2: `pytest.warns(UserWarning, match=...)`
  for `Desktop("stock", tray=False, clock=True)`, `Desktop("stock", taskbar=False, buttons=False)`
  and `Desktop("blank", buttons=False)` (the preset case). The warning's `filename` is the test
  file (stacklevel), each warning shows once per class under `simplefilter("default")`, and a
  subclass that inherits the settings does not warn again.
- The pointer warning: `match="ClassName.pointer_visible"`, and none for `pointer_visible = False`
  on stock.
- No warning for a preset alone, or for an override that takes effect (`Desktop("blank",
  taskbar=True, buttons=False)`).
- The render goes on after a warning: the scene runs and the guest has the effective parts.
- `UsageError` for an unknown preset (lists the choices), a non-`bool` option (`1`, `"off"`), and a
  scene whose `desktop` is `5`; the message holds the class name. `TypeError` for a misspelled
  keyword and for a positional option. `FrozenInstanceError` on assignment.

### Property tests

The input space is small: 2 presets, 7 options of 3 values each (`None`, `True`, `False`), and 3
values of `pointer_visible` (undeclared, `True`, `False`) make 2 x 3^7 x 3 = 13,122 cases of a
pure function. The tests walk all of them with `itertools.product`, so no property library is
needed and every case is covered, not a sample (see "Decisions for the owner", decision 2). Each
test builds an oracle from the level table in section 1, written as explicit lists
(`UNDER = {"buttons": ("taskbar",), "quick_launch": ("taskbar",), "tray": ("taskbar",),
"clock": ("tray", "taskbar")}`), not by calling the implementation's `PARENT` walk.

1. **A warning appears exactly when a written option sits under an off one.** For every case, the
   options that have a warning equal `{o : o written and some option in UNDER[o] is off in base}`,
   where `base` is the preset with the written values on top. One warning per such option, no
   other `Desktop` warning, and each text starts with the owner string, names the option and its
   value, and names the highest off option in `UNDER[o]`, with `taskbar=False` or the preset as the
   source.
2. **The effective parts never show a child of an off parent.** For every case and every
   `(child, parent)` in the table, `Parts.child` implies `Parts.parent`, so `clock` implies `tray`
   and `taskbar`.
3. **An effective part is what was written, unless something above is off.** For every case and
   option, `Parts.o` is `False` when some option in `UNDER[o]` is off in `base`, and the written
   value (or the preset's) otherwise.
4. **A warned option does nothing.** For every case with a warned option `o`, replacing its written
   value by `None`, `True` and `False` in turn gives the same `Parts` and the same set of other
   warnings.
5. **A preset alone never warns.** `Desktop(preset)` and the bare string give `STOCK` or `BLANK`
   and no notes, for any `pointer_visible` (which only sets the blank pointer, per property 6).
6. **`pointer_visible` touches only the pointer.** For every case, the three values of
   `pointer_visible` give equal `Parts` apart from `pointer`, and the pointer warning appears
   exactly when `pointer` is written and `pointer_visible` is declared and differs.
7. **Resolving is pure.** Two calls on the same input are equal, and `Desktop` is not changed.
8. **Bad values raise `UsageError`, and nothing else.** For each option, each of `1`, `0`, `"on"`
   and `[]` raises `UsageError` whose message holds the owner string and the option name.
9. **Apply and check agree.** For each distinct `Parts` that `resolve_desktop` produces (a few
   dozen), `apply_desktop` on the extended `DesktopGuest` leaves `check_parts` returning `[]`, and
   no `ShowWindow` call goes to a child whose parent is off.

VM tests in `core/tests/test_stage.py` (marker `stage`, `with attach()`): each part hidden reads
back with `IsWindowVisible` after `run`; a window opened after `buttons` is off gets no button
(`IsWindowVisible` of the button area stays false); `scene.work_area` equals the stock one with
only children off; the tray stays off after `Backdrop`; parts are re-applied after `set_state`;
a pass at 640x480 and 1024x768. If there is no image: `VM tests: not run (no prepared image on
this machine)`. `tools/check_docs.py` renders the doc samples.

Callers of `blank` and `check_blank` move to `apply_desktop` and `check_parts`, including
`core/tests/test_stage.py` (owner decision 4). Probes under `experiments/` stay as they are.

## 7. Docs

`docs/scenes/scene-api.md`:

- The `desktop` row of the Scene table: a preset or a `Desktop`, with a link to the new section.
  The `pointer_visible` row: it maps onto the `pointer` part, and the `Desktop` value wins, with
  a warning.
- A new "Desktop options" subsection after the Scene table: the level table of section 1, the
  options of `Desktop`, the presets, the three scenes above as whole `python` blocks, the override
  warning with its text (a `text` block), what a colour change and a revert do, and the errors.
  It says that a higher option that is off hides the ones under it, and that writing one of those
  is warned about. It says what the probes checked on the real image (800x600 full probe, 640x480
  and 1024x768 hiding and read-back; 1280x1024 at 16 bit not offered by the driver) and what was
  not (the taskbar after a display mode change; see the probe notes). It names `Desktop`, which
  the docs test requires.
- The intro line "work area is the whole screen on the default blank desktop" gets "unless the
  taskbar is on".

`docs/glossary.md`: **Part**, **Preset** and **Override** (an option written after a preset; one
that sits under an off option is warned about). `docs/design/blank-start.md`: one sentence that
blank is now a preset and the steps are the same. `docs/status.md` is not edited.

`CHANGELOG.md`, under `[Unreleased]` / `### Added`:

```text
- `Desktop` sets which parts of the desktop show: `icons`, `pointer`, `taskbar`, `buttons`,
  `quick_launch`, `tray` and `clock`. `desktop = "blank"` and `"stock"` are presets of it, so
  `Desktop("blank", taskbar=True, buttons=False)` is a black desktop with a taskbar. An option that
  is off hides the ones under it (`taskbar` over `buttons`, `quick_launch` and `tray`; `tray` over
  `clock`), and writing one of those gives a warning. The options are applied after every revert
  and survive a colour change. See [Desktop options](docs/scenes/scene-api.md#desktop-options).
```

And under `### Changed`:

```text
- A `Desktop` that sets `pointer` makes `pointer_visible` ignored, with a warning.
```

## Files touched (for tasks.md later)

`core/art98/desktop.py`, `core/art98/guest/win32.py`, `core/art98/anim/scene.py`,
`core/art98/anim/__init__.py`, tests (`test_desktop.py`, `test_stage.py`, any test that calls
`blank` or `check_blank`), `docs/scenes/scene-api.md`, `docs/glossary.md`,
`docs/design/blank-start.md`, `CHANGELOG.md`. `setstate.py` and `backdrop.py` do not change
(`Backdrop` calls `set_colour`, which now keeps the tray). `pyproject.toml` does not change.

## Decisions for the owner

1. **Does an override count when the off option is off only by the preset?** For example
   `Desktop("blank", buttons=False)`: blank's taskbar is off, so `buttons=False` does nothing.
   Options: (a) warn, naming the preset as the source; (b) warn only when the off option above was
   written. Recommendation: **(a)**. The user story of Requirement 6 is that a setting that does
   nothing is reported, and the common slip here is forgetting `taskbar=True` on blank. The cost
   is a warning on a redundant write, which is dead code in the scene anyway. Under (b) the scene
   renders with no taskbar and no explanation. Requirement 6.1 is written for (a) and changes if
   you choose (b); so does the third text in section 2 and test 1.
2. **Property tests walk every case.** Hypothesis is in the dev group (`pyproject.toml`, added
   for the state-file-hashing spec; corrected by Claude Code, since this draft first said it
   wasn't). The space is only 13,122 cases, so the tests walk every case with
   `itertools.product` instead of sampling. Recommendation: walk every case; Hypothesis isn't
   needed here.
3. **One warning per overridden option.** `Desktop("stock", taskbar=False, buttons=False,
   quick_launch=False, tray=False)` gives three. The alternative is one warning per scene class that
   lists them. Recommendation: one per option. Each text is short, each one can be fixed alone, and
   the default filter shows each once.
4. **Options are keyword-only.** `Desktop("stock", False)` is a `TypeError`. Recommendation: keep,
   because a positional boolean has no name to read.

## Owner decisions on the design (2026-11-20)

- **Decision 2 and 3, reversed: flat options with implicit levels.** There are no `Taskbar` or
  `Tray` classes. Every part is a flat option on `Desktop`, as `desktop.item`:
  `Desktop("stock", clock=False)`, `Desktop("stock", tray=False)`,
  `Desktop("blank", taskbar=True, buttons=False)`. The tree still exists, but only as levels:
  some options sit an implicit level higher and override the ones under them (`taskbar` over
  `buttons`, `quick_launch` and `tray`; `tray` over `clock`). When a higher option that's off
  overrides one under it that was written (for example `tray=False, clock=True`, or
  `taskbar=False, buttons=False` on stock), art98 warns, naming both, and the script still runs.
  This is the warning the owner asked for in the requirements (Requirement 6). It's seen when the
  script runs.
- **Decision 1:** accept Python's `TypeError` for a misspelled keyword. Amend Requirement 6.8.
- **Decision 4:** replace `blank` and `check_blank` with no wrapper, and update every caller
  in the repo (`core/tests/test_stage.py` too). Old probes under `experiments/` are throwaway and
  don't need updating.
- **Decisions 5 to 8:** accepted as recommended.
- **Remaining decisions 1 to 4 (2026-11-20):** accepted as recommended. An override that is off
  only by the preset warns and names the preset (1a). The tests walk every case (2). There is one
  warning per overridden option (3). The options are keyword-only (4).
