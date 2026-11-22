# Design: desktop icons

Requirements: `requirements.md` beside this file, with the owner's decisions of 2026-11-22.
Facts: `experiments/desktop-icons/README.md`. Builds on desktop options
(`.kiro/specs/desktop-taskbar-options/`, branch `feat/desktop-options`).

## Overview

A fake icon is a folder on the guest's desktop. Its name is the label. Its `desktop.ini` names
the image: a guest file and index, or an `.ico` art98 copies in. Explorer shows it as an item in
the desktop's `SysListView32`, with no arrow, and art98 places it with `LVM_SETITEMPOSITION`.
A revert removes it.

Four pieces:

1. `core/art98/guest/icons.py`: reads an ICO or a 32x32 PNG on the host and writes the one ICO
   Windows 98 draws well (32x32, 24-bit, AND mask). Pure, no guest.
2. `core/art98/desktop.py`: the guest side. Make and remove the folder, list the items by label,
   place one, delete the stock items, show or hide the list.
3. `core/art98/actions/desktop_icon.py`: the `DesktopIcon` prop.
4. `state.py`, `setstate.py` and `Scene.get_state`: `desktop.icons` in a state.

## 1. The public shape

```python
from art98.anim import DesktopIcon, Scene, Desktop


class Briefcase(Scene):
    desktop = Desktop("blank")

    def construct(self):
        case = DesktopIcon("My Briefcase", "briefcase.png", at=(40, 40))
        pc = DesktopIcon("This PC", "computer")                    # a named guest image
        pc.next_to(case, DOWN, buff=40)
        old = DesktopIcon("Old Stuff", (r"C:\WINDOWS\SYSTEM\shell32.dll", 4))
        old.next_to(pc, DOWN, buff=40)
        self.add(case, id="case")
        self.add(pc, old)
        self.wait(1)
        old.shift(RIGHT * 200)                                     # one frame, at the next frame
        self.wait(1)
        self.remove(old)
```

`DesktopIcon(label, image, *, at=None)`:

| Argument | Meaning |
| --- | --- |
| `label` | the text under the icon, also the folder's name (section 4) |
| `image` | a key of `SHELL_ICONS`; a `(guest file, index)` pair; or a host path (`str` or `Path`) ending `.ico` or `.png` |
| `at` | `(x, y)`, the top left of the 32x32 image. Left out: `(0, 0)` until a layout call moves it |

The prop's `Box` is the 32x32 image: `x, y = at`, `width = height = 32`. Layout calls work on
that square, so `move_to(point)` centres the image on the point and the label hangs below. The
label's size is not part of the box (it depends on the text, and Explorer cuts it).

A string is a key when it has no `.` and no path separator; otherwise it is a path. An unknown key
raises `UsageError` listing the keys.

### One table of named guest images

`Dialog.CUSTOM_ICONS` moves to `core/art98/guest/win32.py` as `SHELL_ICONS` (same seven entries,
same comment on where each was seen). `Dialog.CUSTOM_ICONS` stays as a name for it
(`CUSTOM_ICONS = SHELL_ICONS`) so scenes and `test_dialog.py` keep working. One home per thing
(`.kiro/steering/programs-and-actions.md`).

## 2. The image converter (`core/art98/guest/icons.py`)

```python
ICON_SIZE = 32

def decode_image(data: bytes, source: str) -> list[tuple[int, int, int, int]]:
    """1024 RGBA pixels, top row first, from an ICO or a 32x32 PNG. UsageError if it can't."""

def ico_from_pixels(pixels) -> bytes:
    """A one-image ICO: 32x32, 24-bit, with the AND mask set where alpha < 128."""

def guest_icon(data: bytes, source: str) -> bytes:
    """decode_image, then ico_from_pixels. What reaches the guest."""
```

- **PNG.** Signature, `IHDR`, `PLTE`, `tRNS`, `IDAT` chunks, `zlib` from the standard library,
  the five filter types. Accepted: width and height exactly 32, bit depth 8, colour types 2 (RGB),
  6 (RGBA) and 3 (palette, with `tRNS` for alpha), not interlaced. Anything else is a
  `UsageError` that names it ("an interlaced PNG", "a 16-bit PNG", "a 48x48 PNG").
- **ICO.** The directory picks the entry that is 32x32 (a width or height byte of 0 means 256).
  Among several 32x32 entries, the one with the most bits per pixel. An entry starting with the
  PNG signature is decoded as a PNG. A BMP entry: `BITMAPINFOHEADER`, height twice the image,
  1, 4, 8, 24 or 32 bits, no compression, palette for 1/4/8, then the AND mask. For 32-bit, alpha
  below 128 is transparent (the AND mask is ignored, since many 32-bit icons leave it empty); for
  the rest, the AND mask.
- **Output.** Always one 24-bit entry with the AND mask, whatever came in. A transparent pixel is
  written black in the colour part and 1 in the mask, which is what Windows 98 draws as the
  desktop behind it (README: "32-bit icons"). The output for the same input is the same bytes.
- **Where it runs.** On the host, when the prop is built, so a bad file fails before anything
  reaches the guest (Requirement 2.4), and again when a state is loaded.

No new dependency. `pyproject.toml` does not change.

## 3. The guest side (`core/art98/desktop.py`)

New constants go in `core/art98/guest/win32.py`: `LVM_GETITEMCOUNT` (0x1004),
`LVM_DELETEITEM` (0x1008), `LVM_SETITEMPOSITION` (0x100F), `LVM_GETITEMPOSITION` (0x1010),
`LVM_GETITEMTEXTA` (0x102D),
`SHCNE_MKDIR` (0x8), `SHCNE_RMDIR` (0x10), `SHCNF_PATHA` (0x1), `SHCNF_FLUSH` (0x1000),
`FILE_ATTRIBUTE_HIDDEN` (0x2), `FILE_ATTRIBUTE_SYSTEM` (0x4), `VA_SHARED` (0x08000000) if not there
already, and `DESKTOP_FOLDER = r"C:\WINDOWS\DESKTOP"`.

```python
def desktop_items(guest) -> dict[str, tuple[str, int, int, int]]:
    """{label.casefold(): (label, index, x, y)} for every item. Reads through shared memory.

    Keyed ignoring case: Explorer may show a label in other capitals than the folder's name."""

def make_icon_folder(guest, label: str, icon_file: str, index: int) -> None:
    """The folder, its desktop.ini, the attributes, then SHCNE_MKDIR. Nothing else is notified."""

def remove_icon_folder(guest, label: str) -> None:
    """Clear the attributes, delete desktop.ini, RemoveDirectoryA, then SHCNE_RMDIR."""

def place_item(guest, label: str, x: int, y: int) -> None:
    """LVM_SETITEMPOSITION on the item with this label, found fresh each time."""

def delete_items(guest, keep: set[str]) -> None:
    """LVM_DELETEITEM every item whose label is not in `keep` (the stock icons)."""

```

- **Shared memory.** `desktop_items` and `place_item` use one
  `VirtualAlloc(0, 4096, MEM_COMMIT | MEM_RESERVE | VA_SHARED, PAGE_READWRITE)` block, freed in a
  `finally`, as the recipe in `docs/scenes/win32-recipes.md` does. Explorer owns the list, and a
  private pointer can hang the agent.
- **Never `SHCNE_UPDATEDIR` or `SHCNE_ASSOCCHANGED`.** They bring the stock icons back on a blank
  desktop (README, "On the blank desktop"). A comment says so where the notice is sent.
- **The provided image's guest path** comes from `guestfiles.ensure(guest, ico, "ICON.ICO")`,
  which puts it at `C:\ART98\F<7 hex digits of its sha256>\ICON.ICO` as for every other file
  art98 copies in. A new image is a new path, which avoids the icon cache (README: "The icon
  cache").
- **A guest image is checked** before the folder is made, with `ExtractIconA(0, file, index)` and
  `DestroyIcon` on the handle, using `NO_ICON` and `NOT_ICON_FILE` from `dialog.py` (moved to
  `win32.py` beside `SHELL_ICONS`). A miss is `UsageError` (Requirement 1.5). All seven
  `SHELL_ICONS` were measured as desktop icon images (README).
- **Waiting.** After `make_icon_folder`, `wait_for` polls `desktop_items` until the label is listed
  (every 0.05 s, up to `ICON_TIMEOUT = 5.0` s), else `GuestError` naming the label. Removal waits
  the same way for it to go.

### The stock icons when the options have them off

The scene keeps one flag, `Scene._icon_list_shown`. On the first fake icon while
`parts.icons` is off:

1. make the folder and wait for the item (the list is still hidden),
2. `delete_items(guest, keep={labels of fake icons on stage, including this one})`,
3. `ShowWindow(list, SW_SHOW)` (what the probe used), set the flag, and remember the deleted
   labels in `Scene._deleted_stock` for the clash check.

On removing the last fake icon while the flag is set: `ShowWindow(list, SW_HIDE)`, clear the flag
(measured: the list hides, and later adds and removes leave the stock icons away). After a revert
the flag and `_deleted_stock` are cleared with the props.

No item state is cleared: adding with `SHCNE_MKDIR` alone draws no focus box (README). The VM
test checks Requirement 5.6 instead.

`check_parts` does not change: it runs in `prepare_desktop`, before any fake icon exists in a
state or a run. `set_colour` re-hides the list only when it was hidden, so a shown list stays
shown (measured). On the stock preset nothing is deleted and the list is never hidden.

## 4. The prop (`core/art98/actions/desktop_icon.py`)

```python
class DesktopIcon(Prop):
    def __init__(self, label, image, *, at=None): ...
    source: tuple[Path, bytes] | None     # a provided image: for the scene's dependency hash
    guest_image: tuple[str, int]          # what desktop.ini names, set at attach
    def attach(self, scene): ...          # check the label, write files, wait, place, check
    def apply(self): ...                  # move if the box changed since the last apply
    def remove(self): ...                 # remove the folder, wait for it to go
    def refresh(self): ...                # apply() first, as Win does, then read the place back
    def to_state(self, files: Path) -> dict: ...
    @property
    def animate(self): raise UsageError(...)
```

- **Label rules** (Requirement 4), checked in `__init__`: `label_problem(label) -> str | None`,
  beside `id_problem` in `state.py`, so the state loader uses the same rules. It wraps
  `guestfiles.name_problem` (characters, control characters, a trailing space or dot, Windows
  1252, DOS devices) and adds: at most 80 characters, no leading space or dot, and no all-capital
  8.3 name (a base of 1 to 8 and an optional extension of 1 to 3 characters, no space, no small
  letter, at least one capital; README "All-capital short labels change").
- **The clash check** is in `attach`: `desktop_items` once, then a case-insensitive compare with
  the labels it lists, `Scene._deleted_stock`, and the fake icons on stage. The hidden list still
  holds the stock items before the first fake icon, and `_deleted_stock` holds them after.
- **A label used again** (Requirement 2.6): `Scene._icon_images` maps each label (casefolded)
  added since the last revert to its image (the guest pair, or the provided ICO's sha256). A
  different image for a known label raises `UsageError` in `attach`, before the guest is touched.
  Cleared on revert.
- **`attach` order:** label clash and label reuse, guest image check or `ensure` of the converted
  ICO, `make_icon_folder`, then in a `try`: wait, the stock-icon steps of section 3 if they apply,
  `place_item`, `guest.sync()`, read the place back (Requirement 3.5). On any error in the `try`,
  `remove_icon_folder` runs (its own errors suppressed) and the first error is raised
  (Requirement 3.7).
- **Off screen** (Requirement 3.6): the image square must lie inside the screen
  (`scene.space` gives its size). Checked in `apply` and `attach`.
- **`apply`** compares `(pixel(x), pixel(y))` with the last place it set, and calls `place_item`
  only when it changed, then `guest.sync()`. `Scene._apply` already calls `apply` on every prop
  each frame, so a layout call shows on the next frame (Requirement 7.1).
- **`animate`** raises `UsageError`: "a DesktopIcon moves only in one frame: change its place and
  let the next frame show it (animated desktop icons are out of scope, docs/design/decisions.md)".
  `MoveAlongPath` raises the same in `begin` for a target with `one_frame_moves = True` (a class
  attribute `DesktopIcon` sets; `Box` has it `False`). `Teleport` is one frame and works.
- **`refresh`** calls `apply()` first, as `Win.refresh` does (`win.py`, `refresh`), so a pending
  `shift` isn't lost when `next_to` or `get_state` reads the place back.
- **Removing.** `Scene.remove` today sends every prop through `Close`, which takes only a `Win`.
  It becomes: a `Win` goes through `Close` as today; any other prop must be on stage
  (`UsageError` "can't remove ...: it is not on stage", as `Close.begin` says), then gets
  `prop.remove()` and leaves `self.props`. `Close(icon)` still raises `UsageError`.
- **Dependencies.** `Scene.add` records `source` for any prop that has one, not only a `Win`
  (`scene.py` add, the `isinstance(prop, Win)` test), so an edited image makes a capture stale
  (Requirement 6.7).
- **Tracking.** A fake icon has no window, so `check_tracking` ignores it. A double-click's folder
  window is untracked, as today.

## 5. States

### The schema

```json
"desktop": {
  "fill_colour": [0, 0, 0],
  "icons": [
    {"id": "case", "label": "My Briefcase", "at": [40, 40],
     "image": {"file": "case.png", "sha256": "..."}},
    {"id": "pc", "label": "This PC", "at": [40, 120],
     "image": {"guest": "C:\\WINDOWS\\SYSTEM\\shell32.dll", "index": 15}}
  ]
}
```

- `state.py`: `icons` leaves `LATER_DESKTOP` and joins `DESKTOP_FIELDS`. A new frozen dataclass
  `IconState(id, label, at, image: FileRef | tuple[str, int])`, and `DesktopState.icons:
  tuple[IconState, ...] = ()`. `State.files()` adds each provided image after the wallpaper.
- The loader checks: `id` with `id_problem`, unique across icons and windows; `label` with
  `label_problem`, unique ignoring case among the icons; `at` two integers; `image` exactly one of
  the two shapes, unknown keys refused; a file through `self.file(...)` and then `guest_icon` (a
  `UsageError` becomes a problem at `desktop.icons[i].image.file`); a guest path a non-empty
  string and `index` a non-negative integer. Named keys are not used in a state: `get_state`
  writes the resolved pair.
- `_ORDER` in `state.py` gets `"icon": ("id", "label", "at", "image")` and the image keys, and
  `dump_state` walks `desktop.icons` and each nested `image` (it orders only the top, desktop and
  file levels today), so a dumped state reads in a fixed order.

### Applying and checking

- `apply_state`: after the wallpaper and before the windows, each icon is
  `scene.add(DesktopIcon.from_state(icon), id=icon.id)`. The props dict it returns holds icons
  too.
- `wallpaper_sample` avoids the icons too: each icon's cell (its `at` minus (13, 2) to plus
  (45, 51), from the measured rects in README) joins the rectangles it already keeps clear of
  windows and the pointer.
- `check_state`: `icon_problems(guest, state)` reads `desktop_items` once. For each icon: missing
  ("desktop.icons[case]: 'My Briefcase' isn't on the desktop"), or at another place (wanted and
  found, as `window_problems` words it).

### Capturing

`Scene.get_state`: the icons on stage, in `self.props` order, each needing an id
(Requirement 6.5). `DesktopIcon.to_state(files)` writes a provided image to
`files/desktop/icons/<id><suffix>` (the original bytes, the `.png` or `.ico` suffix) and returns
the dict above with the hash. A guest image writes `{"guest", "index"}`.

## 6. Testing

Unit tests, no VM:

- `core/tests/test_icons.py` (converter): PNG colour types 2, 6 and 3 with `tRNS`; each filter
  type; the refusals (size, interlace, 16-bit, grey, not a PNG); ICO entries 4, 8, 24 and 32-bit
  and a PNG entry; the 32x32 pick among several sizes; alpha 127 transparent and 128 opaque;
  same input, same bytes. Test images are built in the test with `zlib` and `struct`, not files.
- `core/tests/test_desktop_icon.py`: `DesktopGuest` (from `test_desktop.py`) learns a desktop
  list: items by label with positions, `CreateDirectoryA`, `RemoveDirectoryA`, `DeleteFileA`,
  `SetFileAttributesA`, `SHChangeNotify` (records the event; `SHCNE_UPDATEDIR` fails the test),
  `put_file`, `ExtractIconA`, `LVM_*`. Cases: each image kind; label rules (including "PC" and
  "TEMP" refused, "MY STUFF" allowed) and clashes; a label reused with another image refused, with
  the same image allowed; placement and read-back; `apply` moves once per change; `icon.shift()`
  then `other.next_to(icon)` keeps the shift; `animate` and `MoveAlongPath` refused, `Teleport`
  works; off-screen refused; a failed wait or read-back removes the folder; blank: stock deleted
  and list shown on the first icon, hidden after the last, a deleted stock label refused; stock:
  nothing deleted; remove; revert forgets.
- `core/tests/test_state.py` and `test_wallpaper_state.py`: the `desktop.icons` loader, problems
  at their paths, round trip through `dump_state`. The two tests that expect
  "desktop.icons: not supported yet" change to expect icons to load.
- `test_dialog.py` keeps passing with `CUSTOM_ICONS` as the shared table.

VM tests (`core/tests/test_stage.py`, next to the desktop ones):

- A guest image and a provided PNG on stock: both listed, at their places, read-back exact.
- On blank: the fake icon is the only item; after `Backdrop`, a Notepad open and close, and a
  second icon added and removed, still the only one(s).
- No fake icon has a focus box or selection after `add` (`LVM_GETITEMSTATE`), on stock and blank.
- A state with icons at 640x480 through `set_state` (the display change runs `prepare_desktop`
  again): the icons at their places and the label background the desktop colour.
- `get_state` then `set_state` of the capture: same items at the same places.

## 7. Docs

- `docs/scenes/scene-api.md`: a "Desktop icons" section (the table in section 1, images, labels,
  places, the options, errors, a sample the docs check renders) and `desktop.icons` under States.
  The line "Icons and the tray are not in a state yet" changes to the tray only.
- `docs/design/state-and-action.md`: the "Icon positions" row of "Not proven yet" goes (measured);
  `desktop.icons` joins the schema.
- `docs/design/decisions.md`: a short entry: fake icons are folders with `desktop.ini`, why not
  `.url` (the arrow) or drawn windows (not Explorer's look), and never `SHCNE_UPDATEDIR`.
- `docs/design/inspiration.md` B9: custom icons are built.
- `docs/glossary.md`: Fake icon, Guest image, Provided image.
- `CHANGELOG.md`: Added `DesktopIcon` and `desktop.icons`.
- `docs/status.md` is left to the coordinator.

## Files touched

| File | Change |
| --- | --- |
| `core/art98/guest/icons.py` | new: the converter |
| `core/art98/guest/win32.py` | constants, `SHELL_ICONS`, `NO_ICON`, `NOT_ICON_FILE` |
| `core/art98/desktop.py` | the guest functions of section 3 |
| `core/art98/actions/desktop_icon.py` | new: `DesktopIcon` |
| `core/art98/actions/programs/dialog.py` | uses the shared table and constants |
| `core/art98/actions/__init__.py`, `core/art98/anim/__init__.py` | export `DesktopIcon` |
| `core/art98/anim/scene.py` | `remove` for non-window props, `source` for any prop, `get_state` icons, `_icon_list_shown`, `_deleted_stock`, `_icon_images` |
| `core/art98/base/animation.py`, `core/art98/base/props.py` | `one_frame_moves`, refused by `MoveAlongPath` |
| `core/art98/state.py` | `IconState`, `label_problem`, the loader, `_ORDER` |
| `core/art98/anim/setstate.py` | apply and check icons |
| tests and docs | sections 6 and 7 |

## Risks

- **Explorer's list after a long run.** Measured for seconds, not minutes. The VM tests run a
  Notepad and a colour change; a scene of several minutes is untested.
- **Unmeasured.** A raw `set_display_mode` mid-scene on the stock desktop with fake icons (the
  probe ran it on blank). The VM test's display pass goes through `set_state`.
- **Fonts and label width.** The box leaves the label out, so `next_to` beside a long label can
  overlap it. The docs say so.
- **The icon cache across reverts.** Names by content mean a changed image gets a new path. An
  image named the same with the same content is the same picture, so a stale entry is right.
