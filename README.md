# 98artware

art98 makes animations out of a real Windows 98 desktop. You write a short Python script in
the style of [Manim](https://www.manim.community/), art98 plays it on Windows 98 SE running in
a virtual machine, and the video is what that machine's screen showed. Python draws nothing:
every window, letter and brush stroke is drawn by Windows itself.

![Notepad types a line, Paint draws and fills a heart, Minesweeper opens with one click, a Notepad is dragged by its title bar, and a message box is answered](docs/assets/gifs/hero.gif)

That clip is [examples/readme/hero.py](examples/readme/hero.py): one short scene, played on
real Windows 98 programs. Each clip below is one scene from the [gallery](docs/scenes/gallery.md),
which has the source of every one.

<table>
  <tr>
    <td align="center"><a href="docs/scenes/gallery.md#typing"><img src="docs/assets/gifs/typing.gif" width="260" alt="Notepad types three lines, deletes a few words and types new ones"></a><br>Typing into Notepad</td>
    <td align="center"><a href="docs/scenes/gallery.md#dragging"><img src="docs/assets/gifs/drag-window.gif" width="260" alt="The pointer drags a Notepad window by its title bar, then resizes it by a corner"></a><br>Dragging with the pointer</td>
    <td align="center"><a href="docs/scenes/gallery.md#window-motion"><img src="docs/assets/gifs/window-motion.gif" width="260" alt="A Notepad window moves, resizes and follows a path"></a><br>Moving and resizing windows</td>
  </tr>
  <tr>
    <td align="center"><a href="docs/scenes/gallery.md#paint"><img src="docs/assets/gifs/paint-drawing.gif" width="260" alt="Paint draws a flower outline with the brush and fills it"></a><br>Drawing in Paint</td>
    <td align="center"><a href="docs/scenes/gallery.md#minesweeper"><img src="docs/assets/gifs/minesweeper-win.gif" width="260" alt="Minesweeper is won click by click and the best time is signed"></a><br>Winning Minesweeper</td>
    <td align="center"><a href="docs/scenes/gallery.md#dialog-storm"><img src="docs/assets/gifs/dialog-storm.gif" width="260" alt="A cascade of message boxes on a teal desktop that turns dark red"></a><br>Message boxes and desktop colours</td>
  </tr>
</table>

## How it works, in short

- Windows 98 SE runs inside **QEMU**, an emulator, in a **Docker container**. You supply the
  Windows disc and product key; nothing here includes them.
- `art98 up` installs Windows once, with no input, and saves the **`ready` snapshot**: a saved
  moment of the running machine, with Windows booted and art98's helper program running.
- `art98 vm start` starts the **VM service**: that machine, kept running in the background and
  paused between renders.
- `art98 render scene.py` takes the VM, restores `ready` (about a second), plays your scene,
  records the screen frame by frame, and writes an MP4 or GIF with ffmpeg. The next render
  starts from `ready` again, so nothing carries over.

Inside the guest, a small program called the **agent** (`AGENT.EXE`) makes any Win32 call the
script asks for. Every frame waits until Windows has finished drawing, and QEMU emulates the CPU
in software, so a scene gives the same frames on any machine.

New words are in the [glossary](docs/glossary.md).

## What you need

- Linux. Other systems may work through Docker Desktop but have not been tried.
- Docker, or Podman with the `podman-docker` package. art98 only ever runs the `docker` command.
- Python 3.11 or newer, and [uv](https://docs.astral.sh/uv/).
- ffmpeg.
- Your own Windows 98 SE disc image (an `.iso`) and its product key. The disc must boot from
  an emulated floppy and hold a `WIN98` folder; see [other discs](docs/setup/troubleshooting.md#a-different-disc).
  Setup has been run on one OEM disc only, so another disc may fail.
- About 3 GB of free disk space, and 25 to 40 minutes for the one-time install.

art98 runs from a checkout with `uv run`. There is no package to install and no `pip install`.

## From nothing to a video

**1. Get the code and check your machine.**

```bash
git clone https://github.com/StanLukuvka/98artware 98artware && cd 98artware
```

```bash
uv run art98 doctor
```

`doctor` lists each tool it looks for. On a machine with only Docker and ffmpeg it says the VM
is usable once you have run `art98 up`; the other tools are only for installing on the host.

**2. Build the prepared image, once.**

```bash
uv run art98 up --iso /path/to/win98se.iso
```

This builds the container image, asks for your product key at a visible prompt (or reads
`ART98_PRODUCT_KEY`), installs Windows into `work/` with no further input, and stops. It takes
25 to 40 minutes. Add `--watch` and point a VNC viewer at `127.0.0.1:5998` to see the install.
If it stops part way, run the same command again: it resumes.

**3. Start the VM.**

```bash
uv run art98 vm start
```

It stays up, paused, until `art98 vm stop`. `uv run art98 vm status` says how it is.

**4. Render a scene.**

```bash
uv run art98 render examples/mvp/mvp.py -o mvp.mp4
```

You get `mvp.mp4`. Give `-o` a `.gif` name for a GIF instead, or add `--gif mvp.gif` for both.

**5. Stop the VM when you are done.**

```bash
uv run art98 vm stop
```

Next, follow the [tutorial](docs/scenes/tutorial.md) to write your own scene.

Renders take turns: while one runs, another fails with `busy`, unless you give it `--wait S`
to wait up to S seconds. If something goes wrong, [troubleshooting](docs/setup/troubleshooting.md)
covers the install. art98's own errors are one line starting with `error:`.

The unit tests need no VM and run in CI on every push;
[Contributing](CONTRIBUTING.md#tests) has the commands and says which suite covers what.

### Before you share anything

Running `art98 up` (or `art98 setup`) accepts the Windows 98 licence agreement on your behalf:
the answer file asks to skip it, and OEM discs that show it anyway get "I accept" by keystroke.
Only run it with a disc and key you are licensed to use.

**Don't publish `work/`.** It holds an installed copy of Windows 98, which is not yours to
share, and your key in clear text. `work/` is gitignored for that reason. Product keys are public
and reusable, not secrets, but never add one to the repo. The real secret is the VM token,
`work/vm.token`. See [the key on the image](docs/setup/image.md#your-product-key-is-on-the-image).

## A scene: a state, then actions

A scene starts from a **state**: a JSON file you write by hand that describes a still desktop.
It says which windows are open, where they sit, what they show, and where the pointer is.

```json
{
  "version": 1,
  "display": [800, 600, 16],
  "windows": [
    {"id": "album", "app": "picture", "title": "Album", "at": [380, 220], "size": [360, 280]},
    {"id": "flower", "app": "picture", "title": "Flower", "at": [60, 60], "size": [240, 200],
     "open": {"file": "../assets/flower.bmp", "sha256": "<sha256 of the file>"}}
  ],
  "pointer": [400, 500]
}
```

A file a state opens is named by path and by its hash, so a changed file is caught. Fill in
`sha256` with the output of `sha256sum`, for example `sha256sum examples/mvp/assets/flower.bmp`.

Everything after that is **actions**: free Python that moves windows, types, clicks or makes
any Win32 call. This is the MVP scene, without its pauses:

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
        self.add(
            Picture(
                "Sky", image=HERE / "assets" / "sky.bmp", at=(100, 260), size=(240, 200)
            )
        )

        self.set_state("states/gallery.json")  # a new starting desktop, off camera
        self.play(self.prop("picture").animate.shift(100 * DOWN), run_time=2)
```

`self.prop("flower")` is a **prop**: a Python handle on the real window. `self.play` runs
**animations** on props, one frame at a time. Positions are screen pixels with y running down,
so `DOWN` is `(0, 1)`.

What happens when it runs:

1. **Set.** The guest reverts to the `ready` snapshot, the state's windows open, and art98
   reads the desktop back to check that it matches. A mistake in the file is listed before the
   desktop is touched, and a mismatch stops with each difference. A Set takes about 1.5 s, and
   none of it is filmed.
2. **A blank start.** The desktop is cleared to plain black, with no icons, taskbar or pointer,
   so only what the scene puts there shows. `desktop = "stock"` keeps the normal Windows
   desktop. See [Blank start](docs/design/blank-start.md).
3. **Actions.** `play` moves real windows, and each frame waits for the guest to repaint before
   it is captured. `self.guest` is the raw link to the agent, so any Win32 call can sit between
   two animations.
4. **Again.** `set_state` can run as often as a scene likes, and each time it gives the same
   desktop. Every scene also starts from a fresh `ready` desktop, even when several scenes are
   rendered one after another from Python.

When art98 raises one of its own errors during a scene, such as a state that doesn't match or
a guest call that fails, `art98 render` prints one line that ends with where it happened in
your file, such as `error: ... (mvp.py:21, in construct)`. Set `ART98_TRACE=1` for the full
traceback. Other Python errors in a scene show the usual traceback.

The windows a scene can use: [`Picture`](docs/scenes/scene-api.md#picture), art98's own small
viewer for a BMP; [`Notepad`](docs/scenes/scene-api.md#notepad);
[`Dialog`](docs/scenes/scene-api.md#dialog), a real message box;
[`Paint`](docs/scenes/scene-api.md#paint), [`Minesweeper`](docs/scenes/scene-api.md#minesweeper)
and [`Screensaver`](docs/scenes/scene-api.md#screensaver). A state can open `picture` and
`notepad` windows; the others are added in `construct`. [`Backdrop`](docs/scenes/scene-api.md#backdrop)
sets the desktop colour, and a state can set a colour and a wallpaper. `self.cut()` ends one
video clip and starts the next, and `self.next_section(name)` does the same with a label; the
clips are kept as `<stem>-01.mp4` and on, and joined into the output.

## Where to go next

| You want to | Read |
| --- | --- |
| Write your first scene | [Tutorial](docs/scenes/tutorial.md) |
| Look up a class or option | [Scene API](docs/scenes/scene-api.md), [Animations](docs/scenes/animations.md) |
| Copy from working examples | [Gallery](docs/scenes/gallery.md), [examples/](examples/) |
| Call Win32 directly | [Bridge](docs/scenes/bridge.md), [Win32 recipes](docs/scenes/win32-recipes.md) |
| Understand the install | [Part 1: preparing the VM](docs/setup/README.md) |
| Look up a command or setting | [CLI](docs/setup/cli.md), [Configuration](docs/setup/config.md) |
| Render from another container | [Attach from another container](docs/setup/config.md#attach-from-another-container) |
| Understand why it is built this way | [Design decisions](docs/design/decisions.md), [Architecture](docs/design/architecture.md) |
| Find your way round the code | [Repo tour](docs/tour.md) |
| Change art98 | [Contributing](CONTRIBUTING.md), and [AGENTS.md](AGENTS.md) for coding agents |
| See what is built and what is next | [Status](docs/status.md), [Changelog](CHANGELOG.md) |

Every page is listed in [docs/README.md](docs/README.md).

## How it fits together

```
Host: Python                          Container: art98 serve       Guest: Windows 98 SE
  your scene, art98.anim
  art98.Bridge ---- agent channel ---> relayed to COM1 ----------> AGENT.EXE: Win32 call proxy
  RemoteVM -------- control channel -> QEMU: keys, revert -------> the desktop
  Recorder, ffmpeg <--------------- frames ----------------------- QEMU's screenshots
```

Your machine keeps the scene, the bridge, the recorder and ffmpeg. Only QEMU runs in the
container. On Linux the two channels are a Unix socket in a mounted folder, and QEMU writes
frames straight into that folder; elsewhere they are a loopback TCP port. The details are in
[the container design](docs/design/container.md).

| Folder | What it holds |
| --- | --- |
| [core/](core/art98/) | The `art98` package. `anim/` is what scenes import; it sits on `base/` (animations, props, vectors, the desktop space) and `actions/` (the pointer, the keyboard, windows and programs). Beside them: the bridge, QEMU control, state files, and the VM service in `service.py` and `container/` |
| [setup/](setup/art98_setup/) | `art98 setup` and `art98 up`, which turn a disc into `work/golden.qcow2`, and the `Dockerfile` |
| [guest/](guest/) | The programs that run inside Windows 98: `AGENT.EXE`, the `VIEW.EXE` picture viewer and the install disk's boot record |
| [examples/](examples/) | Maintained scenes: the MVP, the dialog storm, the blank-start proof scene, the gallery, `hello.py` and `showcase.py`. The docs embed them |
| [tools/](tools/) | `render_all.py` makes the gallery GIFs, `check_docs.py` renders the doc samples |
| [experiments/](experiments/) | Throwaway probes behind design decisions. Not part of art98, with no tests |
| [docs/](docs/README.md) | Every page, starting from [docs/README.md](docs/README.md) |
| `work/` | Your prepared image. Gitignored, never shared |
| `out/` | Render output from the tools and probes. Gitignored |

## Under the scene layer

Any exported Win32 function from any DLL is one call away. Outside a scene, `art98.attach()`
takes the running VM for one script and restores `ready`:

```python
from art98 import Out, attach

with attach() as stage:
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

In a scene the same bridge is `self.guest`. See the [bridge](docs/scenes/bridge.md), the
[instruction set](docs/scenes/instruction-set.md) and the
[Win32 recipes](docs/scenes/win32-recipes.md).

A guest reboot ends the VM, because Windows freezes on its logo after a warm reset in the same
QEMU process. Run `art98 vm stop` and `art98 vm start` to get it back. `ExitWindowsEx` never
replies, so call it with `acall`.

## Installing on the host instead

`art98 setup` can install Windows with QEMU on your own machine instead of in the container,
in 25 to 40 minutes. Renders still use the container, so run `uv run art98 up` afterwards. The
`ready` snapshot only loads on the QEMU version that saved it, and the container pins QEMU
10.2.2, so a host-made image may not load. Packages and steps:
[Quick path on the host](docs/setup/README.md#quick-path-on-the-host).

## Measured on real Windows 98

From a Windows 98 SE OEM disc, on QEMU 10.2.2 with software emulation. "Host QEMU" figures
were taken before the VM service, when a render could still run QEMU on the host.

| What | Result |
|------|--------|
| Full `art98 up` in the container, quiet host | About 25 min, of which Windows Setup 22 min |
| Full `art98 setup` on the host | About 40 min |
| Snapshot restore to a working agent | About 1 s |
| A Set with two windows and an image | 1.2 to 1.6 s |
| The MVP scene, 257 frames | 5.5 s on host QEMU, 6.2 s through the container |
| Frames of the MVP scene that differ, host QEMU against container, and host-built image against container-built | 0 of 257 |
| All 32 scene-docs samples through the container, three at a time | 38 s |
| One recorded frame, host QEMU and through the container on Linux | 5.6 to 6.3 ms and 6.8 to 7.0 ms ([timing](docs/design/container.md#timing)) |
| `PING` round trip | About 5 ms |
| `put_file` | 100 to 190 KB/s |
| `get_file` | About 325 KB/s |
| Guest clock against host | 5004 ms over 5 s |

Times depend on how busy your machine is; [on a busy host](docs/setup/troubleshooting.md#on-a-busy-host)
a render can take about 5 times as long, with the same frames. The serial port is emulated and
QEMU doesn't pace it to 115200 baud, so files move well above the line rate.

## Not done yet

- Audio. art98 is video only for now, though the VM keeps its Sound Blaster.
- Re-recording one section of a scene (`--section`).
- Paint, Minesweeper and `Dialog` in a state file, desktop icons and the tray in a state, and a
  `Cascade` helper for message boxes.
- Programs that don't ship with Windows 98 SE, and any plugin system for them. These are out of
  scope.

[docs/status.md](docs/status.md) has the full list of what is built and what is next, and the [changelog](CHANGELOG.md) has the release notes and known limits.
[PLAN.md](docs/archive/PLAN.md), now archived, has the original creative direction.

## Licence

art98 is under the [MIT License](LICENSE). It covers art98's own code only: Windows 98 comes
from your own disc and key, and stays under Microsoft's licence.
