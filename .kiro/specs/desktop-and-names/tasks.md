# Tasks: one form of desktop, and searchable names

Requirements: [requirements.md](requirements.md). Design: [design.md](design.md). The design
and its four decisions were approved 2026-11-23.

## How to read this list

- `UNIT`, run by every task, with `uv run ruff check core setup tools && uv run ruff format --check core setup tools`:

  ```bash
  uv run python -m pytest core/tests setup/tests -q --ignore=core/tests/test_stage.py --ignore=core/tests/test_stage_scenes.py --ignore=core/tests/test_qemu.py
  ```

- Tasks run in order. Each PR starts from `dev` after the one before it merges.
- Don't touch `docs/status.md`, `work/`, prep, the `ready` snapshot, `examples/`, `experiments/` or
  other specs. Don't run `art98 up` or `art98 setup`. Don't commit or push; the owner does.
- Rename with a code-aware tool, never text replace. Messages and attribute names hold the same words.

## PR 1: one form of desktop

- [ ] 1. Only a `Desktop` is accepted
  - Files: `core/art98/desktop.py`, `core/art98/anim/scene.py`, tests.
  - `resolve_desktop` loses its `str` branch; `resolve_scene_desktop` replaces `_desktop_of` and
    `check_desktop` and refuses anything else, with the design's texts. `Scene.desktop = Desktop()`.
  - Update the string form in `test_desktop.py`, `test_desktop_options.py`, `test_stage.py`,
    `test_stage_scenes.py` and `drift_check.py`, and in the recipes that write it, in this task, so
    `UNIT` stays green. Keep every assertion about the guest. The "teal" tests become refusals.
  - Carry the `set_colour` docstring from `5763b92` (what the desktop colour is).
  - _Requirements: 1, 4_
- [ ] 2. `pointer_visible` is retired
  - `RETIRED`, the instance check in `run`, no pointer note, no `pointer_visible` parameter. Update
    `blank_start.py` and the tests; remove the tests of the two disagreeing.
  - `warn_desktop` replaces both warning loops. A test checks each warning's file and line.
  - _Requirements: 2, 3.4, 4_
- [ ] 3. Resolved once per run
  - `_resolved` as in the design. Tests: one resolve in a run with a display change; a changed
    `desktop` is refused; a second run resolves again; a failed run clears it; `prepare_desktop`
    outside a run works.
  - _Requirements: 3_
- [ ] 4. Docs and changelog
  - `README.md`, `AGENTS.md`, `docs/scenes/*`, `docs/glossary.md`, `docs/design/blank-start.md`,
    decision text in `docs/design/decisions.md`, `.kiro/steering/tests.md`, `CHANGELOG.md`
    ("Changed" and "Removed", with the design's table). Every sample uses the new form.
  - Check: `grep -rnE 'desktop *= *["'"'"']|pointer_visible' core recipes docs README.md AGENTS.md .kiro/steering`
    shows only `RETIRED`, its tests, the refusal tests, the changelog and `docs/archive/`.
  - _Requirements: 4.2_
- [ ] 5. **[VM]** Stage tests and doc samples
  - `test_stage.py`, `test_stage_scenes.py`, `tools/check_docs.py`. Report any difference.
  - _Requirements: 4.1_

## PR 2: the rules, and the desktop names

- [ ] 6. The rules in the repo
  - `CONTRIBUTING.md` "Code style" gets "Variable names" (rules, scopes, exemptions); a link from
    `AGENTS.md` "Conventions"; `docs/design/code-names.md` with the desktop bases.
  - _Requirements: 5_
- [ ] 7. Desktop declarations
  - The design's table, with callers, tests and `docs/diagrams/function-tree.drawio`.
  - _Requirements: 6_
- [ ] 8. Desktop variables
  - The design's table, one commit's worth per base, `desktop.py` then `scene.py` then
    `setstate.py`. `UNIT` after each. Docstrings and comments follow.
  - Compare string literals before and after.
  - _Requirements: 6_
- [ ] 9. The test
  - `core/tests/test_code_names.py`, for `desktop.py` whole and the desktop bases in `scene.py` and
    `setstate.py`. Show it failing on one wrong name per row of the scopes table.
  - _Requirements: 7.1_
- [ ] 10. **[VM]** Stage tests
  - _Requirements: 6.4_

Desktop icons can restart here (owner decision 4).

## PRs 3 to 7: the other groups

One PR for each group in the design, A to E. For each:

- [ ] 11. A: `guest/`
- [ ] 12. B: `state.py`, `anim/`
- [ ] 13. C: `base/`, `actions/`
- [ ] 14. D: `output/`
- [ ] 15. E: `session.py`, `settings.py`, `cli.py`, `legacy.py`, `container/`

Each one is:

1. Write `trace-<group>.md`. **Stop for the owner's approval of the bases.**
2. Add the bases to `code-names.md`; rename declarations, then variables, one base per commit.
3. Add the modules to the test. Compare string literals.
4. **[VM]** Stage tests; for A and E also `test_qemu.py`, and the container tests that group covers.

_Requirements: 5.3, 6, 7_

## Coverage

| Requirement | Tasks |
|---|---|
| 1 | 1 |
| 2 | 2 |
| 3 | 2, 3 |
| 4 | 1, 2, 4, 5 |
| 5 | 6, 11-15 |
| 6 | 7, 8, 10, 11-15 |
| 7 | 9, 11-15 |
