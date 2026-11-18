# Requirements: state file hashing

## Introduction

`art98 render --section NAME` plays one section of a scene from a capture that an earlier full
run wrote: `NN-name.state.json`, its `NN-name.state.files/` folder, and `NN-name.meta.json`,
all in `<scene file stem>.<Scene>.sections/`. The meta file holds the video time and a set of
hashes from `Scene._hashes()`. `Scene._start_from_capture()` recomputes them and, on any
difference, raises `UsageError`: "section 'b' starts from a capture made before X changed:
render the whole scene again".

This feature makes a capture go stale when any host file it depends on changes. It is the only
blocker for 0.3.0, which is a breaking release. The owner has decided that untracked state is an
error, not something to guess around.

### What is hashed today

From `core/art98/anim/scene.py`, `_hashes()` records:

- `setup`: sha256 of the source of `type(self).setup`.
- `state`: sha256 of the bytes of the scene's `state` file (found by `_find_state`), or null.
- `section <name>`: sha256 of the source of each section method that ran before this one.

### Which part of the marker's gap is already covered

The marker on `_hashes()` says "the files a state file points at aren't hashed". For the scene's
own `state` file, most of that is already covered by a different mechanism. Every file a state
file points at (`desktop.wallpaper`, a window's `open`, a Notepad's `text`) carries its own
`sha256` inside the state file, and `load_state` refuses the file when the bytes don't match
(`_Reader.file` in `core/art98/state.py`). So a changed picture, text or wallpaper that the state
still accepts means the `sha256` in the state was edited too, the state file's bytes changed, and
the existing `state` hash catches it.

The capture's own files are covered the same way. `NN-name.state.json` names each file under
`NN-name.state.files/` with its `sha256`, and the solo run loads it through `load_state` in
`_set_state`, so an edited capture file fails with `StateError`. The one thing not covered is a
hand-edited `NN-name.state.json` whose `sha256` fields were edited to match; the owner has
decided the meta file hashes that file too (Requirement 1).

### What is left: dependencies no recorded hash covers

1. **A file the scene's state points at, changed without updating its `sha256`.** A full run
   fails with `StateError`. A solo run of section 2 or later never loads the scene's state file
   (it skips `_begin`), and `_hashes()` reads only its raw bytes, which are unchanged. The solo
   run plays from the old capture with no error. Section 1 is not affected, because a solo run of
   it runs `_begin` and loads the state.
2. **State files passed to `set_state()` in `setup()` or an earlier section.** Only the path
   literal in the method's source is hashed. Neither the state file's bytes nor the files it
   points at are recorded. Editing that state file (window positions, the wallpaper, its `open`
   files with updated hashes) leaves every recorded hash the same.
3. **Host files given to a prop in `setup()` or an earlier section**: `Picture(image=...)` and
   `Notepad(open=...)`. Both read the file through `guestfiles.read_host_file`, and `to_state`
   copies those bytes into the capture. Nothing records a hash of the source file, so a changed
   picture or text file leaves the capture unchanged and the solo run shows the old contents. A
   prop built outside `run` (at import, as a class attribute) reads its file even earlier, but
   its bytes still reach the capture only when it is added.

No other host file reaches a capture through art98. The wallpaper only comes from a state file
(`setstate.apply_state`); `Backdrop` takes a colour, not a file. `VIEW.EXE` comes from
`guest/build` on every run, solo runs included, and is not part of a capture.

Outside the marker, and outside this feature by the owner's decision (see Owner decisions):
source the section methods call (helper functions, other methods, `recipes/helpers/` modules),
Scene class attributes such as `desktop`, `pointer_visible` and `strict_placement`, and files a
scene reads with its own Python code (`open()`). art98 does not see these reads.

## Glossary

- **Capture**: the state file, its files folder and the meta file a full run writes at the start
  of each section after the first.
- **Solo run**: a render with `--section NAME`.
- **Dependency file**: a host file whose bytes reached the guest, or the capture, during
  `setup()` or a section before the captured one, through art98: a state file loaded by the
  scene's `state` or by `set_state()`, a file such a state points at, or a file given to a prop.
- **Stale error**: the existing `UsageError` "section 'NAME' starts from a capture made before X
  changed: render the whole scene again".
- **Recorded path**: how a dependency file is named in the meta file and in the stale error: its
  path relative to the scene file's folder, or an absolute path when the file is outside that
  folder.

## Requirements

### Requirement 1: Record every dependency file in the capture

**User story:** As a scene author, I want a capture to record every file it was built from, so
that a solo run can tell when one has changed.

#### Acceptance criteria

1. WHEN a full run writes a capture, THE SYSTEM SHALL record in its meta file a sha256 for every
   dependency file, alongside the existing `setup`, `state` and `section <name>` hashes.
2. WHEN the scene's `state` file is loaded at the start of a full run, THE SYSTEM SHALL record
   the state file and every file it points at as dependency files.
3. WHEN `set_state(path)` runs in `setup()` or in a section, THE SYSTEM SHALL record that state
   file and every file it points at as dependency files of every later capture.
4. WHEN a prop that holds a host file (`Picture` with `image`, `Notepad` with `open`) is added
   in `setup()` or in a section, THE SYSTEM SHALL record that file as a dependency file of every
   later capture, whether the prop was built inside or outside `run`.
5. WHEN a dependency file is recorded, THE SYSTEM SHALL hash the bytes art98 read from the host
   file, before any conversion (such as Notepad's line-end fix in `check_text`), so that any
   change to the file on disk counts.
6. WHEN the same file is used more than once before a capture, THE SYSTEM SHALL record it once.
7. WHEN a state file loaded in a full run points at a file whose `sha256` doesn't match, THE
   SYSTEM SHALL keep raising `StateError` as today, and SHALL write no capture.
8. WHEN two full runs of an unchanged scene write captures, THE SYSTEM SHALL write meta files
   with the same bytes.
9. WHEN a dependency file is recorded, THE SYSTEM SHALL store it under its recorded path: relative
   to the scene file's folder when the file is inside that folder, and absolute otherwise. A
   path that reaches a file inside the folder through `..` or a symlink is recorded in its
   relative form.
10. WHEN a project is moved or re-cloned with its captures and every dependency file keeps its
    place relative to the scene file's folder, THE SYSTEM SHALL find the recorded hashes
    matching, so the captures stay fresh. Recorded paths SHALL use `/` as the separator on every
    platform, so the meta file is the same bytes everywhere.
11. WHEN a full run writes a capture, THE SYSTEM SHALL also record the sha256 of that capture's
    own `NN-name.state.json`, so that a hand-edited capture state file, even with its `sha256`
    fields updated to match, makes the capture stale.

### Requirement 2: A changed dependency file makes the capture stale

**User story:** As a scene author, I want a solo run to refuse a capture when a file it was
built from has changed, so that the section never plays from an old desktop.

#### Acceptance criteria

1. WHEN a solo run reaches its section, THE SYSTEM SHALL hash each dependency file recorded in
   the capture's meta file and compare it with the recorded hash, before it touches the guest.
2. WHEN a dependency file's bytes differ from the recorded hash, THE SYSTEM SHALL raise the
   stale error, with X being that file's recorded path and nothing else, for example "section
   'b' starts from a capture made before assets/flower.bmp changed: render the whole scene
   again".
3. WHEN a dependency file named in the meta file no longer exists or can't be read, THE SYSTEM
   SHALL raise a `UsageError` naming its recorded path with its own wording, "section 'b' starts
   from a capture made before assets/flower.bmp was moved or deleted: render the whole scene
   again", and SHALL NOT look for the file anywhere else. The message does not say how the file
   got into the scene.
4. WHEN a file the scene's state points at has changed but the state's `sha256` for it has not
   (gap 1 above), THE SYSTEM SHALL raise the stale error naming that file in a solo run of any
   section, not only section 1.
5. WHEN several recorded items have changed, THE SYSTEM SHALL name exactly one of them, as it
   does today, picked in a fixed order, so the same change always gives the same message. It
   SHALL NOT list every change. The order is the existing items first (`setup`, the scene's
   `state`, then section methods in the order they ran), then the capture's own
   `NN-name.state.json`, then dependency files in the order they were first recorded.
6. WHEN every recorded hash matches, THE SYSTEM SHALL set the desktop to the capture and play the
   section as it does today.
7. THE SYSTEM SHALL keep the stale error's class (`UsageError`) and its message shape, "section
   'NAME' starts from a capture made before X changed: render the whole scene again", for the
   existing `setup()`, state file and section method cases.

### Requirement 3: Untracked dependencies are an error

**User story:** As the owner, I want art98 to refuse a capture it can't check, rather than guess
that it is still good.

#### Acceptance criteria

1. WHEN a solo run finds a meta file without dependency file records (one written before this
   change), THE SYSTEM SHALL raise the stale error, or another `Art98Error` that says to render
   the whole scene again, and SHALL NOT treat the missing records as "no dependency files".
2. WHEN a meta file's dependency records are malformed, THE SYSTEM SHALL raise `MissingFile` with
   the existing "no capture for section 'NAME' in ...: render the whole scene once first"
   message, as it does for a meta file it can't read today.

### Requirement 4: Nothing else changes

**User story:** As a scene author, I want this check to cost nothing in the video, so that the
same scene still gives the same frames.

#### Acceptance criteria

1. THE SYSTEM SHALL produce the same frames, clips and capture state files as before this change
   for the same scene and inputs.
2. THE SYSTEM SHALL read dependency files only on the host, and SHALL NOT add guest calls.
3. THE SYSTEM SHALL keep the capture state file format (`state.py`, `VERSION = 1`) unchanged; the
   new records go in the meta file only.

### Requirement 4a: A window's `open` file is read once

**User story:** As a scene author, I want the bytes `load_state` checked to be the bytes the
program shows, so that a file changing mid-run is never used unchecked.

#### Acceptance criteria

1. WHEN `load_state` has checked a window's `open` file against its `sha256`, THE SYSTEM SHALL
   give those same bytes to the program (through `Win.from_state` and the constructor), and SHALL
   NOT read the file from disk a second time.
2. WHEN that file changes on disk between the check and the use, THE SYSTEM SHALL still use the
   checked bytes.
3. THE SYSTEM SHALL keep the state file format and the frames for an unchanged file the same as
   before this change.

### Requirement 5: Code, tests and docs

**User story:** As a contributor, I want the change to leave the code and docs telling the truth.

#### Acceptance criteria

1. WHEN this feature is done, THE SYSTEM SHALL no longer carry the "lazy: the files a state file
   points at aren't hashed" marker on `_hashes()`, and SHALL carry a `lazy:` comment that says
   source called from section methods (helpers, `recipes/helpers/` modules) and Scene class
   attributes are not tracked, and what the limit is. Separately from this spec, the owner opens
   an issue for that gap.
2. THE SYSTEM SHALL have unit tests on the existing stand-in guests (`FakeVM` in `test_anim.py`)
   for each case in Requirements 1 to 3: a changed, a missing and an unchanged file, for the
   scene's state, a `set_state` file, a file a state points at, and a prop's file, plus an old
   meta file, a hand-edited capture `NN-name.state.json`, the exact wording of the changed and
   the moved-or-deleted messages, a file outside the scene's folder (absolute record), and a
   scene folder that is moved. Requirement 4a has its own test with a file that changes
   between check and use.
3. THE SYSTEM SHALL describe what makes a capture stale where the docs describe sections
   (`docs/scenes/scene-api.md`, "Sections"), including that files a scene reads with its own
   `open()` are not tracked by art98 and that there is no way to declare them, and SHALL list the
   breaking change (old captures must be rendered again) wherever 0.3.0's changes are recorded,
   without editing `docs/status.md`.

## Owner decisions

Given 2026-11-18.

1. **Paths**: dependency files are recorded relative to the scene file's folder; a file outside
   it is recorded as an absolute path (Requirement 1.9, 1.10).
2. **Error text**: X is the recorded path only. A missing or unreadable file says "was moved or
   deleted" (Requirement 2.2, 2.3).
3. **One change**: the error names one change, picked in a fixed order (Requirement 2.5).
4. **Helpers, `recipes/helpers/` modules, class attributes**: not in 0.3.0. A `lazy:` marker stays
   and the owner opens an issue (Requirement 5.1).
5. **Files a scene opens itself**: documented as not tracked; no declaration API (Requirement
   5.3).
6. **The capture's own state file**: the meta file hashes it (Requirement 1.11).
7. **Double read of `open`**: fixed in this feature (Requirement 4a).
