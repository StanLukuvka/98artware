# Inspiration: a Windows 98 lyric video

Draft, 2026-11-11. The analysis was written first. The dialog-storm milestone then built the parts
marked built below, and proved them on the real image with `examples/dialog_storm`.

The video that inspired art98 is a lyric video for a song about a computer virus, 154 s long, 1280x720
at 24 fps, with a soundtrack. This page breaks it into shots, then into the small parts it is made
from, and says which of those art98 can already do, which need work, and which don't belong in art98.
It is checked against the code (`core/art98/`), not only the docs.

The video repeats itself a lot. The same few parts come back with different words and wallpaper, so
the useful view is the table of **building blocks** below. The shot table after it is the timeline
of those blocks.

Scope set by the user: animating desktop icons is out of scope for now. Icons are noted where they
appear, and marked out of scope.

Categories:

- **(a)** can be done today
- **(b)** needs a program or action that is not yet built
- **(c)** needs a new feature
- **(d)** out of reach, or better done outside art98

## What is in the video

Five kinds of footage, cut together on the beat:

1. **Dialog storms on a coloured desktop.** Classic Windows 98 message boxes with the title `???`,
   one line of text, an icon and two greyed buttons. They pop in one by one into a stair-step
   cascade, or in pairs, or as a scattered pile. This is about 60% of the running time.
2. **An Address Book window** (Outlook Express's `wab`) on a dark-red or red desktop, with a large
   typed line, "YOU'VE GOT MAIL!", that stutters and doubles.
3. **Kinetic lyric type.** Big bold white or black words, one phrase at a time, over a desktop. On the
   red desktop the line sits at the bottom. On the white desktop it is right-aligned.
4. **CRT cartoon interludes.** A flat illustration of a monitor on a brown or blue background, with
   yellow pixel-font lyrics on its black screen.
5. **A VHS look over everything:** soft focus, scanlines, colour fringing, a tracking glitch line,
   small jitter.

Desktop colours seen: teal-blue (plain, then with a mottled texture), dark red, bright red with a
grunge texture, white, and a pink-to-orange gradient. Icons, the taskbar and the Start button are
visible in nearly all desktop shots. No mouse pointer is ever shown: everything appears by itself.

## Building blocks

| # | Block | What it is, in the video | Today | What is missing |
| --- | --- | --- | --- | --- |
| B1 | **Solid desktop colour** | Teal, dark red, red | Built: `Backdrop(colour)` (teal, dark red, red, white and any RGB), proved on the stock and the blank desktop | Nothing. The 16-bit screen rounds the colour (128 becomes 120) |
| B2 | **Textured or gradient wallpaper** | Mottled blue, red grunge, pink-orange gradient | Built for a tiled BMP: `desktop.wallpaper` in a state, sent on a CD | The video's mottled and gradient textures are not tried. See "Wallpaper (B2), as built" |
| B3 | **Message box** | `???` title, one line, icon, two greyed buttons, at an exact position | Built: `Dialog` with `size`, `disabled` and the custom icons, in `art98.anim` | See "Message box (B3), as built" below |
| B4 | **Cascade** | 5 to 8 boxes appear 2 to 3 frames apart, each offset up and right | Built, by hand: a loop of `Dialog(..., at=...)` with `add` and a `pause` of two frames. Proved with eight boxes | A `Cascade` helper, only if the loop keeps coming back |
| B5 | **Pair and jitter** | Two copies of a box a few pixels apart, or side by side | Built: two `Dialog` props with a seeded jitter. Proved with a pair | Nothing |
| B6 | **Scatter pile** | About a dozen boxes at random positions (1:58) | Likely built: the same loop with random positions. Not proved at a dozen boxes | A run with a dozen boxes |
| B7 | **Box with typing text** | A box whose text is just "A" (0:56) | Built: `Dialog.set_message(text)`, one letter per frame in the proof | Nothing |
| B8 | **Address Book with typed big text** | The window, and a huge thin "YOU'VE GOT MAIL!" in its list area | (b): the program is on the image but there is no class. Nothing in the docs says it was ever opened | A `programs/` class for `wab.exe`. The big text is most likely added in editing: see B13 |
| B9 | **Static desktop icons and taskbar** | My Computer, My Briefcase, Recycle Bin, Internet Explorer, Notepad, two folders, a Start button, quick launch, tray | Built for stock icons and taskbar: `desktop = "stock"` plus `Backdrop` keeps the taskbar and icons on the new colour (`DialogStormStock`) | The custom icons ("My Briefcase", the two folders with their labels) need icons in states (c). Animating or recolouring icons is out of scope |
| B10 | **Hard cut and black** | Cuts on the beat, black frames | (a): `cut()` and `next_section()`, and the blank desktop is black | Nothing |
| B11 | **Fixed frame rate** | 24 fps | (a): `fps = 24` on the scene (the class default is 30) | Nothing |
| B12 | **Scene layout of the screen** | 16:9 | (c) | art98's guest only offers 4:3 modes. See "Aspect ratio" below |
| B13 | **Kinetic lyric type** | Big bold words, one phrase at a time, over the desktop | (d) | Not a Windows program. Do it in the editor over the footage, or with ffmpeg `drawtext`. A real window with a big font would be a new feature and gains little |
| B14 | **CRT cartoon interludes** | A flat monitor illustration with pixel-font lyrics | (d) | 2D animated artwork, not a desktop. Make it elsewhere and cut it in |
| B15 | **VHS look** | Blur, scanlines, fringing, glitch line | (d) | A post filter over the finished MP4, ffmpeg or the editor. It would hide art98's crisp pixels on purpose |
| B16 | **Zoom into a box** | The "SO I CAN'T" box fills the screen (1:40) | (d), or (c) | A zoom on the finished footage is trivial in post. `Box.scale` keeps the font size, so it is not a real zoom |
| B17 | **Audio** | The whole song | (c), deferred | Audio is deferred until the user asks. The scene can be timed to beat times by hand in the meantime |
| B18 | **Fade and white flash** | White to grey gradient at 1:12 | (d) | Post |

### Message box (B3), as built

`Dialog` is a real `MessageBoxA` on its own guest thread, now exported from `art98.anim` (see
[Dialog](../scenes/scene-api.md#dialog)). The gaps this page listed before it was built came out
like this, each probed on the image ([experiments/dialog-storm](../../experiments/dialog-storm/README-p1.md)):

- **Icons.** Done, by `STM_SETICON` on the box's icon slot, not `MessageBoxIndirect`. The seven
  custom icons (computer, printer, mouse, telephone, cd, globe, flag) all exist in the guest's
  shell DLLs and are in `Dialog.CUSTOM_ICONS`. Any `(dll, index)` pair works too. The red X and
  the warning triangle are the stock keys.
- **Greyed buttons.** Done: `disabled=True` runs `EnableWindow` on every button.
- **Size.** Done: `size=(w, h)` resizes the frame and lays the buttons and text out again. A size
  smaller than the stock box is refused, because it would clip.
- **Changing the text (B7).** Done: `set_message(text)` sets the text of the static control. The
  control clips to its own rectangle, so it is moved to fit the new lines.
- **Not in a state.** Still true. `APPS` in `anim/setstate.py` holds only `picture` and `notepad`,
  so a cascade is built in `construct`. That is fine for this video.
- **Title.** Any title works. Several boxes may share one, such as `???`: each `Dialog` takes only
  the window that is new since its call.
- **Window colours.** Not checked against the video's exact blue.

### Wallpaper (B2), as built

A tiled BMP works. The BMP goes to the guest on a CD in drive `D:`, not by `put_file`, so the
15 s or more that a 1.4 MB file would have taken is about a second (the disc goes in in 1 to 8 ms,
and setting the wallpaper takes 0.3 to 0.8 s). `center`, `tile` and `stretch` all work. See
[Desktop colour and wallpaper](state-and-action.md#desktop-colour-and-wallpaper). Not tried: the
video's mottled and gradient textures themselves. The dialog storm uses a small red lattice tile.

### Aspect ratio (B12)

The Cirrus driver offers 640x480, 800x600, 1024x768 and 1280x1024 (8 bit only). There is no 16:9
mode, and `set_display_mode` only takes a mode the driver reports. A scene renders at 800x600 or
1024x768. To match a 1280x720 video, stretch or pad the finished footage with ffmpeg. I can't tell
from the video whether the original was stretched too. The dialogs and icons look a little wide,
which would fit a stretched 4:3 desktop, but that is a guess.

## Shot table

Times are from the 2 s contact sheets and the scene-change timestamps, so edges are accurate to
about 0.5 s. "Dialog" in the How column means the `Dialog` action (B3). The categories in the table below are as first written,
before `Dialog` and `Backdrop` were built. Lyrics are described, not copied.

| Time | On screen | What moves | Cat. | How |
| --- | --- | --- | --- | --- |
| 0:00 to 0:02 | CRT cartoon, dark brown, black screen | Fade in | (d) | B14, made elsewhere |
| 0:02 to 0:04 | Plain teal desktop, no windows | Holds, then boxes start | (a)/(c) | B1 with `desktop = "stock"`. Colour is the video's blue, not stock teal |
| 0:04 to 0:06 | Cascade of about eight `???` boxes with warning icons, stepping up and right | One new box every 2 to 3 frames | (b) | B4 |
| 0:06 to 0:08 | Two overlapping boxes, computer icon | Pair pops in | (b) | B5, custom icon (B3) |
| 0:08 to 0:10 | Cascade of six, printer icon | Stair-step build | (b) | B4, custom icon |
| 0:10 to 0:12 | Three stacked boxes, red X | Pop in with a few px of jitter | (b) | B5, stock error icon |
| 0:12 to 0:14 | One box, mouse icon, then a second beside it | Second pops in | (b) | B5, custom icon |
| 0:14 to 0:18 | Pairs: telephone icon, then a Windows-flag icon | Each pair offset a few px | (b) | B5, custom icons |
| 0:18 to 0:20 | Boxes close, empty desktop | Boxes vanish together | (b) | `Close` on each |
| 0:20 to 0:24 | One box, globe icon | Single pop-in, hold | (b) | B3, custom icon |
| 0:24 to 0:26 | Dark-red desktop, icons black, big white bold line at the bottom | Words type in | (c)/(d) | B1 red. Text is B13. Icon recolouring is out of scope |
| 0:26 to 0:34 | Address Book window on the right, big thin text in its list area | Text types, stutters, repeats and doubles with a red ghost | (b) | B8. The stutter is almost certainly edited in |
| 0:34 to 0:44 | Teal desktop, one CD-icon box, same place for 8 s | Sits still, slight shake, one resize wobble at 0:38 | (b) | B3, then `.animate.shift` for the shake |
| 0:44 to 0:46 | Three stacked CD-icon boxes | Cascade | (b) | B4 |
| 0:46 to 0:50 | Pair "computer program" boxes, one big warning box, then a six-box printer cascade | Pop-ins | (b) | B3, B4, B5 |
| 0:52 to 0:54 | Red desktop, icons black, taskbar reduced to a bare Start button, big text at bottom | Cut to red | (c)/(d) | Taskbar contents are tray work (not built). Icons: out of scope. Text: B13 |
| 0:54 to 0:58 | Globe box, then a second box whose text is "A" | Text typed into a box | (b) | B3, B7 |
| 0:58 to 1:12 | White desktop with dark icons, taskbar normal, right-aligned bold black words, one phrase at a time | Words change every 1 to 3 s | (d) | B1 white. Text is B13. Dark icons: out of scope |
| 1:12 to 1:14 | White-to-grey gradient fills the frame | Fade | (d) | B18 |
| 1:14 to 1:32 | CRT cartoon, brown, yellow pixel lyrics on the screen, one word or line at a time | Text swaps, one line blank | (d) | B14 |
| 1:32 to 1:34 | Black | | (a) | `cut()`, or a blank desktop |
| 1:34 to 1:38 | Blue desktop, five-box cascade, Windows-flag icon, then a pile of four | Cascade | (b) | B4, B5, custom icon |
| 1:38 to 1:40 | Blue mottled wallpaper, one box | Pop-in | (b)/(c) | B3, B2 |
| 1:40 to 1:42 | One box zoomed to full screen, printer icon, text spoken in two steps | Zoom in | (d) | B16, a zoom on the footage |
| 1:42 to 1:44 | Black, tiny empty box with no icon | Box fades or pops in | (b) | B3 on a blank desktop |
| 1:44 to 1:46 | Pink-to-orange gradient desktop, pair of "computer program" boxes | Pop-in | (b)/(c) | B3, B2 gradient |
| 1:46 to 1:52 | Six-box cascade, mixed overlap of "virus" and "printer" boxes, then a diagonal four | Several cascades one after another | (b) | B4, B5 |
| 1:52 to 1:58 | Pairs: mouse, telephone, then a pile of about a dozen with the Windows-flag icon | Pairs, then scatter | (b) | B5, B6 |
| 1:58 to 2:02 | One globe box on the gradient, then a cut to dark red with big text at the bottom | Cut | (b)/(c) | B3, B13 |
| 2:02 to 2:14 | Address Book on bright red grunge, same big text and stutter | Typed text | (b)/(c) | B8, B2 |
| 2:14 to 2:24 | One CD box on red, a second copy appears offset and they jitter | Doubling | (b) | B3, B5 |
| 2:24 to 2:34 | CRT cartoon, blue background, title and author text types on, then blank | Text types | (d) | B14 |

## What art98 does well here

The video is a **desktop with windows popping in at exact times and places**. That is art98's core:
a real Windows 98 desktop, a scene that places things at known pixels, and a recorder that waits for
every repaint, so pop-ins land on the frame they were written for. There is no pointer to animate,
which skips the hardest part of the code (`Glide`, `Drag`). The blank start gives the black frames
for free, and `cut()` gives the hard cuts.

The real Windows look is the point of the video, and a real `MessageBoxA` is a better source for it
than a copy.

## What to build, ranked

Ranked by how much of the video each step unlocks.

1. **Built: `Dialog`, and the small options the video needs.** Unlocks B3 to B7: about 60% of
   the running time, about 20 of the 32 rows. Four additions, each tiny: pass `size` through, a `disabled`
   flag for the buttons, a way to change a box's text (`set_text` on the static control, for B7), and
   a custom icon. The icon is the only one with a risk, so test it first on a private image copy.
   Follows the Notepad pilot in `docs/design/programs.md`: its own file in `actions/programs/`,
   exported from `art98.anim`, with a test beside `test_notepad.py`.
2. **Built: a `Backdrop` action for the desktop colour.** A named action over the `SetSysColors` call in
   `desktop.py`, with colours in the video (teal, dark red, red, white). Unlocks B1 and
   the colour of every desktop shot.
3. **Built: stock desktop with the taskbar, at the video's colour.** Needed only a check that
   `desktop = "stock"` plus a colour change looks right, since the stock desktop was last checked for
   a different reason. Gives B9 without the custom icons.
4. **Built for a tile: wallpaper in states, with the transfer cost measured.** Unlocks B2: the textured and gradient
   desktops, about a quarter of the rows. This is the biggest gap, and the one with a real unknown
   (the cost of putting a BMP on the guest). Do the test the design asks for first.
5. **A `Cascade` helper.** A group animation that adds N boxes with an offset and a delay, since
   B4, B5 and B6 are the same shape. Pure Python over item 1, and it would make the scene readable.
   Worth it only after the plain loop has been written once by hand.
6. **Address Book program.** B8, two shots of about 8 s each. Check first that `wab.exe` opens on the
   image and has a window that takes `SetWindowPos`. Then it is the Notepad recipe again.
7. **Audio.** Deferred until the user asks. The song drives this video, so it would matter here.

Not worth building in art98: the kinetic type (B13), the CRT cartoons (B14), the VHS look (B15) and
the zoom and fades (B16, B18). They belong in the editor or in ffmpeg, over footage art98 renders.
`--section` replay is not needed for this video, but it would help tuning one cascade at a time.

## A first replica scene, using what exists today

Only category (a), so no boxes yet. It shows the blank desktop, a cut, and the 24 fps setting,
and it stands in for the shot where boxes will go.

```python
from art98.anim import *


class Replica(Scene):
    fps = 24
    desktop = "stock"  # the taskbar and stock icons, as in most of the video

    def construct(self):
        self.pause(2)  # 0:02 to 0:04, an empty desktop
        # self.play(Backdrop((0, 60, 160))) here, for the video's blue
        self.next_section("boxes")
        # the cascade goes here:
        #   for i in range(8):
        #       self.add(Dialog("", "???", icon="warning", at=(300 + 14 * i, 380 - 22 * i)))
        #       self.pause(2 / 24)
        self.pause(1)
```

This is a sketch and has not been run. The built version, run on the image, is
[examples/dialog_storm](../../examples/dialog_storm/dialog_storm.py).

## What was and wasn't checked

- Checked: the video's resolution, frame rate and length with `ffprobe`; every shot by eye from 2 s
  contact sheets plus the 23 scene-change timestamps; two full-size frames.
- Checked in code: `Dialog` and its parameters, the `APPS` list, `desktop.py`, the display modes,
  the scene's `fps`, the exports of `art98.anim`.
- Not checked when this was written, since proved: icons (by `STM_SETICON`), the wallpaper transfer
  time (about 1 s on a CD) and the stock desktop with a colour. Still not checked: whether `wab.exe`
  opens, the video's textures, and the exact blues and reds.
