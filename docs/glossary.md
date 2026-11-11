# Glossary

The words art98 uses, in plain terms. Each one links to where it is explained in full.

| Term | Meaning |
| --- | --- |
| **Guest** | The Windows 98 SE system running inside the virtual machine. "Host" is your own computer. |
| **VM** | The virtual machine: QEMU emulating a 1998-era PC in software, with Windows 98 SE installed on its disk. |
| **Prepared image** | The disk `art98 up` (or `art98 setup`) builds from your own Windows 98 disc: `work/golden.qcow2`. It is made once, takes 25 to 40 minutes, and is never changed by a render. See [Part 1](setup/README.md). |
| **`ready` snapshot** | A saved moment of the running VM, stored inside the prepared image: Windows booted, settings applied, the agent running. Every scene starts by restoring it, which takes about a second, so nothing one scene did is left for the next. See [The image](setup/image.md). |
| **Revert** | Restoring the `ready` snapshot. Every window, process and copied file from before is gone afterwards. |
| **VM service** | The VM running in one long-lived container, started with `art98 vm start` and stopped with `art98 vm stop`. It sits paused between renders. `art98 render` attaches to it, uses it for one render, and pauses it again. Only one render can hold it at a time; another one gets `busy`. See [The VM service](design/container.md#the-vm-service). |
| **Container** | A Docker (or Podman) container that holds QEMU and its tools, so your machine needs only Docker, Python and ffmpeg. Built by `art98 up` from `setup/Dockerfile`. See [Container](design/container.md). |
| **Agent** | `AGENT.EXE`, a small program art98 puts in the guest. It reads requests from the guest's serial port (COM1) and makes the Win32 calls they ask for. See [Instruction set](scenes/instruction-set.md). |
| **Bridge** | The Python side of the agent: `self.guest` in a scene. `self.guest.user32.SetWindowPos(...)` becomes one call inside Windows. See [Bridge](scenes/bridge.md). |
| **Scene** | A Python class with a `construct` method, written in the style of [Manim](https://www.manim.community/). One scene makes one video. See [Scene API](scenes/scene-api.md#scene). |
| **State** | A JSON file you write by hand that describes a still desktop: the screen mode, the background, which windows are open, where they sit, and where the pointer is. A scene can start from one, and `set_state` can jump to another. A state here is a desktop, not Manim's `save_state`. See [States](scenes/scene-api.md#states). |
| **Set** | Applying a state: revert, open the state's windows off camera, then read the desktop back and check it matches. In code, `set_state()`. |
| **Action** | Everything a scene does after the state is set: free Python in `construct`, with no limit and no JSON. The code behind it is grouped into **action classes**, one per kind of thing on screen (the pointer, a window, a program), in `core/art98/actions/`. |
| **Program** | An action class for one program on the image, such as `Notepad` or `Paint`, in `core/art98/actions/programs/`. Only programs that ship with Windows 98 SE are in scope, plus art98's own picture viewer. See [Programs](design/programs.md). |
| **Prop** | A Python handle on something in the guest, usually a window. `Notepad()`, `Picture(...)` and the pointer are props. A prop mirrors the real window: Windows owns it, and the prop reads it back before it acts. See [Prop](scenes/scene-api.md#prop). |
| **Animation** | Something you pass to `self.play`, such as `pad.animate.shift(...)`, `Glide`, `TypeWithCursor` or `Close`. It changes props over a run time, frame by frame. See [Animations](scenes/animations.md). |
| **Spot** | A place on screen worked out when an animation begins, such as `pad.title_bar`, so it stays right after the window moves. |
| **Desktop space** | The screen size, work area, taskbar and window metrics, read from the guest after each revert into `scene.space`. Every window action places itself against it. See [Desktop space](scenes/scene-api.md#desktop-space). |
| **Blank start** | The default desktop a scene starts on: plain black, with no icons, taskbar or pointer, so only what the scene puts there shows. `desktop = "stock"` keeps the normal Windows desktop. See [Blank start](design/blank-start.md). |
| **Recorder** | The class that writes frames to video with ffmpeg on the host. `self.cut()` ends one clip and starts the next. See [Clips](scenes/scene-api.md#clips). |
| **Clip, section** | A clip is one video file of a scene. `self.cut()` starts a new clip; `self.next_section(name)` does the same and records a label. The clips are kept beside the output and joined into it. |
| **Frame sync** | Before each frame is captured, art98 sends the agent a `SYNC` request, which waits until the guest's windows have repainted. Only then does QEMU take the screenshot. Together with software emulation, that is why a scene renders the same frames on any host. |
| **Work folder** | `work/`: the prepared image and the files the VM service uses. It holds an installed copy of Windows and your product key, so it is never committed or shared. See [The work directory](setup/cli.md#the-work-directory). |
