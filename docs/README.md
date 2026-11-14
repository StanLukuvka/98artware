# Documentation

art98 makes animations from a real Windows 98 SE desktop running in a virtual machine. It has
two parts. [Part 1](setup/README.md) prepares the VM image once, and
[Part 2](scenes/README.md) drives that image to make videos.

Audio is deferred, so everything here is video only.

![System overview](diagrams/system-overview.png)

## Start here

1. The [README](../README.md): what art98 is, and from nothing to a first video.
2. The [glossary](glossary.md): the words these pages use, such as state, prop, action and the
   `ready` snapshot.
3. The [tutorial](scenes/tutorial.md): your first scenes, step by step.
4. The [gallery](scenes/gallery.md): short scenes to copy from.

To change art98 itself, read [Contributing](../CONTRIBUTING.md), the
[design decisions](design/decisions.md) and the [repo tour](tour.md). Coding agents start from
[AGENTS.md](../AGENTS.md).

## Part 1: VM preparation

| Page | What it covers |
| --- | --- |
| [Overview](setup/README.md) | What `art98 up` and `art98 setup` do, what you need, and the quick paths. |
| [Steps](setup/stages.md) | The four setup steps in detail: inputs, outputs, failures. |
| [CLI](setup/cli.md) | Every `art98` command and flag, environment variables, and the work directory. |
| [Configuration](setup/config.md) | `art98.toml`: the image, the work folder, the ports, and how to attach from another container. |
| [The image](setup/image.md) | What the finished image holds, every setting and why, including your product key. |
| [Troubleshooting](setup/troubleshooting.md) | Setup quirks, a busy host, and how to recover from a failed run. |

## Part 2: scenes

| Page | What it covers |
| --- | --- |
| [Overview](scenes/README.md) | A first scene, how the layers fit, and how art98 differs from Manim. |
| [Tutorial](scenes/tutorial.md) | Your first scenes, step by step. Start here. |
| [Scene API](scenes/scene-api.md) | `Scene`, props, programs, states, the desktop space, clips, rendering. |
| [Animations](scenes/animations.md) | Everything you pass to `play`, and how to write your own. |
| [Gallery](scenes/gallery.md) | One short scene per feature, with its GIF and source. |
| [Bridge](scenes/bridge.md) | The raw Win32 link behind `self.guest`. |
| [Instruction set](scenes/instruction-set.md) | The serial protocol the agent speaks. |
| [Win32 recipes](scenes/win32-recipes.md) | Win32 calls that are known to work from the agent. |
| [App catalog](scenes/app-catalog.md) | What is on the image, and how each program behaves. |

## Design

| Page | What it covers |
| --- | --- |
| [Design decisions](design/decisions.md) | Each major choice, why it was made, and the rule for future work of that kind. |
| [Architecture](design/architecture.md) | Every part of art98 and how a render flows through them, and how it compares with Manim. |
| [State and action design](design/state-and-action.md) | Hand-written starting states and free Python on top, the recorder, and the tests behind them. |
| [Container](design/container.md) | QEMU in a container, `art98 up`, the VM service, the relay protocol and its timings. |
| [Blank start](design/blank-start.md) | Why nothing pops up, and how a scene gets its black, empty screen. |
| [Programs](design/programs.md) | What a program class is, how a state opens one, and how to add the next. |
| [Inspiration](design/inspiration.md) | A Windows 98 lyric video, mapped to what art98 can do. |

[All diagrams](diagrams/README.md), each with an editable `.drawio` file.

## Working on art98

| Page | What it covers |
| --- | --- |
| [Contributing](../CONTRIBUTING.md) | Setup, tests, lint, adding a program or a state feature, doc rules, scope, licence. |
| [AGENTS.md](../AGENTS.md) | The same for coding agents, with the house rules spelled out. |
| [Repo tour](tour.md) | Every folder and file in reading order, with what each does and where it is explained. |
| [Status](status.md) | What works, what is open, and the bugs on hold. Start here when picking work up. |
| [Changelog](../CHANGELOG.md) | What each release holds, and its known limits. |
| [Release checklist](release-checklist.md) | A hand-run list for checking a release: clean clone, renders, frames, the VM service, tests, tree hygiene. |

Archived, kept for their reasoning: [build history](archive/build-history.md), [PLAN.md](archive/PLAN.md), the original creative
direction, the [Manim mapping plan](archive/MANIM_MAPPING_PLAN.md) and its
[review](archive/MANIM_MAPPING_REVIEW.md).
