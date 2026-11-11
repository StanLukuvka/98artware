# Inspiration: a Windows 98 lyric video

Draft, 2026-11-11. Analysis only, nothing here is built.

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
- **(b)** needs a program or action that is parked or not yet built
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
| B1 | **Solid desktop colour** | Teal, dark red, red | (a): `self.guest.user32.SetSysColors(...)`, the call `desktop.py` already makes for black | A named action so a scene doesn't write the struct packing by hand |
| B2 | **Textured or gradient wallpaper** | Mottled blue, red grunge, pink-orange gradient | (c) | Wallpaper in states, designed but untested. See "Wallpaper" below |
| B3 | **Message box** | `???` title, one line, icon, two greyed buttons, at an exact position | (b): `Dialog` exists but is parked in `art98.anim.apps` | See "Message box gaps" below |
| B4 | **Cascade** | 5 to 8 boxes appear 2 to 3 frames apart, each offset up and right | (b): a loop of `Dialog(..., at=...)` with `add` and a one-frame `pause` | Needs B3 |
| B5 | **Pair and jitter** | Two copies of a box a few pixels apart, or side by side | (b): two `Dialog` props | Needs B3 |
| B6 | **Scatter pile** | About a dozen boxes at random positions (1:58) | (b): a seeded loop of `Dialog`s | Needs B3 |
| B7 | **Box with typing text** | A box whose text is just "A" (0:56) | (b), partly: `Dialog` text is fixed when it opens | Changing a box's text: `SetDlgItemText` on the static control, not wrapped |
| B8 | **Address Book with typed big text** | The window, and a huge thin "YOU'VE GOT MAIL!" in its list area | (b): the program is on the image but there is no class. Nothing in the docs says it was ever opened | A `programs/` class for `wab.exe`. The big text is most likely added in editing: see B13 |
| B9 | **Static desktop icons and taskbar** | My Computer, My Briefcase, Recycle Bin, Internet Explorer, Notepad, two folders, a Start button, quick launch, tray | (a) in part: `desktop = "stock"` gives the stock icons and taskbar | The custom icons ("My Briefcase", the two folders with their labels) need icons in states (c). Animating or recolouring icons is out of scope |
| B10 | **Hard cut and black** | Cuts on the beat, black frames | (a): `cut()` and `next_section()`, and the blank desktop is black | Nothing |
| B11 | **Fixed frame rate** | 24 fps | (a): `fps = 24` on the scene (the class default is 30) | Nothing |
| B12 | **Scene layout of the screen** | 16:9 | (c) | art98's guest only offers 4:3 modes. See "Aspect ratio" below |
| B13 | **Kinetic lyric type** | Big bold words, one phrase at a time, over the desktop | (d) | Not a Windows program. Do it in the editor over the footage, or with ffmpeg `drawtext`. A real window with a big font would be a new feature and gains little |
| B14 | **CRT cartoon interludes** | A flat monitor illustration with pixel-font lyrics | (d) | 2D animated artwork, not a desktop. Make it elsewhere and cut it in |
| B15 | **VHS look** | Blur, scanlines, fringing, glitch line | (d) | A post filter over the finished MP4, ffmpeg or the editor. It would hide art98's crisp pixels on purpose |
| B16 | **Zoom into a box** | The "SO I CAN'T" box fills the screen (1:40) | (d), or (c) | A zoom on the finished footage is trivial in post. `Box.scale` keeps the font size, so it is not a real zoom |
| B17 | **Audio** | The whole song | (c), deferred | Audio is deferred until the user asks. The scene can be timed to beat times by hand in the meantime |
| B18 | **Fade and white flash** | White to grey gradient at 1:12 | (d) | Post |

### Message box gaps (B3)

`Dialog` is a real `MessageBoxA` on its own guest thread. It is tested and works, but it is parked
(`art98/anim/apps.py`, listed in `PARKED`). Against what the video needs:

- **Icons.** `MessageBoxA` gives only error, question, warning and information. The video uses the red
  X and the warning triangle, which are stock, but also a computer, a printer, a mouse, a telephone,
  a CD, a globe and a Windows flag. Those are icons from the shell DLLs. A box with one of them
  needs `MessageBoxIndirect` with a user icon, or a `STM_SETICON` message to the box's icon control.
  Neither is wrapped, and neither has been tried on the image. Likely small, but untested.
- **Greyed buttons.** The video's buttons are disabled. `EnableWindow(button, 0)` does that, and
  `Dialog.button(label)` already finds the button. So it is one raw guest call today, and a
  `disabled=True` option later.
- **Size.** A message box sizes itself to its text. The video's boxes are wider and less tall than
  the text alone would give. `Win` takes a `size`, but `Dialog.__init__` doesn't pass it on.
- **Not in a state.** `APPS` in `anim/setstate.py` holds only `picture` and `notepad`, so a box
  can't be in a starting state. Cascades are built in `construct`, which is fine for this video.
- **Title.** Any title works, so `???` is no problem.
- **Window colours.** Title bars here are plain blue. With gradient captions off, which the blank
  start already does, Windows 98 draws a plain bar, so that probably matches. The exact blue is
  unchecked.

### Wallpaper (B2)

`state-and-action.md` lists wallpaper as "Likely easy, but the bitmap must reach the guest first".
It has no test. `put_file` runs at about 90 KB/s on a quiet host and about 12 KB/s on a busy one, so a
full-screen 16-bit BMP at 800x600 (about 940 KB) takes roughly 10 s on a quiet host, once per
scene, and far longer when the host is busy. The video needs three or four textures. Two ways to
live with it: put the BMPs on a read-only disc the backend attaches, or accept a one-time cost
per render. A smaller tiled texture fixes the size for the noise textures but not for the
gradient.

### Aspect ratio (B12)

The Cirrus driver offers 640x480, 800x600, 1024x768 and 1280x1024 (8 bit only). There is no 16:9
mode, and `set_display_mode` only takes a mode the driver reports. A scene renders at 800x600 or
1024x768. To match a 1280x720 video, stretch or pad the finished footage with ffmpeg. I can't tell
from the video whether the original was stretched too. The dialogs and icons look a little wide,
which would fit a stretched 4:3 desktop, but that is a guess.

## Shot table

Times are from the 2 s contact sheets and the scene-change timestamps, so edges are accurate to
about 0.5 s. "Dialog" in the How column means the parked `Dialog` action (B3), so every shot with
boxes is (b) until it is un-parked. Lyrics are described, not copied.

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

1. **Un-park `Dialog`, and add the small options the video needs.** Unlocks B3 to B7: about 60% of
   the running time, about 20 of the 32 rows. Four additions, each tiny: pass `size` through, a `disabled`
   flag for the buttons, a way to change a box's text (`set_text` on the static control, for B7), and
   a custom icon. The icon is the only one with a risk, so test it first on a private image copy.
   Follows the Notepad pilot in `docs/design/programs.md`: its own file in `actions/programs/`,
   exported from `art98.anim`, with a test beside `test_notepad.py`.
2. **A `Backdrop` action for the desktop colour.** A named action over the `SetSysColors` call in
   `desktop.py`, with colours in the video (teal, dark red, red, white). Unlocks B1 and
   the colour of every desktop shot.
3. **Stock desktop with the taskbar, at the video's colour.** Already possible. Needs only a check that
   `desktop = "stock"` plus a colour change looks right, since the stock desktop was last checked for
   a different reason. Gives B9 without the custom icons.
4. **Wallpaper in states, with the transfer cost measured.** Unlocks B2: the textured and gradient
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
        # SetSysColors(1, ...) here, once Backdrop exists, for the video's blue
        self.next_section("boxes")
        # the cascade goes here, once Dialog is un-parked:
        #   for i in range(8):
        #       self.add(Dialog("", "???", icon="warning", at=(300 + 14 * i, 380 - 22 * i)))
        #       self.pause(2 / 24)
        self.pause(1)
```

This is a sketch and has not been run. With the VM not used for this analysis, nothing here was
tried on the image.

## What was and wasn't checked

- Checked: the video's resolution, frame rate and length with `ffprobe`; every shot by eye from 2 s
  contact sheets plus the 23 scene-change timestamps; two full-size frames.
- Checked in code: `Dialog` and its parameters, the `APPS` list, `desktop.py`, the display modes,
  the scene's `fps`, the exports of `art98.anim`.
- Not checked: any of this on the real image. Whether `MessageBoxIndirect` icons work, whether
  `wab.exe` opens, how long a wallpaper transfer takes, and the exact blues and reds.
