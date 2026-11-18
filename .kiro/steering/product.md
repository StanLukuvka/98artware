---
inclusion: always
---

# Product: art98

Kiro also loads the root `AGENTS.md` on every request. That file holds the rules, the
commands and the repo map. This file adds what art98 is for, so choices fit the product.

## What it is

art98 makes animations out of a real Windows 98 SE desktop. A scene author writes a short
Python script in the style of Manim. art98 plays it on Windows 98 SE in a QEMU virtual machine
and records the screen. Python draws nothing: every window, letter and brush stroke is drawn
by Windows itself.

## Who it is for

- **Scene authors**: people who make videos and GIFs of Windows 98, and the AI agents that
  write scenes for them. They see `from art98.anim import *`, the CLI, and the docs under
  `docs/scenes/`. A change to what they see needs a matching docs change.
- **Contributors** to art98. Their guide is `CONTRIBUTING.md`.

## What matters most

1. **The output is real.** Pixels come from Windows, never from Python. Don't fake a window,
   cursor or effect on the host side to make a scene easier.
2. **The same scene gives the same frames.** Every render starts from the `ready` snapshot and
   waits until Windows has finished drawing each frame. Don't add anything that depends on
   wall-clock timing or on state left over from an earlier render.
3. **Errors say what to do.** An error a user can cause gets one `error:` line that tells them
   how to fix it.
4. **Lean first.** One module and one code path. Add more only when a measurement or a real use
   asks for it.

## Out of scope

These won't be merged, so don't plan for them:

- programs that don't ship on the Windows 98 SE disc, and any add-on or plugin system
- audio
- resolutions other than 640x480, 800x600, 1024x768 and 1280x1024
- animated desktop icons

The reasons are in `docs/design/decisions.md`, section 10.

## Where to look

- What is built and what is next: `docs/status.md`. Read it, but don't edit it in a feature
  change; it is updated at release time.
- Why things are built the way they are: `docs/design/decisions.md`. Steering file
  `design-decisions` loads it for spec design documents and questions about direction or scope.
- Words like *ready snapshot*, *agent*, *state* and *blank start*: `docs/glossary.md`.
