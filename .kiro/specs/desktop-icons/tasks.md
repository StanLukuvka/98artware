# Tasks: desktop icons

Requirements and design are beside this file. Facts: `experiments/desktop-icons/README.md`.
No task touches `requirements.md`, `design.md`, `docs/status.md`, `work/`, prep, the answer file,
`ready.py` or the `ready` snapshot. Nothing here runs `art98 up` or `art98 setup`.
`pyproject.toml` does not change: the converter uses only the standard library.

**Before Task 3 starts, `feat/desktop-options` is merged into the branch these tasks build on.**
It rewrites `desktop.py` and `scene.py`, which Tasks 3, 4 and 5 edit, and Task 5 reads
`Parts.icons`. Tasks 1 and 2 don't need it.

## How to read this list

- `UNIT` is the check command for every task unless it names a narrower one:

  ```bash
  uv run python -m pytest core/tests setup/tests -q --ignore=core/tests/test_stage.py --ignore=core/tests/test_stage_scenes.py --ignore=core/tests/test_qemu.py
  ```

- `Requires` names the tasks that must be done first. Tasks in one wave touch different files and
  can run in parallel.
- Every task that changes Python ends with
  `uv run ruff check . && uv run ruff format --check core setup tools` passing.
- Test names are sentences (CONTRIBUTING). Desktop tests extend `DesktopGuest` in
  `core/tests/test_desktop.py`; scene tests use `FakeGuest`, `FakeSession` and `FakeVM` from
  `core/tests/test_anim.py`. Teach the fakes only what the probes saw.
- A comment about Windows 98 behaviour cites the probe README or says it is unmeasured.
- Do not commit, push or switch branches. The owner commits.

## Waves

| Wave | Tasks |
| --- | --- |
| 1 | 1, 2 |
| 2 | 3 |
| 3 | 4 |
| 4 | 5, 6 |
| 5 | 7, 8 |
| 6 | 9 |

## Tasks

### Wave 1

#### Task 1: The image converter

Requires: none. Requirements 2.1 to 2.4. Design section 2.

- New `core/art98/guest/icons.py` with `ICON_SIZE`, `decode_image`, `ico_from_pixels` and
  `guest_icon`, as the design gives them. Every refusal is a `UsageError` (from
  `core/art98/errors.py`) that names the file (`source`) and the reason.
- New `core/tests/test_icons.py`, with the cases of design section 6. Build PNGs and ICOs in the
  test with `zlib` and `struct`; add no binary fixtures.
- Done when `uv run python -m pytest core/tests/test_icons.py -q` passes and a 24-bit output
  round-trips through `decode_image` to the same pixels.

#### Task 2: Constants and one table of guest images

Requires: none. Requirement 1.3. Design sections 1 and 3.

- In `core/art98/guest/win32.py`: the `LVM_*`, `SHCNE_*`, `SHCNF_*`, `FILE_ATTRIBUTE_*`
  constants of design section 3, `DESKTOP_FOLDER`, `ICON_TIMEOUT = 5.0`,
  `SHELL_ICONS` (moved from `Dialog.CUSTOM_ICONS` with its comment), and `NO_ICON`,
  `NOT_ICON_FILE` (moved from `dialog.py`). Check `VA_SHARED` and `SW_SHOW` aren't there already
  before adding them.
- `dialog.py` imports them; `Dialog.CUSTOM_ICONS = SHELL_ICONS` stays as the public name.
- Done when `UNIT` passes, including `test_win32.py` (no constant defined twice) and
  `test_dialog.py` unchanged.

### Wave 2

#### Task 3: The guest functions

Requires: 2, and `feat/desktop-options` merged. Requirements 1.4, 1.5, 5.5. Design section 3.

- In `core/art98/desktop.py`: `desktop_items`, `make_icon_folder`, `remove_icon_folder`,
  `place_item`, `delete_items`, and a `check_guest_image(guest, file, index)`
  that raises `UsageError` (ExtractIconA, then DestroyIcon).
- The shared-memory block is allocated and freed in each function, in a `finally`.
- The notice sent is `SHCNE_MKDIR` or `SHCNE_RMDIR` only, with a comment citing the README on why
  never `SHCNE_UPDATEDIR`.
- Tests in a new `core/tests/test_desktop_icon.py`: teach `DesktopGuest` a desktop list (labels,
  positions, indices that change on delete, a label listed in other capitals), the file calls and
  `SHChangeNotify` (any event other than MKDIR and RMDIR fails the test). Cover each function,
  including a missing label, a lookup ignoring case, and a guest file with no icon.
- Done when `UNIT` passes.

### Wave 3

#### Task 4: The `DesktopIcon` prop

Requires: 1, 3. Requirements 1, 2, 3, 4, 7. Design sections 1 and 4.

- New `core/art98/actions/desktop_icon.py` with `DesktopIcon` and `label_problem` placed in
  `core/art98/state.py` beside `id_problem` (the state loader in Task 6 uses it).
- Export it from `core/art98/actions/__init__.py` and add it to `__all__` in
  `core/art98/anim/__init__.py`.
- `core/art98/anim/scene.py`: `remove` sends a `Win` through `Close` as today, and for any other
  prop checks it is on stage and calls `prop.remove()`; `add` records `source` for any prop that
  has one; `_icon_images`, cleared in `_reset`.
- `one_frame_moves` on `Box` (`False`) and `DesktopIcon` (`True`); `MoveAlongPath.begin` refuses
  such a target (`core/art98/base/animation.py`).
- In this task the stock icons are always treated as on (the stock preset). Task 5 adds the
  blank case.
- Tests in `core/tests/test_desktop_icon.py`: the prop cases of design section 6 that don't need
  the blank desktop, plus `Close(icon)` refused and `remove` of an icon not on stage refused.
- Done when `UNIT` passes.

### Wave 4

#### Task 5: Fake icons when the stock icons are off

Requires: 4, and `feat/desktop-options` merged. Requirement 5. Design section 3, "The stock icons
when the options have them off".

- `Scene._icon_list_shown` and `Scene._deleted_stock`, cleared in `_reset`. `DesktopIcon.attach`
  and `remove` follow the design's steps when the scene's resolved parts have `icons` off.
- Tests: on `Desktop("blank")` the first icon deletes every non-fake item and shows the list;
  a second icon deletes nothing more; a deleted stock label is refused; removing the last hides
  the list; on `"stock"` and on `Desktop("blank", icons=True)` nothing is deleted and the list is
  never hidden; `check_parts` is unchanged.
- Done when `UNIT` passes.

#### Task 6: Icons in a state file

Requires: 4. Requirement 6.1, 6.2. Design section 5, "The schema".

- `core/art98/state.py`: `IconState`, `DesktopState.icons`, `icons` out of `LATER_DESKTOP` and
  into `DESKTOP_FIELDS`, the loader checks, `State.files()`, `_ORDER`, and `dump_state` walking
  `desktop.icons` and each `image`. Ids are unique across icons and windows.
- Tests in `core/tests/test_state.py`: a good state loads; each problem is reported at its path,
  all at once; a dump reads back the same. Update the two tests that expected "desktop.icons:
  not supported yet" (`test_state.py:131`, `test_wallpaper_state.py:98`):
  `icons` now loads, `tray` still says later.
- Done when `UNIT` passes.

### Wave 5

#### Task 7: Apply, check and capture icons

Requires: 5, 6. Requirements 6.3 to 6.7. Design section 5.

- `core/art98/anim/setstate.py`: `apply_state` adds the icons after the wallpaper and before the
  windows; `check_state` gets `icon_problems`; `wallpaper_sample` keeps clear of icon cells.
- `core/art98/anim/scene.py` `get_state`: captures icons (id needed), `DesktopIcon.to_state`
  writes a provided image under `files/desktop/icons/`.
- Tests with the scene fakes: apply then check a state with both image kinds; a missing or moved
  icon is reported; a wallpaper sample point under an icon is skipped; a capture holds the icons,
  copies the image and loads back; an icon with no id raises; an edited image makes a capture
  stale.
- Done when `UNIT` passes.

#### Task 8: Docs

Requires: 5, 6. Requirement 8.1. Design section 7.

- Each doc of design section 7. The scene-api sample must be a scene the docs check can render
  (`tools/check_docs.py`), with its image as a PNG built by the sample or kept small under
  `docs/assets/`.
- The CHANGELOG Added bullet names `DesktopIcon` and `desktop.icons`.
- Done when `uv run python -m pytest core/tests/test_anim_docs.py -q`
  passes and every public name is documented.

### Wave 6

#### Task 9: VM tests and the final check

Requires: 7, 8. Requirement 8.2. Design section 6, the VM tests.

- Add the VM tests of design section 6 to `core/tests/test_stage.py`. Start the VM with
  `art98 vm start` (`. .tools/env.sh` for host QEMU). Note `/proc/pressure/cpu` beside any timing.
- Run `shortcut r . docs-check` for the new sample.
- Run `UNIT`, the lint line, and the `lad:debt` scan: no `lazy:` marker added without an upgrade path, no
  `FLOW-PRODUCED` marker left after the final review.
- The report says the scene-author skill (`skills/art98/SKILL.md`, Hermes plugin) needs a
  follow-up for `DesktopIcon`.

## Requirement coverage

| Requirement | Tasks |
| --- | --- |
| 1 Guest image | 2, 3, 4, 9 |
| 2 Provided image | 1, 4, 9 |
| 3 Placing | 4, 9 |
| 4 Labels | 4, 6 |
| 5 Desktop options | 3, 5, 9 |
| 6 States and sections | 6, 7, 9 |
| 7 Same frames | 4, 7 |
| 8 Docs and tests | 8, 9 |
