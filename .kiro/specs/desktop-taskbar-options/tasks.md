# Tasks: desktop options

Design approved 2026-11-20, with every owner decision at the end of `design.md`. No task touches
`requirements.md`, `design.md`, `docs/status.md`, `work/`, prep, the answer file, `ready.py`, the
`ready` snapshot, or the display-mode path in `core/art98/anim/setstate.py` (`apply_state` keeps
calling `scene.prepare_desktop()`). `core/art98/actions/backdrop.py` and `pyproject.toml` do not
change. Nothing here runs `art98 up` or `art98 setup`.

## How to read this list

- `UNIT` is the check command for every task unless it names a narrower one:

  ```bash
  uv run python -m pytest core/tests setup/tests -q --ignore=core/tests/test_stage.py --ignore=core/tests/test_stage_scenes.py --ignore=core/tests/test_qemu.py
  ```

  A narrower form is `uv run python -m pytest core/tests/<file> -q`. Only Tasks 11 and 14 need a
  VM, and each says so.
- `Requires` names the tasks that must be finished first. Tasks in one wave have no dependency on
  each other and touch different files, so they can run in parallel. A wave starts when every
  task it requires is done.
- Every task that changes Python also ends with `uv run ruff check . && uv run ruff format --check core setup tools`
  passing.
- Test names are sentences (CONTRIBUTING). Desktop tests extend `DesktopGuest` in
  `core/tests/test_desktop.py`; scene tests use `FakeGuest`, `FakeSession` and `FakeVM` from
  `core/tests/test_anim.py`. No new fakes. Teach `DesktopGuest` only what the probes in
  `experiments/taskbar/README.md` saw.
- Do not commit, push or switch branches (AGENTS.md "Git safety"). The owner commits.

## Existing desktop tests (read before writing tests)

In `core/tests/test_desktop.py` today, these call `desktop.blank` or `desktop.check_blank`:
`test_blank_hides_the_shell_and_turns_everything_off` (guest state, `CopyIcon` count,
`DestroyCursor`, `syncs == 3`), `test_blank_can_keep_the_pointer`,
`test_blank_says_so_when_there_is_no_empty_pointer`,
`test_blank_says_so_when_a_pointer_shape_will_not_swap`, `test_blank_says_what_did_not_take`
(parametrized over `ignore`), `test_check_blank_reports_a_missing_shell`. The scene-level ones
(`Blank`, `test_a_scene_starts_blank_and_measures_the_whole_screen`,
`test_a_scene_hides_the_pointer_unless_it_wants_it`, `test_a_stock_scene_leaves_the_desktop_alone`,
`test_an_unknown_desktop_is_refused_where_the_class_is_defined`,
`test_an_unknown_desktop_set_on_an_instance_is_refused_at_run`,
`test_scenes_start_blank_unless_told_otherwise`) go through `Scene` and must keep passing.

Task 3 moves each of the first group to `apply_desktop(guest, BLANK)`,
`apply_desktop(guest, replace(BLANK, pointer=True))` or `check_parts(guest, BLANK)`, with every
assertion kept. A test may be renamed to fit, but none is dropped and no assertion is weakened.

Other callers of `blank` / `check_blank` in the repo, found with an AST search:
`core/art98/anim/scene.py` (`prepare_desktop`) and `core/tests/test_stage.py` line 123
(`desktop.blank(guest)`). Callers under `experiments/` are throwaway probes and stay as they are
(owner decision 4). `examples/` holds the owner's private, untracked working notes, never part of
the repo: no task reads, edits or checks anything under it.

## Waves

| Wave | Tasks |
| --- | --- |
| 1 | 1, 2 |
| 2 | 3 |
| 3 | 4 |
| 4 | 5 |
| 5 | 6 |
| 6 | 7 |
| 7 | 8, 9, 11 |
| 8 | 12 |
| 9 | 13, 14 |
| 10 | 15 |

Task 1 adds only the pure resolution and its own test file, so it stands alone. Tasks 3 to 5 all
edit `core/art98/desktop.py` and `core/tests/test_desktop.py`, and Tasks 6 and 7 both edit
`core/art98/anim/scene.py` and `test_desktop.py`, so each runs in its own wave. Wave 7 is where
parallel work happens: its tasks touch a `scene.py` comment, `test_desktop.py`,
and `test_stage.py`, one each.

## Tasks

### Wave 1

- [ ] 1. Tree resolution: `Desktop`, `Parts`, `PARENT`, `resolve_desktop`, the warning texts
  - Files: `core/art98/desktop.py`, new `core/tests/test_desktop_options.py`.
  - In `desktop.py`, with no guest call and no `warnings.warn`: the frozen `Desktop` dataclass
    (`preset="blank"`, then `KW_ONLY`, the seven options defaulting to `None`); the internal frozen
    `Parts` (seven parts and `blank_steps`); `PARENT`; `PRESETS`; `STOCK` and `BLANK` as `Parts`;
    `resolve_desktop(value, owner, pointer_visible) -> tuple[Parts, list[str]]` following design
    section 2, steps 1 to 6: a `str` or a `Desktop`, anything else
    `UsageError("Name.desktop 5: use one of blank, stock, or a Desktop(...)")`; an unknown preset
    with today's `check_desktop` text; `type(x) is bool` checks; base from the preset with the
    written values on top; the `PARENT` walk; the pointer rule. Override texts follow the design's
    template, name the highest off option and its source (`tray=False` or `the "blank" preset`),
    one per overridden option in table order, then the pointer warning text. `blank`,
    `check_blank` and `DESKTOPS` are not touched yet.
  - Tests in the new file walk every case with `itertools.product` (2 presets x 3^7 options x 3
    `pointer_visible` values = 13,122) against an oracle written as explicit `UNDER` lists, not the
    implementation's `PARENT`. They cover design properties 1 to 8: a warning exactly when a
    written option sits under an off one, with the right text; no child shown under an off parent;
    an effective part is what was written unless something above is off; a warned option does
    nothing; a preset alone never warns; `pointer_visible` touches only the pointer, and its
    warning; resolving is pure; bad values `1`, `0`, `"on"`, `[]` raise `UsageError` naming the
    owner and the option. Plus the named examples: the three exact warning texts of design
    section 2, the pointer warning text, `resolve_desktop("stock", ...)[0] == STOCK`,
    `resolve_desktop("blank", ..., None)[0] == BLANK`, `Desktop("stock", False)` and
    `Desktop(clok=False)` raise `TypeError`, assignment raises `FrozenInstanceError`, `"foo"` and
    `5` give the `UsageError` texts with the class name.
  - Requires: none.
  - Covers: 1.1, 1.2, 1.3, 1.11, 2.3, 2.4, 2.6, 2.7, 6.1, 6.2, 6.3, 6.7, 6.8.
  - Done when: `uv run python -m pytest core/tests/test_desktop_options.py -q` passes, then `UNIT`.

- [ ] 2. Taskbar constants in `guest/win32.py`
  - Files: `core/art98/guest/win32.py`.
  - Add `WM_SIZE = 0x0005`, `TASKBAR_CLASS`, `REBAR_CLASS`, `QUICK_LAUNCH_CLASS`, `BUTTONS_CLASS`,
    `TRAY_CLASS` and `CLOCK_CLASS` with the values in design section 5, each defined once (check
    first that `WM_SIZE` is not already there). No other file uses them yet.
  - Requires: none.
  - Covers: 3.8.
  - Done when: `uv run python -m pytest core/tests/test_win32.py -q` passes, then `UNIT`.

### Wave 2

- [ ] 3. `apply_desktop` and `check_parts` replace `blank` and `check_blank`
  - Files: `core/art98/desktop.py`, `core/tests/test_desktop.py`, `core/art98/anim/scene.py`
    (the one `blank(...)` call in `prepare_desktop` and its import only),
    `core/tests/test_stage.py` (line 123 only).
  - `shell_windows` uses `TASKBAR_CLASS`. Add `taskbar_windows(guest, taskbar)` (design section 3,
    step 2). Write `apply_desktop(guest, parts)` with steps 1 to 11 in design order, and
    `check_parts(guest, parts)` with the table of design section 4, every existing message text
    kept and the lead chosen by `blank_steps`. Delete `blank` and `check_blank`, with no wrapper.
  - Move the existing tests (see "Existing desktop tests"). `BLANK` must make today's calls step
    for step: add `test_blank_makes_the_same_calls_in_the_same_order`, which pins the full call
    sequence of `apply_desktop(guest, BLANK)` (colour, icons, taskbar hide and disable, desktop
    disable, work area, effects, pointer, one `sync`), and keep `syncs == 3`.
  - Until Task 7 wires the tree in, `prepare_desktop` calls
    `apply_desktop(self.guest, replace(BLANK, pointer=self.pointer_visible))` for `"blank"` and
    nothing for `"stock"`, so every scene behaves as today. `test_stage.py` calls
    `apply_desktop(guest, BLANK)`.
  - Extend `DesktopGuest` as design section 6 lists: `FindWindowExA` finds the rebar,
    `ToolbarWindow32`, `MSTaskSwWClass`, `TrayNotifyWnd` and `TrayClockWClass` under their
    parents; a child is visible only when it and every ancestor is; `ShowWindow(SW_HIDE)` hides a
    part; `SendMessageA(taskbar, WM_SIZE)` is recorded.
  - Requires: 1, 2.
  - Covers: 2.2, 3.1 to 3.3, 3.6, 3.7, 5.1.
  - Done when: `uv run python -m pytest core/tests/test_desktop.py core/tests/test_desktop_options.py -q`
    passes, `grep -rnE "check_blank|desktop\.blank|import .*\bblank\b" core tools recipes`
    finds nothing, then `UNIT`.

### Wave 3

- [ ] 4. Part-by-part apply and check tests
  - Files: `core/tests/test_desktop.py` (and `core/art98/desktop.py` only to fix what a test
    shows; name it in the report).
  - Tests: each part off on stock alone (buttons, quick launch, tray, clock, icons, pointer,
    taskbar) and one combination, each read back on `DesktopGuest`; `work_area` unchanged when only
    children are off (3.5); stock with `pointer=False` hides the pointer once (1.10); blank with
    `taskbar=True` has the taskbar visible and enabled, the work area as the guest gave it, the
    colour black, `Progman` disabled and the effects off (3.4, 3.6); the clock hide and `WM_SIZE`
    come before the other hides and the tray is hidden last (5.2); `STOCK` makes no guest call
    (1.4, 2.1); `DesktopError` names a part that will not hide and a part not found, one line
    each, two problems give two lines, and the lead is "the desktop options didn't take:" without
    `blank_steps` (3.7); design property 9: for every distinct `Parts` that `resolve_desktop`
    produces, `apply_desktop` leaves `check_parts` returning `[]` and no `ShowWindow` goes to a
    child of an off parent.
  - Requires: 3.
  - Covers: 1.2 to 1.10, 3.4, 3.5, 3.7, 5.2.
  - Done when: `uv run python -m pytest core/tests/test_desktop.py -q` passes, then `UNIT`.

### Wave 4

- [ ] 5. `set_colour` keeps the tray hidden
  - Files: `core/art98/desktop.py`, `core/tests/test_desktop.py`.
  - As design section 3, "`set_colour` keeps the tray hidden": look up the tray only when the
    taskbar is visible, collect the hidden icons and tray, and hide them again after
    `SetSysColors`. `set_wallpaper`, `backdrop.py` and `setstate.py` do not change.
  - Teach `DesktopGuest` that `SetSysColors` shows the tray again and nothing else (probe table).
  - Tests: `test_a_colour_change_keeps_the_tray_hidden` (buttons, quick launch and clock stay
    hidden too); `test_a_colour_change_on_blank_adds_no_show_window` (the only new call is one
    `IsWindowVisible(taskbar)`); `test_a_backdrop_keeps_the_tray_hidden`, through `Backdrop`.
  - Requires: 4 (both edit `test_desktop.py` and `DesktopGuest`).
  - Covers: 4.3, 4.4, 5.2.
  - Done when: `uv run python -m pytest core/tests/test_desktop.py -q` passes, then `UNIT`.

### Wave 5

- [ ] 6. `check_desktop` resolves the tree
  - Files: `core/art98/anim/scene.py`, `core/tests/test_desktop.py`.
  - Add `_desktop_of(scene)`, which collects `desktop` and `pointer_visible` (declared when a class
    in the MRO other than `Scene` has it in `vars()`, or the instance has it in `__dict__`).
    `check_desktop(scene)` calls `resolve_desktop` through it and returns `(parts, notes)`; it
    raises `UsageError` and never warns. Its callers in `__init_subclass__` and at the start of
    `run` keep working. Remove `DESKTOPS` once nothing reads it.
  - Tests: the existing unknown-desktop tests still pass with today's text;
    `test_a_desktop_that_is_not_a_preset_or_desktop_is_refused` (`5`);
    `test_a_non_bool_option_is_refused_naming_the_class` (`1`, `"off"`), at class definition and
    when set on an instance before `run`.
  - Requires: 5.
  - Covers: 2.5, 6.8.
  - Done when: `uv run python -m pytest core/tests/test_desktop.py core/tests/test_anim.py -q`
    passes, then `UNIT`.

### Wave 6

- [ ] 7. `Scene` wiring: warnings, `prepare_desktop`, `pointer_visible`
  - Files: `core/art98/anim/scene.py`, `core/tests/test_desktop.py`.
  - `__init_subclass__` warns inline as design section 2, "Where it runs", shows (`UserWarning`,
    `stacklevel=2`, only when `desktop` or `pointer_visible` is in `vars(cls)`).
    `prepare_desktop` becomes `apply_desktop(self.guest, check_desktop(self)[0])` then
    `self.calibrate()`, replacing Task 3's interim call.
  - Tests: `pytest.warns(UserWarning, match=...)` with the exact texts for
    `Desktop("stock", tray=False, clock=True)`, `Desktop("stock", taskbar=False, buttons=False)`
    and `Desktop("blank", buttons=False)`; the warning's `filename` is the test file; each shows
    once per class under `simplefilter("default")`; a subclass that inherits the settings does not
    warn again; the pointer warning (`match="ClassName.pointer_visible"`), and none for
    `pointer_visible = False` on stock; no warning for a preset alone or for
    `Desktop("blank", taskbar=True, buttons=False)`; the render goes on after a warning and the
    guest has the effective parts; `"blank"` and `"stock"` strings behave as before;
    `pointer_visible = True` on blank keeps the pointer and on stock changes nothing; `set_state`
    applies the parts again after a revert (`FakeSession`); the parts are applied before `setup`
    runs.
  - Requires: 6.
  - Covers: 2.1, 2.2, 2.6, 2.7, 4.1, 4.2, 4.5, 6.4, 6.5, 6.6, 7.2.
  - Done when: `uv run python -m pytest core/tests/test_desktop.py core/tests/test_anim.py -q`
    passes, then `UNIT`.

### Wave 7

- [ ] 8. Keep the `lazy:` marker true
  - Files: `core/art98/anim/scene.py` (comment only, if needed).
  - The `lazy:` marker on `_hashes()` names Scene class attributes (`desktop`, `pointer_visible`)
    as not tracked. The owner's answer to open question 6 keeps it. Check that it still reads true
    now that `desktop` can be a `Desktop`, and change its words only if it describes `desktop` as a
    string.
  - Requires: 7.
  - Covers: 4.5 (open question 6 as decided).
  - Done when: `grep -n "lazy:" core/art98/anim/scene.py` shows the marker, and `UNIT` passes.

- [ ] 9. State files stay as they are
  - Files: `core/tests/test_desktop.py` (tests only; no change to `state.py` or `setstate.py`).
  - Tests: a state file with a `tray` key is still rejected with "the tray comes after this
    milestone"; `get_state` on a scene with parts off writes no part fields. If `test_state.py`
    already pins the `tray` rejection, point to it in the report instead of duplicating it.
  - Requires: 7.
  - Covers: 7.1, 7.3, 7.4.
  - Done when: `uv run python -m pytest core/tests/test_desktop.py core/tests/test_state.py -q`
    passes, then `UNIT`.

- [ ] 10. (Merged into Task 12, so the export and its docs land together and `UNIT` never goes
  red.)

- [ ] 11. VM tests in `core/tests/test_stage.py` (needs a running VM)
  - Files: `core/tests/test_stage.py`.
  - Needs `art98 vm start` running and the prepared image in `work/` (or the folder
    `ART98_TEST_WORK` names); the tests skip without it. Do not run `art98 up` or `art98 setup`.
    Mark the tests `stage` and use `with attach()` or the `booted` fixture, so the VM is released
    on failure.
  - Tests: each part hidden reads back with `IsWindowVisible` after `run`; a window opened after
    `buttons` is off gets no button; `scene.work_area` equals the stock one with only children
    off; the tray stays off after `Backdrop`; the parts are applied again after `set_state`; one
    pass at 640x480 and one at 1024x768.
  - Without a VM or image, write the tests, confirm they are collected and skip
    (`uv run python -m pytest core/tests/test_stage.py -q`), and report
    `VM tests: not run (no prepared image on this machine)`.
  - Requires: 7.
  - Covers: 1.5, 3.5, 4.2, 4.3, 8.4.
  - Done when: with a VM, `uv run python -m pytest core/tests/test_stage.py -q` passes; without
    one, the new tests skip and `UNIT` passes.

### Wave 8

- [ ] 12. Export `Desktop`, and the scene API docs: "Desktop options"
  - Files: `core/art98/anim/__init__.py`, `docs/scenes/scene-api.md`.
  - Add `Desktop` to the imports and to `__all__` of `art98.anim`. `Parts`, `PARENT` and
    `resolve_desktop` stay internal. `test_anim_docs.py` requires every `__all__` name in
    `scene-api.md`, so the export and the docs change together in this task.
  - The `desktop` row of the Scene table (a preset or a `Desktop`, linking the new section) and
    the `pointer_visible` row (it maps onto `pointer`; the `Desktop` value wins, with a warning). A
    "Desktop options" subsection after the Scene table, as design section 7 lists: the level
    table, the options, the presets, the three scenes of design section 1 as whole `python`
    blocks, the override warning in a `text` block, what a colour change and a revert do, the
    errors, what the probes checked on the real image (800x600 full probe; 640x480 and 1024x768
    hiding and read-back; 1280x1024 at 16 bit not offered by the driver) and what they did not
    (the taskbar after a display mode change). The intro line about the work area gets "unless
    the taskbar is on".
  - Requires: 7.
  - Covers: 8.1, 8.2.
  - Done when: `uv run python -c "from art98.anim import Desktop; Desktop('stock', clock=False)"`
    works, `uv run python -m pytest core/tests/test_anim_docs.py -q` passes, then `UNIT`.

### Wave 9

- [ ] 13. Glossary, `blank-start.md`, CHANGELOG
  - Files: `docs/glossary.md`, `docs/design/blank-start.md`, `CHANGELOG.md`.
  - Glossary: **Part**, **Preset** and **Override**. `blank-start.md`: one sentence that blank is
    now a preset and its steps are the same. `CHANGELOG.md` under `## [Unreleased]`: the
    `### Added` and `### Changed` bullets of design section 7, word for word. Do not edit
    `docs/status.md`.
  - Requires: 12 (the CHANGELOG links `#desktop-options`).
  - Covers: 8.1, 8.5.
  - Done when: `git diff CHANGELOG.md` shows only the new bullets inside `[Unreleased]`, and
    `uv run python -m pytest core/tests/test_anim_docs.py -q` still passes (it checks links).

- [ ] 14. Doc samples on the real VM (needs a running VM)
  - Files: none changed (fix only what a failing sample shows, and name the file in the report).
  - With the VM running, run `uv run python tools/check_docs.py`, so the three new scenes render.
    Without a VM, report it as not run.
  - Requires: 12.
  - Covers: 8.1, 8.4.
  - Done when: `tools/check_docs.py` exits 0, or the report says it was not run and why.

### Wave 10

- [ ] 15. Final check
  - Files: none changed (fix only what a failing check shows, and name the file in the report).
  - Run `UNIT` and `uv run ruff check . && uv run ruff format --check core setup tools`. Confirm
    with `git status` that only the files named in these tasks changed; that `docs/status.md`,
    `setstate.py`, `backdrop.py`, `setup/` and `work/` are untouched; and that no temporary files
    remain. When Tasks 11 and 14 could not run on a VM, the PR note line is
    `VM tests: not run (no prepared image on this machine)`.
  - Requires: 8, 9, 11, 13, 14.
  - Covers: all.
  - Done when: both commands exit 0 and `git status` lists only intended files.

## Requirement coverage

| Requirement | Tasks |
| --- | --- |
| 1.1, 1.11 | 1 |
| 1.2, 1.3 | 1, 4 |
| 1.4 | 4 |
| 1.5 | 4, 11 |
| 1.6 to 1.10 | 4 |
| 2.1 | 4, 7 |
| 2.2 | 3, 7 |
| 2.3, 2.4 | 1 |
| 2.5 | 6 |
| 2.6, 2.7 | 1, 7 |
| 3.1 to 3.3, 3.6 | 3, 4 |
| 3.4 | 4 |
| 3.5 | 4, 11 |
| 3.7 | 3, 4 |
| 3.8 | 2 |
| 4.1, 4.2 | 7, 11 |
| 4.3, 4.4 | 5, 11 |
| 4.5 | 7, 8 |
| 4.6 | none: no mid-scene action is added |
| 5.1 | 3 |
| 5.2 | 4, 5 |
| 5.3, 5.4 | every task (run time only; no prep or snapshot change) |
| 6.1 to 6.3, 6.7 | 1, 7 |
| 6.4 to 6.6 | 7 |
| 6.8 | 1, 6 |
| 7.1, 7.3, 7.4 | 9 |
| 7.2 | 7 |
| 8.1 | 12, 13, 14 |
| 8.2 | 12 |
| 8.3 | 1, 3 to 7, 9 |
| 8.4 | 11, 14 |
| 8.5 | 13, 15 |

## Problems found while writing these tasks

None blocks the design.

1. **`examples/` is out of bounds** (corrected by Claude Code). This list first had Task 3 edit
   `examples/inspiration/storm.py`. That folder is the owner's private, untracked working notes,
   not part of the repo, so no task touches it, and Task 3's grep leaves it out.
2. **Requirement 8.3 names `FakeVM`; the design names `DesktopGuest`.** Desktop tests use
   `DesktopGuest` in `test_desktop.py`, as the design and the existing tests do; scene tests use
   the `test_anim.py` stand-ins. Both already exist, so "no new fakes" holds.
3. **An interim `prepare_desktop`.** Deleting `blank` in Task 3 breaks `scene.py` unless its call
   moves too, so Task 3 makes a minimal change there and Task 7 replaces it. Each task stays green
   on its own.
4. **Export with the docs** (corrected by Claude Code). `test_anim_docs.py` requires every name in
   `__all__` to appear in `scene-api.md`. The first list exported in Task 10 and documented in
   Task 12, leaving `UNIT` red in between; Task 12 now does both.
5. **Shell checks** (checked by Claude Code). Kiro had no shell while writing this list. The
   grep in Task 3 was run afterwards: today it finds only `scene.py` line 25 and
   `test_stage.py` line 123, the two callers Task 3 moves. Every path named here exists.
