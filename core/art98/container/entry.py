"""The image's entry point: become the host's user if need be, then run art98.

What a file written to the work folder ends up owned by depends on the engine.
Under a rootless engine (Podman, rootless Docker) the container's root is the
host user already, so nothing changes. Under a rootful one (plain Docker) it
is the host's real root, and the work folder would fill with root-owned files.
So the host always passes its uid and gid as ART98_HOST_UID and ART98_HOST_GID,
and this module drops to them when the container's user namespace is the
host's own: /proc/self/uid_map then maps all of 0 to 4294967295 onto itself.
The host never asks which engine it is talking to.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

UID_MAP = Path("/proc/self/uid_map")
# The initial user namespace: every id maps onto itself.
IDENTITY = [0, 0, 4294967295]


def is_rootful(uid_map: str) -> bool:
    """True when uid_map is the identity map, so root here is the host's root."""
    lines = [line.split() for line in uid_map.splitlines() if line.strip()]
    return len(lines) == 1 and [int(field) for field in lines[0]] == IDENTITY


def host_user(environ, uid_map: str, uid: int) -> tuple[int, int] | None:
    """The uid and gid to drop to, or None to stay as we are.

    Drop only as root, on a rootful engine, to a host user that isn't root.
    """
    try:
        wanted = int(environ["ART98_HOST_UID"]), int(environ["ART98_HOST_GID"])
    except (KeyError, ValueError):
        return None
    if uid != 0 or wanted[0] == 0 or not is_rootful(uid_map):
        return None
    return wanted


def become_host_user(environ=os.environ, uid_map_path: Path = UID_MAP) -> None:
    try:
        uid_map = uid_map_path.read_text()
    except OSError:
        return
    user = host_user(environ, uid_map, os.getuid())
    if user is None:
        return
    uid, gid = user
    os.setgroups([])
    os.setgid(gid)
    os.setuid(uid)
    # root's home isn't ours any more.
    environ["HOME"] = "/tmp"


def main() -> int:
    become_host_user()
    from art98.cli import main as cli

    return cli(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
