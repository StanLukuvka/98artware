"""Probe A1, host side: nested ro/rw mounts, reflink, snapshot over inherited tag, cold boot.
Works only on a fresh copy of the clone's work/ under PROBE (never a real work dir).
Every docker run goes through safe_boot.check_docker, every QEMU argv through check_vm
(the container runs the same argv with /work for PROBE/work). Usage: probe.py PROBE_DIR"""

import json
import shlex
import subprocess
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "core"))
sys.path.insert(0, str(HERE.parents[1] / "wide-display"))
import safe_boot  # noqa: E402
from art98.qemu import VMConfig  # noqa: E402

IMG = "localhost/art98:latest"  # already local; no pull
CLONE = Path("/home/admin/art98-release-check/98artware/work")
probe = Path(sys.argv[1]).resolve()
work, addons, src = probe / "work", probe / "work" / "addons", probe / "addons-src"

MOUNT_SH = r"""
exec 2>&1
echo "id: $(id)"; grep -E ' /(work|addons)' /proc/self/mountinfo | cut -d' ' -f5,6
try() { if sh -c "$2" >/dev/null 2>&1; then echo "WROTE   $1"; else echo "denied  $1"; fi; }
try "core dir /work/x" ': > /work/x'
try "sentinel /work/.art98-write-test (O_EXCL)" 'set -C; : > /work/.art98-write-test'
try "mkdir /work/newdir" 'mkdir /work/newdir'
try "repo addons ro /addons/x" ': > /addons/x'
try "rw nested /work/addons/ok" ': > /work/addons/ok'
[ "$(id -u)" = 0 ] && { echo "root-owned file made: $(stat -c %u:%g /work/addons/ok)"; rm -f /work/addons/ok; exit 0; }
echo "owner of /work/addons/ok: $(stat -c %u:%g /work/addons/ok)"; rm -f /work/addons/ok
mkdir -p /work/addons/m1
for mode in always auto; do
  s=$(date +%s%N); cp --reflink=$mode /work/golden.qcow2 /work/addons/m1/$mode.qcow2; rc=$?
  echo "cp --reflink=$mode ro->rw: rc=$rc $((($(date +%s%N) - s) / 1000000))ms"
done
[ "$(sha256sum < /work/golden.qcow2)" = "$(sha256sum < /work/addons/m1/always.qcow2)" ] && echo "reflink copy identical"
"""


def docker(name, args, cmd, bg=False):
    argv = ["docker", "run", "--rm", "--name", name, "--network", "none",
            "--security-opt", "label=disable", *args, IMG, *cmd]  # fmt: skip
    safe_boot.check_docker(argv, probe)
    line = "env -u DOCKER_HOST sg docker -c " + shlex.quote(shlex.join(argv))
    print("+", shlex.join(argv)[:200], flush=True)
    if bg:
        return subprocess.Popen(line, shell=True, text=True, stdout=open(probe / f"{name}.out", "w"), stderr=subprocess.STDOUT)
    r = subprocess.run(line, shell=True, text=True, capture_output=True)
    print(r.stdout + r.stderr, f"rc={r.returncode}", flush=True)


def guard_vm(loadvm):
    cfg = VMConfig.from_json(json.loads((work / "image.json").read_text()))
    cfg.disk, cfg.loadvm = addons / "a1" / "disk.qcow2", loadvm
    sock = probe / "sock"
    vm = types.SimpleNamespace(config=cfg, qmp_path=sock / "qmp", serial_path=sock / "serial")
    safe_boot.check_vm(vm, probe)


def main():
    safe_boot.check_settings({"work_dir": work}, probe)
    guard_vm("ready"); guard_vm(None)  # noqa: E702
    mounts = ["-v", f"{work}:/work:ro", "-v", f"{addons}:/work/addons", "-v", f"{src}:/addons:ro"]
    sh = ["--entrypoint", "sh"]
    for user in ([], ["--user", "1000:1000"]):  # root, then the owner uid
        docker("a1-mount", [*user, *sh, *mounts], ["-c", MOUNT_SH])
    (probe / "script").mkdir(exist_ok=True)
    (probe / "script" / "guest.py").write_bytes((HERE / "guest.py").read_bytes())  # the guard wants it in probe
    run = ["--user", "1000:1000", "-v", f"{probe / 'script'}:/probe:ro", *mounts]
    py = ["--entrypoint", "python3"]
    procs = [docker(f"a1-{m}", [*py, *run], ["/probe/guest.py", m], bg=True) for m in (sys.argv[2] if len(sys.argv) > 2 else "ab")]
    for p in procs:
        p.wait()


if __name__ == "__main__":
    main()
