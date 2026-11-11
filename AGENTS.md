# AGENTS.md

This file is for coding agents working on art98. Humans: see [CONTRIBUTING.md](CONTRIBUTING.md).
This file links to it rather than repeating it.

art98 scripts animations on a real Windows 98 SE desktop. A VM runs in QEMU inside a Docker or
Podman container as a long-lived service. A render attaches to it, restores the `ready` snapshot,
drives the guest through an agent that proxies Win32 calls, and records the screen. Terms are in
[docs/glossary.md](docs/glossary.md); the [repo tour](docs/tour.md) walks every file. Why things are
built the way they are is in [docs/design/decisions.md](docs/design/decisions.md), the authority
for design: read the section for the area you touch before changing it.
[docs/status.md](docs/status.md) says what is built and what is open.

## Quick start without a VM

You do not need Windows 98 or a prepared image to work on most of art98. Run everything from the
repository root:

```bash
uv sync
```

```bash
uv run python -m pytest core/tests setup/tests -q --ignore=core/tests/test_stage.py --ignore=core/tests/test_stage_scenes.py --ignore=core/tests/test_qemu.py
```

```bash
uv run ruff check . && uv run ruff format --check core setup tools
```

There are no runtime dependencies; `uv sync` installs the `dev` group (pytest, pycdlib, ruff).
Tests that need a missing tool or image skip themselves. If you keep a local QEMU build outside
`PATH`, load it in each shell before running `test_qemu.py` or host-side setup. `art98 up`,
`art98 vm` and `art98 render` do not need it, because QEMU runs in the container.

## Commands

The unit-test and lint commands are above; CI runs the same commands, except that its test command has no
`test_stage_scenes.py` ignore (that file skips without an image).
VM tests drive the real prepared image. `art98 vm start` must be running, and they skip without
`work/image.json` (or the folder `ART98_TEST_WORK` names):

```bash
uv run python -m pytest core/tests/test_stage.py core/tests/test_stage_scenes.py -q
```

If `DOCKER_HOST` points at a different engine than the one that runs the VM, unset it for art98
commands. Doc samples on the real VM: `uv run python tools/check_docs.py`.

## Which tests need what

| Test files | Needs |
| --- | --- |
| `core/tests/test_stage.py`, `test_stage_scenes.py` | A running VM service and the prepared image in `work/` |
| `core/tests/test_qemu.py` | `qemu-system-i386` on `PATH` (no Windows) |
| `core/tests/test_agent_wine.py` | Wine |
| Everything else in `core/tests` and `setup/tests` | Nothing |

`make -C guest` needs the mingw cross-compiler. CI (`.github/workflows/tests.yml`) runs on Python
3.11 and 3.13: `uv run ruff check .`, `uv run ruff format --check core setup tools`, and the unit
tests (it ignores only `test_stage.py` and `test_qemu.py`; `test_stage_scenes.py` skips without an image). It has no VM. Which tests a change
needs: [CONTRIBUTING.md](CONTRIBUTING.md#which-tests-a-change-needs).

## Rules

- **`work/` stays out of git.** It holds installed copies of Windows 98, which are not ours to
  share. Never copy, commit or upload anything from `work/`, including `work/runs/`. Reading your
  own setup logs and screenshots there is fine. `.gitignore` and `.dockerignore` keep it out;
  keep them that way.
- **Windows 98 product keys** are public and reusable, not secrets; still never add one to the
  repo: you supply your own.
- **Prep and the `ready` snapshot need an issue first**, as in
  [CONTRIBUTING.md](CONTRIBUTING.md#scope). That means `setup/art98_setup/` steps that change the
  image, the answer file, `ready.py`, and anything that would need a new `art98 setup` run. Do at
  run time what can be done at run time (the blank start and the CD wallpaper are built that way).
- **Don't run `art98 up` or `art98 setup`, delete `work/`, or download Windows media** unless
  your user asks. Setup takes a long time and needs their own disc and key.
- **Scope.** Only base Windows 98 SE programs (plus art98's own `VIEW.EXE`): no programs that need
  their own install, no named snapshots for them, no add-on or plugin system. Audio is deferred:
  don't build, document as a feature, or render it. The VM keeps its Sound Blaster because
  removing it would change the image. Resolutions are fixed to the four Cirrus modes (640x480,
  800x600, 1024x768, 1280x1024); custom or 16:9 resolutions, upscaling and a different display
  driver are out of scope (see [decisions.md](docs/design/decisions.md)).
- **No AI credit lines** in commits, PRs or code: see [CONTRIBUTING.md](CONTRIBUTING.md#commits-and-pull-requests).
- **Git safety.** Don't commit, push, switch branches or reset unless your user asked you to.
  Never discard changes you did not make.
- **Kill a stray VM with `art98 vm stop`, or by its PID**, never `pkill -f qemu-system-i386`: the
  pattern can match the shell that runs it.
- `lazy:` comments mark a known shortcut with its limit. Keep them true; remove one only when you
  fix what it describes.

## Where things live

| Path | What |
| --- | --- |
| `core/art98/anim/` | What scenes import (`from art98.anim import *`). `scene.py` is `Scene`; `setstate.py` applies and checks a state; `timeline.py` is `play`/`wait`/`pause`/`live`; `renderer.py` is `render()` |
| `core/art98/base/` | Building blocks with no guest I/O of their own: `Animation` and groups, rate functions, vectors, `Box`/`Prop`/`Spot`, `DesktopSpace` (`space.py`) |
| `core/art98/actions/` | Action families: `pointer.py`, `keyboard.py`, `backdrop.py`, `window/` (`Win`, commands, `Menu`, `Picture`) and `programs/` (one file per program, each a `Win` subclass) |
| `core/art98/win32.py` | Win32 constants and small named guest reads. Put a new constant or a repeated guest read here, not inline |
| `core/art98/bridge.py`, `protocol.py` | The host side of the agent protocol. Transport only |
| `core/art98/session.py` | `Session`: a VM and a bridge, with `revert`. `boot_local`/`stage` are host QEMU for experiments only |
| `core/art98/service.py`, `container/` | The VM service: `start`, `stop`, `status`, and `attach()` for Python callers; `serve.py` runs inside the container, `host.py` on the host |
| `core/art98/recorder.py` | `Recorder`: frames to clips, `cut()`, the join |
| `core/art98/state.py` | Reading and checking state JSON files |
| `core/art98/desktop.py` | The blank start |
| `core/art98/settings.py` | `art98.toml` |
| `core/art98/cli.py` | The `art98` command |
| `setup/art98_setup/` | `art98 setup` (four steps) and `art98 up`; `setup/Dockerfile` |
| `guest/` | C and assembly built with `make -C guest` into `guest/build/` (gitignored): `agent.exe`, `view.exe`, `mbr.bin` |
| `core/tests/`, `setup/tests/` | Tests. `pythonpath` in `pyproject.toml` puts `core` and `setup` on the path |
| `examples/` | Maintained scenes the docs embed. Keep them rendering |
| `tools/` | `render_all.py` (gallery GIFs), `check_docs.py` (renders doc samples on the real VM) |
| `experiments/` | Throwaway probes. No tests, not imported by art98 |
| `docs/` | Every page; index in `docs/README.md`. `docs/status.md` is the pick-up point |
| `work/` | The prepared image. **Never copy, commit or upload anything from it** |


## Conventions

Formatting is ruff's: `uv run ruff format core setup tools`.

**Code**

- Python 3.11+. Modules with code start with a docstring that says what the module is for, then
  `from __future__ import annotations`.
- No runtime dependencies. Don't add any to `[project] dependencies`.
- One home per thing. A guest read used twice becomes one helper (in `win32.py`, or on `Win`); a
  Win32 constant goes in `win32.py`; the programs a state can open are listed once, in
  `APPS` in `anim/setstate.py`. No compatibility shims or old import paths when something moves,
  and no commented-out or parked code: delete what you replace and move its callers.
- Lean first: one module and one code path, and more only when a measurement or a real use
  asks for it.
- New action code goes in its family's folder: a program in `actions/programs/<name>.py`
  subclassing `Win`, never in a shared grab-bag module.
- Props mirror the guest; the guest is the truth. Read back before acting (`refresh`), and
  check after (`check_state`, the placement read-back). Don't cache what Windows can change.
- Errors a user can cause get their own exception class with a message that says what to do,
  and are added to `RUN_ERRORS` in `cli.py` so the CLI prints one `error:` line.
- Write about measured behaviour: a comment or docstring that states a Windows 98 fact says it
  was checked on the real image, or doesn't state it.

**Tests**

- The authoritative rules (stand-in guests, test names as sentences, tools that skip, the `stage`
  marker) are in [CONTRIBUTING.md](CONTRIBUTING.md#writing-tests). Beyond them: other stand-ins
  are `FakeVM` in `test_anim.py`, `FakeEngine` in `test_service.py`/`test_freshness.py`, and
  `serve_harness.py` for the container server. Extend those rather than writing new fakes.
- `conftest.py` pins scenes to `desktop = "stock"` (the fakes don't model the blank start) and
  silences freshness warnings. `test_desktop.py` covers the blank start.
- VM tests must release the VM when they end (`with attach()` or the `booted` fixture), so a
  failure never holds the lock.
- `test_anim_docs.py` keeps the scene docs honest: every ```` ```python ```` block in
  `docs/scenes/README.md`, `tutorial.md`, `scene-api.md` and `animations.md` must run and define
  exactly one `Scene`; every name in `art98.anim.__all__` must appear in `scene-api.md` or
  `animations.md`; the gallery must show each source file exactly; links must resolve. Use
  ```` ```text ```` or ```` ```bash ```` for anything that is not a whole scene.

**Docs**

- Plain, short sentences. Define a term the first time a page uses it, or link the
  [glossary](docs/glossary.md).
- Docs follow the code. If they disagree, fix the doc, or report the bug.
- Every timing names its conditions (host load, engine); on Linux, `/proc/pressure/cpu` is one way
  to record load.
- Link design docs instead of repeating them. Don't edit `docs/status.md` in a feature PR; the
  maintainer updates it at release time.
- No personal details: no names, emails, or details of one machine beyond what setup needs.

## Pull requests

- One change per PR, with its tests and docs. Imperative commit message: "Add Calculator as a
  program".
- Run the unit tests, `ruff check` and `ruff format --check` before you open it.
- Say which tests you ran and on which engine (Docker or Podman).
- If you touched anything that talks to the guest or the container and did not run the VM tests,
  write this line in the PR description: `VM tests: not run (no prepared image on this machine)`.
- If a result is uncertain, say what you ran, what you saw and what you did not check.

## Related guides

A separate scene-author guide lives outside this repo; say in the PR when a change alters what
scene authors see (a tool, the state format, an error). Also: [CONTRIBUTING.md](CONTRIBUTING.md),
[docs/design/decisions.md](docs/design/decisions.md), [docs/status.md](docs/status.md).
