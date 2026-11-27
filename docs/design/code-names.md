# Code names

The bases behind the variable-name rules in
[CONTRIBUTING.md](../../CONTRIBUTING.md#variable-names). This page is for contributors, not scene
authors. Each commit that adds, renames or removes a base updates it.

`core/tests/test_code_names.py` reads four things from this page: the **Checked modules** table,
the **Exempt** table, each **Bases** table, and the example names in the **Scopes** table. It fails
if one of them is missing. Only the **Exempt** table may be empty. **Left alone** is for readers;
the test does not read it.

## Scopes

| Where | Example with base `notes` |
| --- | --- |
| function `resolve` or `_resolve` | `resolve_notes`, `_resolve_notes` |
| method `Scene.run` or `Scene._apply` | `scene_run_notes`, `scene__apply_notes` |
| `Scene.__init__`, or any dunder | `scene_init_notes` |
| `inner` inside `outer` | `outer_inner_notes` |
| private attribute of `Scene` | `self._scene_notes` |
| module constant: base in capitals, no scope; a word may go in front | `NOTES`, `STOCK_NOTES` |

## Checked modules

The test checks the names each module binds against the bases of its group: parameters (lambdas
included), assignments, augmented, annotated and walrus targets, `with` and `except` names,
`import ... as` names, private class-body names and `self._x` stores. Loop and comprehension
variables, public names, `self`, `cls` and `_` names that are never read are not checked.

| Module | Group |
| --- | --- |
| `core/art98/desktop.py` | desktop |
| `core/art98/anim/scene.py` | desktop |
| `core/art98/anim/setstate.py` | desktop |

## Exempt

Public parameters that a caller passes by keyword are not checked. Each row names the function,
the parameter and the page that documents the API. The test skips a parameter only when its
function and name are both a row here. No other name is skipped.

| Where | Parameter | Documented in |
| --- | --- | --- |

The table is empty because no public parameter in the checked modules takes a desktop base, so
none needs an exemption. The test passes with the table empty, which shows that no parameter
there breaks the rule. A new exemption needs its row and the page that documents the parameter.

## Bases: desktop

| Base | Meaning | Type |
| --- | --- | --- |
| `desktop` | The scene's `Desktop`, as its author wrote it | `Desktop` |
| `desktop_owner` | The option's name in messages, such as `MyScene.desktop` | `str` |
| `desktop_parts` | The `DesktopParts` it resolves to | `DesktopParts` |
| `desktop_notes` | Warning texts about it | `list[str]` |
| `desktop_problems` | Ways the guest differs from the parts | `list[str]` |
| `desktop_state` | A state file's `desktop` | `DesktopState`, or the dict written to a state file |
| `taskbar_children` | Names of the taskbar children to touch | `list[str]` |
| `taskbar_child_hwnds` | Their window handles, by name | `dict[str, int]` |
| `taskbar_hwnd` | The taskbar's window handle | `int` |
| `tray_hwnd` | The tray's window handle | `int` |
| `progman_hwnd` | The Progman (desktop) window's handle | `int` |
| `icons_hwnd` | The desktop icon list's window handle | `int` |

## Left alone

These values cross a function boundary, or belong to a public name, but keep their plain names.
The test does not read this table.

| Name | Where | Reason |
| --- | --- | --- |
| `written`, `base`, `effective` | `resolve_desktop` | Never leave the function. |
| `rebar` | `taskbar_windows` | A window handle that never leaves the function. |
| `view` | `shell_windows` | The `SHELLDLL_DefView` handle, used only to find the icon list. |
| `_desk` | `set_colour` | Unused, `_`-prefixed. |
| `_parts` | `Scene.__init_subclass__` | Unused, `_`-prefixed. |
| `problems`, `lead` | `DesktopError.__init__`, `DesktopError.problems` | `DesktopError` is not exported from `art98.anim` (only `Desktop` is). Its callers pass `problems` and `lead` by position, and only the tests read `.problems`. |
