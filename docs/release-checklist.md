# Release checklist

A hand-run list for checking a release. A release is a git tag `vX.Y.Z` and a GitHub release. No wheel or sdist is uploaded: art98 runs from a checkout and a wheel can't find `guest/build`. Tick a box only with evidence: command output, or a file you looked at. Note `/proc/pressure/cpu` next to any timing.

## Clean checkout

- [ ] `git clone https://github.com/StanLukuvka/98artware 98artware && cd 98artware && uv sync`
- [ ] The Python version used is noted here: `uv run python --version`.

## Setup

- [ ] `uv run art98 doctor` reports the tools you need as usable.
- [ ] `uv run art98 up --iso <path>` (installs in the container), or `uv run art98 setup --iso <path>` (installs on the host) followed by `uv run art98 up`, on a machine with the Windows 98 SE disc image.

## Renders

- [ ] `uv run art98 render recipes/scenes/blank_start/blank_start.py -o out/blank_start.mp4 --gif out/blank_start.gif`
- [ ] `uv run art98 render recipes/scenes/mvp/mvp.py -o out/mvp.mp4`

## Frames

- [ ] First frame: the first frame is the finished desktop, not a brighter or half-drawn one.
- [ ] Pointer: the pointer is drawn where the scene puts it.
- [ ] No stray label pixels after window moves.
- [ ] GIF palette: colours match the mp4 with no banding or dither noise.
- [ ] Clips: when the scene cuts, the numbered clips `-01..` are kept beside the output.

## VM service

- [ ] `uv run art98 vm start`, then `uv run art98 vm status` prints `up since` and `ready snapshot: yes`.
- [ ] `uv run art98 render recipes/scenes/mvp/mvp.py -o out/mvp.mp4`, then `uv run art98 vm stop`.

## Tests

- [ ] Unit tests: `uv run python -m pytest core/tests setup/tests -q --ignore=core/tests/test_stage.py --ignore=core/tests/test_stage_scenes.py --ignore=core/tests/test_qemu.py`
- [ ] VM tests, with `art98 vm start` running: `uv run python -m pytest core/tests/test_stage.py core/tests/test_stage_scenes.py -q`
- [ ] QEMU tests, with QEMU on `PATH` (or your local build sourced): `uv run python -m pytest core/tests/test_qemu.py -q`
- [ ] `uv run ruff check .`
- [ ] `uv run python tools/check_docs.py`

## Tree hygiene

- [ ] `git ls-files | grep -c '^work/'` prints `0`.
- [ ] `git ls-files | grep -E '\.(qcow2|iso|img)$'` prints nothing.
- [ ] `LICENSE` is present.
- [ ] `git log --format=%B | grep -ci "co-authored-by\|generated with"` prints `0`.
- [ ] The version in `pyproject.toml` matches the tag.
- [ ] `git status` is clean, and `git status --ignored` and `git ls-files --others` show nothing untracked that is fit to leak.
- [ ] `art98.toml` equals the defaults in `docs/setup/config.md` (no `transport`, `token_file` or `connect`).
- [ ] `CHANGELOG.md` has an entry for this version, with its known limits.

## Release

- [ ] The tag `vX.Y.Z` is on the commit that was checked, and is pushed.
- [ ] The GitHub release is published from the tag, with the changelog entry as its notes.
- [ ] No wheel or sdist is uploaded or attached (`dist/` is not part of the release).

## Busy host

- [ ] With another heavy job running on the host, run `uv run art98 render recipes/scenes/mvp/mvp.py -o out/mvp.mp4` once. Note the timing next to `/proc/pressure/cpu`.

---

`work/` holds installed copies of Windows 98 and must never be committed or uploaded.
