# Requirements: desktop options

## Introduction

A scene can hide parts of the stock desktop today only with raw guest calls: `ShowWindow(hwnd,
SW_HIDE)` on taskbar children found by class name. Those calls do not last. A colour change shows
the tray again, and a revert (including `set_state`) shows everything. The blank desktop is a
separate kind of desktop with its own fixed steps.

This feature makes the desktop a tree of parts. Each part is off, or on with its children. The
blank desktop becomes a preset of that tree. art98 applies the scene's options after every revert
and keeps them in place.

The owner's answers of 2026-11-19 settle the shape. This revision replaces the first draft's
four-flag taskbar model, its blank-refuses-options rule and its open questions 3, 4, 5, 6, 8 and 9.

### The tree

```text
desktop
├─ icons
├─ pointer
└─ taskbar
    ├─ buttons
    ├─ quick_launch
    └─ tray
        └─ clock
```

A part that is off hides its children. The form is flat options on `Desktop`, each `True`, `False`
or left out (the preset's value): `Desktop("stock", clock=False)`,
`Desktop("blank", taskbar=True, buttons=False)`. The tree is implicit: an option that is off
overrides the options under it, and writing one of those is warned about (Requirement 6).

### Source facts

From `experiments/taskbar/README.md` (run 2026-11-19 on the real VM, 800x600):

- `Shell_TrayWnd` has these children: Start (`Button`); `ReBarWindow32`, which holds quick launch
  (`ToolbarWindow32`) and the window buttons (`MSTaskSwWClass`); and `TrayNotifyWnd` (the tray),
  which holds `TrayClockWClass` (the clock).
- Hiding `MSTaskSwWClass` removes every window button, and windows opened later get none.
- Hiding `ReBarWindow32` removes quick launch and the buttons.
- Hiding the clock leaves an empty tray frame until the next colour change, which shrinks the tray
  to its icon.
- Hiding `TrayNotifyWnd` removes the tray, but every `set_colour` broadcast shows it again.
- Each part reads back with `IsWindowVisible`. A revert restores all of them.

From the code (`core/art98/desktop.py`, `core/art98/state.py`, `core/art98/anim/scene.py`):

- `Scene.desktop` is a string checked by `check_desktop` against `DESKTOPS = ("blank", "stock")`.
  `prepare_desktop` calls `desktop.blank()` for `"blank"` and does nothing for `"stock"`.
  `_start_desktop` runs it after every revert, which covers `run` and every Set.
- `desktop.blank()` does these steps, and `check_blank` verifies them: the desktop colour goes
  black; the icon list is hidden; the whole `Shell_TrayWnd` is hidden and disabled; the desktop
  window (`Progman`) is disabled; the work area becomes the whole screen; menu, combo box and list
  box animations, gradient captions and hot tracking are turned off; and every system pointer
  shape is swapped for an empty one unless `pointer=True`.
- The pointer is swapped once per desktop, right after a revert. Swapping it later is not reliable
  (module notes in `desktop.py`, tested on the `ready` image, November 2026).
- `set_colour` hides the icon list again after a colour change when it was hidden. It does not
  know about the tray.
- `DesktopState` in `state.py` has `fill_colour`, `wallpaper` and `style`. `LATER_DESKTOP` rejects
  a `tray` key with "the tray comes after this milestone".
- The stock desktop keeps menu animations on, so its menu timing follows the guest clock.
- `Scene` class attributes, `desktop` included, are not hashed for section captures (the `lazy:`
  marker near `core/art98/anim/scene.py:779`).

Not verified in this revision (shell access was unavailable, so no search or run was possible):
the exact default and use of `pointer_visible`, and the exact text of the existing `warnings.warn`
calls in `scene.py`, `renderer.py` and `recorder.py`.

No raw callers of the taskbar class names exist in the repository. Only a reference table in
`docs/scenes/app-catalog.md` mentions them, and nothing needs moving.

## Glossary

- **Part**: a node of the tree above.
- **On, off**: a part that is on is shown; a part that is off is hidden. A part is effectively off
  when it or any part above it is off.
- **Preset**: a named setting of the whole tree. `"stock"` has every part on. `"blank"` has
  `taskbar`, `icons` and `pointer` off.
- **Override**: a value written after a preset that changes one part, for example blank with the
  taskbar on.
- **Window buttons**: the `MSTaskSwWClass` area, one button per window (`buttons`).
- **Quick launch**: the toolbar of launch icons left of the window buttons (`quick_launch`).
- **Tray**: the `TrayNotifyWnd` area at the right end, with its icons and the clock (`tray`).
- **Clock**: `TrayClockWClass` inside the tray (`clock`).

## Requirements

### Requirement 1: The desktop is a tree of parts

**User story:** As a scene author, I want to say which parts of the desktop are off, so that my
scene shows only the parts I want.

#### Acceptance criteria

1. THE Scene SHALL let an author turn each part of the tree off independently of its siblings:
   `icons`, `pointer`, `taskbar`, and under `taskbar` the parts `buttons`, `quick_launch` and
   `tray`, and under `tray` the part `clock`.
2. WHEN a part is off, THE guest SHALL show that part and every part below it as off.
3. WHEN a part is on, THE guest SHALL show that part and every child of it that is not itself
   off.
4. WHEN an author turns off no part of the stock preset, THE Scene SHALL leave the desktop as the
   `ready` snapshot has it.
5. WHEN `buttons` is off, THE guest SHALL show no button for any window, including windows opened
   later in the scene.
6. WHEN `tray` is off, THE guest SHALL show no tray, which includes its icons and the clock.
7. WHEN `clock` is off and `tray` is on, THE guest SHALL show the tray without the clock.
8. WHEN `quick_launch` is off and `buttons` is on, THE guest SHALL still show the window buttons.
   (Open question 1.)
9. WHEN `icons` is off on the stock desktop, THE guest SHALL show no desktop icons. (Open
   question 4.)
10. WHEN `pointer` is off on the stock desktop, THE guest SHALL draw no system pointer shapes, as
    the blank desktop does. (Open question 4.)
11. THE Scene SHALL take the options as flat options on one `Desktop` value: `icons`, `pointer`,
    `taskbar`, `buttons`, `quick_launch`, `tray` and `clock`, each `True`, `False` or left out
    (`None`, meaning the preset's value), as in `Desktop("stock", clock=False)`. THE levels SHALL
    be implicit: `taskbar` sits over `buttons`, `quick_launch` and `tray`, and `tray` sits over
    `clock`. THE Scene SHALL NOT offer nested values or separate `Taskbar` and `Tray` types.

### Requirement 2: Presets, with "blank" as one of them

**User story:** As a scene author, I want `"blank"` and `"stock"` to keep working and to build on
them, so that I can say "blank, but with a taskbar".

#### Acceptance criteria

1. WHEN a scene sets `desktop = "stock"`, THE Scene SHALL behave exactly as it does today.
2. WHEN a scene sets `desktop = "blank"`, THE Scene SHALL behave exactly as it does today: the
   same steps, the same guest state, and the same `DesktopError` when a step does not take.
3. THE `"blank"` preset SHALL have `taskbar`, `icons` and `pointer` off, and the other steps of
   Requirement 3.
4. WHEN an author writes a preset and then turns a part back on (for example `"blank"` with the
   taskbar on) or off, THE Scene SHALL treat the written value as an override. It SHALL NOT treat
   it as a conflict, raise an error, or warn, unless the override sits under an off option
   (Requirement 6.1).
5. WHEN a scene sets an unknown preset name, THE Scene SHALL raise a `UsageError` that lists the
   valid choices. `check_desktop` SHALL do this when the scene class is defined and again at the
   start of `run`, as it does for the string today.
6. THE `pointer_visible` attribute SHALL keep working. It SHALL map onto the `pointer` part of the
   tree: `pointer_visible = True` means `pointer` on. (Open question 3.)
7. WHEN a scene sets neither `pointer_visible` nor a `pointer` option, THE Scene SHALL use the
   preset's own pointer value: on for `"stock"`, off for `"blank"`.

### Requirement 3: Which blank steps go with which part

**User story:** As a scene author, I want blank with a part turned back on to be correct, so that
a blank desktop with a taskbar still has a usable work area.

#### Acceptance criteria

1. WHEN `icons` is off, THE Scene SHALL hide the desktop icon list.
2. WHEN `pointer` is off, THE Scene SHALL swap every system pointer shape for an empty one, once,
   right after the revert.
3. WHEN `taskbar` is off, THE Scene SHALL hide the whole `Shell_TrayWnd`, disable it so the
   Windows key and Ctrl+Esc do not open the Start menu, and make the work area the whole screen.
4. WHEN `taskbar` is on, THE Scene SHALL leave the taskbar enabled and the work area as the
   guest gives it, so that `scene.work_area` and `scene.space` equal the stock values when no
   other part changes them.
5. WHEN `taskbar` is on and any of its children is off, THE Scene SHALL hide those children only,
   with `SW_HIDE`. THE taskbar SHALL keep its size, so `scene.work_area` does not change. (The
   probe shows the taskbar keeps its size when its children are hidden.)
6. THE steps that belong to no part (the black desktop colour, the disabled desktop window, and
   the turned-off animations, gradient captions and hot tracking) SHALL still happen for
   `"blank"` exactly as today. Where they happen for a preset with a part turned back on is open
   question 2.
7. THE Scene SHALL check the result after applying the options, in the way `check_blank` does,
   and raise `DesktopError` listing every difference, one per line. This SHALL include a part not
   found on the guest, named in the line.
8. THE Win32 constants and repeated guest reads the feature needs SHALL live in `guest/win32.py`.
   THE class names of the taskbar parts SHALL be defined once.

### Requirement 4: The options hold for the whole scene

**User story:** As a scene author, I want an off part to stay off, so that I don't re-hide it
after every colour change or state jump.

#### Acceptance criteria

1. WHEN the scene starts, THE Scene SHALL apply the options before `setup` runs and before the
   first frame is recorded.
2. WHEN a revert happens (the start of `run`, `set_state`, a section start), THE Scene SHALL
   apply the options again, as `_start_desktop` does today.
3. WHEN `set_colour` runs, from `Backdrop`, from a state's `fill_colour` or from any other path,
   THE Scene SHALL leave every part that is off, off. This covers the tray, which a colour change
   shows again today, and the icons, which `set_colour` already hides again.
4. WHEN a part is off, THE Scene SHALL NOT show it again for any reason other than a revert
   followed by a fresh application of the options.
5. WHEN a section is rendered alone, THE Scene SHALL start it with the same options as a full
   render has at that point. A section run alone gets the scene's current options because they
   are applied again on every Set. (Whether that is enough is open question 6.)
6. THE options SHALL be per scene. THE Scene SHALL NOT offer an action that changes them partway
   through a scene.

### Requirement 5: Same frames every run

**User story:** As a scene author, I want identical frames from identical scenes, so that renders
can be compared.

#### Acceptance criteria

1. WHEN the options have been applied, THE Scene SHALL wait until the guest has finished
   repainting (`guest.sync()`) before the first frame, so no frame shows a half-hidden taskbar.
2. WHEN `clock` is off, THE taskbar SHALL look the same whether or not a colour change follows.
   THE application SHALL settle the tray itself and not leave it to a later broadcast. (Open
   question 7.)
3. THE options SHALL NOT depend on wall-clock time or on state left over from an earlier render.
4. THE feature SHALL run at run time only. It SHALL NOT change setup, the answer file, `ready.py`
   or the `ready` snapshot.

### Requirement 6: A setting that does nothing warns

**User story:** As a scene author, I want to hear about an option that cannot take effect, so that
I do not wonder why my scene looks the same.

#### Acceptance criteria

1. WHEN a written option sits under an option that is off, THE Scene SHALL issue a Python
   warning with `warnings.warn`, as the project already does in `wait_until`
   (`core/art98/anim/scene.py`), `core/art98/anim/renderer.py` and `core/art98/output/recorder.py`.
   The option above can be off because it was written off or because the preset has it off (for
   example `Desktop("blank", buttons=False)`, where blank's taskbar is off). The value written
   does not matter, `True` or `False`.
2. THE warning SHALL name the scene class, the option with its value, and the highest option that
   is off, with where its off value came from, and say what to do. For example:
   `Name.desktop: clock=True has no effect, because tray is off (tray=False). Remove clock=True,
   or write tray=True.` and, for a preset, `Name.desktop: buttons=False has no effect, because
   taskbar is off (the "blank" preset). Remove buttons=False, or write taskbar=True.`
3. THE Scene SHALL issue one such warning for each overridden option, for every combination of
   written options (for example `tray=False, clock=True`, and `taskbar=False, buttons=False` on
   stock).
4. THE warning SHALL show on stderr of a plain `python scene.py` run and of `art98 render`, under
   Python's default warning filters. THE Scene SHALL therefore use a category that those filters
   show (`UserWarning`, or a subclass of it), not `DeprecationWarning` or `ImportWarning`.
5. THE Scene SHALL warn once per scene class, not once per revert or Set.
6. THE warning SHALL NOT stop the render. THE options that can take effect SHALL still apply.
7. WHEN an author writes a preset and then overrides a part (Requirement 2.4), THE Scene SHALL NOT
   warn, unless the override itself cannot take effect under Criterion 1.
8. THE Scene SHALL still raise `UsageError` for a value that is not `True`, `False` or `None`, or
   an unknown preset. THE message SHALL name the scene class and the setting, as `check_desktop`
   does today, and list the valid choices. A misspelled option name (`Desktop(clok=False)`) is
   Python's own `TypeError`, which names the keyword and the author's line; THE Scene SHALL NOT
   wrap it.

### Requirement 7: Saved states

**User story:** As a scene author using sections, I want a section that starts from a capture to
have the same desktop as a full render, so that `--section` gives the same frames.

#### Acceptance criteria

1. THE state file SHALL have no taskbar fields for now.
2. WHEN a scene runs a Set (`set_state` or a section capture), THE Scene SHALL show the desktop
   the options describe after the Set, because Requirement 4.2 applies them again.
3. WHEN a state file has a `tray` key, THE loader SHALL keep rejecting it with the present
   "the tray comes after this milestone" message.
4. THE `get_state` capture and the `check_state` check SHALL NOT include the parts of the tree.

### Requirement 8: Documentation and tests

**User story:** As a contributor, I want the feature documented and tested, so that the docs test
and CI stay green.

#### Acceptance criteria

1. THE new public names SHALL be exported from `art98.anim` and described in
   `docs/scenes/scene-api.md`, with every Python block a whole scene that runs, so
   `test_anim_docs.py` passes. THE glossary SHALL define any new term.
2. THE docs SHALL say that the taskbar behaviour was checked on the real image, citing the probe,
   and SHALL state what was and was not checked (open questions 1, 7, 8, 9).
3. THE unit tests SHALL use the existing stand-in guest (`FakeVM` in `test_anim.py`) and cover:
   each part applied after a revert; the tray off again after `Backdrop`; presets with overrides;
   `"blank"` and `"stock"` unchanged; `pointer_visible`; the warning (named option, named part,
   once per class, shown under default filters); and the `UsageError` and `DesktopError` cases.
4. A VM test SHALL cover each part's read-back, windows opened after `buttons` is off, and that
   `scene.work_area` is unchanged when only taskbar children are off. WHERE no prepared image
   exists, THE pull request SHALL say `VM tests: not run (no prepared image on this machine)`.
5. THE feature SHALL NOT edit `docs/status.md`.

## Out of scope

- A mid-scene action that changes the options (owner's answer 5). Options are per scene.
- Taskbar fields in state files (owner's answer 4).
- Start as a part of its own, and a taskbar that is shown but disabled. (First draft assumption
  A1, kept: it is a different feature.)
- Dialog options (button labels, active captions) and other raw guest calls.
- A per-window "keep off the taskbar" option. `buttons` off covers it.
- Any change to prep, the answer file, `ready.py` or the `ready` snapshot.
- Animated or timed taskbar changes, and moving or resizing the taskbar.
- Audio, other resolutions as a feature, and programs that are not on the disc (product scope).

## Assumptions

- A1. A part that is off is hidden only (`SW_HIDE`), except the whole taskbar, which is also
  disabled as `blank` does today. The probe measured hiding only.
- A2. The warning is issued when the scene class is defined or at the start of `run`. Either
  gives once per class. The design decides which.
- A3. The tree's `pointer` on the stock desktop is applied by the same one-time swap as on blank,
  after each revert, which is the pattern the module notes allow.

## Open questions

1. **Quick launch off on its own.** Not probed: `ToolbarWindow32` hidden while `ReBarWindow32`
   stays. The band may leave a gripper or an empty band, or the buttons may shift. Probe before
   the design. If it looks wrong, the design can hide the whole rebar only when both children are
   off, and say so in the docs.
2. **Blank steps that belong to no part.** The black colour, the disabled desktop window (no
   right-click menu) and the animation, gradient caption and hot tracking switches have no part
   in the tree. Options: they belong to the `"blank"` preset only; or the disabled desktop window
   goes with `icons` off; or animations become an option (see question 5). Owner to decide, and
   what blank with a taskbar then does about each.
3. **`pointer_visible` against the tree.** What happens when a scene sets both `pointer_visible`
   and a `pointer` option and they differ: which wins, or a `UsageError`. Also whether the
   attribute's present default (not verified here) would hide the pointer on stock if mapped
   naively; Requirement 2.7 says it must not.
4. **Icons and pointer on the stock desktop.** Not probed: hiding the icons on stock (blank
   already does), and the pointer on stock. Docs say the stock desktop always draws the pointer,
   and `pointer_visible` applies to blank only today. Read `desktop.py` and probe why the pointer
   is set once per desktop before the design.
5. **Animations as an option.** The stock desktop keeps menu animations, so its menu timing
   follows the guest clock. Whether the animation switches become a part or an option is open.
6. **Stale section captures.** Options are not hashed for section captures. Since they are
   applied again on every Set, a section run alone gets the current options. Is that enough, or
   should a changed desktop option make a capture stale? (This also covers the `desktop` string
   today, per the `lazy:` marker.)
7. **Settling the tray after the clock is hidden.** The probe saw the tray shrink only after a
   colour change. Which call settles it without a colour change is unknown.
8. **Wallpaper and display changes.** Whether the `SPI_SETDESKWALLPAPER` / `WM_SETTINGCHANGE`
   broadcast from `set_wallpaper`, or a display mode change, shows hidden parts again. Probe.
9. **Other resolutions.** The probe ran at 800x600 only. Layout at 640x480, 1024x768 and
   1280x1024 is unchecked.
10. **Warning visibility in the CLI.** Whether `art98 render` runs the scene in a process whose
    stderr reaches the user with default filters, or filters warnings itself. Not verified.

## Owner decisions on the open questions (2026-11-20)

- **Question 2:** the black colour, the disabled desktop window and the animation, gradient
  caption and hot tracking switches stay steps of the `"blank"` preset only. Blank with a part
  turned back on still does them. No new part or option.
- **Question 3:** when `pointer_visible` and the tree's `pointer` differ, the tree wins, and a
  warning (Requirement 6) says `pointer_visible` is ignored.
- **Question 5:** animations don't become an option in this spec.
- **Question 6:** enough for now. The `lazy:` marker stays; a section run alone gets the
  current options.
- **Question 10, checked:** `art98 render` loads the scene in its own process (`_load_scene` in
  `core/art98/cli.py`) and sets no warning filters, so a `UserWarning` reaches stderr. Python's
  default filter shows a warning once per message and code line, not once per scene class, so
  "once per class" (Requirement 6.5) needs the class name in the message or art98's own
  de-duplication. `pointer_visible` defaults to `False`.
- **Questions 1, 4, 7, 8 and 9** are probed on the VM before the design.

## Owner decisions on the design (2026-11-20)

- The form is flat options on `Desktop` with implicit levels, not nested values: Requirement 1.11
  and Requirement 6 are amended, and 6.8 now leaves a misspelled keyword to Python's `TypeError`.
  The level table and the warning texts are in `design.md`. Whether an option under a preset's off
  option warns is a recommendation there (decision 1), which Requirement 6.1 follows.
