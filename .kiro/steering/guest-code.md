---
inclusion: fileMatch
fileMatchPattern: ["guest/**", "core/art98/guest/**"]
---

# Guest code and the agent protocol

Two folders share the name. The top-level `guest/` is C that runs inside Windows 98:
`agent.exe` (the agent), `view.exe` (art98's picture viewer) and `mbr.bin`.
`core/art98/guest/` is the Python side of talking to the VM: `bridge.py` and `protocol.py` (the
host side of the agent protocol), `qemu.py`, `win32.py`, `guestfiles.py` and `disc.py`.

## Rules

- **Keep the agent thin.** It makes any Win32 call the host asks for, and nothing more. Put new
  behaviour in Python on the host, not in the agent (`docs/design/decisions.md`, section 3).
- **`bridge.py` and `protocol.py` are transport only.** No scene or program logic there.
- **Big files go on a CD image, not down the serial line** (`docs/design/decisions.md`,
  section 15).
- The build output in `guest/build/` is gitignored. Don't commit it.

## Building and testing

```bash
make -C guest
```

That needs the mingw cross-compiler. CI builds `guest/` too, so the checks on the guest
programs run there. A guest change also needs a rebuilt image and a fresh VM
before the VM tests:

```bash
uv run art98 up --rebuild
```

```bash
uv run art98 vm stop && uv run art98 vm start
```

`core/tests/test_agent_wine.py` runs the agent under Wine, and skips if Wine is missing.

Stop a stray VM with `art98 vm stop` or by its PID. Never use `pkill -f qemu-system-i386`,
because the pattern can match the shell that runs it.

More: `docs/scenes/bridge.md` and `docs/scenes/instruction-set.md`.
