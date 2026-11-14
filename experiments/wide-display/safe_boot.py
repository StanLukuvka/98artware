"""Fail-closed pre-flight guard for display probes.

A probe calls one of these before it starts QEMU or copies a disk:
  config_argv(config, qmp, serial, probe_dir)  build the argv and check it
  check_vm(vm, probe_dir)                      before art98.qemu.VM.start()
  check_stage(work_copy, probe_dir)            before art98.session.stage()
  check(argv, probe_dir, socket_dirs=())       the argv check itself
  check_docker(argv, probe_dir)                before every `docker run` (allow-list)
  check_settings(settings, probe_dir)          settings.work_dir stays in probe_dir

A failed check raises AssertionError before anything is started. Plain `if`
checks are used instead of `assert`, so `python -O` cannot strip them.

Every argv token is split into its values (comma separated, ",," is a literal
comma, key=value pairs). A value with "/" or under a path key is a path. It is
resolved (symlinks, "..", cwd) and must lie inside probe_dir or a socket dir,
and never at or inside a real work dir.

Run `python3 -I experiments/wide-display/safe_boot.py --self-test` to test it.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import types
from pathlib import Path

REAL_WORK_DIRS = (
    Path("/home/admin/Documents/scripts/manim windows/98artware/work"),
    Path("/home/admin/art98-release-check/98artware/work"),
)

# Read-only system paths VMConfig.argv emits. None: it emits only the bare
# binary name, disk/floppy/wav paths (probe dir) and socket paths (socket dir).
SYSTEM_READONLY: tuple[Path, ...] = ()

_PATH_KEYS = {"file", "path", "filename"}
# Options whose next argv token is a bare file name, even without a "/".
_PATH_OPTS = {
    "-hda", "-hdb", "-hdc", "-hdd", "-cdrom", "-fda", "-fdb", "-mtdblock",
    "-pflash", "-kernel", "-initrd", "-bios", "-dtb", "-drive-file",
}  # fmt: skip


_PREFIX = re.compile(r"^[A-Za-z][\w+.-]*:")


def _real_work() -> list[Path]:
    return [p.resolve() for p in REAL_WORK_DIRS]


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _fields(token: str) -> list[str]:
    """Split a QEMU option on single commas; ",," is a literal comma."""
    out, cur, i = [], [], 0
    while i < len(token):
        if token[i] == ",":
            if token[i + 1 : i + 2] == ",":
                cur.append(",")
                i += 2
                continue
            out.append("".join(cur))
            cur = []
        else:
            cur.append(token[i])
        i += 1
    out.append("".join(cur))
    return out


def _paths(argv: list[str]) -> list[str]:
    """Every argv value that is, or may be, a path."""
    found: list[str] = []
    for i, token in enumerate(argv):
        if i and argv[i - 1] in _PATH_OPTS:
            found.append(token)
        for field in _fields(token):
            key, sep, value = field.partition("=")
            if sep and key.rsplit(".", 1)[-1] in _PATH_KEYS:
                found.append(value)
            text = value if sep else field
            if "/" in text:
                found.append(text)
    return found


def _check_dir(label: str, directory: Path) -> Path:
    """Resolve a directory; reject it if it is, is inside, or contains a real work dir."""
    resolved = Path(directory).resolve()
    for work in _real_work():
        if _inside(resolved, work) or _inside(work, resolved):
            raise AssertionError(f"{label} {resolved} overlaps real work dir {work}")
    return resolved


def check(argv: list[str], probe_dir: Path, socket_dirs: tuple[Path, ...] = ()) -> None:
    """Raise AssertionError unless every path in argv is safe to hand to QEMU."""
    probe = _check_dir("probe dir", probe_dir)
    roots = [probe, *(_check_dir("socket dir", d) for d in socket_dirs)]
    roots += [Path(p).resolve() for p in SYSTEM_READONLY]
    # A bare relative name resolves against cwd, so cwd must not be a real work dir.
    cwd = Path.cwd().resolve()
    work = _real_work()
    if any(_inside(cwd, w) for w in work):
        raise AssertionError(f"cwd {cwd} is inside a real work dir")

    if not any(
        a == "-drive" and i + 1 < len(argv) and "file=" in argv[i + 1]
        for i, a in enumerate(argv)
    ):
        raise AssertionError("argv has no -drive file=... disk path")

    for token in argv:
        if "{" in token or "json:" in token:
            raise AssertionError(f"argv token {token!r} uses json:/{{...}} syntax")

    for value in _paths(argv):
        if value.startswith("unix:"):
            value = value[len("unix:") :]
        elif _PREFIX.match(value):
            raise AssertionError(f"path value {value!r} has a protocol prefix")
        if not value.startswith("/"):
            raise AssertionError(f"path value {value!r} is not absolute")
        target = Path(value).resolve()
        for w in work:
            if _inside(target, w):
                raise AssertionError(f"path {target} is in real work dir {w}")
        if not any(_inside(target, r) for r in roots):
            raise AssertionError(f"path {target} is outside the allowed roots")


_DOCKER_BOOL = {"--rm", "-i", "-t", "-it", "-ti"}
_DOCKER_VAL = {
    "--name", "--user", "--network", "--security-opt", "--cidfile", "-e", "--env",
    "--entrypoint", "-w", "--workdir", "-v", "--volume", "--mount",
}  # fmt: skip
_MOUNT_KEYS = {"type", "src", "source", "dst", "destination", "target", "ro", "readonly"}


def _probe_path(label: str, value: str, probe: Path) -> None:
    """value must be absolute and resolve inside probe, clear of every real work dir."""
    if not value.startswith("/"):
        raise AssertionError(f"{label} {value!r} is not an absolute path")
    target = Path(value).resolve()
    for w in _real_work():
        if _inside(target, w) or _inside(w, target):
            raise AssertionError(f"{label} {target} overlaps real work dir {w}")
    if not _inside(target, probe):
        raise AssertionError(f"{label} {target} is outside probe dir {probe}")


def check_docker(argv: list[str], probe_dir: Path) -> None:
    """Fail-closed allow-list for `docker run` options; call before running it."""
    probe = _check_dir("probe dir", probe_dir)
    if len(argv) < 2 or Path(argv[0]).name not in ("docker", "podman") or argv[1] != "run":
        raise AssertionError("argv is not `docker run ...`")
    i, image = 2, False
    while i < len(argv):
        tok = argv[i]
        if not tok.startswith("-"):
            image = True  # first non-option token is the image; the rest is its command
            break
        flag, eq, val = tok.partition("=")
        if tok in _DOCKER_BOOL:
            i += 1
            continue
        if flag not in _DOCKER_VAL:
            raise AssertionError(f"docker option {tok!r} is not allowed")
        if not eq:
            i += 1
            if i >= len(argv):
                raise AssertionError(f"docker option {flag} has no value")
            val = argv[i]
        i += 1
        if flag == "--network" and val != "none":
            raise AssertionError(f"--network {val!r} is not allowed (only none)")
        elif flag == "--security-opt" and val != "label=disable":
            raise AssertionError(f"--security-opt {val!r} is not allowed")
        elif flag == "--entrypoint" and val not in ("sh", "python3"):
            raise AssertionError(f"--entrypoint {val!r} is not allowed")
        elif flag == "--cidfile":
            _probe_path("--cidfile", val, probe)
        elif flag in ("-e", "--env"):
            name, sep, value = val.partition("=")
            if not sep:
                raise AssertionError(f"env {val!r} must be NAME=VALUE")
            if value.startswith("/"):
                _probe_path(f"env {name}", value, probe)
        elif flag in ("-v", "--volume"):
            src, sep, _ = val.partition(":")
            if not sep:
                raise AssertionError(f"volume {val!r} has no SRC:DST")
            _probe_path("volume source", src, probe)  # a bare name = named volume: rejected
        elif flag == "--mount":
            kv = {}
            for field in _fields(val):
                k, _, v = field.partition("=")
                if k not in _MOUNT_KEYS:
                    raise AssertionError(f"--mount key {k!r} is not allowed")
                if k == "source":
                    k = "src"  # Docker treats source and src as one field
                if k in kv:
                    raise AssertionError(f"--mount key {k!r} appears more than once")
                kv[k] = v
            if kv.get("type") != "bind":
                raise AssertionError("--mount type must be bind")
            src = kv.get("src")
            if src is None:
                raise AssertionError("--mount has no src=")
            _probe_path("--mount source", src, probe)
    if not image:
        raise AssertionError("docker run argv has no image name")


def check_settings(settings, probe_dir: Path) -> None:
    """settings.work_dir (attribute or dict key) must be inside probe_dir."""
    probe = _check_dir("probe dir", probe_dir)
    work = (
        settings.get("work_dir") if isinstance(settings, dict) else getattr(settings, "work_dir", None)
    )
    if work is None:
        raise AssertionError("settings has no work_dir")
    if not str(work).startswith("/"):
        raise AssertionError(f"settings.work_dir {str(work)!r} is not absolute")
    _probe_path("settings.work_dir", str(Path(work).absolute()), probe)


def config_argv(config, qmp: Path, serial: Path, probe_dir: Path) -> list[str]:
    """Build argv with art98's VMConfig.argv, then run check() on it.

    The socket dirs (qmp.parent, serial.parent) are allowed beside probe_dir.
    """
    from art98.qemu import VMConfig

    if not isinstance(config, VMConfig):
        raise TypeError("config must be an art98.qemu.VMConfig")
    qmp, serial = Path(qmp), Path(serial)
    argv = config.argv(qmp, serial)
    check(argv, probe_dir, (qmp.parent, serial.parent))
    return argv


def check_vm(vm, probe_dir: Path) -> None:
    """Call before vm.start(): check the argv start() would use."""
    argv = vm.config.argv(vm.qmp_path, vm.serial_path)
    check(argv, probe_dir, (Path(vm.qmp_path).parent, Path(vm.serial_path).parent))


def check_stage(work_copy: Path, probe_dir: Path) -> None:
    """Call before stage()/private_stage(): the copy and its recorded disk stay in probe_dir."""
    from art98.session import IMAGE_FILE, image_disk

    probe = _check_dir("probe dir", probe_dir)
    copy = _check_dir("work copy", work_copy)
    if not _inside(copy, probe):
        raise AssertionError(f"work copy {copy} is outside probe dir {probe}")
    with open(copy / IMAGE_FILE) as f:
        config = json.load(f)
    disk = image_disk(copy, config).resolve()
    for w in _real_work():
        if _inside(disk, w):
            raise AssertionError(f"image.json disk {disk} is in real work dir {w}")
    if not _inside(disk, probe):
        raise AssertionError(f"image.json disk {disk} is outside probe dir {probe}")


def _import_art98() -> None:
    """Make art98 importable (python -I ignores PYTHONPATH)."""
    try:
        import art98  # noqa: F401
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "core"))


def _self_test() -> None:
    _import_art98()
    from art98.qemu import VMConfig

    real = REAL_WORK_DIRS[0]
    repo = real.parent
    failures: list[str] = []

    def rejects(label: str, fn) -> None:
        try:
            fn()
        except AssertionError:
            print(f"  rejected  {label}")
            return
        failures.append(f"no AssertionError for {label}")

    def accepts(label: str, fn) -> None:
        try:
            fn()
        except AssertionError as exc:
            failures.append(f"clean case {label} rejected: {exc}")
            return
        print(f"  accepted  {label}")

    with tempfile.TemporaryDirectory(prefix="art98-guard-") as tmp:
        probe = Path(tmp) / "probe"
        socks = Path(tmp) / "socks"
        probe.mkdir()
        socks.mkdir()
        disk = probe / "golden.qcow2"

        def argv_for(*extra: str, drive: Path = disk) -> list[str]:
            return [
                "qemu-system-i386",
                "-drive",
                f"file={drive},format=qcow2,if=ide,index=0",
                "-chardev",
                f"socket,id=qmp,path={socks / 'qmp'},server=on,wait=off",
                *extra,
            ]

        def chk(argv: list[str], p: Path = probe) -> None:
            check(argv, p, (socks,))

        def per_work(work: Path) -> None:
            rw = str(work)
            rejects("drive in work dir", lambda: chk(argv_for(drive=work / "g.qcow2")))
            rejects("-hdb ..", lambda: chk(argv_for("-hdb", f"{repo}/x/../work/g")))
            rejects("-hdb .", lambda: chk(argv_for("-hdb", f"{repo}/./work/g")))
            rejects("-cdrom", lambda: chk(argv_for("-cdrom", f"{rw}/g.iso")))
            rejects(
                "-blockdev file.filename=",
                lambda: chk(
                    argv_for("-blockdev", f"driver=qcow2,file.filename={rw}/g")
                ),
            )
            rejects(
                "-blockdev filename= ..",
                lambda: chk(
                    argv_for("-blockdev", f"driver=file,filename={repo}/a/../work/g")
                ),
            )
            rejects("-loadvm path", lambda: chk(argv_for("-loadvm", f"{rw}/snap")))
            esc = rw.replace(",", ",,")
            rejects(
                ",, escaping",
                lambda: chk(argv_for("-drive", f"file={esc}/g,if=ide,index=1")),
            )
            rejects(
                "work dir itself",
                lambda: chk(argv_for("-hdb", rw)),
            )

        for work_dir in REAL_WORK_DIRS:
            per_work(work_dir)
        rejects(
            "relative path from cwd",
            lambda: _in_cwd(
                repo.parent, lambda: chk(argv_for("-hdb", "98artware/work/g"))
            ),
        )
        w0 = str(real)

        def in_probe(argv: list[str]) -> None:
            _in_cwd(probe, lambda: chk(argv))

        js = json.dumps(
            {
                "driver": "qcow2",
                "file": {"driver": "file", "filename": f"{w0}/golden.qcow2"},
            }
        )
        rejects(
            "cwd=probe -hdb fat:rw:W",
            lambda: in_probe(argv_for("-hdb", f"fat:rw:{w0}")),
        )
        rejects(
            "cwd=probe -drive file=fat:rw:W",
            lambda: in_probe(argv_for("-drive", f"file=fat:rw:{w0},format=raw")),
        )
        rejects(
            "cwd=probe -hdb file:W/g",
            lambda: in_probe(argv_for("-hdb", f"file:{w0}/golden.qcow2")),
        )
        rejects(
            "cwd=probe -hdb json:{...}",
            lambda: in_probe(argv_for("-hdb", "json:" + js)),
        )
        rejects(
            "cwd=probe -drive file=json:{...}",
            lambda: in_probe(argv_for("-drive", f"file=json:{js},if=ide")),
        )
        rejects(
            "cwd=probe relative path", lambda: in_probe(argv_for("-hdb", "x/y.img"))
        )
        rejects(
            "cwd=probe relative -hda name", lambda: in_probe(argv_for("-hda", "y.img"))
        )
        accepts(
            "unix: socket prefix",
            lambda: chk(argv_for("-chardev", f"socket,id=q,path=unix:{socks}/q")),
        )
        rejects(
            "bare name from cwd in work",
            lambda: _in_cwd(real, lambda: chk(argv_for("-hda", "g"))),
        )
        link = probe / "link.qcow2"
        link.symlink_to(real / "golden.qcow2")
        rejects(
            "symlink in probe dir to real disk",
            lambda: chk(argv_for("-hdb", str(link))),
        )
        rejects("path outside probe dir", lambda: chk(argv_for("-hdb", "/elsewhere/g")))
        rejects("probe dir is repo root", lambda: chk(argv_for(), repo))
        rejects("probe dir is parent of repo", lambda: chk(argv_for(), repo.parent))
        rejects("probe dir is $HOME", lambda: chk(argv_for(), Path.home()))
        rejects("probe dir is work dir", lambda: chk(argv_for(), real))
        rejects("probe dir inside work dir", lambda: chk(argv_for(), real / "runs"))
        rejects("socket dir is repo root", lambda: check(argv_for(), probe, (repo,)))
        accepts("clean argv", lambda: chk(argv_for("-hdb", str(probe / "x.img"))))
        accepts(
            ",, in clean path",
            lambda: chk(
                argv_for(
                    "-drive",
                    f"file={(probe / 'a,b').as_posix().replace(',', ',,')},if=ide,index=1",
                )
            ),
        )

        # config_argv / check_vm through VMConfig.
        qmp, serial = socks / "qmp", socks / "serial"
        good = VMConfig(disk=disk)
        accepts("config_argv", lambda: config_argv(good, qmp, serial, probe))
        bad = VMConfig(disk=disk, extra_args=["-hdb", f"{repo}/x/../work/g"])
        rejects(
            "config_argv extra_args ..", lambda: config_argv(bad, qmp, serial, probe)
        )
        rejects(
            "config_argv probe dir = repo root",
            lambda: config_argv(good, qmp, serial, repo),
        )
        rejects(
            "config_argv non-VMConfig",
            lambda: _typeerr(lambda: config_argv(object(), qmp, serial, probe)),
        )
        vm = types.SimpleNamespace(config=good, qmp_path=qmp, serial_path=serial)
        accepts("check_vm", lambda: check_vm(vm, probe))
        vm_bad = types.SimpleNamespace(config=bad, qmp_path=qmp, serial_path=serial)
        rejects("check_vm extra_args ..", lambda: check_vm(vm_bad, probe))

        # check_stage with image.json files.
        copy = probe / "copy"
        copy.mkdir()
        (copy / "g.qcow2").touch()

        def write_image(disk_value: str) -> None:
            (copy / "image.json").write_text(json.dumps({"disk": disk_value}))

        write_image(str(copy / "g.qcow2"))
        accepts("check_stage", lambda: check_stage(copy, probe))
        write_image(str(real / "golden.qcow2"))
        rejects(
            "check_stage image.json names real disk", lambda: check_stage(copy, probe)
        )
        write_image(f"{repo}/x/../work/golden.qcow2")
        rejects("check_stage image.json disk with ..", lambda: check_stage(copy, probe))
        write_image(str(copy / "g.qcow2"))
        rejects("check_stage copy outside probe", lambda: check_stage(copy, socks))
        rejects("check_stage probe = repo root", lambda: check_stage(copy, repo))
        rejects("check_stage copy is real work", lambda: check_stage(real, probe))

        # check_docker / check_settings.
        pd = str(probe)
        (probe / "d").mkdir()
        base = ["docker", "run", "--rm", "--name", "a1", "--network", "none"]

        def dk(*extra: str, image: str = "img") -> None:
            check_docker([*base, *extra, image, "true"], probe)

        accepts(
            "docker allowed argv",
            lambda: dk(
                "--security-opt=label=disable", "--user", "1000:1000", "-w", "/w",
                "-e", f"WORK={pd}/d", "-e", "X=1", "--cidfile", f"{pd}/cid",
                "-v", f"{pd}/d:/m:ro", "--volume", f"{pd}/d:/n",
                "--mount", f"type=bind,src={pd}/d,dst=/o,readonly",
            ),
        )  # fmt: skip
        rejects("docker not run", lambda: check_docker(["docker", "ps"], probe))
        rejects("docker --privileged", lambda: dk("--privileged"))
        accepts("docker --entrypoint sh", lambda: dk("--entrypoint", "sh"))
        rejects("docker --entrypoint other", lambda: dk("--entrypoint=/bin/evil"))
        rejects("docker --device", lambda: dk("--device", "/dev/kvm"))
        rejects("docker --device=", lambda: dk("--device=/dev/kvm"))
        rejects("docker --volumes-from", lambda: dk("--volumes-from", "x"))
        rejects("docker --cap-add", lambda: dk("--cap-add=SYS_ADMIN"))
        rejects("docker --pid", lambda: dk("--pid", "host"))
        rejects("docker --ipc", lambda: dk("--ipc=host"))
        rejects("docker --network host", lambda: dk("--network", "host"))
        rejects("docker --network=host", lambda: dk("--network=host"))
        rejects("docker --env-file", lambda: dk("--env-file", f"{pd}/e"))
        rejects("docker -e NAME only", lambda: dk("-e", "HOME"))
        rejects("docker --security-opt other", lambda: dk("--security-opt", "seccomp=unconfined"))
        rejects("docker no image", lambda: check_docker([*base], probe))
        rejects("docker probe dir is work", lambda: check_docker([*base, "img"], real))
        rejects("docker named volume", lambda: dk("-v", "vol:/m"))
        rejects("docker anonymous volume", lambda: dk("-v", "/m"))
        rejects("docker -v=SRC:DST named", lambda: dk("-v=vol:/m"))
        rejects("docker mount type=volume", lambda: dk("--mount", f"type=volume,src={pd}/d,dst=/m"))
        rejects("docker mount no type", lambda: dk("--mount", f"src={pd}/d,dst=/m"))
        rejects("docker mount named", lambda: dk("--mount", "type=bind,src=vol,dst=/m"))
        rejects("docker mount extra key", lambda: dk("--mount", f"type=bind,src={pd}/d,dst=/m,bind-propagation=shared"))
        rejects("docker mount type dup", lambda: dk("--mount", f"type=bind,type=volume,src={pd}/d,dst=/x"))
        rejects("docker -v outside probe", lambda: dk("-v", "/tmp:/m"))
        rejects("docker -v relative", lambda: dk("-v", "d:/m"))
        rejects("docker cidfile outside", lambda: dk("--cidfile", "/tmp/cid"))
        rejects("docker -e path outside", lambda: dk("-e", "P=/etc"))
        (probe / "wlink").symlink_to(real)
        for wk in REAL_WORK_DIRS:
            w = str(wk)
            rejects(f"docker --volume {w}", lambda: dk("--volume", f"{w}:/m"))
            rejects(f"docker -v=SRC:DST {w}", lambda: dk(f"-v={w}:/m"))
            rejects(f"docker --volume= {w}", lambda: dk(f"--volume={w}:/m"))
            rejects(f"docker --mount src= {w}", lambda: dk("--mount", f"type=bind,src={w},dst=/m"))
            rejects(f"docker --mount source= {w}", lambda: dk(f"--mount=type=bind,source={w},dst=/m"))
            rejects(f"docker --mount src=probe,source= {w}", lambda: dk("--mount", f"type=bind,src={pd}/d,source={w},dst=/x"))
            rejects(f"docker --mount source=,src= {w}", lambda: dk("--mount", f"type=bind,source={pd}/d,src={w},dst=/x"))
            rejects(f"docker --mount src=dup {w}", lambda: dk("--mount", f"type=bind,src={pd}/d,src={w},dst=/x"))
            rejects(f"settings.work_dir relative {w}", lambda: _in_cwd(repo.parent, lambda: check_settings({"work_dir": os.path.relpath(w, repo.parent)}, probe)))
            rejects(f"docker .. path {w}", lambda: dk("-v", f"{pd}/../../../..{w}:/m"))
            rejects(f"docker -v inside {w}", lambda: dk("-v", f"{w}/runs:/m"))
            rejects(f"docker -v parent of {w}", lambda: dk("-v", f"{wk.parent}:/m"))
            rejects(f"docker cidfile {w}", lambda: dk("--cidfile", f"{w}/cid"))
            rejects(f"docker -e P={w}", lambda: dk("-e", f"P={w}"))
            rejects(f"docker -v symlink {w}", lambda: dk("-v", f"{pd}/wlink:/m" if wk == real else f"{w}:/m"))
            rejects(f"settings.work_dir {w}", lambda: check_settings({"work_dir": w}, probe))
        accepts("settings in probe", lambda: check_settings(types.SimpleNamespace(work_dir=probe / "d"), probe))
        rejects("settings outside probe", lambda: check_settings({"work_dir": "/tmp/x"}, probe))
        rejects("settings relative", lambda: check_settings({"work_dir": "d"}, probe))
        rejects("settings symlink to work", lambda: check_settings({"work_dir": probe / "wlink"}, probe))
        rejects("settings none", lambda: check_settings({}, probe))

    if failures:
        raise SystemExit("self-test FAIL:\n  " + "\n  ".join(failures))
    print("self-test ok")


def _typeerr(fn) -> None:
    try:
        fn()
    except TypeError as exc:
        raise AssertionError(str(exc)) from None


def _in_cwd(directory: Path, fn) -> None:
    old = Path.cwd()
    os.chdir(directory)
    try:
        fn()
    finally:
        os.chdir(old)


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        _self_test()
        sys.exit(0)
    print("usage: safe_boot.py --self-test", file=sys.stderr)
    sys.exit(1)
