# Requirements: desktop icons

## Introduction

A scene can show the desktop icons the `ready` snapshot has, or hide them all. It cannot put an
icon of its own on the desktop. The recipes that need one (the B9 scene in
`docs/design/inspiration.md`: "My Briefcase" and two labelled folders) have no way to do it, and
a state file refuses `desktop.icons` with "desktop icons come after this milestone".

This feature adds fake desktop icons. A fake icon is a real item in Explorer's desktop list, with
a label and an image the scene chooses, at a place the scene chooses. Its image is one already on
the guest (an icon in a DLL or EXE) or one the scene provides (an `.ico` or a 32x32 `.png` on the
host). Fake icons can be saved in a state and captured at a section boundary.

The probes in `experiments/desktop-icons/README.md` (run 2026-11-22 on the real VM) settle how:
a folder on the desktop with a `desktop.ini` naming the image. It shows with no shortcut arrow,
can be placed anywhere, and goes with a revert.

### Source facts

From `experiments/desktop-icons/README.md`:

- A folder in `C:\WINDOWS\DESKTOP` with the system attribute and a hidden, system `desktop.ini`
  (`[.ShellClassInfo]`, `IconFile`, `IconIndex`) shows as an item with that image and the folder's
  name as its label, with no arrow. A `.url` file gets the shortcut arrow.
- `SHChangeNotify(SHCNE_MKDIR)` makes it show in 0.07 s. `SHCNE_RMDIR` after removing it makes it
  go in 0.06 to 0.21 s.
- `LVM_SETITEMPOSITION` places an item exactly; the position is the top left of its 32x32 image.
  Indices change on a refresh, so items are found by label.
- An `.ico` written over a path already shown keeps showing the old image (the icon cache). A
  label removed and added again keeps its first image until a revert.
- Windows 98 shows an all-capital label that fits 8.3 ("PC") softened ("Pc").
- All seven named images `Dialog` uses work as a desktop icon's image.
- Windows 98 ignores an icon's alpha channel. Transparency comes from the AND mask only.
- On the blank desktop, with the list shown and the stock items deleted from it with
  `LVM_DELETEITEM`, a fake icon shows alone. A colour change, `SHCNE_MKDIR`, `SHCNE_RMDIR` and a
  window opening do not bring the stock items back. `SHCNE_UPDATEDIR` brings all seven back.
- A display change keeps fake icons where they are.

This spec builds on desktop options (`.kiro/specs/desktop-taskbar-options/`, branch
`feat/desktop-options`): `Desktop(icons=...)` and `Parts.icons`.

## Glossary

- **Fake icon**: an item on the desktop that a scene made, shown by Explorer like any other.
- **Stock icons**: the items the `ready` snapshot has (My Computer, My Documents, Internet
  Explorer, Recycle Bin, Setup MSN Internet Access, Online Services, Outlook Express).
- **Guest image**: an icon inside a file on the guest, named by the file and an index, such as
  `shell32.dll` 15.
- **Provided image**: an `.ico` or `.png` file on the host that the scene names.
- **Place**: the screen point of the top left of the icon's 32x32 image.
- **Label**: the text under the icon. It is also the folder's name on the guest.

## Requirements

### Requirement 1: A fake icon with a guest image

**User story:** As a scene author, I want to put an icon on the desktop with a label I choose and
an image Windows 98 already has, so that I can stage desktops that aren't the stock one.

#### Acceptance criteria

1. THE Scene SHALL offer a prop `DesktopIcon(label, image, *, at=None)`, added with
   `self.add(icon)` and taken off with `self.remove(icon)`.
2. WHEN `image` is a `(file, index)` pair, THE guest SHALL show the icon at that index of that
   guest file.
3. WHEN `image` is a named key, THE guest SHALL show the guest image the key names. THE keys SHALL
   be the same table `Dialog` uses for its custom icons, kept in one place.
4. WHEN a fake icon is added, THE guest SHALL show it with its label and no shortcut arrow, and
   THE `add` call SHALL return only once Explorer lists it.
5. IF the guest file has no icon at that index, THEN THE Scene SHALL raise `UsageError` naming the
   file and the index, and leave no item behind.

### Requirement 2: A fake icon with a provided image

**User story:** As a scene author, I want to give my own picture for an icon, so that I can show
things Windows 98 has no icon for.

#### Acceptance criteria

1. WHEN `image` is a path to an `.ico` file, THE Scene SHALL use its 32x32 image.
2. WHEN `image` is a path to a `.png` file of exactly 32x32 pixels, THE Scene SHALL use it.
3. THE guest SHALL draw a provided image's transparent pixels as the desktop behind them. A pixel
   is transparent when its alpha is below 128 (PNG, 32-bit ICO) or its AND mask bit is set
   (ICO with fewer bits).
4. IF the file is missing, is not a PNG or ICO, is a PNG of another size, is an ICO with no 32x32
   image, or uses an encoding the converter does not read, THEN THE Scene SHALL raise
   `UsageError` naming the file and the reason, before anything reaches the guest.
5. WHEN two fake icons in one run have different images, THE guest SHALL show each its own
   image.
6. IF a label was used earlier in the run (since the last revert) with a different image, THEN
   THE Scene SHALL raise `UsageError` saying Windows 98 would keep showing the first image, and to
   use another label. The same label with the same image may be added again.

### Requirement 3: Placing a fake icon

**User story:** As a scene author, I want to say where an icon is and lay it out like other props,
so that my desktop looks the way I drew it.

#### Acceptance criteria

1. WHEN `at` is given, THE guest SHALL show the icon's image with its top left at `at`.
2. WHEN `at` is not given, THE icon SHALL be placed by the prop's box, which layout calls
   (`move_to`, `next_to`, `to_edge` and the rest) set before or after `add`. The box SHALL be the
   32x32 image, so its centre is the image's centre.
3. WHEN the box changes after `add` and `apply()` runs, or a frame is drawn, THE guest SHALL show
   the icon at the new place in that one frame.
4. WHEN a scene asks for `icon.animate`, or plays `MoveAlongPath` on it, THE Scene SHALL raise
   `UsageError` saying a fake icon moves only in one frame. `Teleport` works, but not with `size=`: the box stays 32x32. (Animated desktop icons are out of scope, `docs/design/decisions.md`.)
5. WHEN a fake icon is placed, THE Scene SHALL read its place back and raise `GuestError` if it
   differs.
6. IF the place is off the screen, THEN THE Scene SHALL raise `UsageError`.
7. IF adding a fake icon fails after its folder was made, THEN THE Scene SHALL remove the folder
   before raising, so the same `add` can be tried again.

### Requirement 4: Labels

**User story:** As a scene author, I want clear errors about a label Windows can't use, so that I
don't find out from a broken frame.

#### Acceptance criteria

1. IF a label is empty, longer than 80 characters, has characters outside Windows 1252, has any
   of `\ / : * ? " < > |` or a control character, starts or ends with a space or a dot, is a
   reserved DOS device name, or fits 8.3 with capitals and no small letters (Windows 98 would show
   "PC" as "Pc"), THEN THE Scene SHALL raise `UsageError` saying which.
2. IF a label matches, ignoring case, an item already in the desktop list, a stock icon deleted
   from it, or another fake icon on stage, THEN THE Scene SHALL raise `UsageError` naming the
   clash.
3. THE guest SHALL show a long label the way Explorer does: cut to two lines and "...".

### Requirement 5: Fake icons and the desktop options

**User story:** As a scene author, I want fake icons on a blank desktop without the stock ones, so
that the scene shows only my icons.

#### Acceptance criteria

1. WHEN the stock icons are on (`Desktop(icons=True)`, as in `"stock"`), THE guest SHALL show fake
   icons beside them.
2. WHEN the stock icons are off (`"blank"`, or `icons=False`) and the first fake icon is added, THE
   guest SHALL show the fake icons and none of the stock icons.
3. WHEN the stock icons are off and the last fake icon is removed, THE guest SHALL hide the icon
   list again, so the desktop is as the options say.
4. WHILE fake icons are showing on a desktop with the stock icons off, THE stock icons SHALL stay
   away through a colour change (`Backdrop`), a window opening or closing, and adding or removing
   another fake icon.
5. THE Scene SHALL never send a change notice that brings the stock icons back
   (`SHCNE_UPDATEDIR`, `SHCNE_ASSOCCHANGED`).
6. THE desktop SHALL show no focus box or selection on any fake icon after `add`.

### Requirement 6: Saved states and sections

**User story:** As a scene author, I want fake icons in a state file and in section captures, so
that `set_state` and `--section` keep my desktop.

#### Acceptance criteria

1. THE state file SHALL accept `desktop.icons`, a list of icons, each with `id`, `label`, `image`
   and `at`. `image` is `{"guest": ..., "index": ...}` for a guest image (a guest path, never a
   host file) or `{"file": ..., "sha256": ...}` for a provided image, named and hashed as other
   state files are.
2. THE loader SHALL check each icon as Requirements 2 and 4 do, and report every problem at once
   with the field's path, as it does for other fields.
3. WHEN a state with icons is applied, THE guest SHALL show them at their places, and
   `check_state` SHALL raise if one is missing or elsewhere. THE wallpaper pixel check SHALL not
   sample a point an icon or its label covers.
4. WHEN `get_state` runs with fake icons on stage, THE capture SHALL hold each one with its id,
   label, image and place, and copy each provided image beside the state.
5. IF a fake icon on stage has no id at a capture, THEN THE Scene SHALL raise `UsageError` saying
   to add it with `id=`, as it does for windows.
6. THE ids of icons and windows SHALL share one namespace, and `self.prop(id)` SHALL find either.
7. WHEN a provided image file changes, THE section capture built from it SHALL be stale, as for
   other state files.

### Requirement 7: Same frames every run

**User story:** As a scene author, I want an icon scene to render the same frames every run.

#### Acceptance criteria

1. WHEN a scene adds, moves or removes a fake icon, THE change SHALL show in the next frame and
   not before, as for other props.
2. THE guest files SHALL be named by content (a provided image) or by label (the folder), never by
   time or a counter.
3. WHEN a revert happens (`run`'s start, a Set), THE fake icons and their files SHALL be gone and
   their props forgotten.

### Requirement 8: Documentation and tests

#### Acceptance criteria

1. `docs/scenes/scene-api.md` SHALL describe `DesktopIcon`, its images, labels, places, the
   options it meets, its errors, and `desktop.icons` in a state, with a sample that renders.
2. Unit tests SHALL cover the converter, the label rules, the prop against a stand-in guest, and
   the state loader. A VM test SHALL cover a guest image, a provided image, the blank desktop, a
   colour change, a display change through `set_state`, and a capture.
3. THE change SHALL say in its report that the scene-author skill (`skills/art98/SKILL.md`, in the
   Hermes plugin) needs a follow-up.

## Out of scope

- Gliding or animated icons, and recolouring the stock icons.
- Clicking, double-clicking or dragging a fake icon. A double-click opens an empty folder window,
  which tracking reports as an untracked window, as for any window a scene didn't add.
- Removing, moving or relabelling stock icons on a desktop where they are on.
- Images other than ICO and 32x32 PNG. Sizes other than 32x32.
- All-capital short labels such as "PC": Windows 98 softens them, so they are refused.
- Any change to prep, the answer file or the `ready` snapshot.

## Assumptions

- `C:\WINDOWS\DESKTOP` is the desktop folder on the image (measured).
- A provided image is small (a 32x32 24-bit ICO is 3,262 bytes), so `put_file` carries it, not a
  CD.
- feat/desktop-options is merged before the tasks that touch `Parts` start.

## Owner decisions (2026-11-22)

- Provided images: `.ico`, and `.png` at exactly 32x32. A PNG is converted on the host.
- Fake icons go into states and section captures.
- Moves are instant only. `.animate` is refused.
