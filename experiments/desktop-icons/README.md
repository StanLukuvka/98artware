# Desktop icons probe

Can a scene put icons of its own on the desktop, with an image already on the guest or one it
brings, and place them? Run 2026-11-22 on the real VM (800x600) through the service
(`art98 vm start`, then each probe with an output folder). Each probe attaches, which reverts the
guest first, and reverts again at the end. CPU pressure `avg10` was 0.00 to 0.12 throughout.

| Probe | What it tries |
| --- | --- |
| `probe_icons.py` | three kinds of item on the stock desktop, moving them, a full refresh |
| `probe_icons_2.py` | the blank desktop, what brings the stock icons back, timing, the icon cache, labels |
| `probe_icons_3.py` | adding and removing with `SHCNE_MKDIR` and `SHCNE_RMDIR` only, a focus box, two icons on one spot |
| `probe_icons_4.py` | the item's rectangles, a 32-bit icon with alpha, a display change |
| `probe_icons_5.py` | all-caps labels, a label added again with a new image, every named guest image, the list hidden again |

## How an item is made

A folder in `C:\WINDOWS\DESKTOP` named for the label, holding a `desktop.ini` (hidden and system):

```ini
[.ShellClassInfo]
IconFile=C:\WINDOWS\SYSTEM\shell32.dll
IconIndex=15
```

The folder gets the system attribute, then `SHChangeNotify(SHCNE_MKDIR, SHCNF_PATHA | SHCNF_FLUSH,
path, 0)`. Removing it is the reverse: clear the attributes, delete `desktop.ini`,
`RemoveDirectoryA`, then `SHCNE_RMDIR`.

## Results

| Kind | Image | Arrow | Result |
| --- | --- | --- | --- |
| Folder + `desktop.ini`, `IconFile` a DLL | `shell32.dll` 15 | none | shows as the computer icon |
| Folder + `desktop.ini`, `IconFile` an `.ico` copied in with `put_file` | 32x32, 24-bit, AND mask | none | shows the image with the mask as transparent |
| `.url` file with `IconFile` and `IconIndex` | `shell32.dll` 13 | **shortcut arrow** | shows, but with the arrow |

- **Placing.** `LVM_SETITEMPOSITION` on the `SysListView32` puts an item anywhere, and
  `LVM_GETITEMPOSITION` reads back exactly what was set. Two items may share one spot: Explorer
  moves neither.
- **The position is the top left of the 32x32 image.** At position (200, 200),
  `LVM_GETITEMRECT` gives icon cell 192,198 to 240,234 and label 187,236 to 245,251 on stock
  (188 on blank). The bounds' width follows the label.
- **Find items by label.** After a full refresh (`SHCNE_ASSOCCHANGED`) the items keep their
  places and images, but their indices change (7, 8, 9 became 5, 6, 8).
- **Timing.** The create calls take 0.17 s. An item is in the list 0.07 s after `SHCNE_MKDIR`
  alone, 0.24 s when `SHCNE_UPDATEDIR` is sent too. A removed one is gone in 0.06 to 0.21 s.
- **Revert** removes every item and file.
- **Labels.** A long label is cut to two lines and "..." ("A Rather Long Label For An...").
  "notes.txt" shows in full, as folders show their whole name. A folder named "My Computer" is
  allowed and shows beside the real one, so two items share a label.
- **All-capital short labels change.** "PC" is listed and shown as "Pc", "TEMP" as "Temp".
  "MY STUFF" (a space) and "ABCDEFGHI" (nine letters) keep their capitals: Windows 98 shows a name
  that fits 8.3 and has no small letters in this softened form.
- **The icon cache.** Writing a new image over the same `.ico` path and adding a second folder
  showed the old image for the second folder too. A new path showed the new image.
- **A label used again keeps its first image.** "Swap" was added with the orange image, removed,
  and added again naming a red `.ico` at a new path: it showed orange. Only a revert clears it.
- **Every named guest image works** as `IconFile`: the seven of `Dialog.CUSTOM_ICONS`, from
  `shell32.dll`, `main.cpl`, `modem.cpl` and `user.exe`.
- **32-bit icons.** A 32-bit icon with an alpha channel and an all-opaque AND mask draws as a
  black square with the colour inside: Windows 98 ignores the alpha channel. Transparency comes
  only from the AND mask.

### On the blank desktop

`blank()` hides the icon list. With the list shown again and every stock item deleted from it
with `LVM_DELETEITEM` (by label), a fake icon shows alone on black, white label on black.

| After the stock items are deleted | Stock items come back? |
| --- | --- |
| `set_colour` (the list was shown, so it stays shown) | no |
| `SHCNE_MKDIR` for a new fake icon | no |
| `SHCNE_RMDIR` for a removed fake icon | no |
| Notepad opened and closed, then 5 s | no |
| `SHCNE_UPDATEDIR` on the desktop folder | **yes, all seven**, at their stock places |

- Adding with `SHCNE_MKDIR` alone draws no focus box. When `SHCNE_UPDATEDIR` was also sent before
  the stock items were deleted, the fake icon (then the only item) had a focus box.
  `LVM_SETITEMSTATE` with index -1 and `LVIS_FOCUSED | LVIS_SELECTED` cleared it (returned 1).
- **Hiding the list again.** With the last fake icon removed, `ShowWindow(list, SW_HIDE)` hides
  it. A fake icon added and removed while the list is hidden comes and goes in 0.03 to 0.06 s, and
  the list stays hidden with no items.
- **A display change** (640x480x16 with `set_display_mode`) kept both fake icons at their places.
  The desktop colour went back to teal and the labels kept a black background, which is why
  `apply_state` runs `prepare_desktop` again after a display change.
