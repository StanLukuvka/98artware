# Design decisions

This page explains the major choices behind art98: what was chosen, why, and the rule that
new work of the same kind should follow. It records decisions that are still true in the code.
For how the parts fit together, see [Architecture](architecture.md); for the words, the
[glossary](../glossary.md). The detailed designs are linked from each section rather than
repeated here.

Each section ends with **For new work**: the rule to follow. If you need to break one, say why
in your pull request; most of them came from a measurement or a failure on the real image.

## 1. Windows draws everything

**Decision.** The video is what the guest's screen showed. Python never draws a pixel: every
window, letter and brush stroke is made by Windows 98 itself, and a scene drives it with real
Win32 calls and real input.

**Why.** The point of art98 is the look and behaviour of the real thing, with all its quirks.
Imitating Windows 98 in a renderer would lose exactly that. It also means art98 does not own its
world: the Windows desktop is the truth, and Python only holds mirrors of it.

**What follows.** Props refresh before they act and are read back after, because Windows can
move, resize, cover or close a window by itself. There is no render cache, no camera and no
`FadeIn`/`FadeOut`: Windows 98 has no window opacity, and a fake fade would be Python drawing.
`Close` is the honest exit. See [Next to Manim](architecture.md#next-to-manim).

**For new work.** If Windows can't do it, art98 doesn't fake it. A post-process on the captured
video (zoom, crop, joining clips) is fine; drawing over the desktop from Python is not. When an
effect needs pixels Windows can't make, leave it out and say why in [Not built yet](../scenes/README.md#not-built-yet).

## 2. Software emulation, and a sync before every frame

**Decision.** QEMU emulates the CPU in software (TCG). KVM is not used. Before each frame is
captured, the host sends the agent a `SYNC`, which waits until the guest's windows have
repainted, and only then takes QEMU's screenshot.

**Why.** A render should give the same frames on any machine; consistency was put ahead of
speed, even though setup takes 20 to 40 minutes. Software emulation behaves the same everywhere
and needs no `/dev/kvm` or extra privileges in a container. It also avoids two Windows 98
problems: under KVM on a recent CPU, Windows 9x hits a TLB bug that needs a patched VMM, and on a
fast processor it hits timing bugs that an emulated Pentium III keeps it away from. The machine
is fixed too (`VMConfig` in `qemu.py`): a Pentium III with 128 MB, a Cirrus card, a guest clock
that starts at the same moment in 1998 and runs on VM time, and no network card, so nothing can
reach the guest from outside. The sync makes each
frame show a finished repaint instead of whatever the screen held at that instant. Measured: the
MVP scene gives 0 of 257 frames different between host QEMU and the container, and between an
image built on the host and one built in the container. A busy host makes a render about 5 times
slower, with the same frames.

**What follows.** What the script drives lands on exact frames. What the guest times for itself
(caret blinks, tooltips, screensavers) follows the host clock, so those can differ between runs.
Only the `free` clock exists; the stricter clocks would need more from the agent than it does
today. See
[Time](../scenes/README.md#time).

**For new work.** Anything that changes the screen goes through a frame that syncs. Don't add a
capture path that skips the sync, and don't depend on wall-clock timing in the guest for
something the script should control. Check that a new feature renders the same frames twice
(compare with ffmpeg's `framemd5`); the [drift audit](https://github.com/StanLukuvka/98artware/blob/dev/experiments/drift/README.md) is the
model.

## 3. A thin agent: any Win32 call, nothing more

**Decision.** The guest runs one small program, `AGENT.EXE`, started at boot from the `ready`
snapshot. It reads framed requests from COM1 and calls any exported function of any DLL by name,
with the arguments it is given. It has a handful of other verbs (list windows and processes,
start a program, `SYNC`, put and get files). It is built with mingw and links without the C
runtime.

**Why.** A generic call proxy means every new feature is written on the host, in Python, and
tested there, without rebuilding anything in the guest. A custom instruction language was
considered and dropped for the same reason: every new instruction would need an agent rebuild,
and the agent is on the image. A script language in the guest (VBScript) can't call Win32. A
serial port needs no network stack in the guest: VM guest tools don't support Windows 98, and
every shared-folder route needed networking and Samba. So nothing in the guest can reach the host
or the internet. Linking without the CRT
keeps the agent tiny and loadable on a bare Windows 98 install; `pecheck.py` checks every `.exe`
imports only what Windows 98 has.

**What follows.** Calls that block (a message box, `ExitWindowsEx`) go on their own guest thread
with `acall`. A guest reboot ends the VM, because Windows freezes on its logo after a warm reset
in the same QEMU process, so QEMU runs with `-no-reboot`. The pointer in a video is the guest's
own, captured with the screen, not an overlay drawn by the host. The agent's protocol carries
ids, events and a checksum, which is why the container can relay it unchanged (section 5).

**For new work.** Build features from Win32 calls on the host. Add a verb to the agent only when
a call can't be made from the host at all, or would be too slow one call at a time, and then
change the protocol version, `instruction-set.md`, and rebuild with `make -C guest` and
`art98 up --rebuild`. art98's own guest programs (only `VIEW.EXE` so far) follow the same rule:
small C, no CRT, only functions Windows 98 has. See [Instruction set](../scenes/instruction-set.md)
and [Win32 recipes](../scenes/win32-recipes.md).

## 4. One baseline: the `ready` snapshot, restored before every scene

**Decision.** Setup builds the prepared image once and saves one QEMU snapshot, `ready`. Every
render restores it (about a second), and so does every scene, even several scenes run one after
another in one attach. Nothing a scene does is ever saved back.

**Why.** Windows 98 can't be put into a chosen state by script, and it can't be trusted to clean
up after itself. A snapshot restore is fast, complete (every window, process and copied file is
gone) and the same every time. It was tested: Set repeats, and a revert leaves nothing behind
(see [Test results](state-and-action.md#test-results)).

**What follows.** Changing the image is expensive for everyone: it means a new 20 to 40 minute
`art98 up`, and the snapshot only loads on the QEMU machine type that saved it, which is why the
container pins QEMU 10.2.2. So art98 does at run time, after each revert, what it can: the
[blank start](blank-start.md) hides the taskbar and icons in memory, files are copied into the
guest by content hash, and the wallpaper arrives on a CD (section 9). Known prep fixes, such as
the misspelt `UserPreferencemask` setting, are listed in
[Prep changes not made](blank-start.md#prep-changes-not-made) and wait for a reason to rebuild.

**Setup itself** runs as four resumable steps (`vm`, `setup`, `init_api`, `ready`), because a
40-minute install shouldn't start over when one step fails. It needs no input: the licence
agreement, the first-boot wizard and the logon prompt are answered by watching the screen, and a
stall is detected from disk writes, not the screen, because a blinking caret looks like progress.
See [Steps](../setup/stages.md).

**For new work.** Do it at run time after the revert if you can. A change to setup or the `ready`
snapshot needs an issue first ([Scope](../../CONTRIBUTING.md#scope)), and a rebuild tested from scratch in a separate
work folder. Never save a snapshot over `ready`; the VM service refuses `save_snapshot`.

## 5. QEMU in a container; Python, the recorder and ffmpeg on the host

**Decision.** QEMU, the setup tools and the guest programs live in one container image built from
`setup/Dockerfile`. The host keeps the scene, the bridge, the recorder and ffmpeg. The container
relays the agent's serial protocol to the host byte for byte, and answers a small JSON control
channel for screenshots, keys, revert, pause and the CD. art98 calls only the `docker` command.

**Why.**

- **Reproducible.** A pinned image holds the exact QEMU that saved `ready`, on any Linux
  distribution, and nothing about it depends on the host's packages.
- **A relay, not a remote API.** The agent protocol already has ids, events and a checksum, so
  passing it through needs no new format, and the host's `Bridge` is unchanged. An RPC layer
  would need remote handles, event forwarding and its own error mapping.
- **Frames on a shared folder.** On Linux the channels are a Unix socket in a mounted folder,
  and QEMU writes each screenshot into it. That brought a frame to 6.8 to 7.0 ms against 5.6 to
  6.3 ms on host QEMU. Loopback TCP stays for hosts where a Unix socket can't cross into the
  container, such as Docker Desktop. See [Timing](container.md#timing).
- **One engine path.** Podman works through `podman-docker`, so there is one code path. The
  container itself decides who owns the files it writes, by reading its uid map, so rootful
  Docker and rootless Podman both leave `work/` owned by you.
- **Nothing personal in an image.** The disc and `work/` are bind-mounted, and the product key
  and VM token are files mounted read-only. So an image holds only programs and can be shared,
  and the token never shows in `docker inspect`. (Windows 98 product keys are public; the real
  secret is the token.)

**For new work.** Keep the host's view of the VM to the methods `RemoteVM` has. A new control op
goes in `serve.py` and `RemoteVM` together, with a test in `test_container.py`, and must keep
working for an older image (as `eject_disc` is only sent when a disc was inserted). Never publish
the control port beyond loopback: the agent runs any Win32 call it is given. Anything that runs
in the container is in the image, so a change to `core/art98` that `serve` uses needs
`art98 up --rebuild`. See [Container](container.md).

## 6. The VM service: one long-lived VM, one render at a time

**Decision.** `art98 vm start` runs one long-lived container, paused between renders.
`art98 render` and `art98 ping` attach to it; they never boot a VM. The control connection is
the lock: one client holds the VM, and another gets `busy` (or waits with `--wait S`). Settings
live in a committed `art98.toml` with a fixed loopback port per purpose. `art98 up` stops after
setup and prints `art98 vm start`.

**Why.** Booting a VM for every render coupled the animation to VM setup, and cost time on every
run. A paused VM costs no CPU and resumes in an instant. Using the connection itself as the lock
means a crashed or killed render frees the VM when its socket closes, with no lock files to
clean up: a render killed with `kill -9` left the next attach working in about 0.05 s. On
release the server drops the relay, ejects the disc, pauses the VM and frees the lock last, so
the next client never races the cleanup. Pausing matters because an idle Windows 98 under software
emulation keeps a whole CPU core busy. Fixed ports make a clash an error you can see instead of
a silent fallback. On disk it needs only `work/vm.token` and
`work/vm.cid`. The token can live outside `work/` (`[vm] token_file`), so
a client in another container needs only that file and a small `art98.toml`, never `work/`
([how](../setup/config.md#attach-from-another-container)).

**What follows.** Rendering on host QEMU is gone, along with the backend switch.
`session.boot_local()` and `private_stage()` remain for experiments that need a fresh boot. Over
TCP, both ends use keepalive, so a client that vanishes without closing frees the lock in about
a minute; the Unix socket, the default on Linux, frees it at once.

**For new work.** Anything that drives the guest takes a session from `art98.attach()` and
releases it with `with`. Don't add a path that boots its own VM for renders or tests. A test that
needs the VM uses the `attached`/`booted` helpers in `test_stage.py` so a failure never holds the
lock. New settings go in `art98.toml` with a default in `settings.py`, documented in
[Configuration](../setup/config.md). See [The VM service](container.md#the-vm-service).

## 7. States are static and hand-written; actions are free Python

**Decision.** A scene starts from a **state**: a JSON file that describes a still desktop (the
display mode, colour and wallpaper, windows back to front, the pointer). Applying it is a Set:
revert, open the windows off camera, read the desktop back and check it matches. Everything
after that is **actions**: free Python in `construct`, with no limits and no JSON output.

**Why.**

- **A state can't describe everything a scene can do**, and forcing it to would limit scenes.
  So the state is only for a still starting point, and the script stays as free as a Manim
  script.
- **JSON, by hand,** because it is easy to write and read, and it can hold things props can't
  (a wallpaper, later icons and the tray).
- **Checked whole, before the guest is touched,** so every mistake in a file is listed at once
  and a bad file never leaves a half-made desktop. Unknown fields fail.
- **Files by path and `sha256`,** so a state can open a finished drawing or a text file and a
  changed file is caught, without ever saving a scene's result.
- **Checked after Set,** because Windows decides where a window really lands; a mismatch raises
  `StateMismatch` with each difference.
- **Rejected:** saving a scene's result as a state, a snapshot per section, and replaying a log
  of steps. Each would tie the design to the VM and limit what a script can try.

**What follows.** A script is ordinary Python, so how many states or videos it uses is up to it;
art98 has no "video" or "project" concept. The programs a state can open are one list, `APPS` in
`anim/setstate.py` (today `picture` and `notepad`).

**For new work.** A new state field is read and fully checked in `state.py`, applied in
`apply_state`, and verified in `check_state`, in that order (see
[Contributing](../../CONTRIBUTING.md#adding-to-states)). It describes something still, never a
result. See [State and action design](state-and-action.md) and [States](../scenes/scene-api.md#states).

## 8. A Manim-shaped API, in screen pixels

**Decision.** Scenes look like Manim scenes: a `Scene` with `construct`, `play`, `add`, `remove`
and `wait`, animations that `interpolate(alpha)` under a `rate_func`, `.animate`, the group
animations, and frames counted as `run_time × fps`. Names match Manim's wherever the meaning
matches. Units are screen pixels with y running down, so `UP` is `(0, -1)`.

**Why.** Manim is the best-known way to script animations in Python, and people who know it
should be at home. But a scene here moves real windows on an 800 × 600 screen, so pixels are the
honest unit, and Windows' own y-down axis avoids a conversion on every call.

**What follows.** Where the meaning differs, the name differs or the doc says so: `add` starts a
real program, `wait` records the live guest at host speed, and `pause` holds one still frame. A
named part of a scene is a **section**, Manim's word, marked with `next_section`.

**For new work.** Take Manim's name when the behaviour matches, and a new name when it doesn't.
Every public name in `art98.anim` must be documented in [Scene API](../scenes/scene-api.md) or
[Animations](../scenes/animations.md); `test_anim_docs.py` checks it.

## 9. Code by layer and by action family

**Decision.** The package is split by job:

| Layer | Folder | Holds |
| --- | --- | --- |
| Entry point | `anim/` | What scripts import: `Scene`, `render`, and the state and timeline helpers `Scene` calls |
| Actions | `actions/` | One family per folder or file: `pointer.py`, `keyboard.py`, `backdrop.py`, `window/` (`Win`, its commands, `Menu`, `Picture`), and `programs/` under it |
| Building blocks | `base/` | `Animation` and groups, rate functions, vectors, `Box`, `Prop`, `Spot`, `DesktopSpace` |
| Guest helpers | `win32.py` | Win32 constants and small named guest reads |
| Transport | `bridge.py`, `protocol.py` | The agent protocol, and nothing else |
| Machine | `session.py`, `service.py`, `container/`, `qemu.py`, `recorder.py` | The VM, revert, capture, the recorder |

Programs are action classes: one file per program in `actions/programs/`, each a subclass of
`Win`. Docs, render output and experiments are kept apart (`docs/`, `out/`, and
`experiments/`, which is on the `dev` branch only).

**Why.** A program is added one at a time, so each needs its own place, and the layers make it
clear which code talks to the guest.

**For new work.** A new program is `actions/programs/<name>.py`, subclassing `Win`; a new kind of
action that is not a window gets its own file or folder in `actions/`. A constant or a guest
read used twice goes in `win32.py`. Nothing goes in a shared grab-bag module, and when something
moves, the old import path goes too: no compatibility shims. See [Programs](programs.md).

## 10. Only base Windows 98 SE, video only

**Decision.** Program classes are only for what ships with Windows 98 SE, plus art98's own
picture viewer. Programs that need their own install (Office and the like), named snapshots for
them, and an add-on or plugin system are out of scope. Audio is deferred: art98 makes silent video.

**Why.** Extra software would change setup, the prepared image and `ready` for everyone, and a
plugin system is a project of its own. Audio is deferred to keep the focus on getting video right;
the VM keeps its Sound Blaster only because removing it would change the image.

Two more things are out for now: animated desktop icons, and widescreen output. Resolutions stay
the four Cirrus modes (640 x 480, 800 x 600, 1024 x 768, 1280 x 1024), so nothing has to adapt to an
unknown size. The card has no 1280 x 720 or 1920 x 1080 mode, and another adapter, a custom mode or
upscaling would change the image or the pipeline. Scenes are 4:3, 800 x 600 by default
([Display modes](../scenes/scene-api.md#display-modes)).

**For new work.** Don't plan install steps or extension points for non-base programs, and don't
add audio capture, sound in scenes, or audio tracks in the output.

## 11. A picture viewer of art98's own

**Decision.** `Picture` is backed by `VIEW.EXE`, a 4 KB viewer art98 builds and copies to the
guest. It shows one BMP at 1:1, opens at the position, size and title on its command line, and
is a normal window that can be moved and closed.

**Why.** Windows 98 has no small image viewer, and Paint brings its own tools, canvas and quirks.
Opening where the state wants it means nothing moves on screen first. It is copied after each
revert, not put on the image, so the image doesn't change. The host checks a BMP before it is
sent, because Windows 98's `LoadImage` can crash in 16-bit code on a cut-short file.

**For new work.** Prefer a stock program. Write a guest program of art98's own only when Windows
98 has nothing that does the job, and keep it in `guest/` with the agent's toolchain.

## 12. The blank start

**Decision.** By default a scene starts on a black screen with no icons, taskbar, Start menu or
pointer. It is made in memory after every revert by `desktop.py`, then read back. `desktop =
"stock"` keeps the normal desktop, and `pointer_visible = True` shows the pointer.

**Why.** Nothing should be on screen that the scene didn't put there. An audit found nothing that
pops up on its own after a restore. Making the blank screen at run time means the snapshot stays
as it is and the next revert undoes it all.

**For new work.** Anything a scene changes about the desktop as a whole is done after the revert
and checked by reading it back, as `blank()` does. Tests on stand-in guests use the stock desktop
(`conftest.py`), and `test_desktop.py` covers the blank one. See [Blank start](blank-start.md).

## 13. One desktop space for every window action

**Decision.** After each revert, art98 reads the screen size, the work area and the window
metrics from the guest into `scene.space`, a `DesktopSpace`. Every window action places itself
against it: `center()`, `to_corner()`, the title bar, the placement check. It is read again when
a state switches the display mode, or when a scene calls `scene.calibrate()`.

**Why.** The aim was for all window actions to share one positioning space, calibrated at the
desktop level, instead of each reading the screen, the work area and the metrics for itself. One
read per revert keeps them consistent with each other, and a size
outside Windows' limits is caught on the host before it is sent instead of being silently changed
by Windows.

**For new work.** Read screen geometry from `scene.space`, never with a fresh guest call inside an
action. A scene that changes the work area or display mode with raw calls must call
`scene.calibrate()`. See [Desktop space](../scenes/scene-api.md#desktop-space).

## 14. The recorder is a class you can steer

**Decision.** `Recorder` writes frames to video with ffmpeg on the host. A scene reaches it as
`self.recorder`. `self.cut()` ends one clip and starts the next between two frames, and
`self.next_section(name)` does the same with a label. The clips are kept beside the output as
`<stem>-01.mp4` and on, and joined into it.

**Why.** A scene should control its own capture as it runs. Four rules follow:

- **One GIF from the joined lossless clips,** because 4:2:0 H.264 smears Windows' 1-pixel
  coloured text.
- **Clips kept as MP4 beside the output,** so part of a scene can be reused; `keep_clips=False`
  drops them.
- **ffmpeg failures raise `RecorderError`** without hiding the scene's own error.
- **A screen-size change inside a clip raises** and suggests `cut()`, since one video file has
  one size.

Every file is written as `.part` and renamed only when the whole render worked, so a failed
render never leaves a half-written output or clobbers an earlier one.

**What follows.** Re-recording one section on its own (`--section`) is not built; it would sit on
top of `next_section`.

**For new work.** Build capture features on `cut()` and `next_section`. Keep the recorder on the
host. See [Recorder](state-and-action.md#recorder) and [Clips](../scenes/scene-api.md#clips).

## 15. Big files go on a CD, not down the serial line

**Decision.** A state's wallpaper reaches the guest on a small ISO that the host sends to the
container, which puts it in the guest's CD drive (`D:`) after the revert. The next revert ejects
it first, because `loadvm` restores the guest's empty tray but not QEMU's medium.

**Why.** `put_file` over the emulated serial port runs at roughly 90 to 190 KB/s on a quiet host
and far slower on a busy one (about 12 KB/s was measured), so a full-screen BMP could add 15 s or more to every Set. The CD
takes under a second for 1.4 MB and leaves the image unchanged. Putting the images on the image
itself would change prep and `ready`.

**For new work.** Small files (programs, text, small BMPs) go through `guestfiles.ensure`, named by
content hash so a file already there isn't copied again. Anything large goes on the CD. See
[Desktop colour and wallpaper](state-and-action.md#desktop-colour-and-wallpaper).

## 16. Run from a checkout, with no runtime dependencies

**Decision.** art98 runs from a git checkout with `uv run`. There is no wheel and no `pip install`.
The `art98` package has no runtime Python dependencies; pytest, pycdlib and ruff are dev tools only.
The licence is MIT.

**Why.** The audience is people who clone the repository and follow the README. A checkout keeps
the examples, docs and guest sources next to the code, and no dependencies means nothing to break
or audit. The container image installs the same packages from the same checkout. MIT is short,
well known, and what Manim uses; QEMU's GPL doesn't reach art98, which only runs QEMU as a
separate program.

**For new work.** Use the standard library. If something truly needs a dependency, raise it first.
Contributions are MIT too, and nothing from a Windows disc or an installed image ever goes in the
repository.

## 17. Errors say what to do, in one line

**Decision.** An error a user can cause prints as one line, `error: <message>`, and exits 1. When
the traceback passes through the scene file, the line ends with `(scene.py:LINE, in func)`.
`ART98_TRACE=1` shows the full traceback. Warnings say when the image or the guest programs are
older than the code.

**Why.** A traceback through the VM service, the bridge and the scene layer buries the one line
that matters. The scene line points at the user's own code. Stale builds caused confusing
failures, so they are flagged before a render.

**For new work.** Give a user-facing failure its own exception class with a message that says
what to do next (for example "run `art98 vm start`"), and add it to `RUN_ERRORS` in `cli.py`.
`test_cli.py` checks the exact stderr.

## 18. Measure on the real image, keep the probes

**Decision.** A claim about Windows 98 is checked on the real image before it goes into code or
docs. Throwaway probes live in `experiments/<topic>/` (on the `dev` branch only) with a
README of what they found. Unit
tests run on stand-in guests that do only what the real one was seen to do; VM tests run the real
image through the VM service. Every timing names the host load.

**Why.** Windows 98 surprises: Notepad drops a trailing `.txt` from its title, `ShowCursor(FALSE)`
doesn't hide the pointer, a 16-bit screen rounds 128 to 120, a dialog's icon static has id 10.
Each of these was found by a probe, and guessing would have been wrong. Host load changes timings
by five times or more, so a number without its load is not comparable.

**For new work.** Probe first, on the running VM, and write down what you saw. Teach a stand-in
guest only measured behaviour. Note `/proc/pressure/cpu` beside any timing. Keep probes out of the
package and out of the test suite.

## 19. Lean first, then measure

**Decision.** Build the smallest thing that works, and add more only when a measurement or a real
use asks for it. When code moves or a feature is replaced, the old path is deleted: no
compatibility shims, no old import paths, no commented-out or parked code left to drift.

**Why.** art98 is young, and keeping old paths alive costs more than updating the callers.
Features that wait on a number wait for the probe: recreating the run copy of the disk was left
out, and the run copy stayed the same size over 30 renders.

**For new work.** Prefer one module and one code path. Delete what you replace in the same change,
and move its callers. Write a `lazy:` comment for a known shortcut, with its limit.

## Not built, on purpose or not yet

| Idea | Status |
| --- | --- |
| Updaters (`add_updater`), Manim's render cache, a camera | Not built. `live()` and `wait_until` watch the guest instead; zoom or pan would be a post-process |
| `FadeIn`, `FadeOut` | Not possible honestly: Windows 98 has no window opacity |
| The `frozen`, `stepped` and `locked` clocks | Not built; they need agent support |
| Holding the desktop after a render so more actions can run without a restore | Designed in [state and action](state-and-action.md#holding), not built. The VM is paused at the last frame, and the next attach reverts |
| `--section` | Not built; sits on top of `next_section` |
| Desktop icons and the tray in a state, `Dialog` in a state | Not built |
| Audio | Deferred |
| Programs outside base Windows 98 SE, a plugin system | Out of scope |
| Animated desktop icons, widescreen output | Out of scope for now |
