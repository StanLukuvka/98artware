# Tasks: desktop options

Design approved 2026-11-20, with every owner decision and the review fixes at the end of
`design.md`. No task touches `requirements.md`, `design.md`, `docs/status.md`, `work/`, prep, the
answer file, `ready.py`, the `ready` snapshot, or the display-mode path in
`core/art98/anim/setstate.py` (`apply_state` keeps calling `scene.prepare_desktop()`).
`core/art98/actions/backdrop.py` and `pyproject.toml` do not change. Nothing here runs `art98 up`
or `art98 setup`.

**Before Task 3 starts, PR #41 is merged into the branch these tasks build on.** It makes a
state's display mode use `persist=True`, so Explorer moves the taskbar on a mode change. Task 3
measures the parts after that, and Task 10's display passes are only meaningful with it (review
fix 10). Expect small merge conflicts with #41 in the `win32.py` constants and `CHANGELOG.md`.

## How to read this list

- `UNIT` is the check command for every task unless it names a narrower one:

  ```bash
  uv run python -m pytest core/tests setup/tests -q --ignore=core/tests/test_stage.py --ignore=core/tests/test_stage_scenes.py --ignore=core/tests/test_qemu.py
  ```

  A narrower form is `uv run python -m pytest core/tests/<file> -q`. Only Tasks 3, 10 and 13
  need a VM, and each says so.
- `Requires` names the tasks that must be finished first. Tasks in one wave have no dependency on
  each other and touch different files, so they can run in parallel. A wave starts when every
  task it requires is done.
- Every task that changes Python also ends with `uv run ruff check . && uv run ruff format --check core setup tools`
  passing.
- Test names are sentences (CONTRIBUTING). Desktop tests extend `DesktopGuest` in
  `core/tests/test_desktop.py`; scene tests use `FakeGuest`, `FakeSession` and `FakeVM` from
  `core/tests/test_anim.py`. No new fakes. Teach `DesktopGuest` only what the probes in
  `experiments/taskbar/README.md` saw.
- The new `Parts` constants are `STOCK_PARTS` and `BLANK_PARTS`. `scene.py` already imports a
  different `STOCK` from `base.space` (the `DesktopSpace` default, `scene.py:23`); never shadow it.
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

Task 4 moves each of the first group to `apply_desktop(guest, BLANK_PARTS)`,
`apply_desktop(guest, replace(BLANK_PARTS, pointer=True))` or `check_parts(guest, BLANK_PARTS)`,
with every assertion kept. None is dropped and no assertion is weakened.
`test_check_blank_reports_a_missing_shell` must be renamed (for example
`test_check_parts_reports_a_missing_shell`), because Task 4's grep matches its name. The
assertions `guest.visible == set()` (lines 99, 183, 196) and `guest.visible == {TASKBAR, ICONS}`
(line 205) stay exactly as written: `DesktopGuest` keeps the children's visibility in a separate
set (review fix 5).

Other callers of `blank` / `check_blank` in the repo: `core/art98/anim/scene.py` (the import on
line 25 and the call in `prepare_desktop`) and `core/tests/test_stage.py` line 124
(`desktop.blank(guest)`). Callers under `experiments/` are throwaway probes and stay as they are
(owner decision 4). `examples/` holds the owner's private, untracked working notes, never part of
the repo: no task reads, edits or checks anything under it.

## Waves

| Wave | Tasks |
| --- | --- |
| 1 | 1, 2, 3 |
| 2 | 4 |
| 3 | 5 |
| 4 | 6 |
| 5 | 7 |
| 6 | 8 |
| 7 | 9, 10, 11 |
| 8 | 12, 13 |
| 9 | 14 |

Task 1 adds only the pure resolution and its own test file, so it stands alone; Task 3 is a VM
probe under `experiments/`. Tasks 4 to 6 all edit `core/art98/desktop.py` and
`core/tests/test_desktop.py`, and Tasks 7 and 8 both edit `core/art98/anim/scene.py` and
`test_desktop.py`, so each runs in its own wave. Wave 7's tasks touch `test_desktop.py`,
`test_stage.py` and the scene API docs, one each.

## Tasks

### Wave 1

- [ ] 1. Tree resolution: `Desktop`, `Parts`, `PARENT`, `resolve_desktop`, the warning texts
  - Files: `core/art98/desktop.py`, new `core/tests/test_desktop_options.py`.
  - In `desktop.py`, with no guest call and no `warnings.warn`: the frozen `Desktop` dataclass
    (`preset="blank"`, then `KW_ONLY`, the seven options defaulting to `None`); the internal frozen
    `Parts` (seven parts and `blank_steps`); `PARENT`; `PRESETS`; `STOCK_PARTS` and `BLANK_PARTS`
    as `Parts`; `resolve_desktop(value, owner, pointer_visible) -> tuple[Parts, list[str]]`
    following design section 2, steps 1 to 6: a `str` or a `Desktop`, anything else
    `UsageError("Name.desktop 5: use one of blank, stock, or a Desktop(...)")`; an unknown preset
    with today's `check_desktop` text; `type(x) is bool` checks; base from the preset with the
    written values on top; the `PARENT` walk; the pointer rule. Override texts follow the design's
    template, name the highest off option and its source (`tray=False` or `the "blank" preset`),
    one per overridden option in table order, then the pointer warning text last, which starts
    with `Name.pointer_visible`. `blank`, `check_blank` and `DESKTOPS` are not touched yet.
  - Tests in the new file walk every case with `itertools.product` (2 presets x 3^7 options x 3
    `pointer_visible` values = 13,122) against an oracle written as explicit `UNDER` lists, not the
    implementation's `PARENT`. They cover design properties 1 to 8: a warning exactly when a
    written option sits under an off one, with the right text; no child shown under an off parent;
    an effective part is what was written unless something above is off; a warned option does
    nothing; a preset alone never warns and gives `STOCK_PARTS` or `BLANK_PARTS` apart from
    `pointer`; `pointer_visible` touches only the pointer, and its warning; resolving is pure; bad
    values `1`, `0`, `"on"`, `[]` raise `UsageError` naming the owner and the option. Plus the
    named examples: the three exact warning texts of design section 2, the pointer warning text,
    `resolve_desktop("stock", ...)[0] == STOCK_PARTS`,
    `resolve_desktop("blank", ..., None)[0] == BLANK_PARTS`, `Desktop("stock", False)` and
    `Desktop(clok=False)` raise `TypeError`, assignment raises `FrozenInstanceError`, `"foo"` and
    `5` give the `UsageError` texts with the class name.
  - Requires: none.
  - Covers: 1.1, 1.2, 1.3, 1.11, 2.3, 2.4, 2.6, 2.7, 6.1, 6.2, 6.3, 6.7, 6.8.
  - Done when: `uv run python -m pytest core/tests/test_desktop_options.py -q` passes, then `UNIT`.

- [ ] 2. Taskbar constants in `guest/win32.py`
  - Files: `core/art98/guest/win32.py`.
  - Add `WM_SIZE = 0x0005`, `TASKBAR_CLASS`, `REBAR_CLASS`, `QUICK_LAUNCH_CLASS`, `BUTTONS_CLASS`,
    `TRAY_CLASS` and `CLOCK_CLASS` with the values in design section 5, each defined once (check
    first that `WM_SIZE` is not already there, including after PR #41's merge). No other file uses
    them yet.
  - Requires: none.
  - Covers: 3.8.
  - Done when: `uv run python -m pytest core/tests/test_win32.py -q` passes, then `UNIT`.

- [ ] 3. Probe: the tray re-hide spot, and the parts after a persisted display change (needs a
  running VM)
  - Files: new `experiments/taskbar/probe_taskbar_3.py`, `experiments/taskbar/README.md` (a new
    "Third probe" section only).
  - Needs PR #41 merged, `art98 vm start` running and the prepared image. Do not run `art98 up` or
    `art98 setup`. Model it on `probe_taskbar_2.py` (attach, revert before every case, a PNG per
    step, `results.json`, CPU pressure at start and end). No source edits, no `savevm`.
  - Cases:
    1. Tray re-hide spot: hide `TrayNotifyWnd`, then call `SetSysColors` by hand and hide the
       tray (a) before `guest.sync()` and (b) after it, then `repaint_all`; read
       `IsWindowVisible(tray)` straight after and again 2 s later, and take a screenshot. Five
       runs of each.
    2. Display change with `persist=True`: hide buttons, clock and tray, then
       `set_display_mode(g, 1024, 768, 16, persist=True)` and `set_display_mode(g, 640, 480, 16,
       persist=True)`, `sync`; read each part back, and the taskbar's rect (it should sit at the
       new bottom edge). Then hide the parts again (as `prepare_desktop`'s second pass does) and
       read them back.
  - Record the tables in the README. If (a) ever loses, say so; the design already hides after
    the sync. If a part shows again after the persisted change, say so: the second
    `prepare_desktop()` in `apply_state` re-hides it, and Task 10 checks that.
  - Without a VM, report `Probe: not run (no VM)`; Tasks 6 and 10 then rely on the design's
    choice, and Task 10's gate covers it.
  - Requires: none (PR #41 merged).
  - Covers: 4.2, 4.3 (evidence for them).
  - Done when: the README has the third probe's results, or the report says why it was not run.

### Wave 2

- [ ] 4. `apply_desktop` and `check_parts` replace `blank` and `check_blank`
  - Files: `core/art98/desktop.py`, `core/tests/test_desktop.py`, `core/art98/anim/scene.py`
    (the `blank` import on line 25 and the one `blank(...)` call in `prepare_desktop` only),
    `core/tests/test_stage.py` (line 124 only).
  - **First**, before changing `desktop.py`: add `test_blank_makes_the_same_calls_in_the_same_order`
    against today's `desktop.blank(guest)`, pinning the calls that change the guest
    (`SetSysColors`, `ShowWindow`, `EnableWindow`, the `SystemParametersInfoA` set actions, the
    pointer calls, `sync`) in order, not the reads. Run it and see it pass (review fix 2).
  - Then: `shell_windows` uses `TASKBAR_CLASS`. Add `taskbar_windows(guest, taskbar)` (design
    section 3, step 2). Write `apply_desktop(guest, parts)` with steps 1 to 11 in design order,
    and `check_parts(guest, parts)` with the table of design section 4: its rows in the order
    given, today's message texts, only the parts that are off read plus the taskbar, and the lead
    chosen by `blank_steps`. Delete `blank` and `check_blank`, with no wrapper. Point the pin test
    at `apply_desktop(guest, BLANK_PARTS)` with the same expected list; it must still pass.
  - Move the existing tests (see "Existing desktop tests"), keep `syncs == 3`, and rename
    `test_check_blank_reports_a_missing_shell`. Update the `test_desktop.py` module docstring,
    which names `blank()` (review fix 12).
  - Until Task 8 wires the tree in, `prepare_desktop` calls
    `apply_desktop(self.guest, replace(BLANK_PARTS, pointer=self.pointer_visible))` for `"blank"`
    and nothing for `"stock"`, so every scene behaves as today. `scene.py` imports
    `apply_desktop` and `BLANK_PARTS` only, never a name `STOCK`. `test_stage.py` calls
    `apply_desktop(guest, BLANK_PARTS)`.
  - Extend `DesktopGuest` as design section 6 lists: `FindWindowExA` finds the rebar,
    `ToolbarWindow32`, `MSTaskSwWClass`, `TrayNotifyWnd` and `TrayClockWClass` under their
    parents; a child is visible only when it and every ancestor is; `ShowWindow(SW_HIDE)` hides a
    part; `SendMessageA(taskbar, WM_SIZE)` is recorded. The children's visibility lives in its own
    set, not in `visible`.
  - Requires: 1, 2.
  - Covers: 2.2, 3.1 to 3.3, 3.6, 3.7, 5.1.
  - Done when: `uv run python -m pytest core/tests/test_desktop.py core/tests/test_desktop_options.py -q`
    passes, `grep -rnE "check_blank|desktop\.blank|import .*\bblank\b" core tools recipes`
    finds nothing (it finds 11 lines before this task), then `UNIT`.

### Wave 3

- [ ] 5. Part-by-part apply and check tests
  - Files: `core/tests/test_desktop.py` (and `core/art98/desktop.py` only to fix what a test
    shows; name it in the report).
  - Tests: each part off on stock alone (buttons, quick launch, tray, clock, icons, pointer,
    taskbar) and one combination, each read back on `DesktopGuest`; `work_area` unchanged when only
    children are off (3.5); stock with `pointer=False` hides the pointer once (1.10); blank with
    `taskbar=True` has the taskbar visible and enabled, the work area as the guest gave it, the
    colour black, `Progman` disabled and the effects off (3.4, 3.6); the clock hide and `WM_SIZE`
    come before the other hides and the tray is hidden last (5.2); `STOCK_PARTS` makes no guest
    call (1.4, 2.1); `check_parts` does not look up a child that is on; `DesktopError` names a
    part that will not hide and a part not found, one line each, two problems give two lines, the
    lines come in design section 4's order, and the lead is "the desktop options didn't take:"
    without `blank_steps` (3.7); design property 9: for every distinct `Parts` that
    `resolve_desktop` produces, `apply_desktop` leaves `check_parts` returning `[]`, no
    `ShowWindow` goes to a child of an off parent, and applying the same `Parts` a second time
    raises nothing and leaves the same visibility (review fix 9).
  - Requires: 4.
  - Covers: 1.2 to 1.10, 3.4, 3.5, 3.7, 5.2.
  - Done when: `uv run python -m pytest core/tests/test_desktop.py -q` passes, then `UNIT`.

### Wave 4

- [ ] 6. `set_colour` keeps the tray hidden
  - Files: `core/art98/desktop.py`, `core/tests/test_desktop.py`.
  - As design section 3, "`set_colour` keeps the tray hidden": look up the tray only when the
    taskbar is visible; the icons are hidden again before the `sync`, as today; the tray is hidden
    again **after** the `sync` and before `repaint_all` (review fix 3). `set_wallpaper`,
    `backdrop.py` and `setstate.py` do not change.
  - Teach `DesktopGuest` that `SetSysColors` shows the tray again and nothing else (probe table).
  - Tests: `test_a_colour_change_keeps_the_tray_hidden` (buttons, quick launch and clock stay
    hidden too; the tray's `ShowWindow` comes after the `sync`);
    `test_a_colour_change_on_blank_adds_no_show_window` (a `Backdrop` after blank adds only one
    `IsWindowVisible(taskbar)`); `test_a_backdrop_keeps_the_tray_hidden`, through `Backdrop`.
    `test_blank_makes_the_same_calls_in_the_same_order` still passes unchanged: the three new
    reads inside `apply_desktop`'s `set_colour` are reads, which it does not pin (review fix 1).
  - Requires: 3 (its result, if it ran), 5 (both edit `test_desktop.py` and `DesktopGuest`).
  - Covers: 4.3, 4.4, 5.2.
  - Done when: `uv run python -m pytest core/tests/test_desktop.py -q` passes, then `UNIT`.

### Wave 5

- [ ] 7. `check_desktop` resolves the tree
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
  - Requires: 6.
  - Covers: 2.5, 6.8.
  - Done when: `uv run python -m pytest core/tests/test_desktop.py core/tests/test_anim.py -q`
    passes, then `UNIT`.

### Wave 6

- [ ] 8. `Scene` wiring: warnings, `prepare_desktop`, `pointer_visible`, docstrings
  - Files: `core/art98/anim/scene.py`, `core/tests/test_desktop.py`.
  - `__init_subclass__` warns inline as design section 2, "Where it runs", shows (`UserWarning`,
    `stacklevel=2`): override notes only when `desktop` is in `vars(cls)`, the pointer note when
    `desktop` or `pointer_visible` is (review fix 4). The start of `run` warns the same way when
    the instance's `__dict__` has either (review fix 11). `prepare_desktop` becomes
    `apply_desktop(self.guest, check_desktop(self)[0])` then `self.calibrate()`, replacing Task
    4's interim call.
  - Docstrings: the `Scene` docstring's `desktop` paragraph (around line 141) describes presets
    and `Desktop`, and `work_area` (around line 527) says "or the whole screen when the taskbar
    is off" (review fix 12). Check that the `lazy:` marker on `_hashes()` still reads true now that
    `desktop` can be a `Desktop`, and change its words only if it describes `desktop` as a string
    (owner's answer to open question 6).
  - Tests: `pytest.warns(UserWarning, match=...)` with the exact texts for
    `Desktop("stock", tray=False, clock=True)`, `Desktop("stock", taskbar=False, buttons=False)`
    and `Desktop("blank", buttons=False)`; the warning's `filename` is the test file; each shows
    once per class under `simplefilter("default")`; a subclass that inherits the settings does not
    warn again; a subclass of a warned scene that sets only `pointer_visible` gets no override
    warning; an instance that sets `self.desktop = Desktop("stock", tray=False, clock=True)` before
    `run` warns at `run`, with the class name; the pointer warning
    (`match="ClassName.pointer_visible"`), and none for `pointer_visible = False` on stock; no
    warning for a preset alone or for `Desktop("blank", taskbar=True, buttons=False)`; the render
    goes on after a warning and the guest has the effective parts; `"blank"` and `"stock"` strings
    behave as before; `pointer_visible = True` on blank keeps the pointer and on stock changes
    nothing; `set_state` applies the parts again after a revert (`FakeSession`); the parts are
    applied before `setup` runs.
  - Requires: 7.
  - Covers: 2.1, 2.2, 2.6, 2.7, 4.1, 4.2, 4.5, 6.1, 6.4, 6.5, 6.6, 7.2.
  - Done when: `uv run python -m pytest core/tests/test_desktop.py core/tests/test_anim.py -q`
    passes, `grep -n "lazy:" core/art98/anim/scene.py` shows the marker, then `UNIT`.

### Wave 7

- [ ] 9. State files stay as they are
  - Files: `core/tests/test_desktop.py` (tests only; no change to `state.py` or `setstate.py`).
  - Tests: a state file with a `tray` key is still rejected with "the tray comes after this
    milestone"; `get_state` on a scene with parts off writes no part fields. If `test_state.py`
    already pins the `tray` rejection, point to it in the report instead of duplicating it.
  - Requires: 8.
  - Covers: 7.1, 7.3, 7.4.
  - Done when: `uv run python -m pytest core/tests/test_desktop.py core/tests/test_state.py -q`
    passes, then `UNIT`.

- [ ] 10. VM tests in `core/tests/test_stage.py` (needs a running VM)
  - Files: `core/tests/test_stage.py`.
  - Needs PR #41 merged, `art98 vm start` running and the prepared image in `work/` (or the folder
    `ART98_TEST_WORK` names); the tests skip without it. Do not run `art98 up` or `art98 setup`.
    Mark the tests `stage` and use `with attach()` or the `booted` fixture, so the VM is released
    on failure.
  - Tests: each part hidden reads back with `IsWindowVisible` after `run`; a window opened after
    `buttons` is off gets no button; `scene.work_area` equals the stock one with only children
    off; the tray stays off after `Backdrop` (**a gate**: the feature is not done until this
    passes on the VM); the parts are applied again after `set_state`; one pass at 640x480 and one
    at 1024x768, each reaching the mode through a state file's `display` so `apply_state` runs,
    then reading the parts and the taskbar's rect back.
  - Without a VM or image, write the tests, confirm they are collected and skip
    (`uv run python -m pytest core/tests/test_stage.py -q`), and report
    `VM tests: not run (no prepared image on this machine)`. The feature then waits for a VM run
    before it ships.
  - Requires: 3, 8.
  - Covers: 1.5, 3.5, 4.2, 4.3, 8.4.
  - Done when: with a VM, `uv run python -m pytest core/tests/test_stage.py -q` passes; without
    one, the new tests skip and `UNIT` passes.

- [ ] 11. Export `Desktop`, and the scene API docs: "Desktop options"
  - Files: `core/art98/anim/__init__.py`, `docs/scenes/scene-api.md`.
  - Add `Desktop` to the imports and to `__all__` of `art98.anim`. `Parts`, `PARENT`,
    `STOCK_PARTS`, `BLANK_PARTS` and `resolve_desktop` stay internal. `test_anim_docs.py` requires
    every `__all__` name in `scene-api.md`, so the export and the docs change together in this
    task.
  - The `desktop` row of the Scene table (a preset or a `Desktop`, linking the new section) and
    the `pointer_visible` row (it maps onto `pointer`; the `Desktop` value wins, with a warning). A
    "Desktop options" subsection after the Scene table, as design section 7 lists: the level
    table, the options, the presets, the three scenes of design section 1 as whole `python`
    blocks, the override warning in a `text` block (it shows at the `class` line, or at `run` for
    a value set on an instance), what a colour change and a revert do, the errors, and what the
    probes checked on the real image (800x600 full probe; 640x480 and 1024x768 hiding and
    read-back; 1280x1024 at 16 bit not offered by the driver; a persisted display change, as Task
    3 found it, or "not yet measured" if Task 3 did not run). No "not checked: the taskbar after a
    display mode change" line. The intro line about the work area gets "unless the taskbar is
    on".
  - Requires: 8.
  - Covers: 8.1, 8.2.
  - Done when: `uv run python -c "from art98.anim import Desktop; Desktop('stock', clock=False)"`
    works, `uv run python -m pytest core/tests/test_anim_docs.py -q` passes, then `UNIT`.

### Wave 8

- [ ] 12. Glossary, design notes, CHANGELOG
  - Files: `docs/glossary.md`, `docs/design/blank-start.md`, `docs/design/decisions.md`,
    `CHANGELOG.md`.
  - Glossary: **Part**, **Preset** and **Override**. `blank-start.md`: one sentence that blank is
    now a preset and its steps are the same, and `blank(guest)` on line 29 becomes
    `apply_desktop`. `decisions.md` line 329: "as `blank()` does" becomes "as `apply_desktop`
    does". `CHANGELOG.md` under `## [Unreleased]`: the `### Added` and `### Changed` bullets of
    design section 7, word for word. Do not edit `docs/status.md`.
  - Requires: 11 (the CHANGELOG links `#desktop-options`).
  - Covers: 8.1, 8.5.
  - Done when: `git diff CHANGELOG.md` shows only the new bullets inside `[Unreleased]`,
    `grep -rnE "\bblank\(" docs/design` finds nothing, and
    `uv run python -m pytest core/tests/test_anim_docs.py -q` still passes (it checks links).

- [ ] 13. Doc samples on the real VM (needs a running VM)
  - Files: none changed (fix only what a failing sample shows, and name the file in the report).
  - With the VM running, run `uv run python tools/check_docs.py`, so the three new scenes render.
    Without a VM, report it as not run.
  - Requires: 11.
  - Covers: 8.1, 8.4.
  - Done when: `tools/check_docs.py` exits 0, or the report says it was not run and why.

### Wave 9

- [ ] 14. Final check
  - Files: none changed (fix only what a failing check shows, and name the file in the report).
  - Run `UNIT` and `uv run ruff check . && uv run ruff format --check core setup tools`. Confirm
    with `git status` that only the files named in these tasks changed; that `docs/status.md`,
    `setstate.py`, `backdrop.py`, `setup/` and `work/` are untouched; and that no temporary files
    remain. When Tasks 3, 10 or 13 could not run on a VM, the PR note line is
    `VM tests: not run (no prepared image on this machine)`, and the Backdrop gate of Task 10 is
    named as still open.
  - The report says that `Desktop` changes what a scene author sees, so the scene-author skill
    (`skills/art98/SKILL.md`, in the Hermes plugin, outside this repo) needs a follow-up. No task
    edits it (review fix 13).
  - Requires: 9, 10, 12, 13.
  - Covers: all.
  - Done when: both commands exit 0 and `git status` lists only intended files.

## Requirement coverage

| Requirement | Tasks |
| --- | --- |
| 1.1, 1.11 | 1 |
| 1.2, 1.3 | 1, 5 |
| 1.4 | 5 |
| 1.5 | 5, 10 |
| 1.6 to 1.10 | 5 |
| 2.1 | 5, 8 |
| 2.2 | 4, 8 |
| 2.3, 2.4 | 1 |
| 2.5 | 7 |
| 2.6, 2.7 | 1, 8 |
| 3.1 to 3.3, 3.6 | 4, 5 |
| 3.4 | 5 |
| 3.5 | 5, 10 |
| 3.7 | 4, 5 |
| 3.8 | 2 |
| 4.1 | 8 |
| 4.2 | 3, 8, 10 |
| 4.3 | 3, 6, 10 |
| 4.4 | 6 |
| 4.5 | 8 |
| 4.6 | none: no mid-scene action is added |
| 5.1 | 4 |
| 5.2 | 5, 6 |
| 5.3, 5.4 | every task (run time only; no prep or snapshot change) |
| 6.1 to 6.3, 6.7 | 1, 8 |
| 6.4 to 6.6 | 8 |
| 6.8 | 1, 7 |
| 7.1, 7.3, 7.4 | 9 |
| 7.2 | 8 |
| 8.1 | 11, 12, 13 |
| 8.2 | 11 |
| 8.3 | 1, 4 to 9 |
| 8.4 | 10, 13 |
| 8.5 | 12, 14 |

## Problems found while writing these tasks

None blocks the design.

1. **`examples/` is out of bounds** (corrected by Claude Code). This list first had a task edit
   `examples/inspiration/storm.py`. That folder is the owner's private, untracked working notes,
   not part of the repo, so no task touches it, and Task 4's grep leaves it out.
2. **Requirement 8.3 names `FakeVM`; the design names `DesktopGuest`.** Desktop tests use
   `DesktopGuest` in `test_desktop.py`, as the design and the existing tests do; scene tests use
   the `test_anim.py` stand-ins. Both already exist, so "no new fakes" holds.
3. **An interim `prepare_desktop`.** Deleting `blank` in Task 4 breaks `scene.py` unless its call
   moves too, so Task 4 makes a minimal change there and Task 8 replaces it. Each task stays green
   on its own.
4. **Export with the docs** (corrected by Claude Code). `test_anim_docs.py` requires every name in
   `__all__` to appear in `scene-api.md`. The first list exported in one task and documented in a
   later one, leaving `UNIT` red in between; Task 11 now does both.
5. **Shell checks** (checked by Claude Code, corrected after review). The grep in Task 4 finds 11
   lines today: `desktop.py` lines 237 and 242, `scene.py` line 25, `test_stage.py` line 124,
   and seven in `test_desktop.py` (six calls and the test name on line 162). Every path named here
   exists.
6. **Review fixes, 2026-11-20.** A second review changed this list: a probe task (3), the pin
   written against `blank` first (4), `STOCK_PARTS` / `BLANK_PARTS` (all), a separate visibility
   set in `DesktopGuest` (4), `check_parts` reading only parts that are off (4), the tray hidden
   after the sync (6), the warning rules for subclasses and instances (8), applying `Parts` twice
   (5), PR #41 first (3, 10), stale docstrings and design notes (4, 8, 12), and the skill note
   (14). The comment-only task was folded into Task 8 and the empty merged task removed, so the
   tasks are renumbered. Details are at the end of `design.md`.
