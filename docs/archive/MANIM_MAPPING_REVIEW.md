# Review of docs/MANIM_MAPPING_PLAN.md  (verdict: CRITICAL, 6 items)

> **Archived, 2026-11-10.** Superseded by [docs/status.md](../status.md), which is the one
> roadmap, and by [the state and action design](../design/state-and-action.md). This reviews the
> [Manim mapping plan](MANIM_MAPPING_PLAN.md), archived with it.
> It is kept for its reasoning and is no longer kept up to date.

Line refs are to MANIM_MAPPING_PLAN.md unless a file is named.

## CRITICAL

1. Sec 8 / Phase 2 (A1-A8, T2.1): no way to get agent v2 into the `ready` snapshot.
   guest/agent.exe is copied only in prep.py stage_disk (mcopy ::ART98/AGENT.EXE, prep.py:412).
   stage_harden (prep.py:446-464) never copies it and ends with `self.raw.unlink`, so re-running `disk` means a
   full reinstall. boot() loads `ready` (session.py:88-92), where the v1 agent is already running in RAM.
   Phase 2's milestone ("same scene runs with v2 BATCH") cannot be met with the current prep flow.
   Fix: add an explicit task and decision: either bake the final agent before the first `harden` (so decide A1-A8
   now), or add a "redeploy agent + re-save ready" stage (put_file to AGENT2.EXE, edit Run key, reboot, re-snapshot).
   Also state that `wait_ready` negotiation (A5) is moot until the guest binary changes.
2. Sec 8 A6 `HANG`, sec 3.6 row 2, sec 4.6 `TracedPath`: the smear design deadlocks the agent through `SYNC`.
   agent.c:596-601 settle_window() calls `RedrawWindow(hwnd,..., RDW_UPDATENOW|RDW_ALLCHILDREN)` before the
   SendMessageTimeout(SMTO_ABORTIFHUNG), and verb_sync (agent.c:610-620) runs it for every visible top-level window
   on the UI thread. RedrawWindow UPDATENOW sends WM_PAINT synchronously with no timeout. A visible window that
   never pumps (the HANG window, or any hung app that was dragged over) blocks the agent forever, so every later
   frame stalls. The plan's "SMTO_ABORTIFHUNG already used" does not protect that call.
   Fix: SYNC must skip or time-box windows known hung (IsHungAppWindow is NT-only, so use a SendMessageTimeout
   WM_NULL probe first, then RedrawWindow only if it answered), or the smear uses `LockWindowUpdate` /
   SWP_NOREDRAW on a responsive window instead of a non-pumping one. Add this to T2.2 and probe P1.
3. Sec 3.3 + P9 + Risks row 5 + feature #15: the `-snapshot` / "overlay plus savevm in the overlay chain" fallback does not work.
   `ready` is an internal qcow2 snapshot stored in golden.qcow2 (prep.py:462 save_snapshot; plan 2.1). `loadvm` looks it
   up in the top image of each block device. A `-snapshot` temp overlay or backing-file overlay has an empty snapshot
   table, so `-loadvm ready` is expected to fail ("does not have the requested snapshot"). Re-saving inside the overlay
   is circular because RAM state can only be produced by first loading it.
   Two VMs on one golden.qcow2 also hit QEMU's image write lock, which kills #15 (parallel render).
   Fix: say the per-run strategy is a copy (cp --reflink / qemu-img convert) of golden.qcow2 per VM, or migrate-to-file
   (`migrate exec:` + `-incoming`) over a throwaway overlay. Make that the P9 question; drop "overlay chain".
4. Sec 4.3 `screen` back-end (the default for M3, Phase 3 `Wave` example), sec 3.5, sec 6.4: persistence/erase is unspecified.
   "Redrawn every frame" never says how the previous frame's GDI pixels are removed. Pixels drawn on `GetDC(0)`
   stay until the underlying windows repaint, so each frame needs a RedrawWindow(NULL, rect, NULL,
   RDW_INVALIDATE|RDW_ALLCHILDREN|RDW_UPDATENOW) over the old shape bounds (or the whole desktop). That repaints
   every app under it, interacts with item 2, and costs guest CPU/serial that sec 3.5 omits entirely. Moving
   windows over shapes also overwrites them (contradicts "always above windows", sec 4.1 line 383).
   Fix: define the algorithm (dirty-rect union of previous and new bounds, invalidate, SYNC, draw, capture), add
   its op/byte cost to 3.5, and probe it in Phase 0/3. Otherwise make `window` back-end (A7) the default.
5. Sec 8.5 export catalogue + sec 4.3/4.9/4.10 API claims: the catalogue premise is wrong for Win9x, and some listed stand-ins are NT-only.
   Win9x ships exported stubs that return ERROR_CALL_NOT_IMPLEMENTED (the plan itself says this for CreateRemoteThread, sec 4.10 line 614 and P12).
   So "turns 'this API is NT-only' into an authoring error" (8.5) will not fire for stubs. Needed instead: a deny-list from MSDN/WIN32API.CSV "Windows 95/98: Unsupported".
   Confirmed or documented as unsupported or restricted on 9x:
   - AngleArc: NT-only (KB Q125693). PolyDraw: unsupported (KB Q135059). SetWorldTransform/ModifyWorldTransform:
     fail, SetGraphicsMode accepts only GM_COMPATIBLE (KB 136989). MaskBlt: unsupported.
   - ArcTo (listed in 4.3 row 2, line 420): I believe NT-only but did not find the page; treat as unsupported until probed.
   - `Arc/Pie/Chord/RoundRect`: sum of left+right and top+bottom coordinates must not exceed 32K, a stricter rule than the plan's "clamp to +-32767" (3.6, 7.x).
   - Wide (>1 px) pens support only PS_SOLID geometric: `DashedLine` via `PS_DASH` (4.2 line 412, "N") is solid at width>1.
   - CreatePatternBrush/CreateDIBPatternBrush: bitmaps larger than 8x8 unsupported, brush origin is not tracked
     (need UnrealizeObject+SetBrushOrgEx+SelectObject per paint). The `dither` fade (4.6) must be 8x8 and re-origin per window move.
   Fix: amend 8.5 to "export table AND deny-list", remove ArcTo/AngleArc/PolyDraw from the tables, add P15 entries for ArcTo/AngleArc/PolyDraw/GM_ADVANCED, restate the coordinate rule.
6. Sec 1.2 (authenticity ladder), sec 6.5, sec 10.2 Phase 5, T5.1: `strict` is self-contradictory.
   `strict=True` "makes any host-realm operation raise" and must support "every pixel was drawn by Windows 98".
   But sec 3.6 and 7.1 make the cursor overlay mandatory because the hardware cursor is absent from screendump (README), the
   default ladder rung puts captions in the host realm, and the 6.5 example (`strict = True`) calls `Drag(...)` (cursor needed to be seen)
   and `add_sound(...)` (graded F, host-mixed, 4.11). A strict scene as written either raises or has an invisible cursor.
   Fix: define strict precisely (e.g. allows cursor overlay/audio/captions, forbids compositing guest pixels) or require the P3 outcome (software cursor via Display settings) before promising it. Fix the 6.5 example.

## Advisory

A1. Sec 3.4 / 3.5 timing: Win9x system tick is ~55 ms (18.2 Hz): GetTickCount, Sleep granularity (period sources: KB Q81592; Sleep(33) may round to ~55 ms; I could not find a 98SE-specific MS page).
    `advance(1000/fps)` (sec 3.2 diagram) and the agent's `Sleep(READ_POLL_MS=2)` read poll (agent.c:779) may cost up to a tick each, not "2 ms" as sec 3.5 implies. Add to P4/P11: measure Sleep(1/2/33) on guest and request latency.
A2. Sec 3.4 vs 3.2: stepped mode is defined as "guest time advances only during ops plus an explicit advance()", but the sequence diagram calls advance(1000/fps) every frame. Pick one. With the first definition `wait(2)` of caret blink is frozen; the second adds a Sleep per frame.
A3. Sec 3.4 `locked`: P11 does not test that a snapshot saved without `-icount` (the `ready`) loads under `-icount shift=N,sleep=off`. Phase 4 depends on it; add to P11/P21. QEMU timer/vmstate differences are plausible failure.
A4. Sec 8.4 / 6.6: `loadvm` after a `blockdev-change-medium` leaves the guest's CD cache (CDFS/media-change state) inconsistent with the host's medium. Add to P10/P21. Also decide the default IDE CD exists (plan says "probably"; QEMU adds `ide1-cd0` by default unless -nodefaults — likely true, so T0.2 may be verification only).
A5. Sec 4.10 "Windows" row / sec 4.10 keyboard scenes: `SetForegroundWindow` is restricted on Win98+ (foreground lock timeout), so a background agent mostly flashes the taskbar. WM_CHAR caret and Start-menu keyboard scenes need the right window active; the plan uses SWP_NOACTIVATE everywhere (6.2). Add a probe, and `ForegroundLockTimeout=0` plus `CursorBlinkRate` to HARDEN_SETTINGS before the snapshot (cheap now, costly after).
A6. Sec 4.10 desktop/BSOD/shutdown: "with acpi=off Win98 shows the real [safe to turn off] screen" (line 610) is an assumption presented as fact; qemu.py:58 only proves the flag. SeaBIOS APM may make 98 power off. Needs a probe.
A7. Sec 4.10 screensavers: `SC_SCREENSAVE` needs SCRNSAVE.EXE configured and ScreenSaveActive is hardened to 0; use `.scr /s` only. `ssflwbox.scr` is 3D Flower Box, 3D Flying Objects is `ss3dfo.scr`.
A8. Sec 7.1/8: cursor hotspot from `GetCursorInfo` is wrong; that gives HCURSOR/position, hotspot needs `GetIconInfo`. Also `TransparentBlt` has a known resource-leak problem on Win98 (from memory, verify) which matters with the 64 KB GDI heap; prefer the SRCAND/SRCPAINT mask already described.
A9. Sec 3.5 BATCH estimate: inner calls travel as one string arg, so `"` becomes `\"` and newline becomes `\x0a` (protocol.py:49-58): about +8 B per inner call; the "~35 B each" figure is ~43 B. 11 KB/s is just the 115200 8N1 line rate (agent.c:836) not a measurement; the README labels it a claim and the plan does too, fine, but 3.5 "tens of ms" screendump + libx264 per frame will dominate; give a per-frame estimate (~100+ ms/frame => ~10 fps render).
A10. Manim coverage (spot check against docs.manim.community v0.22.1): the class lists in 2.2 match the docs (49 rate functions verified; animations/mobjects index verified). Gaps and misdescriptions:
    - `Wiggle` (4.6) is rotation-wiggle plus scale in Manim, not x/y sinusoidal offsets; `Indicate` also recolours (yellow) and scales 1.2.
    - `Scene.wait(stop_condition=, frozen_frame=)` omitted; `wait_until`-style stop_condition is exactly what Win98 needs (wait until dialog appears).
    - `Mobject.set_z_index/z_index` (animatable layering) mapped only via bring_to_front/back.
    - `.animate` modifiers (`set_run_time`, `set_rate_func`, `set_default`), `override_animation`, `suspend_mobject_updating`, `Animation.introducer/remover/lag_ratio` details not mapped (lag_ratio is listed in 6.1 only).
    - Mobjects not mapped: `ArcBrace`, `BraceLabel`, `BraceText`, `StealthTip`, `LayoutFunction` (Graph layouts), `TransformMatchingAbstractBase`, `ArcPolygonFromArcs`, `TipableVMobject`, `MathTexPart`. `Transform` `path_arc` only via Clockwise.
    - Ecosystem features people actually want and absent from sec 9: manim-slides style presentation export, manim-voiceover style TTS, `--save_sections` consumers. Section 4.1: `on_key_press` etc. not in 0.22 docs set verified here (the 2.2 list says they exist; not verified).
A11. Grading mismatches vs the sec 0 legend: host-only things graded N (`play`, `add_updater`, `next_section`, `add_subcaption` "N (host)") although the legend defines N as "the guest OS does it" and F as host-done; `add_sound` is A in 4.1 line 386 but F in 4.11 line 622; `NumberLine` "A / N (trackbar)" (4.5) grades a widget substitution as native; `Cutout/Union/...` N in 4.3 but 4.3 header says all A.
A12. Wrong cross-references: 2.3 "camera ... section 4.9" (cameras are 4.7); 4.1 last row "see 4.9 and 4.10" (should be 4.7 and 4.9); 4.7 `ThreeDCamera` "4.10" (should be 4.9); Phase 3 milestone "`Wave` example (4.6)" (is 6.4); 4.10 uses "Section 4.10" for Win98 facilities but 3.x text calls them 4.10 and 9 calls them...; Sec 2.1 "Desktop gate: only Program Manager and Shell_TrayWnd may exist" is inaccurate: prep.py:511-519 rejects visible titled windows other than Program Manager and requires Shell_TrayWnd to exist.
A13. Sec 9 ranking: #2 reproducible renders is "very high / M" but sec 3.4 and Phase 4 say `locked` may be impractical and Phase 4 (cache+clock) is L; #2 effort understated and "very high" value rests on an unproven mode; #5 live reload depends on #4 (L) and on item 3 above. #15 parallel VMs depends on the item 3 fix; #10 timeline viewer outranks it. Missing from ranking: agent redeploy/versioning tooling (item 1), a hardening-v2 pass (A5) before the snapshot.
A14. Sec 4.4/4.10: WordPad `EM_SETCHARFORMAT`/`EM_STREAMIN` carry pointers and are not thunked across processes on 9x; the stated workaround ("keyboard or WM_SETTEXT + selection formatting") cannot colour text without them. Either run a RichEdit control inside the agent (as done for SysListView32) or drop WordPad colouring from Phase 6. `Code` (graded N, "most period-faithful") depends on this.
A15. Sec 4.6 `dither` fade is destructive: PATAND on a window DC erases app pixels that only the app can redraw, so `FadeIn(dither)` (reverse) needs invalidation per frame and `FadeOut` leaves the window needing repaint if kept. Sketch the reverse path.
A16. Sec 3.2 diagram: "Static frames are free: reuse previous capture" conflicts with free mode and caret blink; only valid in stepped/locked (the text mentions this; the cache row in 4.12 repeats the constraint; ok), but `wait()` in default clock mode `stepped` freezes guest animations (4.1 line 377) which makes the default render visibly dead (no caret, no clock) for waits; call that out in 6.3 examples.

## Verified claims (no action)
Verbs list (agent.c:680-711); MAX_ARGS/MAX_BLOB/MAX_LINE; per-call LoadLibraryA+GetProcAddress (agent.c:455-460); ACALL DONE event; FrameRecorder.frame never pauses VM (session.py:36-41); Bridge.wait_ready rejects version mismatch (bridge.py:319); pecheck allow-list contents and the claim that CALL targets don't gate on it (pecheck.py:13-33; CreateThread/HeapAlloc/RegisterClassA/DefWindowProcA present); `PLAN.md` §1.1 CreateRemoteThread and §1.2 `color 0a` exist as cited; set_display_mode exists (bridge.py:369); HARDEN_SETTINGS list matches; ready snapshot saved while paused (prep.py:461-462).
Serial arithmetic: 100 B/11 KB/s ~ 9 ms, 1 KB/11 KB/s ~ 93 ms, 1.92 MB/11 KB/s ~ 175 s all check; 11 KB/s is the 115200 8N1 line rate, an upper bound.
Win32 items that exist on 98 and are used correctly: SetWindowRgn, DrawAnimatedRects, FlashWindowEx, LockWindowUpdate, GetCursorInfo (98+), msimg32 AlphaBlend/GradientFill, opengl32/glu32 1.1 (98 ships them), rsrc32 export, LVM_SETITEMPOSITION (no pointer). NT-only calls correctly excluded: SetLayeredWindowAttributes, CreateRemoteThread, PlgBlt, SetWorldTransform (the last two partly).
Sources: KB 136989 (ftp.zx.net.nz mirror), KB Q125693, KB Q135059, KB Q81592, docs.manim.community v0.22.1 animations/mobjects/rate_functions index pages.

---

# Second review (2026-11-06)

Two independent reviewers read the rewritten plan: one for truth and feasibility, against `guest/agent.c`, `src/art98/`, QEMU and Manim sources, the other for Manim coverage and features, against the Manim docs. Together they raised 16 critical findings and 13 advisories. Each was checked against the source before it was applied.

## Applied

| Finding | Change in the plan |
|---------|--------------------|
| Running the guest every frame sets a floor under guest time, so debt may never go positive | 3.2 and 3.4: op-free frames with under a tick owed leave the guest stopped and reuse the capture; P4 measures the floor |
| Pauses, skips, restores and spawns jump the debt | 3.4: `rebase_t0()` at each discontinuity |
| The VM is stopped between frames, so guest calls there time out | 3.2: guarded bridge, T1.6 |
| Double capture of a stopped VM always matches | 3.2: capture, run a slice, recapture, with a caret mask |
| A0 would stop painting agent-owned controls | 8.1: skip only the `HANG` thread's windows; P1 part b checks it |
| Byte figures left out the `#` buffer echo (`agent.c:478`) | 3.5: recomputed by protocol; new in-only blob A11; v1 is 3-4 fps, v2 with `POLY` 7-10 fps |
| `Win98Camera` sketch would not run: RGBA, config, `reset()`, static pass, `static_image` reset, hashing, skipped plays, video time | 6.8 rewritten with `Win98Renderer`; caching off when `self.guest` is used |
| `sleep=off` warps only when the vCPU sleeps, and 9x may never `HLT` | 3.4, P11, feature list and risks |
| `screen` algorithm could not skip hung windows | 4.3: `REPAINT` verb A10 |
| Phase 1 depended on Phase 4, P1 on A0, and no task built the renderer | `free` clock until T4.1, P1 split into parts a and b, T1.6 |
| No UI-action layer | New 4.10b, T1.7, P14 and P22 extended |
| Headline grades broke the N rule (`ChangingDecimal`, `Restore`, `Write`, `Mobject`) | Summary, 4.4, 4.6 |
| Eight animation rows misdescribed Manim | 4.6 rewritten after checking the class docs |
| The Confession claim was false | 10.2: film cut, graph edges corrected, T5.2 split out. A film does not need Phase 2 at all, because v1 can do everything in it |
| Native pixels against Manim units was not surfaced | D10, 3.1 mixing rule, 6.1 `dry` warning, 11.2 question 6, 4.13 wording |
| "Every Manim name" was false | Summary and 4.2b reworded, catch-all row, missing names added |
| Win98 gaps | Control Panel, common dialogs, clipboard, `TileWindows`, cursor shapes, games, Desktop Themes in 4.10 |
| Feature ranking ignored its own rule | Section 9 re-sorted by value then effort, enablers split out as E1-E3 |
| New features | Zoom and pan split out, human input feel, automatic foley |
| Reader test | Summary gained grades, a sample scene, requirements and a glossary; the page gained a mapping diagram |
| Reference errors | A8 replaced by A12 for input, T1.2 no longer touches `protocol.py`, feature E1 phases, `BarChart` in T3.1, P14 and P25 citations, line numbers |
| Cache key cannot deliver "last section only" | 3.3: per-section prefix hash |
| `alpha=1` breaks cumulative guest effects; journal missed raw calls | 6.9: `Animation.fast_forward()`, bridge-level journal |
| `advance` after `SYNC` can leave a half-done paint | 3.2: advance first |
| Small facts | RFC 1924 alphabet, `wParam` branch in A4, `ForegroundLockTimeout` type, machine from `image.json`, `wait_until` wording, 6.4 method names, 2.4 entry-point group |

## Rejected or changed

| Finding | Decision | Why |
|---------|----------|-----|
| HyperTerminal as a facility | rejected | The VM has no NIC, so there is nothing for it to talk to |
| Rows for all 86 remaining method names | changed | A catch-all row says what they are: host-only. Listing them adds length, not information |
| 11.2 question on which phases are in scope | rejected | Question 4 and the film cut already set the order |
| Move `clock="free"` and `cursor` out of 11.1 | rejected | Harmless where they sit, and useful to confirm |
| Manim's tutorial and gallery scenes as a feature | changed | Taken as acceptance scenes in Phase 3b and T3.3 |
| `AnimatedBoundary` as a colour-cycling outline only | changed | Adopted for shapes; marching ants stay as a window variant |

## Could not verify

Whether Win98 executes `HLT` when idle (only forum reports; CPUIdle's documentation covers Windows 95), cross-thread `UPDATENOW` blocking on 9x, `MaskBlt` status on 9x, `DeferWindowPos` across processes on 9x, `DrawAnimatedRects` with `MinAnimate=0`, and `screendump` while stopped. Each is either a probe or part of one. Whether Manim's file writer requires RGBA was inferred from `Camera`, not read. Manim was read from `main`, not a pinned 0.22.1.

# Checked against the real image (2026-11-06)

Windows 98 reached the desktop after both reviews, and the install session measured it. The results are in section 2.7 of the plan. This is how they changed the reviews' conclusions.

| Earlier conclusion | Result on the real image | Plan change |
|--------------------|--------------------------|-------------|
| The pointer is probably in `screendump` | Confirmed | Cursor overlay and the `cursor` exception to `strict` removed; shape lag stays in P3 |
| About 3-4 fps on today's agent | Holds only for a frame with a 64-point polygon, and that byte cost is still an estimate. A frame that moves one window takes about 22 ms | 3.5 now gives three cases. The film cut no longer quotes 3-4 fps |
| The read poll may round up to a 55 ms tick | Not in the request path: `PING` takes about 5 ms | 3.4 hazard narrowed to `advance` and `Sleep`. `Sleep` granularity stays in P4 |
| `SYNC` repaint is unproven | `SYNC` leaves stale pixels after moves, and double capture cannot catch them | `RedrawWindow` after every move; P1 now compares against an expected image, with a part c for other ops |
| `ExitWindowsEx` reboots the guest in the `agent` stage | A warm reboot freezes, so a reboot now ends QEMU | 3.3 reboot sequence; 8.3 step 4 rewritten; `Scene.reboot()` in T6.x |
| What a Typical install holds is unknown | The final image, with `[OptionalComponents]`, holds the accessories, 77 sounds and 11 screensavers. Desktop Themes did not install | 2.1, 4.10 and P26 updated; Desktop Themes has a stand-in row |
| Screensaver names such as `ss3dfo.scr` | Wrong: the files have long names, and `ssmarque.scr` is not on the image | 4.10 lists the real files and says to quote the path |
| Export table alone is not enough | `AngleArc` is exported by `gdi32` on 9x, as the reviews warned | Stays on the deny-list; P15 now says to call each function |

`hello.py`'s "210 frames in under 3 s" was read with care: it is 79 captures and 131 held copies, so it is not a 70 fps result.

One gap neither review raised: the plan had no audio probe. P28 now covers it, including whether the single `midiOut` device makes any sound.
