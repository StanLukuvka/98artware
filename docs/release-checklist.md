# Release checklist

A hand-run list for checking a release. Tick a box only with evidence: command output, or a file you looked at. Note `/proc/pressure/cpu` next to any timing.

## Clean checkout

- [ ] `git clone <repo-url> 98artware && cd 98artware && uv sync`

## Setup

- [ ] `uv run art98 doctor` reports the tools you need as usable.
- [ ] `uv run art98 up --iso <path>` (installs in the container), or `uv run art98 setup --iso <path>` (installs on the host) followed by `uv run art98 up`, on a machine with the Windows 98 SE disc image.

## Renders

- [ ] `uv run art98 render examples/blank_start/blank_start.py -o out/blank_start.mp4 --gif out/blank_start.gif`
- [ ] `uv run art98 render examples/mvp/mvp.py -o out/mvp.mp4`

## Frames

- [ ] First frame: the first frame is the finished desktop, not a brighter or half-drawn one.
- [ ] Pointer: the pointer is drawn where the scene puts it.
- [ ] No stray label pixels after window moves.
- [ ] GIF palette: colours match the mp4 with no banding or dither noise.
- [ ] Clips: when the scene cuts, the numbered clips `-01..` are kept beside the output.

## VM service

- [ ] `uv run art98 vm start`, then `uv run art98 vm status` prints `up since` and `ready snapshot: yes`.
- [ ] `uv run art98 render examples/mvp/mvp.py -o out/mvp.mp4`, then `uv run art98 vm stop`.

## Tests

- [ ] Unit tests: `uv run python -m pytest core/tests setup/tests -q --ignore=core/tests/test_stage.py --ignore=core/tests/test_stage_scenes.py --ignore=core/tests/test_qemu.py`
- [ ] VM tests, with `art98 vm start` running: `uv run python -m pytest core/tests/test_stage.py core/tests/test_stage_scenes.py -q`
- [ ] QEMU tests, with QEMU on `PATH` (`. .tools/env.sh` if you keep a local build): `uv run python -m pytest core/tests/test_qemu.py -q`
- [ ] `uv run ruff check --exclude work .`
- [ ] `uv run python tools/check_docs.py`

## Tree hygiene

- [ ] `git ls-files | grep -c '^work/'` prints `0`.
- [ ] `git ls-files | grep -E '\.(qcow2|iso|img)$'` prints nothing.
- [ ] `LICENSE` is present.
- [ ] `git log --format=%B | grep -ci "co-authored-by\|generated with"` prints `0`.
- [ ] The version in `pyproject.toml` is bumped.

## Busy host

- [ ] With another heavy job running on the host, run `uv run art98 render examples/mvp/mvp.py -o out/mvp.mp4` once. Note the timing next to `/proc/pressure/cpu`.

---

`work/` holds the product key and must never be committed or uploaded.
