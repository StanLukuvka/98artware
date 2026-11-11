# VM service probes (plan V8)

Three probes of the long-lived VM service (`art98 vm start`, `art98.service.attach`): disk growth
(R4), kill -9 mid-render (R3), a VNC viewer (R11). All on **real Docker**, 2026-11-11, quiet host
(20 CPUs). `/proc/pressure/cpu` `some avg10` is logged next to every timing; it read 0.00 every time
(avg10 is a 10 s window, so it would miss a burst shorter than a few seconds; every render here is about 0.6 s (plain) or 3.9 to 4.7 s (stress)). Outputs went outside the repo; nothing from `work/` is copied here.

Files: `common.py` (scenes `Short` ~34 frames and `Longer` ~181 frames, pressure and size helpers),
`probe_disk.py`, `probe_kill.py`, `probe_vnc.py`, `rfb_viewer.py` (view-only RFB 3.8 client, Raw
encoding, never sends key or pointer events).

Every command below starts with `. .tools/env.sh` and, for real Docker, is wrapped as
`env -u DOCKER_HOST sg docker -c '...'`.

## A. Disk growth (R4)

Method: 30 consecutive `attach` + `render` of `Short` (about 1 s of video). The run-copy qcow2
(`work/runs/vm-*/golden.qcow2`) is measured with `stat` (allocated = `st_blocks`) before the first
render and after each. A second series ("stress") also `put_file`s 512 KiB of random data on the
guest in each render, so the guest really writes to its disk (the render time then includes the
upload, about 4 s).

| series | renders | allocated MiB: before / after 1 / after 30 / min / max | apparent MiB | render s | cpu avg10 |
|---|---|---|---|---|---|
| plain | 30 | 414.20 / 414.20 / 414.20 / 414.2 / 414.2 | 415.25 constant | 0.6 each | 0.00 |
| stress (512 KiB written per render) | 30 | 414.20 / 415.14 / 415.14 / 414.2 / 415.26 | 415.25 to 415.44, then constant | 3.9 to 4.7 | 0.00 |

Verdict R4: no unbounded growth. The stress series grew about 1 MiB in the first render and then
oscillated between 415.14 and 415.26 MiB for the other 29, so `loadvm` reuses or releases the
clusters. Caveat: 512 KiB per render is a small write load, and the guest may buffer part of it; a
scene that writes tens of MiB was not tried. Keeping the documented `vm stop` + `vm start` as a
fallback is still cheap. (Podman, run earlier before the scope change: plain series flat at 414.2 MiB,
0.6 s per render.)

Rerun:
```
. .tools/env.sh; S=/some/dir/outside/the/repo
env -u DOCKER_HOST sg docker -c ".venv/bin/art98 vm start; .venv/bin/python experiments/vm-service/probe_disk.py $S/disk 30"
env -u DOCKER_HOST sg docker -c ".venv/bin/python experiments/vm-service/probe_disk.py $S/disk 30 512"
```

## B. kill -9 mid-render (R3)

Method: a child process attaches and renders `Longer` (a full render takes about 1.8 s); the parent
`kill -9`s the child by PID `delay` seconds after it reports "attached". A fresh process then does
`attach(wait=15)`, `bridge.ping()` and a full render. 8 rounds, delays 0.05 to 1.2 s (before the first
frame, mid typing, mid wait, near the end). `busy_wait_s` is the time `attach` took (revert
included).

| round | kill at s | child killed | attach s | ping | render s | bytes | cpu avg10 |
|---|---|---|---|---|---|---|---|
| 1 | 0.05 | yes | 0.05 | 54387 | 1.8 | 34432 | 0.00 |
| 2 | 0.3 | yes | 0.05 | 54387 | 1.8 | 34432 | 0.00 |
| 3 | 0.6 | yes | 0.04 | 54387 | 1.9 | 34433 | 0.00 |
| 4 | 0.9 | yes | 0.05 | 54389 | 1.8 | 34432 | 0.00 |
| 5 | 1.2 | yes | 0.05 | 54390 | 1.8 | 34463 | 0.00 |
| 6 | 0.15 | yes | 0.05 | 54386 | 1.8 | 34433 | 0.00 |
| 7 | 0.45 | yes | 0.05 | 54389 | 1.8 | 34432 | 0.00 |
| 8 | 0.75 | yes | 0.05 | 54387 | 1.8 | 34433 | 0.00 |

(A first attempt with delays up to 6 s killed nothing in 4 of 7 rounds, because the render ends at
1.8 s; those rounds also passed and are not counted.)

Verdict R3: no desync, no hang, no Busy: the owner slot was already free when the next process
attached (attach took 0.05 s, so the `wait=` was never needed). Every ping answered, every second
render completed with a normal output (34.4 kB; round 5 differs by 30 bytes, a caret or clock
pixel). Revert-before-ping recovers COM1. The service still reported `paused`, snapshot present,
afterwards. Podman (run earlier): 8 of 8 the same, attach 0.04 to 0.08 s, bytes 34423 to 34433.

Rerun:
```
. .tools/env.sh; S=/some/dir/outside/the/repo
env -u DOCKER_HOST sg docker -c ".venv/bin/python experiments/vm-service/probe_kill.py $S/kill 8"
```

## C. VNC viewer (R11)

Method: `art98 vm stop`, `art98 vm start --vnc` (`vnc: 127.0.0.1:5900`). `Longer` rendered five
times: none1, none2 (no viewer: the noise floor), stay (view-only `rfb_viewer.py`, Raw encoding,
FramebufferUpdateRequest in a loop, started 1 s before the render), reconnect (the same client
dropping and reconnecting every 0.5 s), none3. Frames compared with `ffmpeg -f framemd5` on the
decoded mp4 (per-frame hashes in the scratch dir).

| run | viewer | frames | render s | cpu avg10 before / after | frames differing from none1 |
|---|---|---|---|---|---|
| none1 | none | 181 | 2.0 | 0.00 / 0.00 | 0 |
| none2 | none | 181 | 1.9 | 0.00 / 0.00 | 5 (75 to 79) |
| stay | 1 connect, 14 updates, 2.9 MB | 181 | 1.9 | 0.00 / 0.00 | 4 (76 to 79) |
| reconnect | 4 connects, 15 updates, 9.7 MB | 181 | 1.9 | 0.00 / 0.00 | 4 (76 to 79) |
| none3 | none | 181 | 2.0 | 0.00 / 0.00 | 2 (74, 75) |

Verdict R11: a view-only viewer, steady or reconnecting, changes neither the frame count (181 in all
five) nor the render time, and its differences (4 frames, all in 76 to 79) sit inside the run-to-run
noise of two renders with no viewer (5 and 2 frames around 74 to 79, probably the Notepad caret
blink; the cause was not inspected). No VNC encoding cost showed at this resolution (800x600), though
the viewer saw only 14 to 15 updates because the screen is mostly static. Not tested: a viewer in
normal mode (sends input; expected to change frames), other encodings, several viewers.

Rerun:
```
. .tools/env.sh; S=/some/dir/outside/the/repo
env -u DOCKER_HOST sg docker -c ".venv/bin/art98 vm stop; .venv/bin/art98 vm start --vnc; .venv/bin/python experiments/vm-service/probe_vnc.py $S/vnc"
env -u DOCKER_HOST sg docker -c ".venv/bin/art98 vm stop; .venv/bin/art98 vm start"   # back to no VNC
```
