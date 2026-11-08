# Documentation

art98 has two parts. [Part 1](prep/README.md) prepares the VM image once, and
[Part 2](actions/README.md) drives that image to make videos.

Audio is deferred, so everything here is video only.

![System overview](diagrams/system-overview.png)

## Part 1: VM preparation

| Page | What it covers |
| --- | --- |
| [Overview](prep/README.md) | What `art98 prep` does, and the quick path. |
| [Stages](prep/stages.md) | Each stage in detail: inputs, outputs, failures. |
| [CLI](prep/cli.md) | `art98 doctor`, `prep` and `ping`, and the work directory. |
| [The image](prep/image.md) | What the finished image holds, including your product key. |
| [Troubleshooting](prep/troubleshooting.md) | Setup quirks and how to recover from a failed run. |

## Part 2: the action handler

| Page | What it covers |
| --- | --- |
| [Overview](actions/README.md) | A first scene and how the layers fit. |
| [Tutorial](actions/tutorial.md) | Your first scenes, step by step. Start here. |
| [Scene API](actions/scene-api.md) | `Scene`, props, app props, rendering. |
| [Animations](actions/animations.md) | Everything you pass to `play`, and how to write your own. |
| [Gallery](actions/gallery.md) | One short scene per feature, with its GIF and source. |
| [Bridge](actions/bridge.md) | The raw Win32 proxy behind `self.guest`. |
| [Instruction set](actions/instruction-set.md) | The serial protocol the agent speaks. |
| [Win32 recipes](actions/win32-recipes.md) | Win32 calls that are known to work from the agent. |
| [App catalog](actions/app-catalog.md) | What is on the image, and how each program behaves. |

## Architecture

[All diagrams](diagrams/README.md), each with an editable `.drawio` file:

- [System overview](diagrams/system-overview.png)
- [Prep pipeline](diagrams/prep-pipeline.png)
- [Install boot chain](diagrams/install-boot-chain.png)
- [Action stack](diagrams/action-stack.png)
- [Request lifecycle](diagrams/request-lifecycle.png)
- [Frame loop](diagrams/frame-loop.png)

## Planning

| Page | What it covers |
| --- | --- |
| [Status](status.md) | What exists, what was done, and what is still open. Start here when picking work up. |
| [State and action design](design/state-and-action.md) | Static starting states and free actions on top. Not built yet, with the first test's results. |
| [PLAN.md](../PLAN.md) | The creative direction. |
| [Manim mapping plan](MANIM_MAPPING_PLAN.md) | How Manim's tools map to Windows 98 actions. Only a first slice is built. |
| [Plan review](MANIM_MAPPING_REVIEW.md) | The review of that plan. |
