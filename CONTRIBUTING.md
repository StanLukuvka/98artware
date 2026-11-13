# Contributing to art98

Thanks for wanting to help. art98 animates a real Windows 98 SE desktop: you write a short
Python scene, art98 plays it on Windows 98 running in a virtual machine, and the video is what
that machine's screen showed. The [README](README.md) has the full picture.

This page is for people. It says what the project takes, how to get a working checkout, how
each kind of contribution goes, and which tests a change needs. If you work with a coding
agent, point it at [AGENTS.md](AGENTS.md), which holds the same rules in a form written for
agents.

You don't need Windows 98 to contribute. Most of art98 is tested against stand-in guests, so
[a lot can be done with no VM](#what-you-can-do-without-windows).

## Scope

art98 drives **base Windows 98 SE**: the programs that ship on the Windows 98 SE disc (Notepad,
Paint, Calculator, WordPad, the games, Explorer and so on), plus art98's own small picture
viewer, `VIEW.EXE`. Please check this list before you start, because changes that add any of
these won't be merged:

- **Other software.** Programs that need their own install disc or a separate snapshot, such as
  Office, and an add-on or plugin system for them.
- **Audio.** It is deferred. art98 makes silent video for now.
- **Other resolutions.** The display modes are fixed to 640x480, 800x600, 1024x768 and
  1280x1024. Custom or widescreen resolutions, upscaling and a different display driver are out.
- **Animated desktop icons.**

The reasons are in
[Design decisions, section 10](docs/design/decisions.md#10-only-base-windows-98-se-video-only),
and the table at the [end of that page](docs/design/decisions.md#not-built-on-purpose-or-not-yet)
lists what else is not built and why. [Status](docs/status.md) says what is open, if you are
looking for something to pick up.

Changes to how Windows is installed, or to the `ready` snapshot every render restores, are a
big deal: they force everyone to rebuild their image. Open an issue first and explain why the
change can't be made at run time instead. See [Setup and prep changes](#setup-and-prep-changes).

Before a bigger change of any kind, read the section of
[Design decisions](docs/design/decisions.md) for the area you are working in. Each one ends
with the rule new work should follow. If you need to break one, say why in your pull request.

## What you need

- Linux. Other systems have not been tried.
- Python 3.11 or newer, and [uv](https://docs.astral.sh/uv/).

That is enough for the unit tests, lint and docs. To render on the real guest you also need:

- Docker, or Podman with the `podman-docker` package. art98 only ever runs the `docker` command.
- ffmpeg.
- Your own Windows 98 SE disc image (an `.iso`) and its product key. art98 does not include
  Windows, and can't. The [README](README.md#what-you-need) says what the disc must be like.
- About 3 GB of free disk space, and 20 to 40 minutes for the one-time install.

## Getting started

Get the code and install the dev tools:

```bash
git clone https://github.com/StanLukuvka/98artware 98artware && cd 98artware
```

```bash
uv sync
```

`uv sync` installs the `dev` group: pytest, pycdlib and ruff. art98 has no runtime
dependencies and runs from the checkout with `uv run`. There is nothing to `pip install`.

Run the [unit tests](#tests). They take well under a minute and need no VM.

Some tests skip themselves when a tool they need is missing. That is expected. If anything
fails on a fresh checkout, that is a bug: please [report it](#reporting-a-bug).

### What you can do without Windows

- Run the unit tests and the lint. They are what CI runs.
- Fix or improve the docs. `core/tests/test_anim_docs.py` checks the scene docs with no VM.
- Work on the scene layer, animations, state parsing, the recorder, the CLI and the setup
  code against the stand-in guests in the tests.

What you can't do is see a render, or run the VM tests. If your change needs those and you
have no image, send it anyway and [say so in the pull request](#if-you-could-not-run-the-vm-tests).

### Your first render

With a Windows 98 SE disc image and key, follow
[From nothing to a video](README.md#from-nothing-to-a-video): `art98 up` once, then
`art98 vm start` and `art98 render`. Running `art98 up` accepts the Windows 98 licence agreement
on your behalf, so only use a disc and key you are licensed to use.
[Troubleshooting](docs/setup/troubleshooting.md) covers an install that stops.

To write a scene of your own, follow the [tutorial](docs/scenes/tutorial.md).

## Where things live

The [repo tour](docs/tour.md) walks every folder and file, and
[AGENTS.md](AGENTS.md#where-things-live) has a table of paths. New words are in the
[glossary](docs/glossary.md).

`work/` holds the prepared image, an installed copy of Windows 98. It is gitignored. Never
commit, attach or upload anything from it.

## Branches

- `dev` is the trunk. Branch off `dev` and keep branches short-lived: a day or two. Open the
  pull request against `dev`. CI must pass before it merges.
- `main` only moves at a release, cut from `dev`.
- `experiments/` lives on `dev` only.

A release goes like this:

```bash
git switch main
git merge --no-ff --no-commit dev
git rm -r -q -f --ignore-unmatch experiments
git status --short | grep experiments
git commit
```

The merge stages the `experiments/` changes from `dev`. Remove the folder before you commit.
`-f` is needed because the merge has staged those files. Without it, `git rm` refuses and the
commit keeps them.

If `dev` changed a file in `experiments/`, the merge stops with a modify/delete conflict and
exits with an error. That is expected. Carry on with `git rm`.

The `grep` line must print nothing before you commit. CI fails on `main` if `experiments/` is
there.

## Ways to contribute

### Reporting a bug

Open a [GitHub issue](https://github.com/StanLukuvka/98artware/issues). A report that can be
acted on has:

- What you ran, what you expected and what happened.
- The `error:` line, in full. art98's own errors are one line starting with `error:`; run the
  command again with `ART98_TRACE=1` set to get the traceback as well.
- The output of `uv run art98 doctor`, and of `uv run art98 vm status` if the VM is involved.
- The engine and its version: Docker or Podman (`docker --version`).
- The commit you are on (`git rev-parse --short HEAD`), and your Python version.
- The scene and its state file, cut down to the smallest one that still shows the problem.
- For anything about timing or speed, how busy the host was. Host load changes timings by five
  times or more. On Linux, paste the output of `cat /proc/pressure/cpu`. See
  [on a busy host](docs/setup/troubleshooting.md#on-a-busy-host).
- For a wrong picture, the frame or a short GIF that shows it.

Don't attach files from `work/`.

If Windows 98 does something you did not expect, that is worth an issue too. Say which
program, what you saw, and that you saw it on the real image.

### Fixing the docs

Small fixes need no issue: open a pull request. Docs-only changes need only the unit tests,
which check that the links in the scene docs resolve and that their samples run. The rules
are under [Docs](#docs).

### Fixing a bug or adding a feature

For a small fix, open a pull request with a test that fails without it. For anything bigger,
or anything that changes what scene authors see, open an issue first so the approach can be
agreed before you write it. Check [Scope](#scope) and the
[design decisions](docs/design/decisions.md) for the area.

### Adding a program

A program is an action class: one Python class that starts a program on the guest, finds its
window, and holds the verbs that drive it. `Notepad`
([core/art98/actions/programs/notepad.py](core/art98/actions/programs/notepad.py)) is the
model to copy. It is about 90 lines: it sets `command` and `window_class`, finds its Edit
control in `ready()`, and adds `text`, `set_text` and a `close()` that skips the save prompt.
[Programs](docs/design/programs.md) explains the design. The steps:

1. Check it ships with Windows 98 SE. See [Scope](#scope).
2. Try it on the real guest first, with `self.guest` calls in a throwaway scene or a probe in
   `experiments/`. Note what Windows actually does: the window class, the title rule, the
   child controls, anything odd. [The app catalog](docs/scenes/app-catalog.md) has what is
   known already, and [Win32 recipes](docs/scenes/win32-recipes.md) shows the calls.
3. Write the class in `core/art98/actions/programs/<name>.py`, subclassing `Win`. Set
   `command` and `window_class`, add `ready()` if it needs a child window, and put the verbs
   on top. Win32 constants and repeated guest reads go in `core/art98/win32.py`.
4. Export it from `core/art98/actions/programs/__init__.py`, and import it and list it in
   `__all__` in `core/art98/anim/__init__.py`.
5. Document it in [Scene API](docs/scenes/scene-api.md) (the docs test fails if a public name
   is missing), and add a line to the [app catalog](docs/scenes/app-catalog.md).
6. Add unit tests on a stand-in guest, beside `core/tests/test_notepad.py`, and a VM test that
   opens it on the real image, beside the ones in `core/tests/test_stage.py`.
7. Add a short scene to `examples/gallery/` and its GIF to the
   [gallery](docs/scenes/gallery.md) if it shows something new.

That makes a program a scene can add in `construct`. To let a state file open it as well, add
`from_state(cls, window)`, add the class to `APPS` in `core/art98/anim/setstate.py`, and give
it a default title rule and a file check for `open` in `core/art98/state.py`. Then document
its `app` name under [States](docs/scenes/scene-api.md#states). Only `picture` and `notepad`
are state apps so far.

A stock program needs no guest change. A program of art98's own, like `VIEW.EXE`, is C in
`guest/`, and needs `make -C guest` and `uv run art98 up --rebuild`. Prefer a stock program.

If you have no image, you can still write the class and its unit tests from what the app
catalog records. Say in the pull request which Windows behaviour you could not check.

### Adding to states

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

A state describes a still desktop, written by hand. Don't add a way to save a scene's result
as a state, or to snapshot the VM per scene: those were considered and rejected (see
[Design decisions](docs/design/decisions.md#7-states-are-static-and-hand-written-actions-are-free-python)).
If a field needs a big file in the guest, look at how the wallpaper goes on a CD image instead
of being copied file by file.

### Setup and prep changes

This covers the setup steps in `setup/art98_setup/`, the answer file, the `ready` snapshot, the
container image and anything else that would make people run `art98 up` again.

**Open an issue before you write code.** A change here alters the prepared image, so everyone
has to rebuild theirs, and an image made before the change may stop working. The issue should
say what the change is for and why it can't be done at run time. The blank start and the
wallpaper CD are both done at run time for that reason.

Such a change also needs a full `art98 up` from an empty work folder to test it, which takes
20 to 40 minutes and a disc:

```bash
uv run art98 up --iso /path/to/win98se.iso --work /path/to/empty-folder
```

Setup has been run on one OEM disc only. A fix that makes another disc work is welcome; say
which disc it is (edition and language, not the key).

## Tests

There are two kinds.

**Unit tests** need no VM. They run against stand-in guests that answer like Windows would:

```bash
uv run python -m pytest core/tests setup/tests -q --ignore=core/tests/test_stage.py --ignore=core/tests/test_stage_scenes.py --ignore=core/tests/test_qemu.py
```

**VM tests** drive the real prepared image through the VM service, including real renders.
Start the VM first with `uv run art98 vm start`. They skip without a prepared image in `work/`
(or the folder `ART98_TEST_WORK` names), and when the VM service is not running:

```bash
uv run python -m pytest core/tests/test_stage.py core/tests/test_stage_scenes.py -q
```

Two more files need a tool and skip without it. `core/tests/test_qemu.py` runs real QEMU with
no Windows (boot chain, QMP, snapshots) and needs `qemu-system-i386`, mtools and a built
`guest/`. `core/tests/test_agent_wine.py` runs the real `agent.exe` under Wine.

### Which tests a change needs

| You changed | Run |
| --- | --- |
| Docs only | Unit tests (`test_anim_docs.py` checks the scene docs) |
| The scene layer, animations, props, vectors, state parsing | Unit tests, plus a real render of an affected example |
| A program class, `setstate.py`, the blank start, anything that makes Win32 calls | Unit tests and VM tests |
| The bridge, the protocol, the recorder | Unit tests and VM tests |
| The VM service, `container/`, `settings.py`, the CLI's attach path | Unit tests and VM tests, on Docker and, if you can, on Podman |
| The agent or `VIEW.EXE` (`guest/`) | `make -C guest`, `uv run art98 up --rebuild`, `uv run art98 vm stop` and `vm start`, then VM tests |
| Setup steps (`setup/art98_setup/`) | Unit tests, then a full `art98 up` into a separate empty work folder |

Lint applies to every change; see [Code style](#code-style).

`uv run python tools/check_docs.py` renders every sample in the scene docs on the real VM, and
`uv run python tools/render_all.py` re-renders the gallery GIFs. Run them when you change what
a documented scene does.

### What CI runs

Every push and pull request runs `.github/workflows/tests.yml` on Python 3.11 and 3.13:

```bash
uv run ruff check .
```

```bash
uv run ruff format --check core setup tools
```

and the unit tests. CI has no VM and no QEMU, so the VM tests skip there. A green CI run does
not show that a change works on Windows 98.

### If you could not run the VM tests

That is fine, and common: not everyone has a disc. Say so, so a maintainer knows to run them.
If your change touches anything that talks to the guest or the container, put this line in the
pull request description:

```text
VM tests: not run (no prepared image on this machine)
```

### Writing tests

- Use the existing stand-in guests (`FakeGuest` and `FakeSession` in `test_anim.py`,
  `GuestWithFiles` in `test_picture.py`, `NotepadGuest` in `test_notepad.py`) rather than
  writing new ones. Teach a stand-in only what Windows was seen to do on the real image.
- Name a test after the behaviour it checks, as a sentence:
  `test_a_wrong_hash_says_what_it_should_be`, not `test_hash_2`.
- A test that needs a tool skips itself when the tool is missing. A VM test is marked `stage`
  and releases the VM when it ends, so a failing test never leaves it locked.
- A fix comes with a test that fails without it.

## Code style

Formatting and lint are [ruff](https://docs.astral.sh/ruff/)'s, pinned in the `dev` group. Both
commands above must pass. This fixes the formatting for you:

```bash
uv run ruff format core setup tools
```

Beyond that:

- **Python 3.11+, standard library only.** Don't add a runtime dependency. If something truly
  needs one, raise it in an issue first.
- **One home per thing.** A Win32 constant or a guest read used twice goes in
  `core/art98/win32.py`. A program goes in its own file under `actions/programs/`.
- **Delete what you replace.** No compatibility shims, old import paths or commented-out code.
- **Lean first.** Build the smallest thing that works, and add more when a measurement or a
  real use asks for it
  ([decision 19](docs/design/decisions.md#19-lean-first-then-measure)).
- **`lazy:` comments.** When you take a shortcut on purpose, mark it with a comment that
  starts `lazy:` and says what the limit is, so the next reader knows it was a choice and
  where it stops working. For example, in `core/art98/disc.py`:

  ```python
  # lazy: one directory sector holds about 40 files; a bigger set needs multi-sector directories
  ```

  Keep these true, and remove one only when you fix what it describes.
- **Errors say what to do.** A failure a user can cause gets its own exception class, a message
  that says what to do next, and a place in `RUN_ERRORS` in `core/art98/cli.py`, so it prints
  as one `error:` line.
- **Windows 98 facts are measured.** A comment or docstring that states how Windows 98 behaves
  says it was checked on the real image, or doesn't state it
  ([decision 18](docs/design/decisions.md#18-measure-on-the-real-image-keep-the-probes)).
- **Test names are sentences**, as under [Writing tests](#writing-tests).

## Docs

A change isn't done until the docs say what it does. Docs change in the same pull request as
the code.

- Update the page that describes what you changed: [Scene API](docs/scenes/scene-api.md) and
  [Animations](docs/scenes/animations.md) for the scene layer, [CLI](docs/setup/cli.md) and
  [Configuration](docs/setup/config.md) for commands and settings, the design pages for how
  things work inside. The index is [docs/README.md](docs/README.md).
- Write for someone who has never seen art98: plain words and short sentences.
- Use the [glossary](docs/glossary.md)'s terms, and define a term or link to the glossary the
  first time a page uses it. A new term gets a glossary entry.
- Say what was measured, and how. A timing names the host load and the engine. A Windows 98
  fact says it was checked on the real image.
- A `python` code block in the scene docs must be one whole scene that runs, because
  `test_anim_docs.py` runs it. Use `text` or `bash` blocks for anything else.
- Link to the design docs instead of repeating them.
- Diagrams in `docs/diagrams/` are draw.io files with a PNG export beside each. Change both.
- Don't include personal details: no names, emails, or details of one machine.
- Leave [docs/status.md](docs/status.md) alone in a feature pull request. It is updated at
  release time.

## Commits and pull requests

- Keep a pull request to one change, with its tests and docs in the same pull request.
- Write commit messages in the imperative: "Add Calculator as a program".
- Run the unit tests, `ruff check` and `ruff format --check` before you open it.
- In the description, say:
  - what the change does and why, and the issue it closes, if any;
  - which tests you ran, and on which engine (Docker or Podman);
  - whether you ran the VM tests, using
    [this line](#if-you-could-not-run-the-vm-tests) if you could not;
  - anything you are unsure of: what you ran, what you saw and what you did not check;
  - whether it changes what scene authors see, such as the state format or an error message.
- This project does not accept AI credit lines (`Co-Authored-By` for an AI, "Generated with
  ...") in commits, pull requests or code.

A maintainer will review it and may ask for changes. If a pull request sits without an answer
for a while, a comment on it is welcome.

## Licence

art98 is under the [MIT License](LICENSE). By contributing you agree that your contribution is
licensed under it too.

Windows 98 is Microsoft's, not part of art98, and not ours to share. Never add anything from
it to the repository, an issue or a pull request: no Windows files, no disc images, no disk
images, no product keys, and nothing from `work/`. Screen recordings that art98 renders are
fine in the docs and gallery.

## Questions and security

Ask questions in a [GitHub issue](https://github.com/StanLukuvka/98artware/issues). There is no
chat or mailing list.

Report security problems privately, as [SECURITY.md](SECURITY.md) says.
