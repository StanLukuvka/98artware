# Tasks: state file hashing

Design approved 2026-11-18, with its "Owner decisions on the design". No task touches
`requirements.md`, `design.md`, `docs/status.md`, `work/`, or the VM. Nothing here runs
`art98 up` or `art98 setup`.

## How to read this list

- `UNIT` is the check command for every task unless it names a narrower one:

  ```bash
  uv run python -m pytest core/tests setup/tests -q --ignore=core/tests/test_stage.py --ignore=core/tests/test_stage_scenes.py --ignore=core/tests/test_qemu.py
  ```

  A narrower form is `uv run python -m pytest core/tests/<file> -q`. No task needs a VM.
- `Requires` names the tasks that must be finished first. Tasks in one wave have no dependency on
  each other and touch different files, so they can run in parallel. A wave starts when every
  task it requires is done.
- Every task that changes Python also ends with `uv run ruff check . && uv run ruff format --check core setup tools`
  passing.
- Test names are sentences (CONTRIBUTING). Tests extend the helpers already in
  `core/tests/test_anim.py` (see "Existing section tests" below). No new fakes.
- Do not commit, push or switch branches (AGENTS.md "Git safety") unless the owner asks.

## Existing section tests (read before writing tests)

All in `core/tests/test_anim.py`, under the heading `# ---- sections and no revert after boot ----`:

- `three_sections(guest, tmp_path, monkeypatch, calls)` builds `Three`, a scene of sections `one`,
  `two`, `three` around one `Picture` (id `flower`) whose file is `tmp_path / "flower.bmp"`.
  `Three` is defined in `test_anim.py`, so `_scene_dir()` is `core/tests`, and `flower.bmp` is
  **outside** the scene folder: its record is absolute.
- `run_sections(scene_class, caps, guest, only=None)` runs a full or solo render. `full_run(...)`
  is a full run with the captures swapped in (`render_module.swap_captures`).
- Tests to **extend, not duplicate**:
  - `test_a_full_run_cuts_and_captures_at_each_later_boundary` already reads `03-three.meta.json`
    and checks `meta["time"]` and `sorted(meta["hashes"])`. New meta assertions (`files`,
    `capture`) go in this test or a sibling that reuses `full_run`.
  - `test_a_capture_made_before_a_method_changed_is_refused_naming_it` is parametrized over
    `(key, value, changed)` and edits `meta["hashes"]`. The 2.7 cases stay as they are. The new
    stale cases get their own parametrized sibling in the same style (edit a file or the meta,
    `pytest.raises(UsageError, match=...)`, `assert calls == []`).
  - `test_a_later_section_with_no_capture_says_to_render_the_whole_scene_first` is the pattern for
    the 3.2 `MissingFile` cases.
  - `test_a_solo_run_of_a_later_section_calls_only_its_method` is the pattern for "every hash
    matches, the section plays" (2.6).
- Needed once, because relative records need a scene file inside `tmp_path`: a small helper in
  `test_anim.py`, `scene_file_in(tmp_path, ...)`, that writes a scene `.py` file and loads it the way
  `test_cli_scene_named_like_a_stdlib_module_finds_its_own_file` does (`art98.cli._load_scene`).
  It is a loader for a real scene file, not a fake guest. It is created in Task 4 and reused later.
- `core/tests/test_state.py` has `bmp(...)` and `load_state` tests; `test_picture.py` has
  `GuestWithFiles`; `test_notepad.py` has `NotepadGuest`.

## Waves

| Wave | Tasks |
| --- | --- |
| 1 | 1, 2, 3, 4, 14, 15 |
| 2 | 5, 6, 7 |
| 3 | 8 |
| 4 | 9 |
| 5 | 10 |
| 6 | 11 |
| 7 | 12 |
| 8 | 13 |
| 9 | 16 |

Tasks 8 to 13 all edit `core/art98/anim/scene.py` and `core/tests/test_anim.py`, so they run one
per wave. Wave 1 and 2 are where parallel work happens.

## Tasks

### Wave 1

- [ ] 1. Add Hypothesis to the dev group
  - Files: `pyproject.toml`, `uv.lock`.
  - Add `hypothesis` to `[dependency-groups] dev` only. `dependencies = []` stays empty.
  - Run `uv lock` then `uv sync` so `uv.lock` matches (needs network for the package; if there is
    none, say so in the report and leave `uv.lock` for the owner).
  - Requires: none.
  - Covers: 5.2 (property tests), owner decision 2.
  - Done when: `uv run python -c "import hypothesis"` works, `git diff pyproject.toml` shows
    one added dev entry and no change under `[project]`, and `UNIT` still passes.

- [ ] 2. `State` learns its own sha256 and lists its files
  - Files: `core/art98/state.py`, `core/tests/test_state.py`.
  - `State.sha256: str = ""` (last field). `load_state` reads bytes once, hashes, decodes `utf-8`,
    keeps the `UnicodeDecodeError` and `JSONDecodeError` handling, returns
    `dataclasses.replace(state, sha256=digest)`. `dump_state` returns `load_state(path)` so
    `get_state` gets a `State` with `sha256` set. `State.files() -> tuple[FileRef, ...]`:
    wallpaper first, then each window in list order, `open` before `text`. `VERSION` and the file
    format do not change.
  - Tests (in `test_state.py`, next to the existing `load_state` tests):
    `test_a_loaded_state_carries_the_sha256_of_its_bytes`,
    `test_a_state_lists_its_files_wallpaper_then_windows_open_before_text`,
    `test_dump_state_returns_a_state_with_its_sha256`,
    `test_the_state_file_format_and_version_are_unchanged` (no new key in a dumped file).
  - Requires: none.
  - Covers: 1.2, 1.3, 1.11 (the `sha256` source), 4.3.
  - Done when: `uv run python -m pytest core/tests/test_state.py -q` passes, then `UNIT`.

- [ ] 3. `Picture` keeps its source and accepts checked bytes
  - Files: `core/art98/actions/programs/picture.py`, `core/tests/test_picture.py`.
  - After `read_host_file`, set `self.source = (self.image.resolve(), data)`, the same object as
    `_image_data`. Add private keyword-only `_data: bytes | None = None`: when given it replaces
    `read_host_file(path)`; the path still names the file and the title. Do not add it to any
    public docs.
  - Tests (`GuestWithFiles`): `test_a_picture_remembers_the_file_and_bytes_it_was_built_from`,
    `test_a_picture_given_checked_bytes_does_not_read_the_file` (delete the file, build with
    `_data`, assert it works and `source[1] is` the bytes given).
  - Requires: none.
  - Covers: 1.4, 1.5, 4a.1 (constructor half).
  - Done when: `uv run python -m pytest core/tests/test_picture.py -q` passes.

- [ ] 4. `Notepad` keeps its raw source and accepts checked bytes
  - Files: `core/art98/actions/programs/notepad.py`, `core/tests/test_notepad.py`.
  - Keep the raw bytes before `check_text`; set `self.source = (self.open_file.resolve(), raw)`.
    `_file_data` stays the converted bytes. Same private `_data` keyword as Task 3.
  - Tests (`NotepadGuest`): `test_the_notepad_source_is_the_raw_bytes_not_the_crlf_ones` (a file
    with `\n` line ends: `source[1]` has `\n`, `_file_data` has `\r\n`),
    `test_a_notepad_given_checked_bytes_does_not_read_the_file`.
  - Requires: none.
  - Covers: 1.4, 1.5, 4a.1 (constructor half).
  - Done when: `uv run python -m pytest core/tests/test_notepad.py -q` passes.

- [ ] 14. Document what makes a capture stale
  - Files: `docs/scenes/scene-api.md` ("Sections" only).
  - List what makes a capture stale: the scene's `state` file, files it points at, `set_state`
    files and what they point at, `Picture(image=)`, `Notepad(open=)`, the capture's own
    `NN-name.state.json`, `setup()` and the source of earlier section methods. Say that files a
    scene reads with its own `open()`, helper code, `recipes/helpers/` modules and class attributes
    are not tracked, and that there is no way to declare them. Say a capture from an older art98
    must be rendered again. Any new code sample is a `text` or `bash` block, or a whole scene
    (`test_anim_docs.py`).
  - Requires: none.
  - Covers: 5.3.
  - Done when: `uv run python -m pytest core/tests/test_anim_docs.py -q` passes, and the "Sections"
    text names each item above.

- [ ] 15. CHANGELOG note
  - Files: `CHANGELOG.md`.
  - Under `## [Unreleased]`, in `### Changed` (after the existing `Scene.remove` bullet): a capture
    now goes stale when any host file it was built from changes, naming that file; a capture
    written by an earlier build has no file records and must be rendered again (breaking). Link
    `docs/scenes/scene-api.md#sections`. Under `### Added`, a bullet is not needed. Do not edit
    `docs/status.md`.
  - Requires: none.
  - Covers: 5.3, owner decision 5.
  - Done when: `git diff CHANGELOG.md` shows only the new bullet(s) inside `[Unreleased]`, and
    `uv run python -m pytest core/tests/test_anim_docs.py -q` still passes (it checks links).

### Wave 2

- [ ] 5. `Win.source` and `from_state` hand over the checked bytes
  - Files: `core/art98/actions/window/win.py`,
    `core/tests/test_picture.py`, `core/tests/test_notepad.py`.
  - Add class attribute `source: tuple[Path, bytes] | None = None`. `Win.from_state` passes
    `_data=window.open.data` along with `cls.open_keyword`.
  - Tests, one per file: `test_a_file_that_changes_after_the_check_is_not_read_again` for
    `Picture.from_state` and for `Notepad.from_state` (build `window` from `load_state`, overwrite
    the file, call `from_state`, assert the prop holds the checked bytes and `source[1]` hashes to
    the state's recorded sha256).
  - Requires: 3, 4.
  - Covers: 4a.1, 4a.2, 4a.3.
  - Done when: `uv run python -m pytest core/tests/test_picture.py core/tests/test_notepad.py core/tests/test_state.py -q` passes, then `UNIT`.

- [ ] 6. Property test: `State.files()`
  - Files: `core/tests/test_state.py` (appended; Task 2 finished, so no clash).
  - Hypothesis test for design property 6: for generated states, every `FileRef` the reader
    produced appears once, wallpaper first, then windows in list order with `open` before `text`.
  - Requires: 1, 2.
  - Covers: 1.2, 1.3, 5.2.
  - Done when: `uv run python -m pytest core/tests/test_state.py -q` passes; the test imports
    `hypothesis` only inside the test module.

- [ ] 7. Scene path helpers and the recorded-files dict
  - Files: `core/art98/anim/scene.py`, `core/tests/test_anim.py`,
    new `core/tests/test_scene_deps_properties.py`.
  - Add `Scene._deps: dict[str, str]`, reset in `run()` next to `self._earlier = []`;
    `_scene_dir()`, `_recorded_path()`, `_resolve_recorded()`, `_depend()` and `_depend_state()`
    exactly as in the design. `_find_state` calls `_scene_dir()`. `_resolve_recorded` treats a
    relative record with `..`, an empty string or a backslash as malformed (raises the `MissingFile`
    the solo check will use; wire the exception when Task 11 calls it). Nothing calls
    `_depend` yet.
  - Add `scene_file_in(tmp_path, ...)` to `test_anim.py` (see "Existing section tests").
  - Tests in `test_anim.py`: `test_a_file_outside_the_scene_folder_is_recorded_absolute`,
    `test_a_dotdot_path_is_recorded_relative`,
    `test_a_symlink_into_the_folder_is_recorded_relative` (skip when symlinks are refused),
    `test_a_record_uses_forward_slashes`, `test_a_file_used_twice_is_recorded_once`,
    `test_a_scene_with_no_file_records_absolute_paths`.
  - Hypothesis tests in the new file: property 1 (record round trip, moved folder gives the same
    string, outside path is absolute and resolves to itself) and property 5 (once only,
    first-seen order).
  - Requires: 1.
  - Covers: 1.6, 1.9, 1.10, 2.5 (order source).
  - Done when: `uv run python -m pytest core/tests/test_anim.py core/tests/test_scene_deps_properties.py -q` passes, then `UNIT`.

### Wave 3

- [ ] 8. Record dependencies at the three points
  - Files: `core/art98/anim/scene.py`, `core/tests/test_anim.py`.
  - `Scene._set_state` calls `_depend_state(state)` after `load_state` succeeds (covers the scene
    `state` from `_begin` and `set_state`). `Scene.add` records a newly added `Win` whose `source`
    is set, hashing `source[1]` with `hashlib.sha256`; a prop built outside `run` is recorded when
    added.
  - Tests (inspect `scene._deps` after the run, using `three_sections` or a state-based variant of
    it): `test_the_scene_state_file_and_the_files_it_points_at_are_recorded` (1.2),
    `test_a_set_state_file_and_its_files_are_recorded` (1.3),
    `test_a_picture_and_a_notepad_file_are_recorded` (1.4),
    `test_a_prop_built_at_import_is_recorded_when_added` (1.4),
    `test_the_notepad_hash_is_of_the_raw_bytes_not_the_crlf_ones` (1.5),
    `test_a_wrong_sha_in_a_state_raises_state_error_and_records_nothing` (1.7).
  - Requires: 2, 5, 7.
  - Covers: 1.2 to 1.7.
  - Done when: `uv run python -m pytest core/tests/test_anim.py -q` passes, then `UNIT`.

### Wave 4

- [ ] 9. Write `files` and `capture` into the meta file
  - Files: `core/art98/anim/scene.py`, `core/tests/test_anim.py`.
  - `_capture` uses the `State` that `get_state` returns for `capture`, and writes
    `files` as a list of `{"path", "sha256"}` in `_deps` order, with `sort_keys=True`. Frames,
    clips and the capture state file writers do not change.
  - Tests: extend `test_a_full_run_cuts_and_captures_at_each_later_boundary` with
    `meta["capture"]` equal to the sha256 of `03-three.state.json` and a `files` list that holds the
    picture's absolute path with its sha256 (1.1, 1.11);
    `test_two_full_runs_write_the_same_meta_bytes` (1.8);
    `test_a_wrong_sha_in_a_state_writes_no_capture` (1.7, extends the pattern of
    `test_a_capture_the_state_cant_hold_stops_the_full_run_with_nothing_swapped_in`);
    `test_the_capture_state_file_is_the_bytes_get_state_wrote` (4.1, 4.3: no new key, `VERSION` 1,
    file bytes equal `dump_state` output).
  - Requires: 8.
  - Covers: 1.1, 1.7, 1.8, 1.11, 4.1, 4.3.
  - Done when: `uv run python -m pytest core/tests/test_anim.py -q` passes, then `UNIT`.

### Wave 5

- [ ] 10. Solo check, part 1: read and validate the meta file; check the capture's own file
  - Files: `core/art98/anim/scene.py`, `core/tests/test_anim.py`.
  - Move the meta parsing of `_start_from_capture` into one private function (for example
    `_read_meta`) that returns `(time, hashes, capture, files)`, so Task 13 can test it without a
    scene. Order as in the design: unreadable or wrong `time`/`hashes` gives the existing
    `MissingFile`; no `files` and no `capture` gives the old-meta `UsageError`; a malformed record
    gives the same `MissingFile`. Add `_stale(name, what, how="changed")`; the existing
    `raise UsageError(...)` becomes `raise _stale(name, changed)` with the message text unchanged.
    After the existing hashes, compare `capture` with the sha256 of `NN-name.state.json`.
  - Tests: `test_an_old_meta_file_says_to_render_again` (3.1, strip `files` and `capture` from a real
    meta), `test_a_malformed_files_record_is_no_capture` (3.2, parametrized: not a list, entry
    without `sha256`, extra key, duplicate path, `..` path, bad `capture`),
    `test_a_hand_edited_capture_state_file_is_stale_even_with_matching_hashes` (1.11; edit the
    file and the `sha256` fields it names), and the unchanged
    `test_a_capture_made_before_a_method_changed_is_refused_naming_it` still passes (2.7).
  - Requires: 9.
  - Covers: 1.11, 2.7, 3.1, 3.2.
  - Done when: `uv run python -m pytest core/tests/test_anim.py -q` passes, then `UNIT`.

### Wave 6

- [ ] 11. Solo check, part 2: dependency files
  - Files: `core/art98/anim/scene.py`, `core/tests/test_anim.py`.
  - After the capture check, hash each `files` entry in recorded order with `_resolve_recorded`.
    `OSError` gives `_stale(name, path, "was moved or deleted")`; a different sha256 gives
    `_stale(name, path)`. Then `_set_state` and `_time_offset` as before. All of it before any guest
    call.
  - Tests, each for the four sources (scene `state` pointed-at file, `set_state` file, a file a
    state points at, a prop's file; parametrize over a three-section scene built with
    `scene_file_in`): `test_a_changed_<source>_makes_a_later_section_stale` (2.2),
    `test_a_missing_<source>_says_moved_or_deleted` (2.3),
    `test_unchanged_files_leave_the_capture_fresh` (2.6, the section plays like
    `test_a_solo_run_of_a_later_section_calls_only_its_method`),
    `test_a_file_a_state_points_at_changed_without_its_sha_is_stale_in_section_two` (2.4, and a solo
    run of section 1 still raises `StateError`), `test_the_stale_messages_match_exactly`
    (2.2, 2.3, full text from the design's table),
    `test_a_moved_project_keeps_its_captures_fresh` (1.10, copy the scene folder with
    `shutil.copytree`, solo run there),
    `test_the_solo_check_makes_no_guest_call_before_it_passes` (2.1, 4.2: `guest.calls` is empty
    when the error is raised).
  - Requires: 10.
  - Covers: 1.10, 2.1 to 2.4, 2.6, 4.2.
  - Done when: `uv run python -m pytest core/tests/test_anim.py -q` passes, then `UNIT`.

### Wave 7

- [ ] 12. Fixed order of the checks, and the property tests on the check
  - Files: `core/tests/test_anim.py`, new `core/tests/test_meta_properties.py`. No change to
    `scene.py`; if a test shows the order is wrong, fix `scene.py` in this task and say so in the
    report.
  - `test_one_change_is_named_in_a_fixed_order` (2.5): change several items at once and assert the
    named one is `setup`, then `state`, sections in run order, the capture's own state file, then
    dependency files in recording order. Peel items off one at a time to walk the whole order.
  - Hypothesis tests in the new file, against `_read_meta` and the dependency loop with `tmp_path`
    files: property 2 (meta round trip and same bytes), property 3 (malformed never crashes: only
    `MissingFile` or the old-meta `UsageError`), property 4 (first change wins, with the "changed"
    or "was moved or deleted" wording per file, against a three-line model).
  - Requires: 11.
  - Covers: 2.5, 3.1, 3.2, 1.8, 5.2.
  - Done when: `uv run python -m pytest core/tests/test_anim.py core/tests/test_meta_properties.py -q` passes, then `UNIT`.

### Wave 8

- [ ] 13. Replace the `lazy:` marker on `_hashes()`
  - Files: `core/art98/anim/scene.py`.
  - Remove "the files a state file points at aren't hashed" and its `lazy:` line from `_hashes()`'s
    docstring. Add the design's `lazy:` comment: source called from section methods (helpers,
    `recipes/helpers/` modules), Scene class attributes (`desktop`, `pointer_visible`,
    `strict_placement`) and files a scene reads with its own `open()` are not tracked, with the
    upgrade path ("hash what the sections call, or declare extra dependencies"). Keep it true:
    the words must match what Tasks 8 to 11 built.
  - Requires: 12.
  - Covers: 5.1.
  - Done when: `grep -n "lazy:" core/art98/anim/scene.py` shows the new marker and no text saying
    state-pointed files are unhashed; `UNIT` passes.

### Wave 9

- [ ] 16. Final check
  - Files: none changed (fix only what a failing check shows, and name the file in the report).
  - Run `UNIT`, `uv run ruff check . && uv run ruff format --check core setup tools`, and confirm
    with `git status` that only the files named in these tasks changed, `work/` is untouched, and
    no temporary files remain. Confirm the PR note line:
    `VM tests: not run (no prepared image on this machine)`.
  - Requires: 13, 14, 15.
  - Covers: 5.2, all.
  - Done when: both commands exit 0 and `git status` lists only intended files.

## Requirement coverage

| Requirement | Tasks |
| --- | --- |
| 1.1 | 9 |
| 1.2, 1.3 | 2, 6, 8 |
| 1.4, 1.5 | 3, 4, 8 |
| 1.6 | 7 |
| 1.7 | 8, 9 |
| 1.8 | 9, 12 |
| 1.9, 1.10 | 7, 11 |
| 1.11 | 2, 9, 10 |
| 2.1 to 2.4, 2.6 | 11 |
| 2.5 | 7, 12 |
| 2.7 | 10 |
| 3.1, 3.2 | 10, 12 |
| 4.1, 4.3 | 2, 9 |
| 4.2 | 11 |
| 4a.1 to 4a.3 | 3, 4, 5 |
| 5.1 | 13 |
| 5.2 | 1, 6, 7, 12, 16 |
| 5.3 | 14, 15 |

## Problems found while writing these tasks

None blocks the design. Three places where the tasks go slightly past or around it:

1. **Meta parsing has no pure function in the design.** Properties 2 to 4 need one. Task 10 splits
   `_read_meta` out of `_start_from_capture` as an implementation detail of design step 1. If the
   owner wants no new private function, those properties go through `_start_from_capture` with
   temp scene files, which is slower.
2. **The existing helper puts the Picture outside the scene folder.** `three_sections` defines
   `Three` in `test_anim.py`, so its `flower.bmp` is recorded absolute, and no existing test can
   show a relative record or a moved project. Task 7 adds `scene_file_in`. The design's Testing
   section already says tests need a real scene file; it just does not name this gap.
3. **The design's wave-ordering of properties.** Hypothesis is not importable until Task 1 is
   done, so property tests are separate tasks (6, 7, 12) after Task 1 rather than part of the
   task that writes the code.

Also: the design could not locate the 0.3.0 note. It is `CHANGELOG.md` `## [Unreleased]`
(owner decision 5), and Task 15 uses it. File paths for `Win`, `Picture` and `Notepad` in Tasks 3
to 5 are from the AGENTS.md map and need a `grep` to confirm.
