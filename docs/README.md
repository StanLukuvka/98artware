# Documentation

art98 has two parts. [Part 1](setup/README.md) prepares the VM image once, and
[Part 2](scenes/README.md) drives that image to make videos.

Audio is deferred, so everything here is video only.

![System overview](diagrams/system-overview.png)

## Part 1: VM preparation

| Page | What it covers |
| --- | --- |
| [Overview](setup/README.md) | What `art98 setup` does, and the quick paths: `art98 up` in a container, or on the host. |
| [Steps](setup/stages.md) | Each step in detail: inputs, outputs, failures. |
| [CLI](setup/cli.md) | `art98 doctor`, `setup`, `ping`, `up` and `serve`, and the work directory. |
| [The image](setup/image.md) | What the finished image holds, including your product key. |
| [Troubleshooting](setup/troubleshooting.md) | Setup quirks and how to recover from a failed run. |

## Part 2: scenes

| Page | What it covers |
| --- | --- |
| [Overview](scenes/README.md) | A first scene and how the layers fit. |
| [Tutorial](scenes/tutorial.md) | Your first scenes, step by step. Start here. |
| [Scene API](scenes/scene-api.md) | `Scene`, props, picture windows, states, rendering. |
| [Animations](scenes/animations.md) | Everything you pass to `play`, and how to write your own. |
| [Gallery](scenes/gallery.md) | One short scene per feature, with its GIF and source. |
| [Bridge](scenes/bridge.md) | The raw Win32 proxy behind `self.guest`. |
| [Instruction set](scenes/instruction-set.md) | The serial protocol the agent speaks. |
| [Win32 recipes](scenes/win32-recipes.md) | Win32 calls that are known to work from the agent. |
| [App catalog](scenes/app-catalog.md) | What is on the image, and how each program behaves. |

## Architecture

[Architecture, and how it compares with Manim](design/architecture.md).
[All diagrams](diagrams/README.md), each with an editable `.drawio` file:

- [Architecture](diagrams/architecture.png) and [art98 vs Manim](diagrams/manim-comparison.png)
- [System overview](diagrams/system-overview.png)
- [Setup pipeline](diagrams/prep-pipeline.png)
- [Install boot chain](diagrams/install-boot-chain.png)
- [Action stack](diagrams/action-stack.png)
- [Request lifecycle](diagrams/request-lifecycle.png)
- [Frame loop](diagrams/frame-loop.png)

## Planning

| Page | What it covers |
| --- | --- |
| [Repo tour](tour.md) | Every folder and file in reading order, with what each does and where it is explained. |
| [Status](status.md) | What exists, what was done, and what is still open. Start here when picking work up. |
| [State and action design](design/state-and-action.md) | Static starting states and free actions on top. The MVP is built; named actions and the recorder aren't. |
| [Architecture](design/architecture.md) | Every part of art98, and how it compares with Manim. |
| [Blank start](design/blank-start.md) | Why nothing pops up, and how a scene gets its black, empty screen. |
| [Container](design/container.md) | QEMU and setup in a Podman or Docker container, `art98 up`, the relay protocol and its timings. Built and tested from scratch. |

Archived, kept for their reasoning: [PLAN.md](archive/PLAN.md), the original creative
direction, the [Manim mapping plan](archive/MANIM_MAPPING_PLAN.md) and its
[review](archive/MANIM_MAPPING_REVIEW.md).
