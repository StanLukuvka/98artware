# P3: CD wallpaper route on the container backend (Podman, Docker) and local

Run 2026-11-11. Script: `probe_cd_container.py` (`. .tools/env.sh && .venv/bin/python experiments/dialog-storm/probe_cd_container.py OUTDIR container|local`;
Docker run: `env -u DOCKER_HOST sg docker -c '...'`). Uses `session.attach_disc` (the real `build_iso`), `wait_for_disc`, `set_wallpaper`,
`session.vm.screenshot(format="ppm")`. Generated 800x600 24-bit BMP (1.44 MB, red = x, green = y, blue 128), made in the script.
Pixel check: 3 points above the taskbar, tolerance 12 per channel.

## G1: PASS (Podman, real Docker, local all green)

`insert_disc` did not answer `unknown op` on either engine (image `localhost/art98:latest`, rebuilt in both stores).

## Timings (ms; send+insert = `attach_disc`, detect = `wait_for_disc`, set = `set_wallpaper`; CPU = /proc/pressure/cpu "some avg10")

| Run | step | send+insert | detect | set | total | CPU avg10 |
|---|---|---|---|---|---|---|
| Podman | center (first) | 6 | 93 | 604 | 703 | 1.63 |
| Podman | stretch (after revert 1, 86 ms) | 8 | 60 | 590 | 658 | 1.63 |
| Podman | center (after revert 2, 75 ms) | 7 | 61 | 476 | 543 | 1.63 |
| Docker | center (first) | 8 | 107 | 710 | 824 | 1.38 |
| Docker | stretch (after revert 1, 133 ms) | 8 | 71 | 735 | 814 | 2.04 |
| Docker | center (after revert 2, 144 ms) | 8 | 72 | 715 | 795 | 2.04 |
| Local | center (first) | 5 | 88 | 733 | 827 | 1.81 |
| Local | stretch (after revert 1, 89 ms) | 5 | 56 | 580 | 641 | 1.81 |
| Local | center (after revert 2, 112 ms) | 5 | 60 | 546 | 611 | 1.84 |

CPU pressure stayed low (1.3 to 2.0) in every run; no other VM visibly competed. Timings are within noise of each other and of P2
(insert about 5-8 ms, detect 60-110 ms, set 0.5-0.8 s). Boot to first screen is not timed here.

## Checks (all PASS on all three)

- Every wallpaper screenshot matched the expected pixel at (10,10), (400,300), (790,540) within 12 per channel.
- Revert twice in a row (`session.revert()` ejects, then loadvm): after each, `cd_drive` exists but the file is unreadable (medium gone);
  a fresh `attach_disc` right after each revert worked and detected on the first poll sequence.
- QEMU in the image: `QEMU emulator version 10.2.2 (qemu-10.2.2-1.fc44)`, identical in the Podman and Docker stores and to the host.
  Docker 29.9.3; Podman 5.8.9; Docker image created 2026-11-11T15:14+11:00.

## Findings / caveats

- `RemoteVM` (container) has no `disc_state()`; the local `VM` does. The "medium gone" check therefore uses only the guest's view
  (file unreadable) on all backends. Fine for the pipeline; mention if code ever calls `vm.disc_state()` on a session.
- The stretch run uses the same 800x600 BMP as the screen, so its pixels cannot tell stretch from centre. The stretch registry path
  itself was proved in P2 (160x120 BMP); here it only shows the call works over the container.
- Screenshots: scratchpad only, not in the repo.
