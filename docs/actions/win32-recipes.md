# Win32 recipes

Short recipes for driving Windows 98 from the host. Every code block on this page ran on the real
image. Each block ran on its own, from a freshly restored `ready` snapshot.

For the calls themselves, see [Bridge](bridge.md). For the programs on the image, see
[App catalog](app-catalog.md). Scenes get the same bridge as `self.guest`, and the scene layer
already wraps much of this. See the [Scene API](scene-api.md).

## Setup

All recipes share this setup.

```python
import struct
import time

from art98 import Out, boot
from art98.session import private_stage

WM_CLOSE, WM_SETTEXT, WM_GETTEXT, WM_COMMAND, WM_CHAR = 0x10, 0x0C, 0x0D, 0x111, 0x102
WM_SYSCOMMAND, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x112, 0x201, 0x202
EM_SETSEL, EM_REPLACESEL, EM_SETMODIFY = 0xB1, 0xC2, 0xB9
MOUSEEVENTF_MOVE, MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x01, 0x02, 0x04
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP, MOUSEEVENTF_ABSOLUTE = 0x08, 0x10, 0x8000


def lparam(x, y):
    """Two 16-bit coordinates packed into one message argument."""
    return (y & 0xFFFF) << 16 | x & 0xFFFF


def cstring(data):
    return data.split(b"\0", 1)[0].decode("cp1252")


def get_text(hwnd, size=1024):
    """The text of a control, in any process."""
    return cstring(u.SendMessageA(hwnd, WM_GETTEXT, size, Out(size)).buffers[0])


def client_origin(hwnd):
    """The screen position of a window's client area."""
    return struct.unpack("<ii", u.ClientToScreen(hwnd, bytes(8)).buffers[0])


```

Each recipe then runs inside this block, on a throwaway copy of the prepared image.

```python
with private_stage("work") as stage, boot(stage) as session:
    g, vm = session.bridge, session.vm
    u, k, gdi = g.user32, g.kernel32, g.gdi32
    ...
```

`boot` restores the same desktop every time, so nothing a recipe does survives the next run. The
desktop is 800 x 600 in 16-bit colour.

Three rules cover most surprises:

- `Window.rect` is `(left, top, right, bottom)` in screen coordinates, not a width and height.
- A value in `result.value` is unsigned. Use `result.signed` for anything that can be negative.
- A call that may block goes through `acall`. See [threading](bridge.md#threading).

## Windows

### Find a window

`find_window` waits up to `timeout` seconds and only sees visible windows. `title` is a
case-insensitive substring. `class_name` is a case-insensitive exact match.

```python
g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad", timeout=5)
assert pad.title == "Untitled - Notepad"
assert g.find_window(title="notepad").hwnd == pad.hwnd
```

### List windows and children

`windows()` lists every top-level window, hidden ones included. `windows(hwnd)` lists all
descendants, not only direct children.

```python
top = g.windows()
assert any(w.class_name == "Progman" for w in top)
assert any(not w.visible for w in top)

g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
assert [c.class_name for c in g.windows(pad.hwnd)] == ["Edit"]
```

### Wait for a window to close

```python
g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
u.PostMessageA(pad.hwnd, WM_CLOSE, 0, 0)
while u.IsWindow(pad.hwnd):
    time.sleep(0.05)
```

### Move and resize

`move_window` keeps the size and stacking order, and repaints the frame. Use it for moves.

```python
g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
g.move_window(pad.hwnd, 100, 80)
u.SetWindowPos(pad.hwnd, 0, 0, 0, 400, 300, 0x0006)     # SWP_NOMOVE | SWP_NOZORDER
assert g.find_window(class_name="Notepad").rect == (100, 80, 500, 380)
u.MoveWindow(pad.hwnd, 50, 50, 300, 200, 1)
assert g.find_window(class_name="Notepad").rect == (50, 50, 350, 250)
```

### Read positions

A `Window` is a snapshot. Fetch it again after anything moves. Rectangles of child windows are in
screen coordinates too. Mouse messages use client coordinates, so convert with `client_origin`.

```python
g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
left, top = client_origin(pad.hwnd)
assert (left, top) == (pad.rect[0] + 4, pad.rect[1] + 42)

rect = struct.unpack("<4i", u.GetClientRect(pad.hwnd, Out(16)).buffers[0])
assert rect[:2] == (0, 0)

edit = g.find_window(class_name="Edit", parent=pad.hwnd)
assert edit.rect[:2] == (left, top)
```

### Minimise, maximise, hide

`ShowWindow` takes `SW_HIDE` 0, `SW_SHOW` 5, `SW_MINIMIZE` 6, `SW_RESTORE` 9 and `SW_MAXIMIZE` 3.

A minimised window stays visible and reports a rectangle at (3000, 3000). A maximised one reports
(-4, -4, 804, 576).

```python
g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
normal = pad.rect

u.ShowWindow(pad.hwnd, 6)
g.sync()
assert u.IsIconic(pad.hwnd).value == 1
assert g.find_window(class_name="Notepad").rect[:2] == (3000, 3000)

u.ShowWindow(pad.hwnd, 3)
g.sync()
assert u.IsZoomed(pad.hwnd).value == 1
assert g.find_window(class_name="Notepad").rect == (-4, -4, 804, 576)

u.ShowWindow(pad.hwnd, 9)
g.sync()
assert g.find_window(class_name="Notepad").rect == normal
```

The same works through the system menu commands, with `PostMessageA`.

```python
g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
u.PostMessageA(pad.hwnd, WM_SYSCOMMAND, 0xF020, 0)      # SC_MINIMIZE
time.sleep(0.4)
assert u.IsIconic(pad.hwnd).value == 1
u.PostMessageA(pad.hwnd, WM_SYSCOMMAND, 0xF120, 0)      # SC_RESTORE
time.sleep(0.4)
u.PostMessageA(pad.hwnd, WM_SYSCOMMAND, 0xF030, 0)      # SC_MAXIMIZE
time.sleep(0.4)
assert u.IsZoomed(pad.hwnd).value == 1
u.PostMessageA(pad.hwnd, WM_SYSCOMMAND, 0xF060, 0)      # SC_CLOSE
```

### Change a title

`SetWindowTextA` works on another program's top-level window. It does not work on another
program's controls. See [does not work](#does-not-work).

```python
g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
u.SetWindowTextA(pad.hwnd, "Written in 1998")
assert g.find_window(class_name="Notepad").title == "Written in 1998"
```

### Keep a window on top

```python
g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
u.SetWindowPos(pad.hwnd, 0xFFFFFFFF, 0, 0, 0, 0, 0x0003)    # HWND_TOPMOST, no move, no size
assert u.GetWindowLongA(pad.hwnd, -20).value & 0x8          # WS_EX_TOPMOST
```

### Bring to front and give focus

`SetForegroundWindow` works from the agent. `GetFocus` and `SetFocus` only see the caller's own
thread, so attach to the target's input queue first.

```python
g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
edit = g.find_window(class_name="Edit", parent=pad.hwnd)
time.sleep(0.5)
u.SetForegroundWindow(pad.hwnd)
assert u.GetForegroundWindow().value == pad.hwnd

mine = k.GetCurrentThreadId().value
theirs = u.GetWindowThreadProcessId(pad.hwnd, 0).value
u.AttachThreadInput(mine, theirs, 1)
u.SetFocus(edit.hwnd)
assert u.GetFocus().value == edit.hwnd
u.AttachThreadInput(mine, theirs, 0)
```

### Disable a window, flash a title bar

```python
g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
u.EnableWindow(pad.hwnd, 0)
assert u.IsWindowEnabled(pad.hwnd).value == 0
u.EnableWindow(pad.hwnd, 1)
u.FlashWindow(pad.hwnd, 1)
```

### Close a window, answer the save prompt

`WM_CLOSE` on a changed document opens a `#32770` dialog. Yes is button 6, No is 7, Cancel is 2.
Post `WM_COMMAND` with the button id to answer it.

```python
g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
edit = g.find_window(class_name="Edit", parent=pad.hwnd)
u.PostMessageA(edit.hwnd, WM_CHAR, ord("x"), 0)
g.sync(pad.hwnd)
u.PostMessageA(pad.hwnd, WM_CLOSE, 0, 0)
prompt = g.find_window(class_name="#32770", timeout=3)
u.PostMessageA(prompt.hwnd, WM_COMMAND, 7, 0)
while u.IsWindow(pad.hwnd):
    time.sleep(0.05)
```

Or clear the Edit control's modified flag first, and no prompt appears.

```python
g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
edit = g.find_window(class_name="Edit", parent=pad.hwnd)
u.SendMessageA(edit.hwnd, WM_SETTEXT, 0, "unsaved")
u.SendMessageA(edit.hwnd, EM_SETMODIFY, 0, 0)
u.PostMessageA(pad.hwnd, WM_CLOSE, 0, 0)
time.sleep(0.5)
assert not u.IsWindow(pad.hwnd)
```

### Create a window of your own

A window made with `call` belongs to the agent's UI thread, which pumps messages, so it stays alive
and paints. `0x90800000` is `WS_POPUP | WS_VISIBLE | WS_BORDER`.

```python
label = u.CreateWindowExA(0, "STATIC", "made by art98", 0x90800000,
                          200, 200, 200, 40, 0, 0, 0, 0)
assert label.value
g.sync()
assert g.find_window(title="made by art98").rect == (200, 200, 400, 240)
u.DestroyWindow(label.value)
```

### Wait for a repaint

`sync` returns once windows have repainted. Pass a window to wait for only that one. Do it before
any capture.

```python
g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
g.move_window(pad.hwnd, 150, 100)
g.sync(pad.hwnd)
vm.screenshot(stage / "moved.png")
```

## Mouse

### Move the pointer

`SetCursorPos` is exact. So is `mouse_event` with absolute coordinates, on a 0 to 65535 scale.

```python
u.SetCursorPos(400, 300)
assert struct.unpack("<ii", u.GetCursorPos(Out(8)).buffers[0]) == (400, 300)

u.mouse_event(MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_MOVE, 16384, 16384, 0, 0)
assert struct.unpack("<ii", u.GetCursorPos(Out(8)).buffers[0]) == (200, 150)
```

Relative moves are not exact. Windows doubles any delta above 2, because of the default mouse
speed settings. Screen captures include the pointer.

```python
u.SetCursorPos(100, 100)
u.mouse_event(MOUSEEVENTF_MOVE, 10, 0, 0, 0)
assert struct.unpack("<ii", u.GetCursorPos(Out(8)).buffers[0]) == (120, 100)
```

### Click with the real pointer

This takes the same path as a person's mouse. The target gets focus and raises itself. Use it
when the visible pointer matters.

```python
g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
u.SetCursorPos(pad.rect[0] + 200, pad.rect[1] + 150)
u.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
u.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
g.sync()
assert u.GetForegroundWindow().value == pad.hwnd
```

### Right click

```python
g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
u.SetCursorPos(pad.rect[0] + 200, pad.rect[1] + 150)
u.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
u.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
popup = g.find_window(class_name="#32768", timeout=3)       # the menu window class
vm.send_keys("esc")
```

### Drag

Press, move in steps, release.

```python
g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
x, y = pad.rect[0] + 100, pad.rect[1] + 10
u.SetCursorPos(x, y)
u.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
for step in range(1, 41):
    u.SetCursorPos(x + step * 3, y + step)
u.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
g.sync()
assert g.find_window(class_name="Notepad").rect[:2] == (pad.rect[0] + 120, pad.rect[1] + 40)
```

### Click without the pointer

Posted mouse messages use client coordinates. They need no foreground window, and the pointer
stays where it is. `wParam` is 1 for the left button held.

```python
g.spawn("calc.exe")
calc = g.find_window(class_name="SciCalc")
seven = next(c for c in g.windows(calc.hwnd) if u.GetDlgCtrlID(c.hwnd).value == 131)
u.PostMessageA(seven.hwnd, WM_LBUTTONDOWN, 1, lparam(5, 5))
u.PostMessageA(seven.hwnd, WM_LBUTTONUP, 0, lparam(5, 5))
g.sync(calc.hwnd)
display = next(c for c in g.windows(calc.hwnd) if u.GetDlgCtrlID(c.hwnd).value == 403)
assert display.title == "7."
```

### Hit test a point

```python
g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
edit = g.find_window(class_name="Edit", parent=pad.hwnd)
assert u.WindowFromPoint(pad.rect[0] + 100, pad.rect[1] + 100).value == edit.hwnd
```

## Keyboard

There are three ways in. They differ in where the text goes.

| Way | Goes to | Speed | Reaches a DOS box |
| --- | --- | --- | --- |
| `vm.send_keys` | The foreground window, as hardware keys | 2.5 to 150 ms a key | Yes |
| `keybd_event` | The foreground window, as Windows input | About 10 ms a key | No |
| `WM_CHAR` | One control, whatever is in front | About 5 ms a key | No |

### Real key presses

`vm.send_keys` takes QEMU key names and presses them together. Windows sees hardware key presses.
It returns at once and QEMU plays the keys out, so a script must pace itself.

```python
g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
edit = g.find_window(class_name="Edit", parent=pad.hwnd)
time.sleep(0.5)                         # a new window takes a moment to become foreground
for key in "hi":
    vm.send_keys(key)
    time.sleep(0.2)
vm.send_keys("shift", "1")
time.sleep(0.4)
assert get_text(edit.hwnd) == "hi!"
```

Chords work the same way.

```python
g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
edit = g.find_window(class_name="Edit", parent=pad.hwnd)
u.SendMessageA(edit.hwnd, WM_SETTEXT, 0, "select me")
time.sleep(0.5)
vm.send_keys("ctrl", "home")
time.sleep(0.3)
vm.send_keys("shift", "end")
time.sleep(0.4)
vm.send_keys("delete")
time.sleep(0.3)
assert get_text(edit.hwnd) == ""
```

### Type a string with real keys

This map covers the keys on a US layout. A key takes about 2 x `hold_ms`, and a shifted key about
4 x `hold_ms`. At `hold_ms=10` that is 20 ms a key. Leave that time between calls: QEMU's queue
overflows and drops keys if about 300 are queued at once.

```python
NAMES = {" ": "spc", "\n": "ret", "\t": "tab", ".": "dot", ",": "comma", "-": "minus",
         "=": "equal", "/": "slash", ";": "semicolon", "'": "apostrophe", "[": "bracket_left",
         "]": "bracket_right", "\\": "backslash", "`": "grave_accent"}
SHIFTED = dict(zip('!@#$%^&*()_+{}|:"<>?~', "1234567890-=[]\\;',./`"))


def press(char, hold_ms=10):
    keys = []
    if char.isupper():
        keys, char = ["shift"], char.lower()
    elif char in SHIFTED:
        keys, char = ["shift"], SHIFTED[char]
    keys.append(NAMES.get(char, char))
    vm.send_keys(*keys, hold_ms=hold_ms)
    time.sleep(len(keys) * hold_ms * 0.002)


g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
edit = g.find_window(class_name="Edit", parent=pad.hwnd)
time.sleep(0.5)
line = 'Hello, "World"! 100% [ok] C:\\TEMP'
for char in line:
    press(char)
time.sleep(0.2)
assert get_text(edit.hwnd) == line
```

### Type into one control

`WM_CHAR` goes to the control you name, even behind another window. The character code 13 makes
a line break in an Edit control.

```python
g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
edit = g.find_window(class_name="Edit", parent=pad.hwnd)
g.spawn("calc.exe")
g.find_window(class_name="SciCalc")
for char in "behind\r":
    u.PostMessageA(edit.hwnd, WM_CHAR, ord(char), 0)
u.PostMessageA(edit.hwnd, WM_CHAR, 0xE9, 0)         # é, in cp1252
g.sync(pad.hwnd)
assert get_text(edit.hwnd) == "behind\r\né"
```

### Set text in one go

`WM_SETTEXT` and `WM_GETTEXT` work across processes with a string or an `Out`. To add to the end,
move the selection there and use `EM_REPLACESEL`.

```python
g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
edit = g.find_window(class_name="Edit", parent=pad.hwnd)
u.SendMessageA(edit.hwnd, WM_SETTEXT, 0, "first")
end = len("first")
u.SendMessageA(edit.hwnd, EM_SETSEL, end, end)
u.SendMessageA(edit.hwnd, EM_REPLACESEL, 1, " second")
assert get_text(edit.hwnd) == "first second"
```

### Synthetic keys

`keybd_event` takes virtual key codes and goes to the foreground window. Letters arrive in lower
case unless Shift is held. `VkKeyScanA` finds the key and shift state for a character.

```python
VK_SHIFT, KEYUP = 0x10, 2

g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
edit = g.find_window(class_name="Edit", parent=pad.hwnd)
time.sleep(0.5)


def tap(vk):
    u.keybd_event(vk, 0, 0, 0)
    u.keybd_event(vk, 0, KEYUP, 0)


u.keybd_event(VK_SHIFT, 0, 0, 0)
tap(ord("A"))
u.keybd_event(VK_SHIFT, 0, KEYUP, 0)
tap(ord("B"))
g.sync(pad.hwnd)
assert get_text(edit.hwnd) == "Ab"
assert u.VkKeyScanA(ord("!")).value == 0x131        # Shift with VK 0x31
```

## Processes

### Start a program

`spawn` calls `CreateProcessA` with no shell. It searches the usual places, so `notepad.exe` works
without a path. Quote a path with spaces. `spawn` raises `BridgeError` if the program cannot start.

```python
from art98 import BridgeError

g.spawn(r'"C:\Program Files\Accessories\WORDPAD.EXE"')
g.find_window(class_name="WordPadClass")

try:
    g.spawn(r"C:\NOPE.EXE")
except BridgeError as error:
    assert str(error).startswith("SPAWN")
```

### Open a file, set the working directory

```python
g.put_file(r"C:\HELLO.TXT", b"hello")
g.spawn(r"notepad.exe C:\HELLO.TXT", cwd="C:\\")
assert g.find_window(class_name="Notepad").title == "Hello - Notepad"
```

### Use the shell

`ShellExecuteA` follows file associations. Values above 32 mean success. `WinExec` also works.

```python
g.put_file(r"C:\HELLO.TXT", b"hello")
assert g.shell32.ShellExecuteA(0, "open", r"C:\HELLO.TXT", 0, 0, 1).value > 32
g.find_window(class_name="Notepad")
assert k.WinExec("calc.exe", 1).value > 31
g.find_window(class_name="SciCalc")
```

### Run a DOS command

There is no pipe to the host. Redirect to a file and read that. `/c` closes the box afterwards, and
the command is finished when the output is complete.

```python
g.spawn(r"command.com /c echo hi > C:\OUT.TXT")
for _ in range(50):
    time.sleep(0.1)
    try:
        if g.get_file(r"C:\OUT.TXT").strip():
            break
    except Exception:
        pass
assert g.get_file(r"C:\OUT.TXT").startswith(b"hi")
```

### List and kill processes

Process ids are large, obfuscated numbers, and Windows reuses them at once. `OpenProcess` with
`PROCESS_TERMINATE` (1) gets a handle that `TerminateProcess` accepts. Names come back in full and
often in upper case.

```python
pid = g.spawn("notepad.exe")
g.find_window(class_name="Notepad")
assert (pid, r"C:\WINDOWS\NOTEPAD.EXE") in g.processes()

handle = k.OpenProcess(1, 0, pid).value
assert k.TerminateProcess(handle, 7)
k.CloseHandle(handle)
time.sleep(0.3)
assert pid not in [p for p, _ in g.processes()]
```

### Read a pointer's text

A function that returns a string returns a guest pointer. Copy it into an `Out`.

```python
pointer = k.GetCommandLineA().value
line = k.lstrcpyA(Out(128), pointer).buffers[0]
assert cstring(line).startswith('"C:\\ART98\\AGENT.EXE"')
```

## Files

### Copy files in and out

`put_file` and `get_file` split the transfer into 4 KB chunks. `PUT` runs at 100 to 190 KB/s and
`GET` at about 325 KB/s.

```python
data = bytes(range(256)) * 40
g.put_file(r"C:\DATA.BIN", data)
assert g.get_file(r"C:\DATA.BIN") == data
```

### Work with paths

```python
assert k.CreateDirectoryA(r"C:\STAGE", 0)
g.put_file(r"C:\STAGE\A.TXT", b"a")
assert k.CopyFileA(r"C:\STAGE\A.TXT", r"C:\STAGE\B.TXT", 0)
assert k.MoveFileA(r"C:\STAGE\B.TXT", r"C:\STAGE\C.TXT")
assert k.GetFileAttributesA(r"C:\STAGE\C.TXT").value == 0x20
assert k.DeleteFileA(r"C:\STAGE\A.TXT")
assert k.DeleteFileA(r"C:\STAGE\C.TXT")
assert k.RemoveDirectoryA(r"C:\STAGE")

missing = k.DeleteFileA(r"C:\NOPE.TXT")
assert (missing.value, missing.last_error) == (0, 2)
```

### Find system folders

```python
assert cstring(k.GetWindowsDirectoryA(Out(128), 128).buffers[0]) == r"C:\WINDOWS"
assert cstring(k.GetSystemDirectoryA(Out(128), 128).buffers[0]) == r"C:\WINDOWS\SYSTEM"
assert cstring(k.GetTempPathA(128, Out(128)).buffers[0]) == "C:\\WINDOWS\\TEMP\\"
```

### List a folder

`WIN32_FIND_DATAA` is 320 bytes: attributes at 0, size at 32, long name at 44.

```python
def listdir(pattern):
    found = k.FindFirstFileA(pattern, Out(320))
    if found.signed == -1:
        return []
    names, data = [], found.buffers[0]
    while True:
        names.append(cstring(data[44:304]))
        step = k.FindNextFileA(found.value, Out(320))
        if not step:
            break
        data = step.buffers[0]
    k.FindClose(found.value)
    return names


assert "NOTEPAD.EXE" in listdir(r"C:\WINDOWS\*.EXE")
assert "3D Pipes.scr" in listdir(r"C:\WINDOWS\SYSTEM\*.scr")
```

### Write an INI file

Windows caches profile writes. Flush with all-zero arguments before reading the file itself.

```python
assert k.WritePrivateProfileStringA("sec", "key", "value", r"C:\T.INI")
k.WritePrivateProfileStringA(0, 0, 0, r"C:\T.INI")
assert g.get_file(r"C:\T.INI") == b"[sec]\r\nkey=value\r\n"

read = k.GetPrivateProfileStringA("sec", "key", "?", Out(32), 32, r"C:\T.INI")
assert cstring(read.buffers[0]) == "value"
```

## Registry

Registry functions return their error code in `.value`, and 0 means success. `last_error` stays 0.

### Create, write, read, delete

`HKEY_CURRENT_USER` is `0x80000001`. A type 1 value is a string with its terminator, and a type 4
value is a DWORD. `RegQueryValueExA` takes the type and data as out buffers, and the size as an
in/out buffer.

```python
HKCU = 0x80000001
made = g.advapi32.RegCreateKeyA(HKCU, r"Software\Art98Demo", Out(4))
assert made.value == 0
key = struct.unpack("<I", made.buffers[0])[0]

assert g.advapi32.RegSetValueExA(key, "name", 0, 1, b"hello\0", 6).value == 0
assert g.advapi32.RegSetValueExA(key, "count", 0, 4, struct.pack("<I", 7), 4).value == 0

read = g.advapi32.RegQueryValueExA(key, "name", 0, Out(4), Out(64), struct.pack("<I", 64))
assert read.value == 0
assert struct.unpack("<I", read.buffers[0])[0] == 1
assert cstring(read.buffers[1]) == "hello"
assert g.advapi32.RegQueryValueExA(key, "nope", 0, Out(4), Out(4), struct.pack("<I", 4)).value == 2

g.advapi32.RegDeleteValueA(key, "count")
g.advapi32.RegCloseKey(key)
assert g.advapi32.RegDeleteKeyA(HKCU, r"Software\Art98Demo").value == 0
```

### Enumerate values

```python
HKCU = 0x80000001
opened = g.advapi32.RegOpenKeyExA(HKCU, r"Control Panel\Desktop", 0, 1, Out(4))
key = struct.unpack("<I", opened.buffers[0])[0]
names, index = [], 0
while True:
    step = g.advapi32.RegEnumValueA(key, index, Out(260), struct.pack("<I", 260), 0,
                                    Out(4), Out(260), struct.pack("<I", 260))
    if step.value:
        break
    names.append(cstring(step.buffers[0]))
    index += 1
g.advapi32.RegCloseKey(key)
assert "ScreenSaveTimeOut" in names
```

## Guest memory

### Keep data in the guest

`Out` and `#` buffers last for one call. For a pointer that stays valid, allocate on the guest.
`RtlMoveMemory` copies both ways: pass bytes to write, and an `Out` to read.

```python
pointer = k.VirtualAlloc(0, 4096, 0x3000, 4).value
k.RtlMoveMemory(pointer, b"kept", 5)
assert k.RtlMoveMemory(Out(5), pointer, 5).buffers[0] == b"kept\0"
k.VirtualFree(pointer, 0, 0x8000)
```

### Pass a struct to another process

Windows copies string arguments of text messages between processes, but not arbitrary structs.
`SendMessageA` with a private pointer can hang the agent. Use memory every process can see:
`VirtualAlloc` with `0x08000000` (`VA_SHARED`) returns an address above 2 GB.

This one lists the desktop icons, which live in Explorer's process. The `LVITEMA` holds a pointer
to a text buffer in the same block.

```python
LVM_GETITEMCOUNT, LVM_GETITEMPOSITION, LVM_GETITEMTEXTA = 0x1004, 0x1010, 0x102D
LVM_SETITEMPOSITION = 0x100F

desktop = g.find_window(class_name="Progman")
icons = g.find_window(class_name="SysListView32", parent=desktop.hwnd)
memory = k.VirtualAlloc(0, 4096, 0x08003000, 4).value
assert memory > 0x80000000

count = u.SendMessageA(icons.hwnd, LVM_GETITEMCOUNT, 0, 0).value
names = {}
for index in range(count):
    item = struct.pack("<IiiIIIiiI", 1, index, 0, 0, 0, memory + 256, 200, 0, 0)
    k.RtlMoveMemory(memory, item, len(item))
    u.SendMessageA(icons.hwnd, LVM_GETITEMTEXTA, index, memory)
    name = cstring(k.RtlMoveMemory(Out(200), memory + 256, 200).buffers[0])
    u.SendMessageA(icons.hwnd, LVM_GETITEMPOSITION, index, memory + 512)
    names[name] = struct.unpack("<ii", k.RtlMoveMemory(Out(8), memory + 512, 8).buffers[0])
assert names["My Computer"] == (21, 2)

u.SendMessageA(icons.hwnd, LVM_SETITEMPOSITION, 0, lparam(300, 200))    # move an icon
k.VirtualFree(memory, 0, 0x8000)
```

## GDI drawing

`GetDC(0)` is the whole screen. Drawing on it paints over every window, and it stays until
something repaints. All of these were checked on screen.

### Shapes

```python
RED, BLUE = 0x0000FF, 0xFF0000                      # GDI colours are 0xBBGGRR

screen = u.GetDC(0).value
pen = gdi.CreatePen(0, 3, RED).value
brush = gdi.CreateSolidBrush(BLUE).value
old_pen = gdi.SelectObject(screen, pen).value
old_brush = gdi.SelectObject(screen, brush).value

gdi.Rectangle(screen, 100, 100, 220, 180)
gdi.Ellipse(screen, 240, 100, 360, 180)
gdi.MoveToEx(screen, 380, 100, Out(8))
gdi.LineTo(screen, 500, 180)
gdi.Polygon(screen, struct.pack("<6i", 520, 180, 580, 100, 640, 180), 3)

gdi.SelectObject(screen, old_pen)
gdi.SelectObject(screen, old_brush)
gdi.DeleteObject(pen)
gdi.DeleteObject(brush)
assert gdi.GetPixel(screen, 160, 140).value == BLUE
u.ReleaseDC(0, screen)
```

### Text

`CreateFontA` takes 14 arguments, the most a call can carry.

```python
screen = u.GetDC(0).value
font = gdi.CreateFontA(48, 0, 0, 0, 700, 0, 0, 0, 0, 0, 0, 0, 0, "Times New Roman").value
old = gdi.SelectObject(screen, font).value
gdi.SetBkMode(screen, 1)                            # TRANSPARENT
gdi.SetTextColor(screen, 0x00FFFF)
gdi.TextOutA(screen, 100, 100, "Hello 1998", 10)
u.DrawTextA(screen, "centred", -1, struct.pack("<4i", 0, 200, 800, 300), 0x25)
gdi.SelectObject(screen, old)
gdi.DeleteObject(font)
u.ReleaseDC(0, screen)
```

### Pixels

`SetPixel` and `GetPixel` are one round trip each, so 5 ms a pixel. Colours snap to the 16-bit
display. `GetPixel` off the screen returns `0xFFFFFFFF`.

```python
screen = u.GetDC(0).value
gdi.SetPixel(screen, 10, 10, 0x0000FF)
assert gdi.GetPixel(screen, 10, 10).value == 0x0000FF
gdi.SetPixel(screen, 10, 10, 0x123456)
assert gdi.GetPixel(screen, 10, 10).value == 0x103858
assert gdi.GetPixel(screen, 9000, 10).value == 0xFFFFFFFF
u.ReleaseDC(0, screen)
```

### Fast batches

One `Polyline` call carries hundreds of points in a single round trip.

```python
import math

points = []
for i in range(500):
    angle = i * math.tau / 500
    radius = 120 + 60 * math.sin(angle * 5)
    points += [round(400 + radius * math.cos(angle)), round(300 + radius * math.sin(angle))]

screen = u.GetDC(0).value
gdi.Polyline(screen, struct.pack(f"<{len(points)}i", *points), 500)
u.ReleaseDC(0, screen)
```

### Copy, stretch, invert

`BitBlt` with `SRCCOPY` (`0xCC0020`) copies screen to screen. To invert an area of the screen, use
`PATINVERT` (`0x5A0049`) with a white brush, or copy it onto itself with `NOTSRCCOPY` (`0x330008`).
`DSTINVERT`, `BLACKNESS` and `InvertRect` draw nothing on the screen. See
[Does not work](#does-not-work).

```python
screen = u.GetDC(0).value
gdi.SetPixel(screen, 310, 310, 0x0000FF)
gdi.BitBlt(screen, 500, 300, 100, 100, screen, 300, 300, 0xCC0020)
assert gdi.GetPixel(screen, 510, 310).value == 0x0000FF
gdi.StretchBlt(screen, 620, 300, 100, 100, screen, 300, 300, 50, 50, 0xCC0020)

old = gdi.SelectObject(screen, gdi.GetStockObject(0).value).value      # WHITE_BRUSH
gdi.PatBlt(screen, 500, 300, 100, 100, 0x5A0049)
gdi.SelectObject(screen, old)
assert gdi.GetPixel(screen, 510, 310).value == 0xFFFF00
gdi.BitBlt(screen, 500, 300, 100, 100, screen, 500, 300, 0x330008)
assert gdi.GetPixel(screen, 510, 310).value == 0x0000FF
u.ReleaseDC(0, screen)
```

### Clean up

Drawing on the screen DC stays until something repaints that area. Ask every window to repaint.

```python
screen = u.GetDC(0).value
gdi.Rectangle(screen, 100, 100, 300, 300)
u.ReleaseDC(0, screen)
u.RedrawWindow(0, 0, 0, 0x85)                       # invalidate, erase, all children
g.sync()
```

### Draw inside one window

`GetDC(hwnd)` clips to the client area and uses client coordinates. The window repaints over it
when it next paints.

```python
g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
edit = g.find_window(class_name="Edit", parent=pad.hwnd)
g.sync()
dc = u.GetDC(edit.hwnd).value
old = gdi.SelectObject(dc, gdi.GetStockObject(4).value).value          # BLACK_BRUSH
gdi.Rectangle(dc, 0, 0, 100, 100)
gdi.SelectObject(dc, old)
assert gdi.GetPixel(dc, 50, 50).value == 0
u.ReleaseDC(edit.hwnd, dc)
```

## Menus

### Read a menu

`GetMenu` works on other programs' windows. Separators report id 0. A submenu reports id -1, so
use `signed`.

```python
def walk(menu):
    items = []
    for index in range(u.GetMenuItemCount(menu).signed):
        label = cstring(u.GetMenuStringA(menu, index, Out(80), 80, 0x400).buffers[0])
        submenu = u.GetSubMenu(menu, index).value
        items.append((label, walk(submenu) if submenu else u.GetMenuItemID(menu, index).signed))
    return items


g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
tree = walk(u.GetMenu(pad.hwnd).value)
assert [label for label, _ in tree] == ["&File", "&Edit", "&Search", "&Help"]
assert ("Save &As...", 2) in tree[0][1]
```

### Choose a menu item

Post `WM_COMMAND` with the item's id to the top-level window. Use `PostMessageA`, because the item
may open a modal dialog.

```python
g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
u.PostMessageA(pad.hwnd, WM_COMMAND, 11, 0)         # Help > About
about = g.find_window(title="About Notepad", timeout=3)
u.PostMessageA(about.hwnd, WM_CLOSE, 0, 0)
```

### Open a menu on screen

The menu appears as a window of class `#32768`. `WM_SYSCOMMAND` with `SC_KEYMENU` (`0xF100`) and
the access key does the same without a key press. Close it with Esc, twice.

```python
g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
time.sleep(0.5)
vm.send_keys("alt", "f")
g.find_window(class_name="#32768", timeout=3)
vm.send_keys("esc")
time.sleep(0.2)
vm.send_keys("esc")
time.sleep(0.2)
u.PostMessageA(pad.hwnd, WM_SYSCOMMAND, 0xF100, ord("f"))
g.find_window(class_name="#32768", timeout=3)
```

### Read the system menu

```python
g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
system = u.GetSystemMenu(pad.hwnd, 0).value
ids = [u.GetMenuItemID(system, i).value for i in range(u.GetMenuItemCount(system).value)]
assert ids == [0xF120, 0xF010, 0xF000, 0xF020, 0xF030, 0, 0xF060]
```

### Open the Start menu

Ctrl+Esc works, and so does `SC_TASKLIST` (`0xF130`) posted to the desktop. The menu is a
`BaseBar` window.

```python
vm.send_keys("ctrl", "esc")
assert g.find_window(class_name="BaseBar", timeout=3).rect == (2, 234, 179, 576)
vm.send_keys("esc")
time.sleep(0.3)
desktop = g.find_window(class_name="Progman")
u.PostMessageA(desktop.hwnd, WM_SYSCOMMAND, 0xF130, 0)
g.find_window(class_name="BaseBar", timeout=3)
```

## Dialogs

### Show a message box

`acall` runs it on its own thread. With `call` the request stays open until the box closes, and
the default timeout is 10 s. The button id comes back as the value. Flag 4 is Yes and No, and flag
0 is OK only.

```python
box = g.acall("user32", "MessageBoxA", 0, "Delete everything?", "art98", 4)
dialog = g.find_window(title="art98", class_name="#32770", timeout=3)
labels = [c.title for c in g.windows(dialog.hwnd)]
assert "Delete everything?" in labels and "&Yes" in labels
u.PostMessageA(dialog.hwnd, WM_COMMAND, 6, 0)       # Yes
assert box.wait(5).value == 6
```

### Use a Save As dialog

A common dialog's file name box is an `Edit`, and `IDOK` is 1. The dialog is a modal child of the
program, so send the menu command with `PostMessageA`.

```python
g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
edit = g.find_window(class_name="Edit", parent=pad.hwnd)
u.SendMessageA(edit.hwnd, WM_SETTEXT, 0, "saved by art98")
u.PostMessageA(pad.hwnd, WM_COMMAND, 2, 0)          # File > Save As
dialog = g.find_window(title="Save As", timeout=4)
name = next(c for c in g.windows(dialog.hwnd) if c.class_name == "Edit")
u.SendMessageA(name.hwnd, WM_SETTEXT, 0, r"C:\SAVED.TXT")
u.PostMessageA(dialog.hwnd, WM_COMMAND, 1, 0)
time.sleep(0.6)
assert g.get_file(r"C:\SAVED.TXT") == b"saved by art98"
assert g.find_window(class_name="Notepad").title == "Saved - Notepad"
```

## Clipboard

`GlobalAlloc` with `GMEM_MOVEABLE | GMEM_DDESHARE` (`0x2002`) gets memory the clipboard can own.
Format 1 is plain text.

```python
text = b"copied by art98\0"
memory = k.GlobalAlloc(0x2042, len(text)).value
pointer = k.GlobalLock(memory).value
k.RtlMoveMemory(pointer, text, len(text))
k.GlobalUnlock(memory)
assert u.OpenClipboard(0)
u.EmptyClipboard()
assert u.SetClipboardData(1, memory)
u.CloseClipboard()

u.OpenClipboard(0)
handle = u.GetClipboardData(1).value
pointer = k.GlobalLock(handle).value
read = k.RtlMoveMemory(Out(len(text)), pointer, len(text)).buffers[0]
k.GlobalUnlock(handle)
u.CloseClipboard()
assert read == text
```

## System information

```python
assert [u.GetSystemMetrics(i).value for i in (0, 1)] == [800, 600]  # SM_CXSCREEN, SM_CYSCREEN
assert u.GetSystemMetrics(4).value == 19                            # SM_CYCAPTION
assert cstring(g.advapi32.GetUserNameA(Out(32), struct.pack("<I", 32)).buffers[0]) == "art98"
assert cstring(k.GetComputerNameA(Out(32), struct.pack("<I", 32)).buffers[0]) == "ART98"

version = bytearray(148)
struct.pack_into("<I", version, 0, 148)
major, minor = struct.unpack_from("<II", k.GetVersionExA(version).buffers[0], 4)
assert (major, minor) == (4, 10)

year, month = struct.unpack_from("<HH", k.GetLocalTime(Out(16)).buffers[0])
assert (year, month) == (1998, 6)
```

### Change the clock

The guest clock starts at 09:00 on 25 June 1998 and the taskbar shows it.

```python
now = struct.pack("<8H", 1999, 12, 5, 31, 23, 59, 50, 0)
assert k.SetLocalTime(now)
assert struct.unpack_from("<H", k.GetLocalTime(Out(16)).buffers[0])[0] == 1999
```

### Format a string

`cdecl` functions work too, because the agent restores the stack after each call.

```python
out = u.wsprintfA(Out(64), "%d-%s-%x", 42, "str", 255)
assert cstring(out.buffers[0]) == "42-str-ff"
```

### Load another DLL

`g.dll(name)` reaches any DLL that `LoadLibraryA` can find. To call through a function pointer,
pass it to `CallWindowProcA`, which takes four arguments.

```python
g.dll("comctl32").InitCommonControls()

handle = k.GetModuleHandleA("kernel32").value
address = k.GetProcAddress(handle, "GetTickCount").value
assert u.CallWindowProcA(address, 0, 0, 0, 0).value > 0
```

## Display modes

`set_display_mode` takes a mode the Cirrus driver offers. The change takes 65 to 150 ms and needs
no reboot. The modes are:

| Width x height | Depths |
| --- | --- |
| 640 x 480 | 4, 8, 16, 24 |
| 800 x 600 | 8, 16 |
| 1024 x 768 | 8, 16 |
| 1280 x 1024 | 8 |

```python
g.set_display_mode(1024, 768, 16, persist=False)
assert u.GetSystemMetrics(0).value == 1024
g.set_display_mode(800, 600, 8, persist=False)
screen = u.GetDC(0).value
assert gdi.GetDeviceCaps(screen, 12).value == 8     # BITSPIXEL
u.ReleaseDC(0, screen)
g.set_display_mode(800, 600, 16, persist=False)
```

`persist=True`, the default, writes the mode to the registry. Program exits that restore "the
default mode" then land on that mode. 3D Maze does this, see [screensavers](#screensavers).

List the modes yourself with `EnumDisplaySettingsA`. A `DEVMODE` is 156 bytes, its `dmSize` field
is at 36, and depth, width and height are at 104.

```python
modes, index = [], 0
while True:
    mode = bytearray(156)
    struct.pack_into("<H", mode, 36, 156)
    found = u.EnumDisplaySettingsA(0, index, mode)
    if not found:
        break
    depth, width, height = struct.unpack_from("<III", found.buffers[0], 104)
    modes.append((width, height, depth))
    index += 1
assert len(modes) == 9 and (1280, 1024, 8) in modes
```

Screen captures follow the mode. A video keeps the size of its first frame, so ffmpeg scales later
frames to fit.

## Screensavers

A screensaver is a program. Run it with `/s`. All of them live in `C:\WINDOWS\SYSTEM`, except
`C:\WINDOWS\Channel Screen Saver.SCR`. Names have spaces, so quote them. The window has class
`WindowsScreenSaverClass`, and the agent keeps answering while one runs. The full list is in the
[App catalog](app-catalog.md#screensavers).

```python
g.spawn(r'"C:\WINDOWS\SYSTEM\Mystify Your Mind.scr" /s')
saver = g.find_window(class_name="WindowsScreenSaverClass", timeout=4)
assert saver.rect == (0, 0, 800, 600)
assert g.ping(timeout=2)

u.SetCursorPos(100, 100)
u.mouse_event(MOUSEEVENTF_MOVE, 20, 20, 0, 0)       # any mouse move ends it
time.sleep(0.3)
u.mouse_event(MOUSEEVENTF_MOVE, 20, 20, 0, 0)
time.sleep(0.6)
assert not u.IsWindow(saver.hwnd)
```

Keep it recording with `FrameRecorder.live`, because a screensaver moves by itself and `sync` does
not wait for it. See [`FrameRecorder`](bridge.md#framerecorder).

`/c` opens the settings dialog, and `/p <hwnd>` previews inside a window of yours.

```python
g.spawn(r'"C:\WINDOWS\SYSTEM\Mystify Your Mind.scr" /c')
g.find_window(title="Options to Mystify Your Mind", class_name="#32770", timeout=4)
```

```python
g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
edit = g.find_window(class_name="Edit", parent=pad.hwnd)
g.spawn(rf'"C:\WINDOWS\SYSTEM\Mystify Your Mind.scr" /p {edit.hwnd}')
g.find_window(class_name="WindowsScreenSaverClass", parent=edit.hwnd, timeout=4)
```

To start the configured saver the way Windows does, name it in `SYSTEM.INI`, using its short file
name, and turn saving on. Then `SC_SCREENSAVE` (`0xF140`) starts it.

```python
short = cstring(k.GetShortPathNameA(r"C:\WINDOWS\SYSTEM\Mystify Your Mind.scr",
                                    Out(128), 128).buffers[0])
k.WritePrivateProfileStringA("boot", "SCRNSAVE.EXE", short, "SYSTEM.INI")
u.SystemParametersInfoA(17, 1, 0, 0)                # SPI_SETSCREENSAVEACTIVE

g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
u.PostMessageA(pad.hwnd, WM_SYSCOMMAND, 0xF140, 0)
g.find_window(class_name="WindowsScreenSaverClass", timeout=4)
```

3D Maze switches the display to 640 x 480 while it runs. It goes back to the registry's mode when
it exits, not to the mode you set with `persist=False`.

```python
g.spawn(r'"C:\WINDOWS\SYSTEM\3D Maze.scr" /s')
time.sleep(2)
assert u.GetSystemMetrics(0).value == 640
u.SetCursorPos(100, 100)
u.mouse_event(MOUSEEVENTF_MOVE, 20, 20, 0, 0)
time.sleep(0.2)
u.mouse_event(MOUSEEVENTF_MOVE, 20, 20, 0, 0)
time.sleep(1)
assert u.GetSystemMetrics(0).value == 800
```

## Video

`winmm` plays AVI files through MCI. `mciSendStringA` takes one text command and returns 0 on
success. The Cirrus display shows an uncompressed clip at its own frame rate. The image carries no
video files, so copy one in. This builder writes the smallest AVI that Windows accepts.

```python
def avi(frames, width, height, fps):
    """Uncompressed 24-bit video from raw bottom-up BGR frames."""
    def chunk(tag, data):
        return tag + struct.pack("<I", len(data)) + data + b"\0" * (len(data) & 1)

    def group(kind, data):
        return b"LIST" + struct.pack("<I", len(data) + 4) + kind + data

    size = width * height * 3
    avih = struct.pack("<14I", 1000000 // fps, size * fps, 0, 0x10, len(frames), 0, 1,
                       size, width, height, 0, 0, 0, 0)
    strh = b"vidsDIB " + struct.pack("<IHHIIIIIIII", 0, 0, 0, 0, 1, fps, 0, len(frames),
                                     size, 0xFFFFFFFF, 0) + struct.pack("<4H", 0, 0, width, height)
    strf = struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0, size, 0, 0, 0, 0)
    head = group(b"hdrl", chunk(b"avih", avih)
                 + group(b"strl", chunk(b"strh", strh) + chunk(b"strf", strf)))
    index, offset = b"", 4
    for frame in frames:
        index += b"00db" + struct.pack("<III", 0x10, offset, len(frame))
        offset += 8 + len(frame)
    body = (b"AVI " + head + group(b"movi", b"".join(chunk(b"00db", f) for f in frames))
            + chunk(b"idx1", index))
    return b"RIFF" + struct.pack("<I", len(body)) + body


def mci(command):
    result = g.winmm.mciSendStringA(command, Out(128), 128, 0)
    assert result.value == 0, command
    return cstring(result.buffers[0])


frames = [bytes((i * 6, 255 - i * 6, 128)) * (64 * 48) for i in range(40)]
g.put_file(r"C:\CLIP.AVI", avi(frames, 64, 48, 10))

mci(r"open C:\CLIP.AVI type avivideo alias clip")
assert mci("status clip length") == "40"
mci("window clip state show")
mci("play clip")
time.sleep(1.5)
assert 5 < int(mci("status clip position")) < 40
assert g.find_window(class_name="AVIWnd").title == "CLIP.AVI"
mci("close clip")
```

Windows Media Player plays the same file. It takes about 2 s to open it first. With `/close` it
exits when the clip ends.

```python
g.put_file(r"C:\CLIP.AVI", avi(frames, 64, 48, 10))
g.spawn(r'"C:\Program Files\Windows Media Player\MPLAYER2.EXE" /play /close C:\CLIP.AVI')
player = g.find_window(class_name="Media Player 2", timeout=6)
while u.IsWindow(player.hwnd):
    time.sleep(0.2)
```

Audio is deferred, so this page covers picture only.

## Games

### Read Minesweeper's mines

Windows' own cheat: type `xyzzy`, press Shift, and Minesweeper paints the screen's top left pixel
as the pointer moves. Black is a mine, white is safe. Progman would clip that pixel, so hide it
for the scan. The whole board takes under a second.

Typing and Shift have to be real keys, so this needs `vm.send_keys`.

```python
g.spawn(r"C:\WINDOWS\WINMINE.EXE")
game = g.find_window(class_name="Minesweeper")
u.SetForegroundWindow(game.hwnd)
time.sleep(0.3)
for letter in "xyzzy":
    vm.send_keys(letter)
    time.sleep(0.15)
vm.send_keys("shift")
time.sleep(0.2)

left, top = client_origin(game.hwnd)
desktop = g.find_window(class_name="Progman")
u.ShowWindow(desktop.hwnd, 0)
g.sync()
screen = u.GetDC(0).value
mines = set()
for row in range(8):
    for column in range(8):
        u.SetCursorPos(left + 20 + column * 16, top + 63 + row * 16)
        g.sync()
        if gdi.GetPixel(screen, 0, 0).value & 0xFFFFFF == 0:
            mines.add((column, row))
u.ReleaseDC(0, screen)
u.ShowWindow(desktop.hwnd, 8)                       # SW_SHOWNA
assert len(mines) == 10

for row in range(8):
    for column in range(8):
        if (column, row) not in mines:
            spot = lparam(20 + column * 16, 63 + row * 16)
            u.PostMessageA(game.hwnd, WM_LBUTTONDOWN, 1, spot)
            u.PostMessageA(game.hwnd, WM_LBUTTONUP, 0, spot)
g.find_window(title="Congratulations", timeout=3)
```

The first game has a beginner board of 8 x 8 cells with 10 mines. The cell at column `c`, row `r`
has its centre at client (`20 + 16c`, `63 + 16r`). See
[Minesweeper](app-catalog.md#minesweeper) for the other sizes.

### Deal Solitaire by mouse

Solitaire needs a real click. This one turns over the stock.

```python
g.spawn(r"C:\WINDOWS\SOL.EXE")
game = g.find_window(class_name="Solitaire")
left, top = client_origin(game.hwnd)
time.sleep(0.5)
dc = u.GetDC(game.hwnd).value
assert gdi.GetPixel(dc, 130, 50).value == 0x008000          # table, no card yet
u.SetCursorPos(left + 40, top + 50)
u.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
u.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
g.sync()
assert gdi.GetPixel(dc, 130, 50).value != 0x008000         # the card to its right
u.ReleaseDC(game.hwnd, dc)
```

## Crashes

A proxied call is free to crash. The agent reports it with `! CRASH`, restarts itself and says
`! HELLO`. The whole round trip takes about 0.3 s. Windows and programs carry on.

### Survive a crash

`GuestCrashed` is raised on the open request. Wait for the new agent, then carry on.

```python
from art98 import GuestCrashed

g.clear_events()
try:
    u.CallWindowProcA(0x70000000, 0, 0, 0, 0)       # jumps to unmapped memory
except GuestCrashed as error:
    assert "0xc0000005" in str(error)
g.wait_event("HELLO", timeout=3)
g.wait_ready(5)
assert g.ping() > 0
```

### Crash without an open request

An `acall` has no open request once it returns, so read the `CRASH` event instead. Its `wait` only
times out.

```python
from art98 import BridgeTimeout

g.clear_events()
call = g.acall("user32", "CallWindowProcA", 0x70000000, 0, 0, 0, 0)
code, address = g.wait_event("CRASH", timeout=3)
assert code == 0xC0000005
g.wait_event("HELLO", timeout=3)
try:
    call.wait(0.2)
except BridgeTimeout:
    pass
```

### Crash on purpose, with your own code

`RaiseException` works as a clean test. The value shows up in the error.

```python
from art98 import GuestCrashed

try:
    k.RaiseException(0xE0001234, 0, 0, 0)
except GuestCrashed as error:
    assert "0xe0001234" in str(error)
g.wait_ready(5)
```

### Recover a hung agent

`SendMessageA` to a window that shows a modal dialog blocks the agent until the dialog closes. A
real key press can still close it, because QEMU does not need the agent.

```python
from art98 import BridgeTimeout

g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
u.SetForegroundWindow(pad.hwnd)
try:
    u.SendMessageA(pad.hwnd, WM_COMMAND, 11, 0, timeout=1)  # About opens, agent blocks
except BridgeTimeout:
    pass
vm.send_keys("ret")                                         # OK
time.sleep(0.5)
g.wait_ready(5)
```

### Start the agent again

`QUIT` ends the agent and nothing restarts it. Type its path into the Run box with real keys.

```python
g.request("QUIT")
time.sleep(0.3)

vm.send_keys("meta_l", "r")
time.sleep(0.5)
for key in (["c"], ["shift", "semicolon"], ["backslash"], ["a"], ["r"], ["t"], ["9"], ["8"],
            ["backslash"], ["a"], ["g"], ["e"], ["n"], ["t"], ["dot"], ["e"], ["x"], ["e"],
            ["ret"]):
    vm.send_keys(*key)
    time.sleep(0.2)
g.wait_ready(10)
```

## Reboot and snapshots

### Reboot

QEMU runs with `-no-reboot`, so a guest reboot ends the VM. `EWX_REBOOT` is 2 and `EWX_FORCE` is 4.
Use `acall`, because the agent dies with Windows. QEMU exits within a second.

```python
g.acall("user32", "ExitWindowsEx", 2 | 4, 0)
assert vm.wait_exit(10)
```

Without `EWX_FORCE`, a program with unsaved work can stop the reboot with its save prompt.

```python
g.spawn("notepad.exe")
pad = g.find_window(class_name="Notepad")
edit = g.find_window(class_name="Edit", parent=pad.hwnd)
u.PostMessageA(edit.hwnd, WM_CHAR, ord("x"), 0)
g.sync(pad.hwnd)
g.acall("user32", "ExitWindowsEx", 2, 0)
assert not vm.wait_exit(4)
g.find_window(class_name="#32770", timeout=3)
```

### Shut down

`EWX_SHUTDOWN` (1) leaves a black screen and QEMU keeps running. Close the VM from the host.

```python
g.acall("user32", "ExitWindowsEx", 1, 0)
assert not vm.wait_exit(5)
vm.close()
```

### Save and restore a moment

A snapshot saves all guest state. Saving takes under 2 s and loading under 0.1 s. The bridge stays
connected through both.

```python
vm.save_snapshot("mine")
g.spawn("notepad.exe")
g.find_window(class_name="Notepad")
vm.load_snapshot("mine")
assert g.ping(timeout=2) > 0
assert not any(w.class_name == "Notepad" for w in g.windows())
vm.qmp.human_silent("delvm mine")
```

### Freeze the guest

While paused the agent cannot answer, but screenshots still work.

```python
from art98 import BridgeTimeout

vm.pause()
vm.screenshot(stage / "frozen.png")
try:
    g.ping(timeout=0.3)
except BridgeTimeout:
    pass
vm.resume()
assert g.ping(timeout=2) > 0
```

## Does not work

Each of these was tried on the real image. They fail for the reason given.

| Tried | Result | Reason or way round |
| --- | --- | --- |
| `SetWindowTextA` on another program's Edit | Returns 1, text unchanged | Windows 9x updates the window's own title only. Use `WM_SETTEXT`. |
| `SetWindowLongA` on another program's window, such as to remove a title bar | Returns 0, style unchanged | It works only on the agent's own windows. `SetWindowPos` still sets topmost. |
| `SendMessageA` with a private struct pointer, such as `LVM_GETITEMPOSITION` with an `Out` | Timed out, agent stayed hung | The target gets a pointer into the wrong process. Use [shared memory](#pass-a-struct-to-another-process). |
| `SendMessageA` that opens a modal dialog | `BridgeTimeout`, agent blocked until the dialog closes | Use `PostMessageA`. |
| `WM_CHAR` or `keybd_event` to a DOS box | No effect | DOS boxes read the virtual keyboard. Use `vm.send_keys`. |
| Alt+Enter in a DOS box, via `vm.send_keys` | The window stayed a window | No way found. |
| `InvertRect`, or `PatBlt` and `BitBlt` with `DSTINVERT` or `BLACKNESS`, on the screen or a window DC | Returns 1, nothing drawn | They work on a memory DC. `WHITENESS`, `PATCOPY`, `PATINVERT` and `NOTSRCCOPY` work on the screen. Use those, or `Rectangle` with a black brush. |
| `BM_CLICK` posted to the Start button | No menu | Use Ctrl+Esc or `SC_TASKLIST`. |
| Alt+Shift+2 Solitaire cheat | No effect | |
| `WM_TIMER` with a bad callback pointer, posted to Notepad | No crash, no fault dialog | Not a way to make a program crash on screen. |
| `GetProcAddress` by ordinal, such as `shell32` 61 | Returns 0, error 6 | Not available for that DLL. |
| `GetFocus` from the agent without `AttachThreadInput` | Returns 0 | Focus belongs to the input queue of the other thread. |
| `UserPreferencesMask` to turn off menu animations | Ignored | The name on Windows 98 is `UserPreferencemask`. See the note below. |

`wsprintfA`, `RtlMoveMemory` and `RtlFillMemory` with a bad pointer do not crash the agent, because
Windows guards them. To crash on purpose, use `RaiseException` or
[`CallWindowProcA`](#crash-without-an-open-request).

On the prepared image, menu animation, combo box animation, list box smooth scrolling and gradient
captions are all on. Prep sets `UserPreferencesMask` to zero, but Windows 98 reads
`UserPreferencemask`, so that setting has no effect.
