# 98artware

Script animations with a real Windows 98 desktop as the medium, in the style of Manim. You
write a Python scene, Windows draws it inside a VM, and the video is what the guest's screen
showed. Python draws nothing.

![Two picture windows are set from a state file, then moved, teleported and closed on camera](docs/assets/gifs/mvp.gif)

That clip is [artware_experiments/set_state/mvp.py](artware_experiments/set_state/mvp.py),
rendered through the container.

## The pattern: a state, then actions

A scene starts from a **state**, a hand-written JSON file that describes a still desktop:
which windows are open, where they sit, what they show, and where the pointer is. Everything
after that is **actions**, which are free Python on top: animations, Win32 calls, anything.

```json
{
  "version": 1,
  "display": [800, 600, 16],
  "windows": [
    {"id": "album", "app": "picture", "title": "Album", "at": [380, 220], "size": [360, 280]},
    {"id": "flower", "app": "picture", "title": "Flower", "at": [60, 60], "size": [240, 200],
     "open": {"file": "../assets/flower.bmp", "sha256": "2357680...a619"}}
  ],
  "pointer": [400, 500]
}
```

This is the scene, without its pauses:

```python
from pathlib import Path

from art98.anim import *

HERE = Path(__file__).parent


class Mvp(Scene):
    state = "states/two_windows.json"  # found beside the scene's file

    def construct(self):
        flower = self.prop("flower")  # the window the state opened
        self.play(flower.animate.shift(200 * RIGHT), run_time=2)
        self.play(Teleport(flower, to=(40, 40), aligned_edge=UL))
        self.play(Close(flower))
        self.add(Picture("Sky", image=HERE / "assets" / "sky.bmp", at=(100, 260), size=(240, 200)))

        self.set_state("states/gallery.json")  # a new starting desktop, off camera
        self.play(self.prop("picture").animate.shift(100 * DOWN), run_time=2)
```

```bash
ART98_BACKEND=container uv run art98 render artware_experiments/set_state/mvp.py -o mvp.mp4
```

What happens when it runs:

1. **Set.** The guest reverts to the `ready` snapshot, the state's windows open, and art98
   reads the desktop back to check that it matches. A mistake in the file is listed before the
   desktop is touched, and a mismatch stops with each difference. A Set takes about 1.5 s,
   and none of it is filmed.
2. **A blank start.** Each Set and boot clears the desktop to plain black, with no icons,
   taskbar or pointer, so only what the scene puts there shows. `desktop = "stock"` keeps the
   normal Windows desktop. See [Blank start](docs/design/blank-start.md).
3. **Actions.** `play` moves real windows, and each frame waits for the guest to repaint
   before it is captured. `self.guest` is the raw bridge, so any Win32 call can sit between
   two animations.
4. **Again.** `set_state` can run as often as a scene likes, and each time it gives the same
   desktop.

Because every frame is synced to the guest and QEMU emulates the CPU in software, a scene
renders the same frames on any host. The MVP scene gives 0 of 257 frames different between
the local backend and the container, and between an image built in the container and one
built on the host.

The MVP's one window is [`Picture`](docs/scenes/scene-api.md#picture), art98's own small
viewer that shows a BMP. Notepad, Paint, Minesweeper, Screensaver and Dialog still work, but
they're parked in `art98.anim.apps` until each comes back as its own action class. Named
actions (`next_section`), re-recording one action, and a recorder that cuts clips are designed
but not built: see the [state and action design](docs/design/state-and-action.md) and
[status](docs/status.md).

## Quick start, in a container

You need Docker, Python 3.11 or newer with [uv](https://docs.astral.sh/uv/), ffmpeg,
and your own Windows 98 SE disc image and product key. Nothing here supplies them. art98
calls only `docker`. On a Podman host, install `podman-docker`, which provides that command.

```bash
uv run art98 up --iso /path/to/win98se.iso
```

`art98 up` builds the container image, asks for the key without echo (or reads
`ART98_PRODUCT_KEY`), installs Windows into `work/` with no further input, then boots the
result and checks the agent answers. It takes 25 to 40 minutes, once. `--watch` shows setup
over VNC on `127.0.0.1:5998`. After that, every render restores the snapshot in about a
second:

```bash
export ART98_BACKEND=container
```

```bash
uv run art98 render artware_experiments/set_state/mvp.py -o mvp.mp4
```

`-o` also takes `.gif`. Each render works on a private copy of the image, so several can run
side by side. The by-hand `docker` commands are in
[the setup guide](docs/setup/README.md#quick-path-in-a-container), and how the container code
is laid out is in [the container design](docs/design/container.md#the-image).

Running `art98 up` or `art98 setup` accepts the Windows 98 licence agreement on your behalf:
the answer file asks to skip it, and OEM discs that show it anyway get "I accept" selected by
keystroke.

**Don't publish `work/`.** The finished image is an installed copy of Windows 98, so never
share `golden.qcow2` or a copy of it. `work/` is gitignored for that reason. It also holds your
product key in clear text, which matters less for a 1998 key; see
[the key on the image](docs/setup/image.md#your-product-key-is-on-the-image).

## Or on the host

The `local` backend, still the default, runs QEMU on the host instead. Install the tools. On
Fedora:

```bash
sudo dnf install qemu-system-x86 qemu-img mtools 7zip ffmpeg make binutils mingw32-gcc
```

On Debian or Ubuntu:

```bash
sudo apt install qemu-system-x86 qemu-utils mtools 7zip ffmpeg make binutils gcc-mingw-w64-i686
```

Then build the guest programs, check the tools, and prepare the image:

```bash
make -C guest
```

```bash
uv run art98 doctor
```

```bash
uv run art98 setup --iso /path/to/win98se.iso
```

Setup runs four steps, `vm`, `setup`, `init_api` and `ready`, saving progress after each, so
rerunning resumes. [Part 1](docs/setup/README.md) explains each one. Render as above, without
`ART98_BACKEND`.

## How it fits together

```
Host: Python                          Container: art98 serve       Guest: Windows 98 SE
  your scene, art98.anim
  art98.Bridge ---- agent channel ---> relayed to COM1 ----------> AGENT.EXE: Win32 call proxy
  RemoteVM -------- control channel -> QEMU: keys, revert -------> the desktop
  FrameRecorder, ffmpeg <---------- frames ----------------------- QEMU's screenshots
```

The host keeps the scene, the bridge, the recorder and ffmpeg, and only QEMU moves. On Linux
the two channels are a Unix socket in a mounted folder, and frames are written into that
folder. Elsewhere the channels are a loopback TCP port and frames come over the control
channel. On the `local` backend `art98.VM` drives QEMU over QMP directly, and nothing else
changes.

![System overview](docs/diagrams/system-overview.png)

| Folder | What it holds |
| --- | --- |
| [core/](core/art98/) | The `art98` package: the scene layer in `anim/`, the bridge, QEMU control, states, and the container backend in `container/` |
| [setup/](setup/art98_setup/) | `art98 setup` and `art98 up`, which turn a disc into `work/golden.qcow2`, and the `Dockerfile` |
| [guest/](guest/) | The programs that run inside Windows 98: `AGENT.EXE`, the `VIEW.EXE` picture viewer and the install disk's boot record |
| [artware_experiments/](artware_experiments/) | The MVP scene, the gallery, older demos and throwaway probes |
| [docs/](docs/README.md) | Every page, starting from [docs/README.md](docs/README.md) |
| `work/` | Your prepared image. Gitignored |

The [repo tour](docs/tour.md) walks through every file in reading order.

## Writing scenes

Start with the [tutorial](docs/scenes/tutorial.md). The [Scene API](docs/scenes/scene-api.md)
covers props, [states](docs/scenes/scene-api.md#states) and rendering, and
[Animations](docs/scenes/animations.md) lists everything you pass to `play`. The
[gallery](docs/scenes/gallery.md) has one short scene per feature, most of them written before
the MVP with the parked programs.

Below the scene layer, any exported Win32 function from any DLL is one call away:

```python
from art98 import Out, boot

with boot("work", backend="container") as stage:
    guest = stage.bridge
    guest.spawn("notepad.exe")
    notepad = guest.find_window(class_name="Notepad")

    guest.user32.SetWindowPos(notepad.hwnd, 0, 100, 80, 400, 300, 0x14)
    guest.user32.SetCursorPos(200, 200)
    rect = guest.user32.GetWindowRect(notepad.hwnd, Out(16)).buffers[0]

    # Anything that blocks goes on its own guest thread.
    dialog = guest.acall("user32", "MessageBoxA", 0, "hello", "98", 0)

    stage.vm.screenshot("frame.png")
```

Every `boot()` restores the same snapshot, so nothing carries over between runs. In a scene
the same object is `self.guest`. See the [bridge](docs/scenes/bridge.md), the
[instruction set](docs/scenes/instruction-set.md) and the
[Win32 recipes](docs/scenes/win32-recipes.md).

A guest reboot ends the VM, because Windows freezes on its logo after a warm reset in the same
QEMU process. Start a new one with `boot()` afterwards. `ExitWindowsEx` never replies, so call
it with `acall`.

## Tests

```bash
uv run --group dev pytest
```

| Suite | Runs against |
|-------|--------------|
| `test_protocol`, `test_bridge` | Python alone |
| `test_anim`, `test_picture`, `test_desktop`, `test_state` | The scene layer, the blank start and state files, on a fake guest |
| `test_anim_docs` | The documented API against the code |
| `test_setup`, `test_up` | The setup tool, with mtools for the disk tests, and `art98 up` without an engine |
| `test_qemu` | Real QEMU with no Windows: boot chain, QMP, snapshots |
| `test_agent_wine` | The real `agent.exe` under Wine, with a pty as COM1 |
| `test_container` | The container's server and the host's end of it, on a fake VM and agent. No container needed |
| `test_stage` | The prepared image in `work/` (or `ART98_TEST_WORK`), on the local and the container backend, including a render |

The QEMU, Wine and container suites skip themselves if those tools are missing, and
`test_stage` skips without a prepared image. Only `test_stage` runs real Windows 98.
[artware_experiments/check_docs.py](artware_experiments/check_docs.py) renders every sample in
the scene docs on the real image, on whichever backend `ART98_BACKEND` names.

## Measured on real Windows 98

From a Windows 98 SE OEM disc, on QEMU 10.2.2 with software emulation:

| What | Result |
|------|--------|
| Full `art98 up` in the container, quiet host | About 25 min, of which Windows Setup 22 min |
| Full `art98 setup` on the host | About 40 min |
| Snapshot restore to a working agent | About 1 s |
| A Set with two windows and an image | 1.2 to 1.6 s |
| The MVP scene, 257 frames | 5.5 s local, 6.2 s through the container |
| Frames of the MVP scene that differ, local against container, and host-built image against container-built | 0 of 257 |
| All 32 scene-docs samples through the container, three at a time | 38 s |
| One recorded frame, local and through the container on Linux | 5.6 to 6.3 ms and 6.8 to 7.0 ms ([timing](docs/design/container.md#timing)) |
| `PING` round trip | About 5 ms |
| `put_file` | 100 to 190 KB/s |
| `get_file` | About 325 KB/s |
| Guest clock against host | 5004 ms over 5 s |

Times depend on host load. The serial port is emulated and QEMU doesn't pace it to 115200
baud, so files move well above the line rate. Setup quirks that `art98 setup` handles are in
[troubleshooting](docs/setup/troubleshooting.md).

## Not done yet

- Audio is deferred. art98 is video only for now, though the VM keeps its Sound Blaster.
- The container is tested through Podman's `docker` command, not with real Docker. Rootful
  Docker's switch to your uid ran only against a stand-in uid map.
- The Wine suite against the final agent. It needs a Wine prefix on this machine.

[docs/status.md](docs/status.md) has the full list of what's built and what's next.
[PLAN.md](docs/archive/PLAN.md), now archived, has the original creative direction.
