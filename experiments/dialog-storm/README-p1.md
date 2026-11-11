# P1: custom icons and box layout (2026-11-11)

Probe: `probe_icons.py` (`. .tools/env.sh; .venv/bin/python experiments/dialog-storm/probe_icons.py [OUT_DIR/] [sheets|icons|struct|layout|misc]`).
Local backend, `art98.session.stage`, no snapshot saved. Screenshots went to the scratchpad, not the repo.
Host CPU pressure (`/proc/pressure/cpu`, "some avg10") was 0.0 to 4.6 during the runs; one boot is 0.2 to 0.45 s.
The 2000-call loops: 6.7 s without `DestroyIcon` and 21 s with it (avg10 0.09 and 3.8): about 3.4 ms per `ExtractIconA`, 10.5 ms per extract+destroy pair.

## Icon table (every icon seen in a real `MB_ICONINFORMATION` box via `STM_SETICON`)

| name | DLL | index |
| --- | --- | --- |
| computer | `C:\WINDOWS\SYSTEM\shell32.dll` | 15 |
| printer | `C:\WINDOWS\SYSTEM\shell32.dll` | 16 |
| mouse | `C:\WINDOWS\SYSTEM\main.cpl` | 0 |
| telephone | `C:\WINDOWS\SYSTEM\modem.cpl` | 0 |
| cd | `C:\WINDOWS\SYSTEM\shell32.dll` | 11 |
| globe | `C:\WINDOWS\SYSTEM\shell32.dll` | 13 |
| flag | `C:\WINDOWS\SYSTEM\user.exe` | 0 |

Alternatives seen on the contact sheets: computer `explorer.exe` 0 (My Computer); printer `explorer.exe` 2; telephone `progman.exe` 25;
cd `progman.exe` 13, `shell32.dll` 40 and 73, `mmsys.cpl` 6; flag `progman.exe` 8, `shell32.dll` 0 and 46. Counts (`ExtractIconA(0, path, 0xFFFFFFFF)`):
shell32 80, moricons 106, pifmgr 38, progman 46, cool 45, setupx 32, inetcpl 34, mmsys 34, url 5, user.exe 7, explorer 7, mplayer 7, cdplayer 3, main.cpl 10, sysdm 19, regedit 9.
USER.EXE also has the stock message box icons: 1 warning, 2 question, 3 red X, 4 info. Missing/invalid index returns 0 (not 1).
Contact sheets were drawn with `DrawIcon` onto the screen DC (one boot per file, to avoid stale pixels), not through a box each; the 7 picks were then each shown in a real box.

## G4: `STM_SETICON` works (route A, keep it)

- Box from `MessageBoxA(0, text, title, MB_ICONINFORMATION|...)` has three child kinds. Measured on `MB_ICONINFORMATION|MB_OK`:
  Button id 2; icon Static `style=0x50020003` (`SS_ICON`), 32x32, **control id 0xa (10), not 20**; text Static `style=0x50022080` (`SS_NOPREFIX`), id 0xffff.
  Find the slot by class `Static` and `style & 0x1F == 3` (as in plan 3.1), never by id.
- Sequence that worked (all on the main agent thread, the box lives on its own acall thread):
  `h = shell32.ExtractIconA(0, dll, i)`; `slot = <icon static>`; `user32.SendMessageA(slot, 0x170, h, 0)` (returns the previous icon `0x201f`);
  `user32.RedrawWindow(slot, 0, 0, RDW_INVALIDATE|RDW_ERASE|RDW_UPDATENOW)`; `bridge.sync(box)`. Icon is 32x32, no scaling, no artefacts, same slot as the stock icon.
- **hInst**: `0` and the agent module (`GetModuleHandleA(NULL)` = 0x400000) give identical pixels (checked by `compare`: 0 differing pixels). Use `0`.
- **DestroyIcon**: the static does NOT own or copy the icon: after `DestroyIcon(h)` while set, a later repaint (box moved + RedrawWindow) leaves the slot BLANK (`misc_8` shot).
  So keep `h` until the box has closed (or the Dialog is removed), then `DestroyIcon(h)`. Leaking is harmless in practice: 2000 `ExtractIconA` calls without `DestroyIcon` never failed
  (the plan's earlier 6000-call run also did not), and a revert wipes the guest. Needed for correctness, not for survival; one line.
- Route B (`MessageBoxIndirect`, `MB_USERICON`) was not needed.

## G5: `size=(w,h)` via `SetWindowPos` on the `#32770` box

Flags: `SWP_NOMOVE|SWP_NOZORDER` = `0x2|0x4`. (`0x1` is `SWP_NOSIZE`, easy to swap.)

- Only the frame changes. Icon, text static and buttons keep their client positions (top-left anchored): a wide box is a left-aligned row with empty space on the right
  (this is the video's look: `layout_yesno_wide_*`). Box stays at its top-left, so a bigger box grows right/down: re-place it after (`at=`) or move it centred.
- No stale pixels and no extra `RedrawWindow` needed after the resize (`_1_setwindowpos` and `_2_redraw` shots are identical).
- A box made SMALLER than the stock one clips the buttons and text (`yesno_narrow`): `size` must be >= the stock box, or the buttons must be re-laid out too.
- Re-centring, measured and good-looking (`layout_manual.png`): per child, `user32.MoveWindow(h, x, y, w, h, 1)` takes CLIENT coordinates; children's `GetWindowRect` is screen.
  Client origin: `ScreenToClient(box, Out(8))` on a zeroed point gives `(-cx, -cy)`; so `client = screen + that`. Client size `GetClientRect(box, Out(16))`.
  Stock metrics: buttons 75x23, gap 6, bottom margin 11 from client bottom, icon at (14, ~11) in client, text static left edge 62.
  Buttons centred: `x0 = (cw - (n*75 + (n-1)*6)) // 2`, keep or lower y (`ch - 11 - 23` for a taller box). Text static: `MoveWindow(ts, 62, y, cw - 62 - 16, h, 1)` (it is left-aligned; `SS_CENTER` not tried).
- Each `MoveWindow` with `bRepaint=1` repainted correctly; a final `RedrawWindow(box, RDW_REPAINT_ALL)` is cheap insurance.
- `WM_CLOSE` closes an OK box only. A Yes/No box ignores it (no cancel): finish with `PostMessageA(box, WM_COMMAND=0x111, IDNO=7, 0)` (or `BM_CLICK` on a button). Matters for `Dialog.remove()`.

## EnableWindow and SetWindowTextA

- `EnableWindow(button, 0)`: returns 0 (was enabled); button greys at once (style gains `WS_DISABLED` 0x08000000), no invalidate needed. Re-enable returns non-zero (was disabled).
  Default button can be disabled too (both greyed works). Disabled buttons look like the video's greyed buttons.
- `SetWindowTextA(text_static, s)`: the text changes at once; a SHORTER string leaves no residue, no invalidate needed. A LONGER or multi-line string is CLIPPED to the static's
  rect (111x15 stock): so `set_message` must first `MoveWindow` the static to fit (width, 15 px per line), and the box/buttons if it grows. With the static resized (250x30) two lines drew correctly.
  Keep the static clear of the buttons (it paints opaque over them if it overlaps).

## Surprises for D1

1. Icon static id is 10 not 20 (find by class+style, as planned). 2. Do not destroy the icon while the box is open: the box paints blank later. Destroy on remove.
3. `size` smaller than stock clips; reject it or fall back to stock size. 4. `set_message` must resize the static (clipping), not only `SetWindowTextA`.
5. Resizing a box moves nothing and re-centring the box on screen is the caller's job (box grows right/down from `at`).
6. `GetFreeSystemResources` is not exported to the agent (NOFUNC); no resource-meter check was possible.
