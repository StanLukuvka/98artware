---
inclusion: fileMatch
fileMatchPattern: ["setup/**", "core/art98/container/**", "compose*.yaml", "core/art98/desktop.py", "core/art98/guest/disc.py"]
---

# Setup, prep and the ready snapshot

These files decide how Windows is installed and what the `ready` snapshot holds. Every render
restores that snapshot. A change here makes everyone rebuild their image, and images made
before the change may stop working.

## Rules

- **Open an issue before writing code** for any change to the setup steps in
  `setup/art98_setup/`, the answer file, `ready.py`, the container image, or anything else
  that would need a new `art98 setup` or `art98 up` run. The issue says what the change is for
  and why it can't be done at run time.
- **Do it at run time if you can.** The blank start (`core/art98/desktop.py`) and the wallpaper
  CD (`core/art98/guest/disc.py`) were built at run time for exactly this reason. Prefer that
  pattern.
- **Containers are configured in `compose.yaml`** (and `compose.tcp.yaml`), not in Python. A new
  mount, port or container variable goes there, and every published port stays on `127.0.0.1`.
- **Don't run `art98 up` or `art98 setup`**, delete `work/`, or download Windows media unless
  the user asks. Setup takes 20 to 40 minutes and needs the user's own disc and key.
- **`work/` never leaves this machine.** It holds installed copies of Windows 98. Never copy,
  commit or upload anything from it, including `work/runs/`. Reading setup logs and screenshots
  there is fine.
- **No product keys in the repo**, in any file, test or doc, even though Windows 98 keys are
  public. A key comes from `ART98_PRODUCT_KEY`, the `art98 up` prompt, or a key file named in
  `compose.override.yaml`. That file and `product-key.txt` stay in `.gitignore` and
  `.dockerignore`.

## Testing a change here

Unit tests first. A setup step change also needs a full install into a separate empty work
folder:

```bash
uv run art98 up --iso /path/to/win98se.iso --work /path/to/empty-folder
```

Container and VM service changes need the VM tests, on Docker and, if possible, on Podman.

## More

- `CONTRIBUTING.md`, section "Setup and prep changes"
- `docs/design/decisions.md`, sections 4 (the `ready` snapshot), 5 (QEMU in a container),
  6 (the VM service) and 12 (the blank start)
- `docs/design/container.md` and `docs/design/blank-start.md`
