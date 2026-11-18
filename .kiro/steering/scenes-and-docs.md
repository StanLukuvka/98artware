---
inclusion: fileMatch
fileMatchPattern: ["docs/**/*.md", "recipes/**", "README.md", "core/art98/anim/__init__.py"]
---

# Scenes and docs

The scene docs are tested. `core/tests/test_anim_docs.py` fails the build when they drift from
the code.

## What the docs test checks

- Every ```` ```python ```` block in `docs/scenes/README.md`, `tutorial.md`, `scene-api.md` and
  `animations.md` must run and define exactly one `Scene`. Use ```` ```text ```` or
  ```` ```bash ```` for anything that is not a whole scene.
- Every name in `art98.anim.__all__` must appear in `scene-api.md` or `animations.md`.
- The gallery (`docs/scenes/gallery.md`) must show each source file exactly as it is, and
  every GIF must be in the gallery with its source, and small.
- Links must resolve.

## Writing docs

- A change isn't done until the docs say what it does, in the same pull request.
- Write for someone who has never seen art98: plain words and short sentences.
- Use the terms in `docs/glossary.md`, and add an entry for a new term.
- Say what was measured and how. A timing names the host load and the engine; on Linux, note
  `/proc/pressure/cpu` next to it. A Windows 98 fact says it was checked on the real image.
- Link to the design docs instead of repeating them.
- Diagrams in `docs/diagrams/` are draw.io files with a PNG export beside each. Change both.
- No personal details: no names, emails, or details of one machine.
- Leave `docs/status.md` alone in a feature change.

## Scenes

- `recipes/scenes/` holds maintained scenes the docs embed. Keep them rendering.
- `recipes/helpers/` holds action modules that scenes import (`from helpers.<module> import ...`).
- When a change alters what a documented scene does, run these on the real VM:

```bash
uv run python tools/check_docs.py
```

```bash
uv run python tools/render_all.py
```
