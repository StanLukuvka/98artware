# Tutorial

This takes you from nothing to a scene with a picture, Notepad and the pointer, and then to a GIF.
The first scene was rendered on the real image.

**Parked.** Paint, Minesweeper, Screensaver and Dialog still work, but
`from art98.anim import *` leaves them out until each program returns as its own action
class. Samples that use them import them from `art98.anim.apps`. The windows you get without that
are [`Picture`](scene-api.md#picture) and [`Notepad`](scene-api.md#notepad).

## Before you start

The easy way is the container. Run `art98 up` once, as the [README](../../README.md) says, then
check the host. The container is the default backend:

```bash
uv run art98 doctor
```

`doctor` passes on a host that has only Docker and ffmpeg. Run everything from a checkout with
`uv run`.

The other way is the `local` backend. It needs the prepared image from [Part 1](../setup/),
and `qemu-system-i386` and `ffmpeg` on your `PATH`. A missing `i686-w64-mingw32-gcc` doesn't
matter here. That compiler only builds the image.

A scene is a Python file. It does not run by itself: `art98 render` boots a private copy of the
image, plays the scene on it, and writes a video.

## Your first scene

A scene starts from a state, a JSON file that describes a still desktop. This one has a picture
window and a Notepad window on the blank desktop, with the pointer near the bottom. Save it as
`states/desk.json` beside your scene:

```json
{
  "version": 1,
  "display": [800, 600, 16],
  "windows": [
    {"id": "flower", "app": "picture", "title": "Flower", "at": [60, 60], "size": [240, 200],
     "open": {"file": "../assets/flower.bmp", "sha256": "<sha256 of the file>"}},
    {"id": "note", "app": "notepad", "at": [320, 180], "size": [320, 200]}
  ],
  "pointer": [400, 540]
}
```

Fill in `sha256` with the output of `sha256sum` on the file, for example `sha256sum assets/flower.bmp` from the folder beside `first.py`. The file must exist at that path, relative to the state file.

Then save this as `first.py`. It is shaped like
[examples/blank_start](../../examples/blank_start/blank_start.py), which has the whole state,
with the real hash and its files:

```python
from art98.anim import *


class First(Scene):
    state = "states/desk.json"
    pointer_visible = True

    def construct(self):
        flower, note = self.prop("flower"), self.prop("note")
        self.pause(1)
        self.play(Glide(note.title_bar), run_time=1)
        self.play(TypeWithCursor(note, "hello from a blank desktop\n"))
        self.play(Teleport(flower, to=(500, 60), aligned_edge=UL))
        self.pause(1)
```

Render it:

```bash
uv run art98 render first.py First -o first.mp4
```

Starting the VM takes a few seconds. What the lines do:

- `state` is read before the scene starts. The windows open off camera, and the video begins
  with them in place.
- `self.prop("note")` is the prop for the window with that `id`.
- `Glide` moves the pointer to the title bar. `note.title_bar` is a `Spot`, a place worked out
  when the animation begins.
- `TypeWithCursor` sends one `WM_CHAR` per letter to Notepad's Edit control, so the real caret
  moves. By default that is ten letters a second.
- `Teleport` moves a window in one frame.
- `self.pause(1)` holds the last frame for one second.

The video starts on a black screen: no icons and no taskbar. Only what the state puts there
shows. `pointer_visible = True` shows the pointer, and `desktop = "stock"` gives the Windows 98
desktop as it is. See [Blank start](../design/blank-start.md).

## States

A state is plain JSON. It lists the windows back to front, and each has an `id`, an `app`, a
place and size, and what it shows. `app` is `"picture"` or `"notepad"`. The file is checked as a
whole before the desktop is touched, so every mistake is listed at once.

`set_state` swaps to another state at any point, off camera, and the guest ends up the same
every time. Props from before are gone after it. The fields are in the
[Scene API](scene-api.md#states).

A Notepad window can take a text file with `open`, and a `title`. Leave the title out and you get
the Windows 98 one: a trailing `.txt` is dropped, so `note.txt` gives "note - Notepad".

## Pictures

`Picture` is art98's own small window that shows one BMP. In a state it takes `open`, with the
file and its `sha256`, so a changed file is caught. In a scene you can also add one while it
runs:

```python
from art98.anim import *


class AddOne(Scene):
    def construct(self):
        sky = Picture("Sky", image="examples/mvp/assets/sky.bmp", at=(100, 100), size=(240, 200))
        self.add(sky)
        self.play(sky.animate.shift(200 * RIGHT), run_time=1)
        self.play(Close(sky))
```

Windows 98 has no small image viewer, so there is nothing else to show a picture with.

## Cuts and sections

`self.cut()` ends the current video clip and starts the next one, between two frames. Nothing
is lost or repeated. `self.next_section("name")` does the same and also records a label in
`self.sections`. The name is only a label: clips stay numbered.

```python
from art98.anim import *


class TwoParts(Scene):
    def construct(self):
        self.pause(0.5)
        self.next_section("second part")
        self.pause(0.5)
        self.cut()
        self.pause(0.5)
```

`art98 render two.py -o two.mp4` writes `two-01.mp4`, `two-02.mp4` and `two-03.mp4`, and joins
them into `two.mp4`. A render doesn't delete clips from an earlier render. If a longer one left
`two-04.mp4` behind, you get a warning naming it. See [Clips](scene-api.md#clips).

## Move a window

Every prop has `.animate`, which turns a layout call into an animation. Positions are screen
pixels, with y running down. `at` is the window's top left corner.

```python
from art98.anim import *


class MoveIt(Scene):
    def construct(self):
        pad = Notepad(at=(60, 60), size=(320, 220))
        self.add(pad)
        self.play(pad.animate.shift(300 * RIGHT + 200 * DOWN), run_time=1.5)
        self.play(pad.animate.center(), pad.animate.resize(420, 300))
        self.pause(0.5)
```

The second `play` has two animations, so they run together. Each frame still sends one
`SetWindowPos`, because both change the same prop.

## Use the mouse

The pointer is an actor too, and it has to travel. `Click` glides there, then presses and
releases. It is real input, so Windows decides what the click does.

```python
from art98.anim import *


class UseTheMouse(Scene):
    pointer_visible = True

    def construct(self):
        pad = Notepad(at=(120, 100), size=(420, 260))
        self.add(pad)
        pad.set_text("Pick a menu item.")
        self.pause(0.3)
        self.play(Menu(pad, "Edit", "Select All"))
        self.pause(0.5)
        self.play(pad.animate.shift(100 * RIGHT))
        self.play(Drag(pad.title_bar, by=(100, 120)))
        self.pause(0.5)
```

`Menu` finds "Edit" and "Select All" in the live menu and clicks them. `pad.title_bar` is a
`Spot`, a place worked out when the animation begins. So the `Drag` aims at where the window is
after the move, and Windows carries the window because the pointer holds its title bar.

## Draw in Paint

Parked: `Paint` is imported from `art98.anim.apps`.

`Paint` gives you targets for its buttons and canvas. It reads them from the live window, so they
stay right after you move it. `Stroke` holds the button down along a path.

```python
from art98.anim import *
from art98.anim.apps import Paint


class Draw(Scene):
    pointer_visible = True

    def construct(self):
        paint = Paint(at=(120, 40), size=(520, 480))
        self.add(paint)
        self.play(Click(paint.tool("brush")))
        self.play(Click(paint.color("red")))
        points = [paint.canvas(40, 40), paint.canvas(300, 80),
                  paint.canvas(120, 240), paint.canvas(40, 40)]
        self.play(Stroke(points, run_time=2))
        self.play(Click(paint.tool("fill")))
        self.play(Click(paint.color("yellow")))
        self.play(Click(paint.canvas(120, 90)))
        self.pause(1)
```

The fill stays inside because the stroke is closed. Paint floods whatever is connected, as it
would for a person. A path can also be a function from 0..1 to a point.
[`examples/showcase.py`](../../examples/showcase.py) draws a rose that way.

## Go under the scene layer

`self.guest` is the [bridge](bridge.md). Call any exported Win32 function with it, then keep
animating. This one reads the screen resolution and shows it.

```python
from art98.anim import *

SM_CXSCREEN, SM_CYSCREEN = 0, 1


class Raw(Scene):
    def construct(self):
        user32 = self.guest.user32
        width = user32.GetSystemMetrics(SM_CXSCREEN).value
        height = user32.GetSystemMetrics(SM_CYSCREEN).value
        pad = Notepad(at=(200, 120), size=(400, 200))
        self.add(pad)
        self.play(TypeWithCursor(pad, f"This desktop is {width} x {height}."))
        self.pause(1)
```

## Write your own animation

Subclass `Animation` and write `interpolate(alpha)`, where `alpha` runs from 0 to 1 after the
rate function. `begin` and `finish` are there if you need them.

```python
from art98.anim import *


class CountInTitle(Animation):
    def __init__(self, window, top, **kwargs):
        super().__init__(window, **kwargs)
        self.top = top

    def interpolate(self, alpha):
        title = f"{round(alpha * self.top)} of {self.top}"
        self.scene.guest.user32.SetWindowTextA(self.target.hwnd, title)


class Counting(Scene):
    def construct(self):
        pad = Notepad(at=(200, 120), size=(360, 200))
        self.add(pad)
        self.play(CountInTitle(pad, 100, run_time=2))
        self.pause(1)
```

## Make a GIF

Give `-o` a `.gif` name, or keep the video and add `--gif`:

```bash
uv run art98 render first.py First -o first.gif --gif-colors 48 --gif-fps 12
```

```bash
uv run art98 render first.py First -o first.mp4 --gif first.gif
```

A GIF is made from a lossless recording, because normal video smears the 1-pixel coloured text of
Windows. Fewer colours and frames make a smaller file. The desktop needs about 48 colours.

## Next

- [Animations](animations.md) lists everything you can pass to `play`.
- [Scene API](scene-api.md) lists props and their methods.
- [Gallery](gallery.md) has short scenes to copy from.
