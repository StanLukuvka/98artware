# Inspiration: a Windows 98 lyric video

The video that inspired art98 is a 154 s lyric video for a song about a computer virus, 1280x720
at 24 fps. It reuses a few parts with different words and wallpaper, so this page breaks it into
**building blocks** and says which art98 can do. Animating desktop icons is out of scope.

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
   typed line over it that stutters and doubles.
3. **Kinetic type.** Big bold white or black words, one phrase at a time, over a desktop.
4. **CRT cartoon interludes.** A flat illustration of a monitor on a brown or blue background, with
   pixel-font text on its black screen.
5. **A VHS look over everything:** soft focus, scanlines, colour fringing, a tracking glitch line,
   small jitter.

Desktop colours seen: teal-blue (plain, then with a mottled texture), dark red, bright red with a
grunge texture, white, and a pink-to-orange gradient. Icons, the taskbar and the Start button are
visible in nearly all desktop shots. No mouse pointer is ever shown: everything appears by itself.

## Building blocks

| # | Block | What it is, in the video | Today | What is missing |
| --- | --- | --- | --- | --- |
| B1 | **Solid desktop colour** | Teal, dark red, red | Built: `Backdrop(colour)` (teal, dark red, red, white and any RGB), proved on the stock and the blank desktop | Nothing. The 16-bit screen rounds the colour (128 becomes 120) |
| B2 | **Textured or gradient wallpaper** | Mottled blue, red grunge, pink-orange gradient | Built for a tiled BMP: `desktop.wallpaper` in a state, sent on a CD | The video's mottled and gradient textures are not tried. See [Desktop colour and wallpaper](state-and-action.md#desktop-colour-and-wallpaper) |
| B3 | **Message box** | a short title, one line, icon, two greyed buttons, at an exact position | Built: `Dialog` with `size`, `disabled` and the custom icons, in `art98.anim` | See [Dialog](../scenes/scene-api.md#dialog) |
| B4 | **Cascade** | 5 to 8 boxes appear 2 to 3 frames apart, each offset up and right | Built, by hand: a loop of `Dialog(..., at=...)` with `add` and a `pause` of two frames. Proved with eight boxes | A `Cascade` helper, only if the loop keeps coming back |
| B5 | **Pair and jitter** | Two copies of a box a few pixels apart, or side by side | Built: two `Dialog` props with a seeded jitter. Proved with a pair | Nothing |
| B6 | **Scatter pile** | About a dozen boxes at random positions| Likely built: the same loop with random positions. Not proved at a dozen boxes | A run with a dozen boxes |
| B7 | **Box with typing text** | A box whose text is a single letter  | Built: `Dialog.set_message(text)`, one letter per frame in the proof | Nothing |
| B8 | **Address Book with typed big text** | The window, and a huge thin line of text in its list area | (b): the program is on the image but there is no class. Nothing in the docs says it was ever opened | A `programs/` class for `wab.exe`. The big text is most likely added in editing: see B13 |
| B9 | **Static desktop icons and taskbar** | My Computer, My Briefcase, Recycle Bin, Internet Explorer, Notepad, two folders, a Start button, quick launch, tray | Built for stock icons and taskbar: `desktop = "stock"` plus `Backdrop` keeps the taskbar and icons on the new colour (`DialogStormStock`) | The custom icons ("My Briefcase", the two folders with their labels) need icons in states (c). Animating or recolouring icons is out of scope |
| B10 | **Hard cut and black** | Cuts on the beat, black frames | (a): `cut()` and `next_section()`, and the blank desktop is black | Nothing |
| B11 | **Fixed frame rate** | 24 fps | (a): `fps = 24` on the scene (the class default is 30) | Nothing |
| B12 | **Scene layout of the screen** | 16:9 | (d) | art98's guest only offers 4:3 modes, and other modes are out of scope. See "Aspect ratio (B12)" below |
| B13 | **Kinetic lyric type** | Big bold words, one phrase at a time, over the desktop | (d) | Not a Windows program. Do it in the editor over the footage, or with ffmpeg `drawtext`. A real window with a big font would be a new feature and gains little |
| B14 | **CRT cartoon interludes** | A flat monitor illustration with pixel-font lyrics | (d) | 2D animated artwork, not a desktop. Make it elsewhere and cut it in |
| B15 | **VHS look** | Blur, scanlines, fringing, glitch line | (d) | A post filter over the finished MP4, ffmpeg or the editor. It would hide art98's crisp pixels on purpose |
| B16 | **Zoom into a box** | One box fills the screen  | (d), or (c) | A zoom on the finished footage is trivial in post. `Box.scale` keeps the font size, so it is not a real zoom |
| B17 | **Audio** | The whole song | (c) | Not supported yet. Time the scene to the beat by hand |
| B18 | **Fade and white flash** | White to grey gradient  | (d) | Post |

### Aspect ratio (B12)

The guest has only 4:3 modes (see [Display modes](../scenes/win32-recipes.md#display-modes)). To
match a 1280x720 video, stretch or pad the finished footage with ffmpeg. The original's slightly
wide dialogs suggest it was a stretched 4:3 desktop.

## What art98 does well here

The video is a **desktop with windows popping in at exact times and places**. That is art98's core:
a real Windows 98 desktop, a scene that places things at known pixels, and a recorder that waits for
every repaint, so pop-ins land on the frame they were written for. There is no pointer to animate,
which skips the hardest part of the code (`Glide`, `Drag`). The blank start gives the black frames
for free, and `cut()` gives the hard cuts.

The real Windows look is the point of the video, and a real `MessageBoxA` is a better source for it
than a copy.

## What is left

Built: `Dialog` with its options (B3 to B7), `Backdrop` (B1), the stock desktop at a new colour
(B9) and a tiled wallpaper (B2). [recipes/scenes/dialog_storm](../../recipes/scenes/dialog_storm/dialog_storm.py)
uses all of them.

Not built, most useful first:

1. A `Cascade` helper: a group animation that adds N boxes with an offset and a delay (B4 to B6).
   Worth it only if the hand-written loop keeps coming back.
2. An Address Book program (B8), two shots of about 8 s. Check first that `wab.exe` opens and takes
   `SetWindowPos`.
3. Audio (B17). The song drives this video.

Not worth building in art98: B13 to B16 and B18. They belong in the editor or ffmpeg.

Still not checked: whether `wab.exe` opens, the video's textures, and its exact blues and reds.
