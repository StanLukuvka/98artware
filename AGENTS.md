# AGENTS.md

Notes for coding agents working on art98. Humans should read [CONTRIBUTING.md](CONTRIBUTING.md)
first; this file repeats the parts an agent needs and adds the rules that are easy to break.

art98 scripts animations on a real Windows 98 SE desktop. A VM runs in QEMU inside a Docker or
Podman container as a long-lived service. A render attaches to it, restores the `ready` snapshot,
drives the guest through an agent that proxies Win32 calls, and records the screen. Terms are in
[docs/glossary.md](docs/glossary.md). Why things are built the way they are is in
[docs/design/decisions.md](docs/design/decisions.md): read the section for the area you touch
before changing it.

## Where things live

| Path | What |
| --- | --- |
| `core/art98/anim/` | What scenes import (`from art98.anim import *`). `scene.py` is `Scene`; `setstate.py` applies and checks a state; `timeline.py` is `play`/`wait`/`pause`/`live`; `renderer.py` is `render()` |
| `core/art98/base/` | Building blocks with no guest I/O of their own: `Animation` and groups, rate functions, vectors, `Box`/`Prop`/`Spot`, `DesktopSpace` (`space.py`) |
| `core/art98/actions/` | Action families: `pointer.py`, `keyboard.py`, `backdrop.py`, `window/` (`Win`, commands, `Menu`, `Picture`) and `programs/` (one file per program, each a `Win` subclass) |
| `core/art98/win32.py` | Win32 constants and small named guest reads. Put a new constant or a repeated guest read here, not inline |
| `core/art98/bridge.py`, `protocol.py` | The host side of the agent protocol. Transport only |
| `core/art98/session.py` | `Session`: a VM and a bridge, with `revert`. `boot_local`/`stage` are host QEMU for experiments only |
| `core/art98/service.py`, `container/` | The VM service: `start`, `stop`, `status`, `attach`; `serve.py` runs inside the container, `host.py` on the host |
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
| `.lad/plans/` | Plans from earlier multi-agent work. History, not instructions |
| `work/` | The prepared image. **Never read, copy or commit anything from it** |

The [repo tour](docs/tour.md) walks every file in reading order.

## Shell setup

Run everything from the repository root with `uv run`. There are no runtime dependencies;
`uv` installs the `dev` group (pytest, pycdlib) by default.

Host QEMU (for `test_qemu.py`, `art98 setup` on the host, and `boot_local` experiments) may come
from a local build in `.tools/`, which is not in git. When it exists, load it in each shell:

```bash
. .tools/env.sh
```

`art98 up`, `art98 vm` and `art98 render` don't need it: QEMU runs in the container.

## Commands

Unit tests, no VM needed. CI runs the same command on every push (without the
`test_stage_scenes.py` ignore, which skips there anyway):

```bash
uv run python -m pytest core/tests setup/tests -q --ignore=core/tests/test_stage.py --ignore=core/tests/test_stage_scenes.py --ignore=core/tests/test_qemu.py
```

VM tests, on the real prepared image. `art98 vm start` must be running, and they skip without
`work/image.json` (or `ART98_TEST_WORK`):

```bash
uv run python -m pytest core/tests/test_stage.py core/tests/test_stage_scenes.py -q
```

On a host where `DOCKER_HOST` points at Podman but the VM runs on real Docker, run them under
the `docker` group with `DOCKER_HOST` unset:

```bash
env -u DOCKER_HOST sg docker -c '. .tools/env.sh && uv run python -m pytest core/tests/test_stage.py -q'
```

Lint (ruff is a separate tool: `uv tool install ruff`, or use `uvx ruff`):

```bash
uv run ruff check --exclude work .
```

Doc samples on the real VM: `uv run python tools/check_docs.py`.

Run the unit tests and ruff after every change. Run the VM tests when you touch anything that
talks to the guest or the container (see [CONTRIBUTING.md](CONTRIBUTING.md#which-tests-a-change-needs)),
and say in your report if you could not.

## House rules

- **`work/` is off limits.** It holds installed copies of Windows 98 and the product key in
  clear text. Never read, copy, list into logs, or commit anything from it, including
  `work/runs/`. `.gitignore` and `.dockerignore` keep it out; keep them that way.
- **Don't change prep or the `ready` snapshot without asking.** That means `setup/art98_setup/`
  steps that change the image, the answer file, `ready.py`, and anything that would need a new
  `art98 setup` run. Do at run time what can be done at run time (the blank start and the CD
  wallpaper are built that way).
- **Kill a stray VM by its PID**, never `pkill -f qemu-system-i386`: the pattern can match the
  shell that runs it. Stop the service with `art98 vm stop`.
- **Audio is deferred.** Don't build, document as a feature, or render audio. The VM keeps its
  Sound Blaster because removing it would change the image.
- **Only base Windows 98 SE programs are in scope.** Program classes are for what ships with
  Windows 98 SE (plus art98's own `VIEW.EXE`). No programs that need their own install, no
  named snapshots for them, and no add-on or plugin system.
- **No AI attribution.** No `Co-Authored-By` trailers for an AI, no "Generated with" lines, no
  session links, in commits, PRs, code comments or docs.
- **Ask before committing**, and never push, switch branches, stash or reset unless asked.
  Other sessions may be editing the same checkout.
- **Leave `FLOW-PRODUCED` marker comments in place.** They are temporary markers from a planned
  flow and are removed by its final review, not by hand.
- `lazy:` comments mark a known shortcut with its limit. Keep them true; remove one only when you
  fix what it describes.

## Conventions the code and tests imply

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

- Unit tests run against stand-in guests, not a VM: `FakeGuest`, `FakeSession` and `FakeVM` in
  `test_anim.py`, `GuestWithFiles` in `test_picture.py`, `NotepadGuest` in `test_notepad.py`,
  `FakeEngine` in `test_service.py`/`test_freshness.py`, and `serve_harness.py` for the container
  server. Extend those rather than writing new fakes.
- `conftest.py` pins scenes to `desktop = "stock"` (the fakes don't model the blank start) and
  silences freshness warnings. `test_desktop.py` covers the blank start.
- Test names are sentences that state the behaviour:
  `test_revert_ejects_the_disc_before_loadvm_only_when_one_was_inserted`.
- Tests that need tools skip themselves when the tool is missing (QEMU, Wine, mtools, the image).
  VM tests are marked `stage` and must release the VM when they end (`with attach()` or the
  `booted` fixture), so a failure never holds the lock.
- `test_anim_docs.py` keeps the scene docs honest: every ```` ```python ```` block in
  `docs/scenes/README.md`, `tutorial.md`, `scene-api.md` and `animations.md` must run and define
  exactly one `Scene`; every name in `art98.anim.__all__` must appear in `scene-api.md` or
  `animations.md`; the gallery must show each source file exactly; links must resolve. Use
  ```` ```text ```` or ```` ```bash ```` for anything that is not a whole scene.

**Docs**

- Plain, short sentences. Define a term the first time a page uses it, or link the
  [glossary](docs/glossary.md).
- Docs follow the code. If they disagree, fix the doc, or report the bug.
- Every timing names its conditions (host load, engine); note `/proc/pressure/cpu` next to
  new measurements.
- Link design docs instead of repeating them. Leave `docs/status.md` to whoever is coordinating
  the work unless you were asked to update it.
- No personal details: no names, emails, or details of one machine beyond what setup needs.

## The scene-author skill

Agents that write scenes, rather than change art98, use a separate skill that ships with the
Hermes agent plugin, outside this repository (in its `skills/art98/SKILL.md`). It belongs to the
plugin: don't edit it from a task in this repository. When a change here alters what a scene
author sees (a tool, the state format, an error), say so in your report so the skill can follow.
