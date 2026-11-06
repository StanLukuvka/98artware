# 98artware — Windows 98 as Animation/Performance Platform

> "Manim for Windows 98" — a repeatable instruction set that treats
> the Win98 desktop as a puppet stage, using the OS itself as medium.

> **Status, 2026-11-06.** The preparation tool and the bridge now exist; see
> `README.md`. Building them changed four things in this plan, and the sections
> below are kept as the original thinking:
>
> - **Transport is COM1, not a shared folder.** VirtualBox's Guest Additions do
>   not cover Windows 98 and QEMU has no shared folder driver for it, so §3.5,
>   §3.8 step 6 and §3.10's recommendation do not hold.
> - **The guest executor is a small C agent, not VBScript.** VBScript cannot call
>   Win32, and the agent is a generic call proxy, so every primitive in §1.1 is
>   reachable from Python without recompiling the guest. The `.act98` format in
>   §4.1 and the instruction list in §4.2 are replaced by this.
> - **QEMU under software emulation, not KVM or VirtualBox.** It sidesteps the
>   Windows 9x TLB and fast-CPU bugs, and allows frame stepping (see below).
> - **All timing lives on the host.** The agent has no WAIT or TYPE speed. Frames
>   are captured when the script asks, which is what makes this Manim-like: the
>   video does not depend on host speed.
>
> §3 entries that do not apply to Windows 98 on FAT32 were dropped rather than
> implemented: System Restore (§3.3), last access times and 8.3 names (§3.6).

---

## 1. CREATIVE POSSIBILITIES CATALOG

### 1.1 PRIMITIVES — What Can Be Manipulated

| Primitive | Win32 Mechanism | Theatrical Meaning |
|-----------|----------------|-------------------|
| Window position | `SetWindowPos` | Character blocking, entrance/exit |
| Window size | `SetWindowPos` | Emotional state (expanding = confidence, shrinking = fear) |
| Window Z-order | `SetWindowPos(HWND_TOP/BOTTOM)` | Depth of field, focus pull |
| Window visibility | `ShowWindow(SW_HIDE/SW_SHOW)` | Character appears/vanishes |
| Window shake | `SetWindowPos` loop with offsets | Character trembling, earthquake |
| Window flash | `FlashWindow` / `FlashWindowEx` | Urgency, alarm, character demanding attention |
| Window title | `SetWindowText` | Character name change, revelation |
| Window region | `SetWindowRgn` | Non-rectangular "bodies", transparency holes |
| Window style | `SetWindowLong(GWL_STYLE)` | Remove title bar = vulnerable, add border = armored |
| Mouse position | `SetCursorPos` | Cursor as narrator/protagonist |
| Mouse click | `SendInput` / `mouse_event` | Interaction, choice, violence |
| Keyboard input | `keybd_event` / `SendInput` | Ghost typer, possession, dialogue |
| Dialog spawn | `MessageBox` / `MessageBoxIndirect` | Speech, emotional expression |
| Dialog auto-dismiss | Timer + `EndDialog` | Rapid-fire dialogue, stutter |
| File create/rename/delete | `CreateFile` / `MoveFile` / `DeleteFile` | Object permanence, death, transformation |
| File with Explorer dialog | `SHFileOperation` | Scene transition (paper-flying animation) |
| Desktop wallpaper | `SystemParametersInfo(SPI_SETDESKWALLPAPER)` | Environment/mood shift |
| Active Desktop HTML | `IActiveDesktop` | Dynamic environment, interactive stage floor |
| System sounds | `PlaySound` / `sndPlaySound` | Score, punctuation, audio character voices |
| Taskbar state | `SHAppBarMessage` | Stage floor rearrangement |
| System tray icons | `Shell_NotifyIcon` | Background characters, status indicators |
| Block all input | `BlockInput` | Frozen moment, dramatic pause |
| Screen DC drawing | `GetDC(0)` + GDI | Direct graffiti on screen surface |
| DOS layer | `ShellExecute("command.com")` | Descent into lower reality |
| Controlled crash | `CreateRemoteThread` to bad address | GPF as character death, system as unreliable narrator |
| ScanDisk trigger | Dirty FAT, improper shutdown | Intermission, "previously on..." recap |
| "Safe to turn off" screen | `ExitWindowsEx` + custom driver | Closing credits, final monologue |
| Registry owner name | `RegSetValue(HKLM\...\RegisteredOwner)` | Identity shift, possession |
| Color scheme | `SetSysColors` | Entire emotional palette shift |
| Screen saver | `SystemParametersInfo(SPI_SETSCREENSAVEACTIVE)` | Time skip, dissociation |
| Resolution/color depth | `ChangeDisplaySettings` | Format shift, reality degradation |

### 1.2 COMPOSITES — Combinations That Tell Stories

**The Confession**
- Notepad appears, types "i need to tell you something", pauses 3 seconds,
  types "never mind", closes, Recycle Bin eats the saved file.

**The Argument**
- Two Explorer windows face each other. They resize aggressively,
  flash their title bars, rename files back and forth.
  A `vbCritical` dialog interrupts. Both windows minimize. Silence.

**The Descent**
- Command prompt opens. `color 0a`. Text types "going deeper."
  Shells out to DOS mode. Mode 13h color bars. Returns.
  Desktop wallpaper now black. Icons slowly rearrange into a spiral.

**The Identity Crisis**
- `RegisteredOwner` changes from "User" to "???" mid-scene.
  System Properties dialog opens, shows the change, closes.
  Start Menu user name flickers between identities.

**The Time Loop**
- Same dialog appears, same window moves, same file created.
  Exactly repeated 4 times. On the 5th, one detail changes.
  Character notices. Panics.

### 1.3 GENRES

**Desktop Horror** — haunted OS, files appear/disappear, GPF as jump scare,
shutdown countdown as dread clock, the system lies about what's happening.

**Desktop Poetry** — Notepad as typewriter, Explorer as visual stanza,
Recycle Bin as metaphor, system sounds as punctuation,
"safe to turn off" screen as final couplet.

**Desktop Soap Opera** — recurring window "characters" with ongoing
relationships across episodes, file exchanges as plot devices,
dialog boxes as emotional confrontations.

**Desktop Documentary** — reconstruct events through file timestamps,
folder structures, IM chat logs rendered in mIRC or AIM,
fake web pages in IE5.

**Desktop Music Visualizer** — windows dance to beat, taskbar pulses,
system sounds as instruments, Media Player visualizer.exe as backdrop,
the entire desktop IS the music video.

**Desktop Game** — interactive experiences where the viewer clicks things,
drag-and-drop as game mechanic, folders as rooms,
files as inventory items, dialogs as branching narrative choices.

---

## 2. SOURCES OF INSPIRATION

### 2.1 WIN98 MALWARE REPOS (harmless/visual/prank category)

| Source | What To Extract |
|--------|----------------|
| **danooct1 YouTube archive** | Best-curated collection of visual Win98-era malware. Window shakers, cursor teleporters, desktop flooders, fake dialogs, icon rearrangers. Every episode is a technique catalog. |
| **VX Heaven** (archived) | Massive malware source code collection. Win98 section has pure Win32 C with no obfuscation — readable, educational, perfect primitives. |
| **Endoftheinternet.com prank apps** | "Ghost Mouse", "Desktop Destroyer", "Fake Error Message" — VB6 source often included. VB6 is trivial to port to Python + ctypes. |
| **r/badcode / r/malware** | Modern discussions with dissections of classic techniques. The `SendMessage(WM_SYSCOMMAND, SC_MOVE)` trick for programmatic drag came from here. |
| **"Windows Trolling" compilations** | The YouTube genre. Documented techniques: rapid wallpaper changes, cursor inversion, Start button relocation, taskbar hiding. |

### 2.2 DEMOSCENE (1998-2002)

| Source | What To Extract |
|--------|----------------|
| **Hugi / scene.org archives** | Mode 13h tutorials. "Dirty rectangles" technique for partial screen updates. How to draw on the desktop without flicker. |
| **fr-08: .the .product by farbrausch** | 64k intro that runs on Win98. Texture generation, software 3D, realtime music — all the techniques that could animate the desktop surface. |
| **Moleman 2 documentary** | Historical context, technique explanations, interviews with the people who pushed Win98 graphics to their limits. |
| **Flipcode / GameDev.net archives** | GDI tricks, BitBlt optimization, double-buffering on the desktop DC. Old forum posts with exact code. |
| **Demo effects ported to Python** | Plasma, fire, rotozoom, starfield — all doable on `GetDC(0)`. Each one is an environmental effect for a scene. |

### 2.3 SHELL REPLACEMENT SCENE

| Source | What To Extract |
|--------|----------------|
| **Litestep** | Reference implementation of "I am the shell now." How to replace explorer.exe, manage the desktop window, handle system tray, taskbar, and icon grid. Open source, well-documented. |
| **bbLean / Blackbox for Windows** | Lighter shell replacement. Plugin architecture. How to hook window creation, manage virtual desktops, theme everything. |
| **Aston Shell** | Commercial but the trial was widely cracked. Skinning engine that could make Win98 look like anything. Techniques for per-window styling. |
| **Talisman** | Another shell replacement. Had a "theater mode" concept — pre-arranged desktop layouts that transition with effects. Close to what we're building. |

### 2.4 NET.ART / EARLY DIGITAL ART

| Source | What To Extract |
|--------|----------------|
| **JODI (jodi.org)** | Artists who treated the OS and browser as medium. `wwwwwwwww.jodi.org` — glitch as grammar. Their work proves the OS IS the artwork, not just a container. |
| **Olia Lialina — "My Boyfriend Came Back From The War"** | Net.art classic using HTML frames as cinematic language. Browser windows as scenes. Directly applicable to Explorer windows as frames. |
| **Alexei Shulgin — "Form Art"** | HTML form elements as visual composition. Active Desktop can do this natively. |
| **Heath Bunting — "_readme.html"** | Early hypertext art. File/folder structures as narrative. The OS file system as choose-your-own-adventure. |
| **Rhizome / Net Art Anthology** | Comprehensive documentation of this era. Theory, technique, specific works. |

### 2.5 UI AESTHETIC REFERENCES

| Source | What To Extract |
|--------|----------------|
| **Guidebookgallery.org** | Screenshot archives of every Windows version. Design language reference. What did "warning" vs "information" vs "question" look like on 98? |
| **Toasty Tech GUI Gallery** | Obsessive documentation of OS GUIs. Version differences, exact color values, font metrics. |
| **Win98 Simulator (online)** | Multiple faithful web recreations. Useful for prototyping scenes before running them on a real VM. |
| **r/Windows98 / r/vintagecomputing** | Active communities. Screenshot references, "how did X work," period-accurate configurations. |
| **"Make It Old" CSS framework** | CSS recreation of Win98 widgets. Useful for storyboarding/prototyping. |

### 2.6 TUTORIAL HELL AESTHETIC

| Source | What To Extract |
|--------|----------------|
| **"How to hack" text files from 1998** | ASCII art, green-on-black, the visual language of "elite" — useful for DOS segments. |
| **Keygen music / chiptune scene** | The soundtrack of Win98. Keygen music players (keygen.exe with embedded chiptune) are well-documented. Can extract/recreate the aesthetic. |
| **AOL warez room logs** | Visual language of early internet communication. AIM/mIRC aesthetics for character dialogue. |
| **Y2K aesthetic / Frutiger Aero precursor** | The transitional design language. Corporate training CD-ROMs. Encarta visual style. |

### 2.7 TECHNICAL REFERENCES (Win98-specific)

| Source | What To Extract |
|--------|----------------|
| **Petzold — "Programming Windows" (5th ed)** | THE Win32 API bible. Win98-era edition covers everything: GDI, controls, message loop, resources. All APIs that work on 98. |
| **MSDN Library CD (October 1998)** | Period-accurate documentation. APIs marked "NT only" are clearly identified. What Win98 can and can't do. |
| **Undocumented Windows 95/98** (Schulman) | The APIs that exist but aren't documented. `MessageBoxIndirect`, `SetWindowRgn` quirks, shell hooks, system-wide message hooks. |
| **win32.hLP / winprog.org** | Win32 API tutorials still online. Working code samples tested on Win98. |
| **ReactOS source code** | Open-source Win32 compatible OS. See how things were IMPLEMENTED — the actual behavior of `MessageBox`, `ShellExecute`, explorer.exe. |

### 2.8 TOOLS & UTILITIES REFERENCE

| Source | What To Extract |
|--------|----------------|
| **AutoIt v2** | Scripting language for Windows automation. Syntax and capability reference for our instruction set. What primitives did AutoIt expose? |
| **WinBatch** | Predecessor to AutoIt. Commercial macro language. Their API surface is a good reference for "what do people actually need to automate." |
| **NirSoft utilities** | Tiny focused Win32 tools by Nir Sofer. Each one does one thing perfectly. Our tool primitives should feel like NirSoft tools — single-purpose, callable from Python. |
| **Sysinternals (pre-Microsoft)** | Process Explorer, RegMon, FileMon. Russinovich's style of exposing OS internals. Our bridge layer should match this level of access. |
| **Macro Express** | Keyboard/mouse macro tool for Win98. Their event model (triggers, timing, conditions) is a reference for our choreography engine. |

---

## 3. VM DETERMINISM PLAN

> Goal: Win98 VM that boots into a KNOWN STATE and stays PREDICTABLE
> across repeated runs. No surprises. No random popups. No "found new
> hardware" wizard. The OS is our instrument, and instruments don't
> randomly go out of tune.

### 3.1 GOLDEN IMAGE PREPARATION

- Install Windows 98 SE (Second Edition — more stable, better USB)
- Install all drivers for the VM platform (VirtualBox/QEMU)
- Pin resolution to 800x600 @ 16-bit color (period-correct, reliable)
- Disable ALL visual effects (animated windows, menu animations, etc.)

### 3.2 STARTUP STERILIZATION

- **msconfig → Startup tab → disable EVERYTHING**
  - No Office toolbar, no RealPlayer agent, no QuickTime task
  - No Windows Update scheduler
  - No anything that spawns based on time or idle detection
- **msconfig → win.ini / system.ini → review for auto-started cruft**
- **Remove from Startup folder**: `C:\Windows\Start Menu\Programs\StartUp\`
  - Should be empty after this
- **Registry Run keys cleaned**:
  - `HKLM\Software\Microsoft\Windows\CurrentVersion\Run`
  - `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`
  - `RunOnce`, `RunServices`, `RunOnceEx` — all emptied

### 3.3 SERVICE/PROCESS MINIMIZATION

Target: boot to ~12 processes (System, Kernel, Explorer, Systray, and nothing else)

- **Disable scheduled tasks**: Task Scheduler service → disabled
- **Disable Windows Scripting Host if not needed** (or keep — VBScript is our friend)
- **Disable System Restore** (Win98's version of it — less overhead)
- **Kill unnecessary services in win.ini**:
  - `load=` — empty
  - `run=` — empty
- **Disable FindFast** (Office indexing service that loves to wake up)

### 3.4 INPUT/OUTPUT LOCKDOWN

- **Screen saver**: DISABLED. No "it's been 10 minutes let me play 3D Pipes."
- **Power management**: ALL OFF. No monitor sleep, no hard disk spin-down, no system standby.
- **USB plug-and-play**: Minimize. Pre-install all VM virtual devices so no "new hardware found" wizard.
- **Auto-insert notification**: Disabled for CD-ROM. No "what do you want to do with this disk?"
- **Error reporting**: Disabled. Win98's minimal version of this.
- **System sounds scheme**: Set to "No Sounds" (we control audio through our API).

### 3.5 NETWORK ISOLATION

- **No network adapter** OR **host-only adapter**(so host can push scripts via SMB/shared folder)
  - If host-only: disable DHCP client (static IP). No DNS resolution delays.
  - Disable "Network Neighborhood" auto-discovery.
- **No dial-up connection configured**. No "do you want to connect?"
- **No Windows Update** (service killed, no internet route)

### 3.6 FILESYSTEM STABILITY

- **Disable "Last Access" timestamps** (NTFS thing, FAT32 doesn't really do this anyway)
- **Disable 8.3 name creation** (less directory noise)
- **Pre-allocate space for temp files** (scripts write to known location)
- **Disable Recycle Bin confirmation dialogs**
- **Disable "low disk space" warnings** (small VM disk triggers this)

### 3.7 DESKTOP STATE

- **Clean desktop**: No icons except Recycle Bin (or My Computer + Recycle Bin)
- **Auto-arrange**: OFF (we control icon positions)
- **Align to grid**: ON (predictable snapping)
- **Wallpaper**: `(None)` — flat teal background (the 98 default)
- **Active Desktop**: Disabled by default, enabled via script when needed
- **Taskbar**: 
  - Always on top: YES
  - Auto-hide: NO
  - Show clock: YES (clock is a character)
  - Group similar taskbar buttons: OFF (Win98 doesn't have this, even better)

### 3.8 THE INIT SCRIPT (`init98.bat` + `init98.reg`)

On every VM boot (or snapshot restore), a single script runs that:

1. **Kills all non-essential processes** (by name — we know exactly what should be running)
2. **Applies registry tweaks** for determinism (color scheme, font sizes, window metrics)
3. **Clears temp directories** (`C:\Windows\Temp\`, `C:\Temp\`)
4. **Sets system time** to a known epoch (scripts can then use relative timing)
5. **Verifies desktop state** (icon count, wallpaper, taskbar config)
6. **Mounts shared folder** from host (`net use X: \\host\share`)
7. **Starts the listener** — our VBScript watcher that polls for new `.act98` files
8. **Writes "READY" semaphore file** to shared folder so host knows VM is ready

### 3.9 SNAPSHOT STRATEGY

- **SNAPSHOT 0**: Clean install + drivers + resolution set
- **SNAPSHOT 1**: Post-init — all sterilization applied, init script verified
- **SNAPSHOT 2**: Post-first-performance — a "reset to ready" snapshot fresh from init

After each performance: **revert to Snapshot 2**. The OS does not accumulate state
between runs. Every performance starts from an identical 6,000-millisecond-old
Windows 98 desktop.

### 3.10 COMMUNICATION CHANNEL: Host → VM

Options ranked by reliability on Win98:

1. **Shared folder + file polling** (most reliable)
   - Host writes `scene_001.act98` to shared folder
   - Guest VBScript polls folder every 100ms
   - Guest executes script, writes `scene_001.done` on completion
   - Host polls for `.done` files, blocks until scene complete
   - WORKS on any Win98, no networking, no DCOM, no complexity

2. **VM serial port** (middle ground, more setup)
   - Host connects to VM serial port via pipe/socket
   - Guest runs a COM port listener
   - Commands stream as lines of text
   - Responses stream back
   - Requires serial port configured in VM settings

3. **Network socket** (if using host-only networking)
   - Guest runs a minimal Winsock listener
   - Host sends commands via TCP
   - More complex setup, but more responsive

**Recommendation for V1: shared folder polling.** Dead simple, zero dependencies,
works on a fresh Win98 SE install with just the VM additions installed.

---

## 4. ARCHITECTURE SKETCH (V1)

```
┌─────────────────────────────────────────────────────────┐
│                    HOST (Python)                         │
│                                                          │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐ │
│  │  Instruction  │   │  Choreography │   │  VM Bridge    │ │
│  │  Set (DSL)    │──▶│  Engine       │──▶│  (write .act98 │ │
│  │               │   │  (timing,     │   │  files, poll  │ │
│  │  scene {       │   │   state,      │   │  for .done)   │ │
│  │    dialog(...) │   │   events)     │   │               │ │
│  │    window(...) │   │               │   │               │ │
│  │  }             │   │               │   │               │ │
│  └──────────────┘   └──────────────┘   └───────┬───────┘ │
│                                                 │          │
└─────────────────────────────────────────────────┼──────────┘
                                                  │ shared folder
┌─────────────────────────────────────────────────┼──────────┐
│                    GUEST (Win98)                │          │
│                                                  │          │
│  ┌──────────────────────────────────────────────▼────────┐ │
│  │              watcher.vbs (polling loop)                │ │
│  │  "oh a new .act98 file! let me run it..."             │ │
│  └───────────────────────┬───────────────────────────────┘ │
│                          │ executes                         │
│  ┌───────────────────────▼───────────────────────────────┐ │
│  │              instruction executor                      │ │
│  │  VBScript wrapping Win32 API + WMI + Shell.Application │ │
│  │  does the thing, writes .done file when finished       │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
│  [Optional] VBScript can also call our custom .dll or .exe   │
│  compiled from C that does the spicy stuff (Region, GDI,    │
│  SendInput, BlockInput, etc.)                               │
└─────────────────────────────────────────────────────────────┘
```

### 4.1 THE INSTRUCTION FORMAT (.act98 files)

Simple, VBScript-friendly. Either:

**INI-like** (easy to parse in VBScript with standard `ReadIni` function):
```ini
[scene:confession]
action=spawn
program=notepad.exe
window_title=untitled - notepad
wait=500

[scene:confession]
action=type
window_title=untitled - notepad
text=i have something to tell you
speed=80
```

**or line-based DSL** (simpler to stream):
```
OPEN notepad.exe "untitled - notepad"
WAIT 500
TYPE "untitled - notepad" "i have something to tell you" /speed=80
WAIT 3000
CLOSE "untitled - notepad"
DONE
```

**Recommendation: line-based.** Easier to generate from Python, easier to parse
in VBScript (split by spaces/quotes), and supports streaming if we move to
serial in the future.

### 4.2 MINIMUM VIABLE INSTRUCTION SET (V1)

```
OPEN <program> <window_title_after>      — launch a program by path or name
CLOSE <window_title>                     — close a window gracefully
KILL <window_title>                      — force-close a window
MOVE <window_title> <x> <y>             — move window to position
SIZE <window_title> <w> <h>             — resize window
FOCUS <window_title>                     — bring to front, set focus
TYPE <window_title> <text> /speed=N     — send keystrokes to window
DIALOG <type> <title> <text> /timeout=N  — show message box (info/warn/error/question)
WALLPAPER <path>                         — change desktop background
CURSOR <x> <y>                          — teleport mouse cursor
CLICK <x> <y>                           — click at position (default left)
DCLICK <x> <y>                          �� double-click at position
RCLICK <x> <y>                          — right-click at position
DRAG <x1> <y1> <x2> <y2> /duration=N   — drag from A to B
WAIT <ms>                                — pause execution
SOUND <system_sound_name>               — play a system sound
PAINT <x> <y> <w> <h> <color>           — draw filled rectangle on screen
TEXT <x> <y> <text> /color=C            — draw text directly on screen
SHELL <dos_command>                      — run a DOS command
DONE                                     — end of act file (writes .done)
```

### 4.3 WHAT NEEDS A COMPILED DLL/EXE (VBScript can't do alone)

- `GetDC(0)` screen drawing (VBScript can't call GDI directly)
- `SetCursorPos` / `mouse_event` (requires DLL calls with structs)
- `BlockInput`
- `SetWindowRgn`
- Alpha/transparency tricks (layered windows on 98 is hacky)
- Raw keyboard injection with delays between keys
- Screen capture (for verification/debugging)

Plan: write a small DLL (`art98core.dll`) in C that exposes high-level functions.
VBScript calls it via `CreateObject` (if COM) or via a helper `.exe` that
takes command-line args.

### 4.4 WHAT'S NEXT

1. **Pick VM platform** — VirtualBox or QEMU? QEMU is scriptable via QMP,
   VirtualBox has better Win98 support. Both work.
2. **Build golden image** — Win98 SE, VM additions, init script.
3. **Write the host Python bridge** — generate .act98 files, poll for .done.
4. **Write the guest VBScript executor.**
5. **Write the first scene** — something simple. "Notepad opens, types 'hello',
   closes." The Win98 equivalent of a triangle on screen.

---

## 5. OPEN QUESTIONS

- **VBScript or compiled EXE as the guest executor?**
  VBScript = zero build chain, editable on the VM itself. But limited API access.
  Compiled C = full API access. But needs build chain and deployment.
  **Leaning: VBScript for 90%, small C DLL for the 10% spicy stuff.**

- **Snapshot restore after every scene, or let state accumulate?**
  Restore = true determinism. Accumulate = more organic, but harder to debug.
  **Leaning: per-scene snapshot restore. The OS is a canvas, not a pet.**

- **Should the init script be part of the golden image or injected?**
  Golden image = simpler. Injected = more flexible for iteration.
  **Leaning: injected via shared folder. The golden image should be minimal
  (clean OS + VM additions) and everything else comes from the host.**

- **Is the host side cross-platform?**
  It's all Python + shared folders. Works anywhere the VM runs.
  The VM bridge is just file I/O.
