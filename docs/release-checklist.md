# Release checklist

A hand-run list for checking a release. Tick a box only with evidence: command output, or a file you looked at. Note `/proc/pressure/cpu` next to any timing.

## Clean checkout

- [ ] `git clone <repo-url> 98artware && cd 98artware && uv sync`

## Setup

- [ ] `uv run art98 doctor` reports the backend you will use as usable.
- [ ] `uv run art98 up` (container) or `uv run art98 setup` (local), on a machine with the Windows 98 SE disc image (`--iso` gives its path).

## Renders

- [ ] `uv run art98 render examples/blank_start/blank_start.py -o out/blank_start.mp4 --gif out/blank_start.gif`
- [ ] `uv run art98 render examples/mvp/mvp.py -o out/mvp.mp4`

## Frames

- [ ] First frame: the first frame is the finished desktop, not a brighter or half-drawn one.
- [ ] Pointer: the pointer is drawn where the scene puts it.
- [ ] No stray label pixels after window moves.
- [ ] GIF palette: colours match the mp4 with no banding or dither noise.
- [ ] Clips: when the scene cuts, the numbered clips `-01..` are kept beside the output.

## Backends

- [ ] `uv run art98 render examples/mvp/mvp.py -o out/mvp.mp4 --backend local`
- [ ] `uv run art98 render examples/mvp/mvp.py -o out/mvp.mp4 --backend container`

## Tests

- [ ] `.venv/bin/python -m pytest core/tests setup/tests -q --ignore=core/tests/test_stage.py --ignore=core/tests/test_qemu.py`
- [ ] `. .tools/env.sh && .venv/bin/python -m pytest core/tests/test_stage.py core/tests/test_qemu.py -q`
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
