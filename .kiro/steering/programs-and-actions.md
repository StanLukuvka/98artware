---
inclusion: fileMatch
fileMatchPattern: ["core/art98/actions/**", "core/art98/anim/setstate.py", "core/art98/anim/scene.py", "core/art98/state.py", "core/art98/guest/win32.py"]
---

# Programs, actions and states

A program is an action class. It is one Python class that starts a program on the guest,
finds its window, and holds the verbs that drive it. `Notepad` is the model to copy:

#[[file:core/art98/actions/programs/notepad.py]]

## Adding a program

1. Check that it ships with Windows 98 SE. Nothing else is in scope.
2. Try it on the real guest first, with a probe in `experiments/` or a throwaway scene. Write
   down what Windows actually does: the window class, the title rule, the child controls.
   `docs/scenes/app-catalog.md` has what is already known.
3. Write the class in `core/art98/actions/programs/<name>.py`, subclassing `Win`. Set
   `command` and `window_class`, add `ready()` if it needs a child window, then add the verbs.
4. Export it from `core/art98/actions/programs/__init__.py`, and add it to `__all__` in
   `core/art98/anim/__init__.py`.
5. Document it in `docs/scenes/scene-api.md` (the docs test fails if a public name is missing),
   and add a line to `docs/scenes/app-catalog.md`.
6. Add unit tests on a stand-in guest beside `core/tests/test_notepad.py`, and a VM test beside
   the ones in `core/tests/test_stage.py`.
7. If it shows something new, add a short scene to `recipes/scenes/gallery/` and its GIF to
   `docs/scenes/gallery.md`.

## Making it a state app

A state app is a program that a state file can open and that `get_state` can capture. Only
`picture` and `notepad` are state apps so far. To make one:

- Add the class to `APPS` in `core/art98/actions/apps.py`. That is the only list; `state.py`
  and `setstate.py` read it.
- Give the class `open_keyword` (the constructor keyword its file is passed as), `check_file`
  for its `open` file, and `default_title(file)` for a window whose state names no title.
  `from_state` is inherited from `Win`.
- Write `to_state(files)`, starting from `Win._state_base()`. `Win.to_state` raises
  `UsageError`, so a program without one can't be captured: in a scene with sections, its
  window can't be open when a later section starts.
- Document its `app` name under "States" in `docs/scenes/scene-api.md`.

A new state field is read and fully checked in `state.py`, applied in `apply_state`, and
verified in `check_state`, in that order. It describes a still desktop. If `get_state` should
capture it too, the prop's `to_state` writes it.

## Tracking: every window has an owner

Saved states depend on this. `get_state` writes the desktop from the scene's props, not by
reading the screen, so it can only capture windows it knows about. `check_tracking()` runs after
every `play`, `wait` and `wait_until`, before `get_state`, and at the end of a run.

- **A window nothing added** raises `UntrackedWindow`. If a verb makes a program open a menu, a
  tooltip or a prompt, the verb claims it with `scene.claim(owner, matches)` while it handles it,
  and releases it after.
- **A prop's window ends only through `Close`** (`Close(window, via=...)` shows the click). If the
  X button, a menu's Exit, Alt+F4 or a dialog button closes it, that raises `ImplicitClose`.
  A verb that closes its own window has to go through `Close`.

## Rules

- **One home per thing.** A Win32 constant or a guest read used twice goes in
  `core/art98/guest/win32.py` or on `Win`; `test_win32.py` fails on a constant defined
  elsewhere. Pixel and frame rounding goes through `core/art98/base/units.py`. Never add a shared
  grab-bag module.
- **The guest is the truth.** Read back before acting (`refresh`) and check after
  (`check_state`, the placement read-back). Don't cache anything Windows can change.
- **Only state measured facts.** A comment or docstring about Windows 98 behaviour says it was
  checked on the real image, or it doesn't make the claim. If there is no image to check on,
  say in the pull request which behaviour wasn't checked.
- **Errors inherit `Art98Error`** from `core/art98/errors.py`, with the built-in base second
  (`class X(Art98Error, ValueError)`). A mistake in what a scene passes in is a `UsageError`.
- **Rejected for sections** (`docs/design/decisions.md`, section 7): a VM snapshot per section,
  replaying earlier sections muted, and replaying a log of steps. Sections start from a captured
  state.
- A stock program needs no guest change. Prefer one over a program of art98's own in `guest/`.

## Tests these changes need

Unit tests and VM tests. The VM tests need `art98 vm start` running and a prepared image. If
they can't be run, the pull request says:

```text
VM tests: not run (no prepared image on this machine)
```

More: `docs/design/programs.md`, `docs/design/state-and-action.md`, and in
`docs/scenes/scene-api.md` the "Tracking", "States" and "Sections" parts. In `CONTRIBUTING.md`,
"Adding a program" and "Adding to states".
