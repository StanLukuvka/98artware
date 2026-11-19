# Design: state file hashing

Status: draft for the design checkpoint. Requirements approved 2026-11-18. No code is changed by
this document.

## Overview

A capture's meta file gains two records. `files` lists every dependency file with its sha256, in
the order it was first recorded. `capture` holds the sha256 of the capture's own
`NN-name.state.json`. A full run collects dependency files as they are read; a solo run
re-hashes them before it touches the guest and names the first one that differs.

Everything extends code that exists. No new module, class or exception. The pieces:

- `state.py`: `State` learns the sha256 of its own bytes and lists the files it points at.
- `Win` and the two state apps: a prop remembers the host file it was built from, and
  `from_state` hands over the bytes `load_state` already checked (Requirement 4a).
- `scene.py`: a dict of recorded files, three recording points, the meta writer, and the solo
  check.

Nothing is added to the guest protocol, the capture state file, or the frames (4.1 to 4.3).

## Current code this design rests on

(Read from the tree; the shell was unavailable during this session, so `grep` over
`core/tests/test_anim.py` for the existing section tests was not possible. See "Testing".)

- `Scene._hashes()` returns `setup`, `state` and `section <name>` hashes. It re-reads the scene's
  state file by `_find_state`.
- `Scene._capture()` calls `get_state`, then writes `{"time", "hashes"}` with
  `sort_keys=True`.
- `Scene._start_from_capture()` compares `_hashes()` to the recorded hashes in `now`'s key
  order, then calls `_set_state(capture)`.
- `Scene._set_state()` is the one place a state file is loaded: `_begin` (scene `state`),
  `set_state`, and the solo start. `load_state` has already verified each file's `sha256`.
- `_Reader.file` reads each pointed-at file once and returns `FileRef(path, sha256, data)` with
  `path` resolved.
- `Win.from_state` rebuilds the prop with `cls(title, at=, size=, <open_keyword>=window.open.path)`,
  so the constructor reads the file again (the double read of 4a).
- `Picture.__init__` keeps `_image_data`. `Notepad.__init__` keeps only `_file_data`, which is
  after `check_text`'s line-end fix, so the raw bytes are gone (1.5).

## Data

### Recorded files: `Scene._deps`

`self._deps: dict[str, str]` maps a recorded path to a sha256. It is reset in `run()` next to
`self._earlier = []`. Python dicts keep insertion order, so the order is the order of first
recording (2.5). A path already present is not overwritten (1.6). It is never cleared by a Set
or a `Close`: a file once read stays a dependency of every later capture. That can make a capture
stale for a file whose prop is gone. This errs towards stale and costs one re-render.

If one path is read twice with different bytes during a run (the file changed mid-run), the first
hash stays. The later bytes may be what the capture holds, and the solo run then reports the file
as changed, which is the safe answer.

### Recorded path

```python
def _scene_dir(self) -> Path | None:
    """The folder of the scene's file, resolved, or None when it has no file."""

def _recorded_path(self, path: Path) -> str:
    """`path` resolved; relative to `_scene_dir()` with `/` when inside it, else absolute with `/`."""
```

`_find_state` already computes the scene folder inline. It changes to call `_scene_dir()`, so
there is one home for it. `resolve()` is applied to both sides, so `..` and a symlink that lands
inside the folder both give the relative form (1.9). `as_posix()` gives `/` on every platform
(1.10). With no scene file (`_scene_dir()` is None, so no sections either) every record is
absolute.

The reverse, used by the solo check:

```python
def _resolve_recorded(self, recorded: str) -> Path:
    """An absolute record as is; a relative one under `_scene_dir()`. Nothing else is searched."""
```

An absolute record is one `PurePosixPath` or `PureWindowsPath` calls absolute. A relative record
with a `..` part, an empty string, or a backslash is treated as malformed (3.2), so a hand-edited
meta file can't send the check outside the scene folder.

### Meta file shape

```json
{
  "capture": "5d3c0e4b1a9f...e7",
  "files": [
    {"path": "assets/flower.bmp", "sha256": "a1b2c3...09"},
    {"path": "intro.state.json", "sha256": "77aa10...f2"},
    {"path": "/home/admin/shared/note.txt", "sha256": "0c9d8e...41"}
  ],
  "hashes": {
    "section intro": "...",
    "setup": "...",
    "state": null
  },
  "time": 4.5
}
```

`files` is a list of objects, not a dict, because `_capture` writes with `sort_keys=True` and
that would put a dict's keys in alphabetical order and lose the recording order 2.5 needs. Keys
inside each object are sorted, and list order is kept, so two full runs of an unchanged scene
write the same bytes (1.8). Paths are relative where the file is in the scene folder (the first
two entries) and absolute otherwise (the third). `hashes` is unchanged.

An old meta file has no `files` and no `capture` key. No version field is added: the missing key
is the signal (3.1).

## Recording points (where each dependency is recorded)

| Dependency | Where | How |
| --- | --- | --- |
| Scene `state` file and files it points at (1.2) | `Scene._set_state`, called from `_begin` | After `load_state` succeeds, `_depend_state(state)` |
| `set_state(path)` file and its files (1.3) | `Scene._set_state`, called from `set_state` | Same line |
| `Picture(image=)`, `Notepad(open=)` in `setup`/sections (1.4) | `Scene.add`, when a prop is newly added | `if isinstance(prop, Win) and prop.source: self._depend(...)` |
| Prop built outside `run` (1.4) | Same: `add`, not the constructor | The constructor stored `source`, `add` reads it |
| Files a state's windows open (1.2, 1.3) | `State.files()` | `Win.from_state` gets the checked bytes, so no separate read |

```python
def _depend(self, path: Path, sha256: str) -> None:
    """Record a file the capture is built from, once, under its recorded path."""
    self._deps.setdefault(self._recorded_path(path), sha256)

def _depend_state(self, state: State) -> None:
    self._depend(state.path, state.sha256)
    for ref in state.files():
        self._depend(ref.path, ref.sha256)
```

`_set_state` also runs for the solo start (`_start_from_capture` loads the capture). That records
the capture's own files into `_deps`, which a solo run never writes, so it has no effect. It is
left alone rather than adding a flag.

Recording happens after `load_state` returns, so a wrong `sha256` still raises `StateError` and
nothing is recorded or captured for it (1.7). That is existing behaviour; the test pins it.

### Changes to `state.py`

```python
@dataclass(frozen=True)
class State:
    ...
    sha256: str = ""          # new, last: the sha256 of the bytes load_state read

    def files(self) -> tuple[FileRef, ...]:
        """Every file the state points at, in file order: the wallpaper, then each window's open and text."""
```

`load_state` reads bytes once (`path.read_bytes()`), hashes them, decodes with `utf-8`, and
returns `dataclasses.replace(state, sha256=digest)`. The decode keeps the two error cases it has
today (`UnicodeDecodeError`, `JSONDecodeError`). The state file format and `VERSION = 1` do not
change (4.3). `dump_state` returns `load_state(path)`, so `get_state` returns a `State` with
`sha256` set, and `_capture` uses it for `capture` with no second read (1.11).

The default `""` keeps any test that builds `State(...)` directly working.

### Changes to the props (1.5 and Requirement 4a)

`Win` gets a class attribute `source: tuple[Path, bytes] | None = None`: the resolved host file
the prop was built from, and the bytes read, before any conversion.

- `Picture.__init__`: after `read_host_file`, `self.source = (self.image.resolve(), data)`. The
  same bytes object as `_image_data`, so no copy.
- `Notepad.__init__`: keeps the raw bytes before `check_text` and sets
  `self.source = (self.open_file.resolve(), raw)`. `_file_data` is still the converted bytes. The
  path is resolved at construction, so a later `chdir` can't change what is recorded.
- Both constructors take a private keyword-only `_data: bytes | None = None`. When given, it is
  used instead of `read_host_file(path)`; the path still names the file and the title.
- `Win.from_state` passes it: `cls(..., **{cls.open_keyword: window.open.path, "_data": window.open.data})`.
  The bytes `load_state` hashed are the bytes the program shows and the bytes recorded. A file
  that changes on disk afterwards is not read again (4a.1, 4a.2). Frames and capture files are
  the same for an unchanged file (4a.3).

`Scene.add` hashes `prop.source[1]` with `hashlib.sha256` when the prop is new.

A private keyword was chosen over a public `data=` so scene authors see no new API and
`test_anim_docs.py` has nothing new to cover. See the decisions at the end.

## Writing the capture (`Scene._capture`)

```python
state = self.get_state(part / state_name)          # a State, with .sha256
meta = {
    "time": self.time,
    "hashes": self._hashes(),
    "capture": state.sha256,
    "files": [{"path": p, "sha256": h} for p, h in self._deps.items()],
}
(part / meta_name).write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
```

`get_state` already returns `load_state(path)`. `_capture` currently discards the value.

## The solo check (`Scene._start_from_capture`)

Order, all before any guest call (2.1):

1. **Read the meta file.** Unreadable, not JSON, or `time`/`hashes` missing or wrong type:
   `MissingFile` "no capture for section ... render the whole scene once first" (as today; this
   also holds when `state` is missing). If `files` and `capture` are both missing, it is an old
   meta file: `UsageError` (3.1). If either is present but malformed (`files` not a list; an
   entry that isn't `{"path": str, "sha256": 64 hex}` and nothing else; a duplicate path; a bad
   relative path; `capture` not 64 hex): the same `MissingFile` (3.2).
2. **Existing hashes**, in `_hashes()` key order, unchanged logic: `setup`, `state`, then
   `section <name>` in the order they ran (2.5, 2.7).
3. **Capture's own state file**: sha256 of the bytes of `captures/NN-name.state.json` against
   `capture`. The error names `NN-name.state.json`.
4. **Dependency files**, in the order of `files` (the recording order): read the bytes of
   `_resolve_recorded(path)`. An `OSError` raises the moved-or-deleted error; a different sha256
   raises the changed error.
5. `_set_state(state)` and `_time_offset = start`, as today (2.6).

The first mismatch raises, so one change is named, the same one every time (2.5). The rendering
of the error stays in one place:

```python
def _stale(name: str, what: str, how: str = "changed") -> UsageError:
    return UsageError(
        f"section {name!r} starts from a capture made before {what} {how}: "
        "render the whole scene again"
    )
```

The existing `raise UsageError(...)` in the loop becomes `raise _stale(name, changed)`. Message
text for the three existing cases is not touched (2.7).

### Error messages

| Case | Class | Message |
| --- | --- | --- |
| Changed dependency (2.2, 2.4) | `UsageError` | `section 'b' starts from a capture made before assets/flower.bmp changed: render the whole scene again` |
| Missing or unreadable dependency (2.3) | `UsageError` | `section 'b' starts from a capture made before assets/flower.bmp was moved or deleted: render the whole scene again` |
| Hand-edited capture state file (1.11) | `UsageError` | `section 'b' starts from a capture made before 02-b.state.json changed: render the whole scene again` |
| Old meta file (3.1) | `UsageError` | `section 'b' has a capture from an older art98 that did not record the files it was built from: render the whole scene again` |
| Malformed or missing records, no capture (3.2) | `MissingFile` | `no capture for section 'b' in <folder>: render the whole scene once first` (existing) |
| Existing `setup`, `state`, section cases (2.7) | `UsageError` | `... made before setup() changed: ...`, `the state file`, `<method>()` (existing) |

The old-meta error is a `UsageError`, so the CLI prints it as one `error:` line, and it says what
to do. It is checked in step 1, before any hash, because an old capture can't be trusted at all.

## `_hashes()` and the markers (5.1)

`_hashes()` keeps computing `setup`, `state` and the section hashes. Its docstring drops "the
files a state file points at aren't hashed", which is now false, and carries:

```text
lazy: source that section methods call (helpers, recipes/helpers modules) and Scene class
attributes (desktop, pointer_visible, strict_placement) are not tracked, nor are files a scene
reads with its own open(); a change there leaves a capture fresh. Upgrade: hash what the
sections call, or declare extra dependencies.
```

The wording will be checked against the owner's issue when it is opened.

## Docs (5.3)

- `docs/scenes/scene-api.md`, "Sections": list what makes a capture stale (the scene's `state`,
  files it points at, `set_state` files and what they point at, `Picture(image=)`,
  `Notepad(open=)`, the capture's own state file, `setup()` and section source). Say that files a
  scene reads with its own `open()`, helper code and class attributes are not tracked, and that
  there is no way to declare them. Python blocks stay whole scenes or become `text`/`bash`
  (`test_anim_docs.py`).
- The 0.3.0 breaking-change entry ("render the whole scene again for old captures") goes where
  0.3.0's changes are recorded. I did not find that place in this session (shell unavailable), so
  the tasks phase must locate it (`CHANGELOG.md` or a release-notes page) before it writes the
  entry. `docs/status.md` is not edited.

## Testing

### Unit tests on existing stand-ins

`FakeGuest`, `FakeVM`, `FakeSession`, `FakeVideo` in `test_anim.py` for the section runs;
`GuestWithFiles` (`test_picture.py`) and `NotepadGuest` (`test_notepad.py`) for the props. No new
fakes. Each test uses `tmp_path` for the scene folder and writes a real scene file, because
`_scene_dir()` and `inspect.getsource` need one. Existing section tests set the pattern; I could
not list them this session, so the tasks phase should reuse their helper for "run a full render,
then a solo render of section N".

Names are sentences, for example:

- `test_a_changed_picture_makes_a_later_section_stale`, `..._notepad_file_...`,
  `..._set_state_file_...`, `..._file_a_state_points_at_...`, `..._scene_state_file_...`
- `test_a_missing_dependency_says_moved_or_deleted` (same four sources)
- `test_unchanged_files_leave_the_capture_fresh`
- `test_a_file_a_state_points_at_changed_without_its_sha_is_stale_in_section_two` (2.4, and a
  solo run of section 1 still loads and raises `StateError`)
- `test_an_old_meta_file_says_to_render_again` (3.1)
- `test_a_malformed_files_record_is_no_capture` (3.2): not a list, entry missing `sha256`,
  duplicate path, `..` path, bad `capture`
- `test_a_hand_edited_capture_state_file_is_stale_even_with_matching_hashes` (1.11)
- `test_the_stale_messages_match_exactly` (2.2, 2.3)
- `test_one_change_is_named_in_a_fixed_order` (2.5): change several items, assert `setup` first,
  then `state`, sections, `capture`, then files in recording order
- `test_a_file_outside_the_scene_folder_is_recorded_absolute`, `test_a_dotdot_path_is_recorded_relative`,
  `test_a_symlink_into_the_folder_is_recorded_relative` (skips where symlinks aren't allowed)
- `test_a_moved_project_keeps_its_captures_fresh` (1.10): copy the folder, solo run
- `test_two_full_runs_write_the_same_meta_bytes` (1.8)
- `test_a_prop_built_at_import_is_recorded_when_added` (1.4)
- `test_a_file_used_twice_is_recorded_once` (1.6)
- `test_a_wrong_sha_in_a_state_raises_state_error_and_writes_no_capture` (1.7)
- `test_the_notepad_hash_is_of_the_raw_bytes_not_the_crlf_ones` (1.5)
- `test_the_solo_check_makes_no_guest_call_before_it_passes` (2.1, 4.2): `guest.calls` is
  empty at the raise
- `test_a_file_that_changes_after_the_check_is_not_read_again` (4a): build `window` from
  `load_state`, overwrite the file, call `Picture.from_state` / `Notepad.from_state`, assert the
  prop holds the checked bytes and `source` hashes to the checked sha256
- A test that the capture state file and frames are identical to before (4.1, 4a.3): compare a
  capture written now with a golden one from the same scene on the stand-in guest.

### Property-based tests

Hypothesis is not in the `dev` group today (`pyproject.toml`: pytest, pycdlib, ruff). The
`tests` rules put it there, never in `[project] dependencies`. Properties that suit it are the
pure ones:

1. **Recorded path round trip** (`_recorded_path` / `_resolve_recorded`): for a generated
   relative path under a temp folder, `resolve(record(p)) == p.resolve()`; the record has no
   `\`, no leading `/`, no `..`; recording after moving the folder gives the same string (1.9,
   1.10). A path outside the folder gives an absolute record that resolves to itself.
2. **Meta round trip and determinism**: any list of unique `(path, sha256)` pairs written and read
   back is the same list in the same order; writing the same input twice gives the same bytes
   (1.8, 2.5).
3. **Malformed never crashes**: generated mutations of a valid meta (drop a key, wrong type,
   duplicate an entry, uppercase or short digest) either read back or give `MissingFile` or the
   old-meta `UsageError`, never `KeyError`, `TypeError` or `AttributeError` (3.1, 3.2).
4. **First change wins**: for a generated recorded list and a generated subset of changed or
   deleted files, the error names the first changed file in list order, and the wording is
   "changed" or "was moved or deleted" according to that file (2.2, 2.3, 2.5), checked against a
   three-line model.
5. **Once only**: for a generated sequence of `_depend` calls with repeats, the keys equal the
   unique paths in first-seen order (1.6).
6. **`State.files()`**: for generated states, every `FileRef` the reader produced appears once,
   wallpaper first, then windows in list order with `open` before `text`.

Not suited: the stand-in guest runs (properties would multiply `inspect.getsource` and temp
scene files for little gain), and anything about window or frame content.

If the owner doesn't want a new dev dependency, properties 1 to 6 become seeded `random` loops
or `pytest.mark.parametrize` tables over hand-picked cases, with less coverage.

### VM tests

Not needed. The feature is host-only, and no guest call is added (4.2). The PR says
`VM tests: not run (no prepared image on this machine)` if that holds.

## Requirement issues

None of these stops the design. Two are places where the requirements are silent or tight.

1. **2.3 and the scene's own `state` file.** `_hashes()` calls `_find_state`, which raises
   `MissingFile` ("state file 'x' not found; looked in ...") when the file is gone. In a solo run
   that happens before step 2, so a deleted scene `state` file never gets the "was moved or
   deleted" message that 2.3 requires of every recorded dependency, and the existing message
   doesn't say to render again. The design leaves the existing `MissingFile` as it is. Making it
   meet 2.3 means `_hashes()` returns `None` for an unreadable state file and the loop words it
   as moved or deleted, using the recorded path from `files`. About ten lines; see decision 1.
2. **1.9 and a symlink inside the folder that points outside.** The text covers a path that
   reaches a file inside the folder through a symlink. A link inside the folder to a file outside
   it resolves to the outside target, so it is recorded absolute. The design takes 1.9 to mean
   the resolved target.
3. **1.6 with different bytes.** The requirement says "record once", not what to do when the
   bytes differ. The design keeps the first hash (see Data).

No requirement was found that can't be met.

## Traceability

| Requirement | Design |
| --- | --- |
| 1.1 | Meta `files` list, `_capture`; `_depend` |
| 1.2 | `_set_state` -> `_depend_state` from `_begin`; `State.files()` |
| 1.3 | `_set_state` -> `_depend_state` from `set_state` |
| 1.4 | `Win.source`, set in `Picture`/`Notepad` constructors; recorded in `Scene.add` |
| 1.5 | `Win.source` holds raw bytes (Notepad keeps them before `check_text`); `FileRef.data` for state files |
| 1.6 | `_depend` uses `setdefault` on `_deps` |
| 1.7 | `_depend_state` runs after `load_state`; existing `StateError` path unchanged |
| 1.8 | List order from insertion; `sort_keys=True`; no sets |
| 1.9 | `_recorded_path`: `resolve()`, relative to `_scene_dir()`, else absolute |
| 1.10 | `_recorded_path` uses `as_posix()`; relative to the scene folder |
| 1.11 | `State.sha256`; meta `capture`; solo step 3 |
| 2.1 | Solo steps 1 to 4 before `_set_state`; no guest call |
| 2.2 | `_stale(name, rec)`; step 4 |
| 2.3 | `_stale(name, rec, "was moved or deleted")`; `_resolve_recorded` searches nowhere else. Exception: the scene's own `state` file, issue 1 |
| 2.4 | Dependency files are checked in every solo run of section 2 or later, from the recorded `files` |
| 2.5 | Check order in "The solo check"; first mismatch raises |
| 2.6 | Step 5 unchanged |
| 2.7 | `_stale` reuses the existing template; existing cases unchanged |
| 3.1 | Step 1: no `files`/`capture` gives the old-meta `UsageError` |
| 3.2 | Step 1: malformed records give `MissingFile` |
| 4.1 | No change to frames, clips or capture state file writers |
| 4.2 | Only `read_bytes` on the host; `test_the_solo_check_makes_no_guest_call...` |
| 4.3 | `VERSION` unchanged; new data only in meta; `State.sha256` is in memory only |
| 4a.1 | `Win.from_state` passes `window.open.data` as `_data`; constructors skip `read_host_file` |
| 4a.2 | Same; test overwrites the file after `load_state` |
| 4a.3 | State format untouched; the bytes are the same for an unchanged file |
| 5.1 | `_hashes()` docstring: old marker removed, new `lazy:` added |
| 5.2 | Testing: unit tests listed above, plus the 4a test |
| 5.3 | Docs: `scene-api.md` "Sections"; 0.3.0 breaking-change entry (location to be found) |

## Owner decisions on the design

Given 2026-11-18.

1. **A deleted scene `state` file:** keep the existing `MissingFile`. Requirement 2.3 doesn't
   apply to the scene's own state file, which `_find_state` reports first.
2. **Hypothesis:** add it to the `dev` dependency group for the property tests. It is never a
   runtime dependency.
3. **Handing over the checked bytes:** a private keyword-only `_data` on `Picture` and
   `Notepad`, as designed. No public API.
4. **Files kept after their prop is gone:** never forget a recorded file, as designed. A capture
   errs towards stale.
5. **The 0.3.0 breaking-change note:** goes under `## [Unreleased]` in `CHANGELOG.md`.
