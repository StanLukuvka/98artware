# Repo tour

A walk through the repository, one section at a time. Each section says what it is for, which
files to open and in what order, and which page explains it. Tick the boxes as you go.

The sections follow the order data moves: the guest-side programs are built, the setup tool
puts them on an image, the core drives that image, and scenes and samples sit on top.

| # | Section | Folder | One line |
| --- | --- | --- | --- |
| 1 | [Front door](#1-front-door) | repo root | What art98 is, how to install and run it. |
| 2 | [Guest programs](#2-guest-programs) | `windows_handlers/` | C and assembly that run inside Windows 98. |
| 3 | [Setup tool](#3-setup-tool) | `98artware_setup/` | Builds the prepared image, once. |
| 4 | [Core: VM and bridge](#4-core-vm-and-bridge) | `98artware_core/art98/` | Starts the VM and talks to the agent. |
| 5 | [Core: scene layer](#5-core-scene-layer) | `98artware_core/art98/anim/` | The Manim-style API scenes are written in. |
| 6 | [Tests](#6-tests) | `*/tests/` | What is checked, and what needs a VM. |
| 7 | [Samples and experiments](#7-samples-and-experiments) | `artware_experiments/` | Scenes to render, and throwaway probes. |
| 8 | [Docs](#8-docs) | `docs/` | Guides, design pages, diagrams, status. |
| 9 | [Container](#9-container) | `98artware_container/` | Runs QEMU and setup in Podman or Docker. Optional. |

Two folders aren't in git: `work/` holds the disk images (installed copies of Windows, so it is never
committed), and `.tools/` holds the local QEMU build. For the local backend, set up a shell
with `. .tools/env.sh`. The container backend doesn't need it.

## 1. Front door

- [ ] [README.md](../README.md): install, `art98 doctor`, `art98 setup`, a first render, the test
  command, timings.
- [ ] [pyproject.toml](../pyproject.toml): one `art98` package built from three folders, the
  `art98` command, and the pytest paths.
- [ ] [docs/README.md](README.md): the index of every doc page.
- [ ] [status.md](status.md): what exists and what is still open. Read this before picking work up.

## 2. Guest programs

Built with `make -C windows_handlers`, into `windows_handlers/build/`.

- [ ] [call_proxy/agent.c](../windows_handlers/call_proxy/agent.c): the agent. It answers the
  host over COM1 and is a thin remote Win32 call proxy. The header comment is the wire format.
- [ ] [picture_viewer/view.c](../windows_handlers/picture_viewer/view.c): the picture window,
  a plain window showing one BMP at 1:1.
- [ ] [boot_record/mbr.S](../windows_handlers/boot_record/mbr.S): the boot sector Windows
  Setup doesn't write.
- [ ] [Makefile](../windows_handlers/Makefile): why the agent links without the mingw CRT.

Explained in: [Instruction set](scenes/instruction-set.md), [Win32 recipes](scenes/win32-recipes.md).

## 3. Setup tool

`art98 setup` runs four steps: vm, setup, init_api, ready. The end result is the `ready`
snapshot that every scene restores.

- [ ] [builder.py](../98artware_setup/art98_setup/builder.py): runs the steps, records progress,
  resumes with `--from`.
- [ ] [vm.py](../98artware_setup/art98_setup/vm.py): step 1, the boot floppy, Setup files and a blank disk.
- [ ] [setup.py](../98artware_setup/art98_setup/setup.py): step 2, unattended Windows Setup.
- [ ] [init_api.py](../98artware_setup/art98_setup/init_api.py): step 3, make the agent start and check it.
- [ ] [ready.py](../98artware_setup/art98_setup/ready.py): step 4, the desktop every run starts from.
- [ ] [pecheck.py](../98artware_setup/art98_setup/pecheck.py): checks an .exe can load on Windows 98.

Explained in: [Setup overview](setup/README.md), [Steps](setup/stages.md), [CLI](setup/cli.md),
[The image](setup/image.md), [Troubleshooting](setup/troubleshooting.md).
Diagrams: [setup pipeline](diagrams/prep-pipeline.png), [install boot chain](diagrams/install-boot-chain.png).

## 4. Core: VM and bridge

The plumbing under every scene. Read in this order, bottom up:

- [ ] [qemu.py](../98artware_core/art98/qemu.py): starts and controls the VM (QMP, snapshots, screenshots).
- [ ] [protocol.py](../98artware_core/art98/protocol.py): the host side of the wire format, and `Out`.
- [ ] [bridge.py](../98artware_core/art98/bridge.py): the link to the agent, as `guest.user32.X(...)`.
- [ ] [guestfiles.py](../98artware_core/art98/guestfiles.py): files copied to the guest, named by content.
- [ ] [session.py](../98artware_core/art98/session.py): a running stage, `boot`, `private_stage`, revert.
- [ ] [state.py](../98artware_core/art98/state.py): the JSON state files for a starting desktop.
- [ ] [desktop.py](../98artware_core/art98/desktop.py): the blank start, a black, empty screen after each revert.
- [ ] [cli.py](../98artware_core/art98/cli.py): the `art98` command.

Explained in: [Bridge](scenes/bridge.md), [Blank start](design/blank-start.md),
[State and action design](design/state-and-action.md).
Diagrams: [request lifecycle](diagrams/request-lifecycle.png), [architecture](diagrams/architecture.png).

## 5. Core: scene layer

What a scene author imports with `from art98.anim import *`.

- [ ] [scene.py](../98artware_core/art98/anim/scene.py): `Scene`, `play`, `wait`, `set_state`, `desktop`.
- [ ] [animation.py](../98artware_core/art98/anim/animation.py) and
  [rate_functions.py](../98artware_core/art98/anim/rate_functions.py): what changes over a run time.
- [ ] [props.py](../98artware_core/art98/anim/props.py): host-side handles on windows and controls.
- [ ] [actions.py](../98artware_core/art98/anim/actions.py): the pointer and keyboard as actors.
- [ ] [apps.py](../98artware_core/art98/anim/apps.py): the programs on the image, as props.
- [ ] [picture.py](../98artware_core/art98/anim/picture.py): picture windows, and one-frame moves.
- [ ] [setstate.py](../98artware_core/art98/anim/setstate.py): applies a state and checks it took.
- [ ] [renderer.py](../98artware_core/art98/anim/renderer.py): VM, recorder, output file.
- [ ] [vectors.py](../98artware_core/art98/anim/vectors.py): screen directions, with y running down.

Explained in: [Tutorial](scenes/tutorial.md) (start here), [Scene API](scenes/scene-api.md),
[Animations](scenes/animations.md), [App catalog](scenes/app-catalog.md).
Diagrams: [frame loop](diagrams/frame-loop.png), [action stack](diagrams/action-stack.png),
[scene lifecycle](design/scene-lifecycle.png).

## 6. Tests

Run everything with `uv run --group dev pytest`. Tests marked `qemu` skip without QEMU on PATH.

- [ ] [test_anim.py](../98artware_core/tests/test_anim.py) and
  [test_picture.py](../98artware_core/tests/test_picture.py): the scene layer against a stand-in guest, no VM.
- [ ] [test_desktop.py](../98artware_core/tests/test_desktop.py): the blank start against a fake guest.
- [ ] [test_bridge.py](../98artware_core/tests/test_bridge.py) and
  [test_protocol.py](../98artware_core/tests/test_protocol.py): the bridge and wire format.
- [ ] [test_state.py](../98artware_core/tests/test_state.py): state file mistakes are caught early.
- [ ] [test_agent_wine.py](../98artware_core/tests/test_agent_wine.py): the real agent.exe under Wine.
- [ ] [test_qemu.py](../98artware_core/tests/test_qemu.py): real QEMU, no Windows.
- [ ] [test_anim_docs.py](../98artware_core/tests/test_anim_docs.py): the docs match the code.
- [ ] [test_setup.py](../98artware_setup/tests/test_setup.py): the setup tool.
- [ ] [test_container.py](../98artware_container/tests/test_container.py): the container's
  server and the host's end of it, on a fake VM and agent.
- [ ] [test_stage.py](../98artware_container/tests/test_stage.py): the prepared image, booted on
  both backends, including a render. Marked `stage`.
- [ ] [conftest.py](../98artware_core/tests/conftest.py): pins test scenes to the stock desktop.

## 7. Samples and experiments

- [ ] [hello.py](../artware_experiments/hello.py): the smallest scene. Renders to `hello.mp4`.
- [ ] [showcase.py](../artware_experiments/showcase.py): a longer tour of the desktop.
- [ ] [set_state/mvp.py](../artware_experiments/set_state/mvp.py): picture windows set from
  [state files](../artware_experiments/set_state/states/two_windows.json), then moved on camera.
- [ ] [gallery/](../artware_experiments/gallery/): one short scene per feature;
  [render_all.py](../artware_experiments/gallery/render_all.py) makes the GIFs in `docs/assets/gifs`.
- [ ] [check_docs.py](../artware_experiments/check_docs.py): renders every sample in `docs/scenes`
  on the real image.
- [ ] [revert-test/](../artware_experiments/revert-test/README.md): throwaway probes behind the
  state design. Not part of art98, no tests.

Explained in: [Gallery](scenes/gallery.md).

## 8. Docs

- [ ] [setup/](setup/README.md): Part 1, preparing the image.
- [ ] [scenes/](scenes/README.md): Part 2, writing and rendering scenes.
- [ ] [design/](design/architecture.md): architecture, the state and action design, the blank start.
- [ ] [diagrams/](diagrams/README.md): every diagram, each with an editable `.drawio`.
- [ ] [archive/](archive/PLAN.md): the original plan and the Manim mapping, kept for their reasoning.

## 9. Container

Optional. The same QEMU, setup tool and guest programs, packed into one image, so a host only
needs Podman or Docker, Python and ffmpeg. The host still runs the bridge, the recorder and
ffmpeg; only QEMU moves.

- [ ] [README.md](../98artware_container/README.md): what each file is for.
- [ ] [Containerfile](../98artware_container/Containerfile): builds the guest programs, then a
  small Fedora image with QEMU 10.2.2.
- [ ] [serve.py](../98artware_container/art98_container/serve.py): runs in the container. Boots
  the run copy, relays the agent's serial port and answers screenshot, keys and revert.
- [ ] [host.py](../98artware_container/art98_container/host.py): runs on the host. Starts the
  container, `RemoteVM`, and `art98 up`.

Explained in: [Container](design/container.md),
[Quick path in a container](setup/README.md#quick-path-in-a-container), [CLI](setup/cli.md).
