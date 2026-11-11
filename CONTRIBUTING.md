# Contributing to art98

Thanks for helping. This page says how to get a working checkout, which tests a change needs,
and how to add the two things people most often add: a program and a state feature. Coding
agents should also read [AGENTS.md](AGENTS.md).

Before a bigger change, read the section of [Design decisions](docs/design/decisions.md) for
the area you are working in. It says what was chosen, why, and how new work of that kind should
be done.

## Scope

art98 drives **base Windows 98 SE**: the programs that ship on the Windows 98 SE disc (Notepad,
Paint, Calculator, WordPad, the games, Explorer and so on), plus art98's own small picture
viewer. These are out of scope for now, and changes that add them won't be taken:

- programs that need their own install disc or a separate snapshot, such as Office;
- an add-on or plugin system for such programs;
- audio. art98 is video only for now.

Changes to how Windows is installed, or to the `ready` snapshot every render restores, are a
big deal: they force everyone to rebuild their image. Open an issue first and explain why the
change can't be made at run time instead.

## Setup

You need what the [README](README.md#what-you-need) lists: Linux, Docker (or Podman with
`podman-docker`), Python 3.11+, uv, ffmpeg, and your own Windows 98 SE disc and key.

```bash
git clone https://github.com/StanLukuvka/98artware 98artware && cd 98artware
```

```bash
uv sync
```

`uv sync` installs the `dev` group (pytest and pycdlib) as well. art98 has no runtime
dependencies, and runs from the checkout with `uv run`.

For the unit tests that is all. For anything that drives the real guest, build the prepared
image and start the VM, as in the [README](README.md#from-nothing-to-a-video):

```bash
uv run art98 up --iso /path/to/win98se.iso
```

```bash
uv run art98 vm start
```

Some tests and `art98 setup` on the host need host tools (QEMU 10.2.2, mtools, 7-Zip, the
mingw cross-compiler). `uv run art98 doctor` lists what is there. If you keep a local QEMU
build in `.tools/` (not in git), load it with `. .tools/env.sh` in each shell.

Never commit anything from `work/`. It holds an installed copy of Windows 98 and your product key.

## Tests

There are two kinds.

**Unit tests** need no VM. They run against stand-in guests that answer like Windows would,
and they are what CI runs on every push:

```bash
uv run python -m pytest core/tests setup/tests -q --ignore=core/tests/test_stage.py --ignore=core/tests/test_stage_scenes.py --ignore=core/tests/test_qemu.py
```

**VM tests** drive the real prepared image through the VM service, including real renders.
Start the VM first; they skip without a prepared image in `work/` (or the folder
`ART98_TEST_WORK` names):

```bash
uv run python -m pytest core/tests/test_stage.py core/tests/test_stage_scenes.py -q
```

`test_qemu.py` runs real QEMU with no Windows (boot chain, QMP, snapshots), and skips without
`qemu-system-i386` on `PATH`. `test_agent_wine.py` runs the real `agent.exe` under Wine and
skips without it.

### Which tests a change needs

| You changed | Run |
| --- | --- |
| Docs only | Unit tests (`test_anim_docs.py` checks the scene docs) |
| The scene layer, animations, props, vectors, state parsing | Unit tests, plus a real render of an affected example |
| A program class, `setstate.py`, the blank start, anything that makes Win32 calls | Unit tests and VM tests |
| The bridge, the protocol, the recorder | Unit tests and VM tests |
| The VM service, `container/`, `settings.py`, the CLI's attach path | Unit tests and VM tests, on Docker and, if you can, on Podman |
| The agent or `VIEW.EXE` (`guest/`) | `make -C guest`, `uv run art98 up --rebuild`, `vm stop`/`vm start`, then VM tests |
| Setup steps (`setup/art98_setup/`) | Unit tests, then a full `art98 up` into a separate empty work folder |

If you couldn't run the VM tests, say so in your pull request.

`uv run python tools/check_docs.py` renders every sample in the scene docs on the real VM, and
`uv run python tools/render_all.py` re-renders the gallery GIFs. Run them when you change what a
documented scene does.

### Writing tests

- Use the existing stand-in guests (`FakeGuest` and `FakeSession` in `test_anim.py`,
  `GuestWithFiles` in `test_picture.py`, `NotepadGuest` in `test_notepad.py`) rather than
  writing new ones. Teach a stand-in only what Windows was seen to do on the real image.
- Name a test after the behaviour it checks, as a sentence:
  `test_a_wrong_hash_says_what_it_should_be`, not `test_hash_2`.
- A test that needs a tool skips itself when the tool is missing. A VM test is marked `stage`
  and releases the VM when it ends, so a failing test never leaves it locked.

## Lint

art98 uses [ruff](https://docs.astral.sh/ruff/), pinned in the `dev` group, so `uv sync`
installs it:

```bash
uv run ruff check .
```

It must pass.

## Adding a program

A program is an action class: one Python class that starts a program on the guest, finds its
window, and holds the verbs that drive it. `Notepad` (`core/art98/actions/programs/notepad.py`)
is the model to copy. [Programs](docs/design/programs.md) has the full walk-through; in short:

1. Check it ships with Windows 98 SE. See [Scope](#scope).
2. Try it on the real guest first, with `self.guest` calls in a throwaway scene or a probe in
   `experiments/`. Note what Windows actually does: window class, title rule, child controls,
   anything odd. [The app catalog](docs/scenes/app-catalog.md) has what is known already.
3. Write the class in `core/art98/actions/programs/<name>.py`, subclassing `Win`. Set
   `command` and `window_class`, add `ready()` if it needs a child window, and the verbs on top.
   Constants and repeated guest reads go in `core/art98/win32.py`.
4. Export it from `core/art98/actions/programs/__init__.py`, and import it and list it in
   `__all__` in `core/art98/anim/__init__.py`.
5. Document it in [Scene API](docs/scenes/scene-api.md) (the docs test fails if a public name is
   missing), and add a line to the [app catalog](docs/scenes/app-catalog.md).
6. Add unit tests on a stand-in guest, beside `core/tests/test_notepad.py`, and a VM test that
   opens it on the real image.
7. Add a short scene to `examples/gallery/` and its GIF to the [gallery](docs/scenes/gallery.md)
   if it shows something new.

To let a state open it, also add `from_state(cls, window)`, add the class to `APPS` in
`core/art98/anim/setstate.py`, and give it a default title rule and a file check for `open` in
`core/art98/state.py`. Then document its `app` name under [States](docs/scenes/scene-api.md#states).

A stock program needs no guest change. A program of art98's own, like `VIEW.EXE`, is C in
`guest/`, and needs `make -C guest` and `art98 up --rebuild`.

## Adding to states

A **state file** is JSON you write by hand; see [States](docs/scenes/scene-api.md#states). To
add one for an example, put it in the example's `states/` folder and any file it opens beside
it, referenced by path and `sha256`.

A **new state field** (say, desktop icons) touches three places, in this order:

1. `core/art98/state.py` reads and checks it. A state is checked completely before the guest
   is touched, so every mistake in a file is listed at once, and unknown fields fail.
2. `core/art98/anim/setstate.py` applies it in `apply_state` and checks it took in
   `check_state`. A mismatch raises `StateMismatch` with each difference.
3. The docs: [States](docs/scenes/scene-api.md#states) and the
   [state and action design](docs/design/state-and-action.md).

A state describes a still desktop, written by hand. Don't add a way to save a scene's result as
a state, or to snapshot the VM per scene: those were considered and rejected (see
[Design decisions](docs/design/decisions.md#7-states-are-static-and-hand-written-actions-are-free-python)). If a field needs a big file in
the guest, look at how the wallpaper goes on a CD image instead of being copied file by file.

## Docs

A change isn't done until the docs say what it does.

- Update the page that describes what you changed: [Scene API](docs/scenes/scene-api.md) and
  [Animations](docs/scenes/animations.md) for the scene layer, [CLI](docs/setup/cli.md) and
  [Configuration](docs/setup/config.md) for commands and settings, the design pages for how
  things work inside.
- Write for someone who has never seen art98: plain words, short sentences, and a term defined
  or linked to the [glossary](docs/glossary.md) the first time a page uses it.
- Say what was measured, and how. A timing names the host load and the engine. A Windows 98
  fact says it was checked on the real image.
- A `python` code block in the scene docs must be one whole scene that runs, because
  `test_anim_docs.py` runs it. Use `text` or `bash` blocks for anything else.
- Link to the design docs instead of repeating them.
- Diagrams in `docs/diagrams/` are draw.io files with a PNG export beside each. Change both.
- Don't include personal details: no names, emails, or details of one machine.

## Commits and pull requests

- Keep a pull request to one change, with its tests and docs.
- Write commit messages in the imperative: "Add Calculator as a program".
- Don't add AI credit lines (`Co-Authored-By` for an AI, "Generated with ...") to commits,
  pull requests or code.
- Say which tests you ran, and on which engine.

## Licence

art98 is under the [MIT License](LICENSE). By contributing you agree that your contribution is
licensed under it too. Windows 98 itself is not part of art98: never add anything from a
Windows disc or an installed image to the repository.
