---
inclusion: fileMatch
fileMatchPattern: ["core/tests/**", "setup/tests/**"]
---

# Tests

## Which tests need what

| Test files | Needs |
| --- | --- |
| `core/tests/test_stage.py`, `test_stage_scenes.py` | A running VM service (`art98 vm start`) and a prepared image in `work/` |
| `core/tests/test_qemu.py` | `qemu-system-i386` on `PATH` (no Windows) |
| `core/tests/test_agent_wine.py` | Wine |
| Everything else in `core/tests` and `setup/tests` | Nothing |

Unit tests, with no VM:

```bash
uv run python -m pytest core/tests setup/tests -q --ignore=core/tests/test_stage.py --ignore=core/tests/test_stage_scenes.py --ignore=core/tests/test_qemu.py
```

VM tests:

```bash
uv run python -m pytest core/tests/test_stage.py core/tests/test_stage_scenes.py -q
```

CI has no VM, so a green CI run does not show that a change works on Windows 98.

## Writing tests

- **Reuse the stand-in guests**; don't write new fakes. They are `FakeGuest`, `FakeSession` and
  `FakeVM` in `test_anim.py`, `GuestWithFiles` in `test_picture.py`, `NotepadGuest` in
  `test_notepad.py`, `FakeEngine` in `test_service.py` and `test_freshness.py`, and
  `serve_harness.py` for the container server.
- **Teach a stand-in only what Windows was seen to do** on the real image.
- **Name a test after the behaviour it checks, as a sentence**:
  `test_a_wrong_hash_says_what_it_should_be`, not `test_hash_2`.
- A test that needs a tool skips itself when the tool is missing.
- A VM test is marked `stage` and releases the VM when it ends (`with attach()` or the `booted`
  fixture), so a failing test never leaves the VM locked.
- A fix comes with a test that fails without it.
- Some tests guard the code's layout: `test_win32.py` fails on a Win32 constant defined outside
  `core/art98/guest/win32.py`, `test_units.py` on a built-in `round` or `math.hypot` in the scene layer, and
  `test_errors.py` on an error that doesn't inherit `Art98Error`. Fix the code, not the guard.
- `conftest.py` pins scenes to `desktop = Desktop("stock")` because the fakes don't model the blank
  start. `test_desktop.py` covers the blank start.

## Property-based tests

Property-based tests suit the pure code with no guest I/O: rate functions, vectors, boxes and
rounding in `core/art98/base/`, the protocol encoding in `core/art98/guest/protocol.py`, and
state parsing in `core/art98/state.py`. A good property for saved states: `dump_state` writes the
same bytes for the same state whatever order its keys came in, and what it writes loads back
through `load_state` as the same state. A test library like
Hypothesis goes in the `dev` dependency group, never in `[project] dependencies`, because art98
has no runtime dependencies.
