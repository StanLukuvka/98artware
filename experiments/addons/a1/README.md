# Probe A1 results (2026-11-13)

Probe dir: `~/art98-release-check/probes/a1-20261113-2020/` (a fresh copy of the clone's `work/`: `golden.qcow2`,
`image.json`, `state.json`). Image `localhost/art98:latest` (already local, real Docker, rootful, QEMU 10.2.2 in the
image and on the host). Scripts: `probe.py` (host, every `docker run` through `check_docker`, QEMU argv through
`check_vm`), `guest.py` (in the container). CPU pressure (`/proc/pressure/cpu` some): avg10 0.02-0.12, avg60 0.05-0.09
during the runs, so timings are not contended.

Golden mtimes (`stat`), before and after, identical:

| file | before | after |
| --- | --- | --- |
| repo `work/golden.qcow2` | 2026-11-06 16:33:29.007260943 +1100 | 2026-11-06 16:33:29.007260943 +1100 |
| clone `work/golden.qcow2` | 2026-11-12 01:34:13.301846608 +1100 | 2026-11-12 01:34:13.301846608 +1100 |

| Question | Answer | Evidence |
| --- | --- | --- |
| Nested ro `/work` + rw `/work/addons` (+ ro `/addons`), `--security-opt label=disable`, owner uid | PASS | mountinfo: `/work ro`, `/work/addons rw`, `/addons ro`. As uid 1000 and as root: `: > /work/x`, `mkdir /work/newdir`, `set -C; : > /work/.art98-write-test` (the O_EXCL sentinel) and `: > /addons/x` all denied; `/work/addons/ok` written, owned 1000:1000 for `--user 1000:1000`. |
| Root in the container writes the rw part as root | Note | The root run created a root-owned `/work/addons/ok` (0:0). Install containers must drop to the owner uid, as `container/entry.py` does with `ART98_HOST_UID`. The probe used `--user 1000:1000` for everything else. |
| `cp --reflink` across the ro and rw mounts | PASS | `--reflink=always` from `/work/golden.qcow2` (ro) to `/work/addons/m1/` (rw): rc=0, 22 ms (6-12 ms on other runs), content identical. The host fs is btrfs; both mounts are the same filesystem. On another fs `auto` falls back to a full copy (not tested, no second fs here). |
| `loadvm ready` on a copy | PASS | Via QMP `loadvm ready` (as `Session.revert` does) and via `-loadvm ready` on the command line: `info status` running, desktop screenshots `a-loadvm.png`, `a-loadvm2.png` (clock 9:00 / 9:01). |
| reboot, then `savevm ready` over the inherited tag | PASS, no `delvm` needed | "Reboot" = quit and start a new process with no loadvm (QEMU runs `-no-reboot`); settled desktop at 60 s. `snapshots()` before and after savevm: `['ready']` (one tag). `qemu-img snapshot -l` after: one row, ID 1, TAG ready, new date and VM clock (`2026-11-13 09:38:44`, `0000:01:00.065`) in place of the inherited `2026-11-11 14:34:13`, `0000:00:42.951`. The new `ready` loads (`-loadvm ready`, status running, desktop). |
| Cold boot of an unmodified golden copy (ScanDisk?) | PASS, no ScanDisk | `b-cold-030s.png` and `b-cold-060s.png` (identical frames) show the plain 800x600 desktop; no ScanDisk or boot prompt. |

Other findings:
- `VM.__enter__` calls `start()`, so `with vm.start() as v` starts QEMU twice on one disk: the second one fails with
  `Failed to get "write" lock` and the first one never answers QMP (the probe hung until fixed). Use `with VM(...) as v`.
- `--entrypoint` is not in the plan's allow-list, but the image's entrypoint is `art98` (a CLI), so a bare probe cannot
  run a script without it. `check_docker` allows `--entrypoint sh|python3` only (a deviation from section 11 for the
  coordinator to ratify).
- Not tested: a non-btrfs filesystem for reflink; rootless Podman (a different engine from the real Docker used here).
- Cleanup: probe containers use `--rm` and are gone; the probe dir (2.1 GB apparent, mostly reflinked) was deleted on 2026-11-14.
