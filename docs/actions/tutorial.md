# Tutorial

This takes you from nothing to a scene that draws in Paint and writes a GIF. Each scene below was
rendered on the real image.

## Before you start

You need the prepared image from [Part 1](../prep/), and `qemu-system-i386` and `ffmpeg` on your
`PATH`. Check the host tools with:

```bash
uv run art98 doctor
```

A missing `i686-w64-mingw32-gcc` doesn't matter here. That compiler only builds the image.

A scene is a Python file. It does not run by itself: `art98 render` boots a private copy of the
image, plays the scene on it, and writes a video.

## Your first scene

Save this as `first.py`:

```python
from art98.anim import *


class First(Scene):
    def construct(self):
        pad = Notepad()
        self.add(pad)
        self.play(TypeWithCursor(pad, "hello from 1998"))
        self.pause(1)
```

Render it:

```bash
uv run art98 render first.py First -o first.mp4
```

Starting the VM takes a few seconds. What the lines do:

- `Notepad()` describes a window. Nothing has happened in the guest yet.
- `self.add(pad)` starts `notepad.exe` and finds its window.
- `self.play(...)` runs an animation, capturing one frame of the screen at a time.
- `TypeWithCursor` sends one `WM_CHAR` per letter to Notepad's Edit control, so the real caret
  moves. By default that is ten letters a second.
- `self.pause(1)` holds the last frame for one second.

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

`Paint` gives you targets for its buttons and canvas. It reads them from the live window, so they
stay right after you move it. `Stroke` holds the button down along a path.

```python
from art98.anim import *


class Draw(Scene):
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
