# Requirements: one form of desktop, and searchable names

## Introduction

Two pieces of tech debt, cleared before new features (desktop icons, release 0.3.0):

1. **The desktop has an old form and a new one.** `desktop = "stock"` and `pointer_visible` are the
   0.2.0 form, kept alive beside `Desktop`. The desktop is also resolved again on every prepare, so
   the scene's value and the guest can disagree.
2. **Variable names lose their idea.** The same thing changes name between functions (`desktop`,
   `value`, `effective`, `parts`), and one name means several things (`desktop` is the option, a
   state's part and the Progman window).

Part 1 comes first: it removes variables Part 2 would otherwise rename.

### Source facts (dev at `577494f`)

- `resolve_desktop(value, ...)` takes a `str` or a `Desktop`. The strings it accepts are `"blank"`
  and `"stock"`. 13 recipe scenes write a string; 1 writes `pointer_visible`.
- `check_desktop` runs at class definition, at the start of `run` and in every `prepare_desktop`.
  Only the last result's parts are used; the other two give warnings.
- `self.desktop` can be set at any time. `prepare_desktop` runs again when a state changes the
  display mode (`setstate.py:72`) and would pick up the new value, without `run`'s warnings.
- `apply_desktop` only hides parts. Going to stock returns early and checks nothing.
- `test_space.py:223` calls `prepare_desktop` on a scene outside `run`.
- `RETIRED` in `scene.py` refuses a removed `Scene` class attribute with a message. It is empty.
- The changelog's Unreleased section already says 0.2.0 scenes need edits.
- `core/art98` and `setup/` (with its tests) have 787 functions in 62 files. The most
  shared parameter names: `path` 46 functions, `guest` 38, `name` 34, `scene` 21, `timeout` 21,
  `data` 17, `hwnd` 17, `value` 12, `size` 12.

## Part 1: one form of desktop

### Requirement 1: a scene's desktop is a `Desktop`

1. `Scene.desktop` SHALL be `Desktop()` by default, which is the blank preset.
2. WHEN a scene class or instance has a `desktop` that is not a `Desktop`, art98 SHALL raise
   `UsageError` where it does today (class definition, or `run` for an instance).
3. WHEN that value is a known preset's name, the message SHALL say what to write:
   `MyScene.desktop = "stock": write Desktop("stock")`. It SHALL NOT be converted.
4. `resolve_desktop` SHALL accept only a `Desktop`.

### Requirement 2: `pointer_visible` is gone

1. WHEN a scene class sets `pointer_visible`, art98 SHALL raise `UsageError` through `RETIRED`,
   naming `Desktop(pointer=...)`.
2. WHEN a scene instance sets it, `run` SHALL raise the same error.
3. The pointer SHALL come only from the `Desktop` and its preset. Blank hides it; stock shows it.
4. The warnings about the two disagreeing SHALL be removed.

### Requirement 3: the desktop is resolved once per run

1. `run` SHALL resolve the desktop once, before any guest call, and every `prepare_desktop` in that
   run SHALL use that result.
2. IF `self.desktop` is not equal to the resolved one when `prepare_desktop` runs, art98 SHALL raise
   `UsageError` saying the desktop can't change during a run.
3. A second `run` of the same scene object SHALL resolve again.
4. The check at class definition SHALL stay, and each warning SHALL appear as often as today.
5. `prepare_desktop` outside a run SHALL still work (`test_space.py`).

### Requirement 4: nothing on screen changes

1. For each desktop a 0.2.0 scene could write, the new form SHALL make the same guest calls in the
   same order.
2. Recipes, tests and current docs SHALL use the new form. Experiments, `.kiro/specs/` of finished
   work and `docs/archive/` SHALL keep the old one as records.

## Part 2: names

### Requirement 5: the rules are in the repo

1. `CONTRIBUTING.md` SHALL hold the naming rules, scopes and exemptions, and `AGENTS.md` SHALL link
   to them.
2. A base list SHALL give every tracked base and its meaning. It SHALL NOT be in user docs.
3. Each commit that adds, renames or removes a base SHALL update the list.

### Requirement 6: tracked variables follow the rules

1. Every tracked variable in `core/art98` SHALL be named `<scope>_<base>`, by the rules in the
   design.
2. A base SHALL mean one idea and keep its whole name in every scope.
3. Public names, parameters a caller can pass by keyword in a public API, dataclass fields, loop
   variables, names fixed by outside code and test variables SHALL stay bare.
4. No behaviour and no message text SHALL change in Part 2.

### Requirement 7: the rename is complete and stays so

1. A unit test SHALL fail when a variable ends in a listed base and isn't named for its scope.
2. WHEN a module is renamed, every value that crosses a function boundary in it SHALL be either on
   the base list or recorded as left alone, with the reason.

## Out of scope

- The Australian English spelling pass. New names use it; old ones wait for their own pass.
- Renaming public names, other than Part 1's removals.
- `setup/art98_setup/`, until the owner agrees: its code makes prep and the `ready` snapshot.
- Tests' variables, `experiments/`, `recipes/`, `guest/` (C) and `tools/`.
- The Hermes scene-author skill. It needs a follow-up outside this repo, because Part 1 changes what
  scene authors write.
