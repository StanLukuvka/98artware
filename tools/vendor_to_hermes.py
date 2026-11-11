"""Copy the art98 library into the Hermes plugin's vendor/ folder.

    uv run python tools/vendor_to_hermes.py ../hermes-plugin

The catalog pins the plugin's commit, so the library it runs has to be inside the plugin.
Only core/art98's .py files are copied (no tests, no caches, not the VM image's entrypoint,
nothing from guest/: the guest programs are binaries and stay a mount). vendor/VENDORED.md records the source commit, and
the copy is refused while core/art98 has uncommitted changes, so that record is true.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LIBRARY = REPO / "core" / "art98"
# Run only inside the VM image (as its entrypoint), never by a client. It drops root with
# setuid/setgid, which Hermes's catalog scanner flags, so it stays out of the plugin.
SKIP = {Path("container/entry.py")}


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(REPO), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "plugin", type=Path, help="the plugin folder (holds plugin.yaml)"
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="copy uncommitted work too, for testing (VENDORED.md says so)",
    )
    args = parser.parse_args(argv)
    plugin = args.plugin.resolve()
    if not (plugin / "plugin.yaml").is_file():
        print(f"error: no plugin.yaml in {plugin}", file=sys.stderr)
        return 2
    dirty = bool(_git("status", "--porcelain", "--", "core/art98"))
    if dirty and not args.allow_dirty:
        print(
            "error: core/art98 has uncommitted changes; commit them first",
            file=sys.stderr,
        )
        return 1
    commit = _git("rev-parse", "HEAD")
    version = next(
        line.split('"')[1]
        for line in (REPO / "pyproject.toml").read_text().splitlines()
        if line.startswith("version")
    )

    target = plugin / "vendor" / "art98"
    if target.exists():
        shutil.rmtree(target)
    files = sorted(
        p
        for p in LIBRARY.rglob("*.py")
        if "__pycache__" not in p.parts and p.relative_to(LIBRARY) not in SKIP
    )
    for src in files:
        dst = target / src.relative_to(LIBRARY)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    shutil.copyfile(REPO / "LICENSE", plugin / "vendor" / "LICENSE")
    (plugin / "vendor" / "VENDORED.md").write_text(
        "# Vendored: art98\n\n"
        "`art98/` is the art98 library, copied "
        + (
            "with uncommitted changes, for testing, from a checkout of\n"
            if dirty
            else "unchanged from\n"
        )
        + f"https://github.com/StanLukuvka/98artware/tree/{commit}/core/art98\n"
        "by `tools/vendor_to_hermes.py` in that repo (without the VM image's entrypoint).\n"
        "Don't edit it here: change art98 and copy it again. Licence: MIT, see `LICENSE`.\n\n"
        f"version: {version}\n"
        f"commit: {commit}{' plus uncommitted changes (a test copy)' if dirty else ''}\n",
        encoding="utf-8",
    )
    print(f"copied {len(files)} files from {commit[:7]} into {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
