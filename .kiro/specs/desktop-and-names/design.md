# Design: one form of desktop, and searchable names

Requirements: [requirements.md](requirements.md). This replaces the draft `docs/design/naming-plan.md`
on `feat/desktop-options`, which was never merged.

## Part 1: the desktop

### Public shape

```python
class Scene:
    desktop: Desktop = Desktop()      # blank

class MyScene(Scene):
    desktop = Desktop("stock")
    # was: desktop = "stock"

class Pointed(Scene):
    desktop = Desktop(pointer=True)
    # was: pointer_visible = True
```

| 0.2.0 | Now |
|---|---|
| nothing, or `desktop = "blank"` | nothing, or `desktop = Desktop()` |
| `desktop = "stock"` | `desktop = Desktop("stock")` |
| blank with `pointer_visible = True` | `desktop = Desktop(pointer=True)` |
| stock with `pointer_visible`, either value | `desktop = Desktop("stock")` (it did nothing) |

`Desktop` is exported from `art98.anim`, and every recipe already imports `*` from it.

### `desktop.py`

`resolve_desktop(desktop: Desktop, owner: str) -> tuple[Parts, list[str]]`. The `str` branch, the
type check, the `pointer_visible` parameter and the pointer note go. The preset and option checks
stay, because they need `owner` for the message.

### `scene.py`

- One module function replaces `_desktop_of` and `check_desktop`: `resolve_scene_desktop(scene)`. It
  refuses a non-`Desktop`, then calls `resolve_desktop`.
- `RETIRED["pointer_visible"]` gives the message. `pin_legacy(cls)` covers classes; `run` checks
  `vars(self)` against `RETIRED` too, for instances.
- The two copies of the warning loop become one helper, `warn_desktop(notes, stacklevel)`. With no
  pointer note, its rule is: warn when `"desktop" in vars(...)`. It keeps `stacklevel` pointing at the
  author's line.
- `run` sets `self._resolved = (self.desktop, parts)`. `prepare_desktop` uses it and refuses a
  changed `self.desktop` (compared with `!=`; `Desktop` is frozen). Outside a run `_resolved` is None
  and it resolves on the spot. `run` sets it back to None when it ends, also on an error.

Part 2 renames these internals; the names above are Part 1's.

### Error texts

```text
MyScene.desktop = "stock": write Desktop("stock")
MyScene.desktop 5: use a Desktop(...)
MyScene.pointer_visible: removed. Write desktop = Desktop(pointer=True)
MyScene.desktop changed during the run. Set it before run
```

## Part 2: the rules

A tracked variable is `<scope>_<base>`.

1. One idea, one base. Never shorten or reword it. Two values of one idea in the same scope get a
   word in front of the base: `full_main`, `coarse_main`.
2. The scope is the function or class name, never a description.
3. Each scope replaces the last one, even if the value is unchanged. Never stack scopes.
4. Write both in full, even when words repeat: `apply_desktop_desktop_parts`.
5. No clashes with a function, class, method, module or a variable in another scope.
6. Renaming a function renames its variables in the same commit.
7. Australian English, except names fixed by outside code.

| Where | Example with base `notes` |
|---|---|
| function `resolve` / `_resolve` | `resolve_notes` / `_resolve_notes` |
| method `Scene.run` / `Scene._apply` | `scene_run_notes` / `scene__apply_notes` |
| `Scene.__init__`, or any dunder | `scene_init_notes` |
| `inner` inside `outer` | `outer_inner_notes` |
| private attribute of `Scene` | `self._scene_notes` |
| module constant: base in capitals, no scope; a word may go in front | `NOTES`, `STOCK_NOTES` |

Class names go to snake_case. Inherited: the class that defines it. A variable read from an outer
function keeps its name. Never prefixed: those in Requirement 6.3, and anything not on the base list.
A value goes on the list when its idea crosses a function or class boundary.

`guest` and `scene` stay off the list: each is one object, under one name, everywhere.

### The base list and its test

`docs/design/code-names.md` is one table per module group, of base, meaning and type.
`core/tests/test_code_names.py` reads it and walks the AST of the modules already renamed, listed in
the same file. In each function it takes every name bound by a parameter or assignment, and fails
when the name ends in `_<base>` or equals a base but isn't `<scope>_<base>`. The longest matching
base wins, so `full_main` isn't checked as `main`. Public parameters are exempt through a list in
the same file, each with the page that documents it. It can't see a base that was reworded, so
Requirement 7.2's record and the review cover that.

### Desktop bases

| Base | Meaning |
|---|---|
| `desktop` | The scene's `Desktop`, as its author wrote it |
| `desktop_owner` | The option's name in messages, such as `MyScene.desktop` |
| `desktop_parts` | The `DesktopParts` it resolves to |
| `desktop_notes` | Warning texts about it |
| `desktop_problems` | Ways the guest differs from the parts |
| `desktop_state` | A state file's `desktop` (`DesktopState`) |
| `taskbar_children` | Names of the taskbar children to touch |
| `taskbar_child_hwnds` | Their window handles, by name |
| `taskbar_hwnd`, `tray_hwnd`, `progman_hwnd`, `icons_hwnd` | Window handles |

### Desktop declarations

| File | Now | New |
|---|---|---|
| `desktop.py` | `Parts` | `DesktopParts` |
| `desktop.py` | `STOCK_PARTS`, `BLANK_PARTS` | `STOCK_DESKTOP_PARTS`, `BLANK_DESKTOP_PARTS` |
| `desktop.py` | `check_parts` | `check_desktop_parts` |

### Desktop variables

| Function | Now | New |
|---|---|---|
| `resolve_desktop` | `desktop`, `owner`, `notes` | `resolve_desktop_desktop`, `resolve_desktop_desktop_owner`, `resolve_desktop_desktop_notes` |
| `resolve_desktop` | `Parts(...)` in the return | `resolve_desktop_desktop_parts` |
| `resolve_scene_desktop` | `scene.desktop`, owner text | `resolve_scene_desktop_desktop`, `resolve_scene_desktop_desktop_owner` |
| `warn_desktop` | `notes` | `warn_desktop_desktop_notes` |
| `Scene.__init_subclass__`, `Scene.run` | `notes` | `scene_init_subclass_desktop_notes`, `scene_run_desktop_notes` |
| `Scene.run` | `parts` | `scene_run_desktop_parts` |
| `Scene` | `self._resolved` | `self._scene_desktop`, `self._scene_desktop_parts` |
| `Scene.prepare_desktop` | parts, inline | `scene_prepare_desktop_desktop_parts` |
| `off_children` | `parts` | `off_children_desktop_parts` |
| `taskbar_windows` | `taskbar`, `tray` | `taskbar_windows_taskbar_hwnd`, `taskbar_windows_tray_hwnd` |
| `taskbar_windows` | `names`, `found` | `taskbar_windows_taskbar_children`, `taskbar_windows_taskbar_child_hwnds` |
| `apply_desktop` | `parts`, `problems` | `apply_desktop_desktop_parts`, `apply_desktop_desktop_problems` |
| `apply_desktop` | `taskbar`, `desk`, `icons` | `apply_desktop_taskbar_hwnd`, `apply_desktop_progman_hwnd`, `apply_desktop_icons_hwnd` |
| `apply_desktop` | `children`, `handles` | `apply_desktop_taskbar_children`, `apply_desktop_taskbar_child_hwnds` |
| `check_desktop_parts` | the same seven | `check_desktop_parts_` and the same bases |
| `shell_windows` | `taskbar`, `desktop`, `icons` | `shell_windows_taskbar_hwnd`, `shell_windows_progman_hwnd`, `shell_windows_icons_hwnd` |
| `set_colour` | `taskbar`, `icons`, `tray` | `set_colour_taskbar_hwnd`, `set_colour_icons_hwnd`, `set_colour_tray_hwnd` |
| `apply_state` and others in `setstate.py` | `desk` | `<function>_desktop_state` |

Left alone: `written`, `base`, `effective` and `rebar`, which never leave their function;
`DesktopError(problems, lead)` and `.problems`, which are in the scene API docs; a `_`-prefixed
unused value.

### The other modules

The same steps for each group, as its own pull request:

1. **Trace.** List every value that crosses a function boundary, its names along the way and its
   type. Write it to `.kiro/specs/desktop-and-names/trace-<group>.md`, with a proposed base, or "left
   alone" and why.
2. **Owner approves** the bases. Nothing is renamed before that.
3. **Rename** declarations, then variables, one base per commit.

| Group | Modules | Names to settle (functions that take them, in all of core and setup) |
|---|---|---|
| A | `guest/` | `data` 17, `hwnd` 17, `timeout` 21, `path` 46, `command`, `pid`, `sock`/`conn`, `file`/`files` |
| B | `state.py`, `anim/` | `value` 12, `where`, `what`, `state`, `path`, `name` 34, `id`, `seconds`/`run_time` |
| C | `base/`, `actions/` | `target`, `point`/`at`, `window`/`hwnd`, `title`/`label`/`text`, `size`/`width`/`height` |
| D | `output/` | `path`/`output`/`source`, `stage`, `seconds`/`hold`, `count`/`index` |
| E | `session.py`, `settings.py`, `cli.py`, `legacy.py`, `container/` | `work`/`work_dir`, `settings`, `engine`, `bridge`/`guest`, `log` |

Generic names such as `value`, `data`, `path` and `name` can't be bases: each covers several ideas.
The trace splits them (a host path, a guest path and a state's path are three).

Most constructors in group C are public, so many of its parameters stay bare.

### Cost

Names get long, and lines wrap. An earlier simulation on `desktop.py`, with shorter names than these,
went from 511 lines to 560.

## Testing

- Part 1: unit tests for every requirement; the 13,122-case test loses its `pointer_visible` axis (to
  4,374); the guest-call order tests keep their assertions. Then the VM tests and `tools/check_docs.py`.
- Part 2: unit tests and lint after every commit; the VM tests once per group. Compare message
  strings before and after: the set of string literals in each renamed module must not change, apart
  from docstrings.

## Owner decisions

Approved 2026-11-23, as written.

| # | Question | Decision |
|---|---|---|
| 1 | `self.desktop` changed during a run | An error (Requirement 3.2) |
| 2 | Is `setup/art98_setup/` renamed too? | Not now: it makes prep and the snapshot |
| 3 | The order of groups | A to E: callers rename after what they call |
| 4 | Do features wait for all of Part 2? | They wait for Part 1 and the desktop rename only. Desktop icons then starts under the new rules, and groups A to E follow |
