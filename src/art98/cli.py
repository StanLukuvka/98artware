"""Command line entry point."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import prep
from .session import boot


def _guest_build() -> Path:
    return Path(__file__).resolve().parents[2] / "guest" / "build"


def cmd_doctor(_args) -> int:
    missing = []
    for tool, path, package in prep.doctor():
        print(f"{tool:24} {path or 'missing'}")
        if not path:
            missing.append(package)
    print(f"{'/dev/kvm':24} not used: Windows 98 runs under software emulation")
    if missing:
        print("\nInstall the missing tools with:")
        print(f"  sudo dnf install {' '.join(missing)}")
        return 1
    return 0


def cmd_prep(args) -> int:
    key = args.key or os.environ.get("ART98_PRODUCT_KEY")
    tool = prep.Prep(
        work=args.work, guest_build=_guest_build(), iso=args.iso, product_key=key,
        disk_mb=args.disk_mb, watch=args.watch,
    )
    try:
        tool.run(args.from_stage)
    except prep.PrepError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"Ready: {Path(args.work).resolve()}")
    return 0


def cmd_ping(args) -> int:
    with boot(args.work) as session:
        print(f"guest tick count: {session.bridge.ping()}")
        for pid, name in session.bridge.processes():
            print(f"{pid:#010x} {name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="art98")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("doctor", help="check the host tools").set_defaults(run=cmd_doctor)

    command = commands.add_parser("prep", help="build the prepared Windows 98 image")
    command.add_argument("--iso", type=Path, help="your Windows 98 SE disc image")
    command.add_argument("--key", help="product key, or set ART98_PRODUCT_KEY")
    command.add_argument("--work", type=Path, default=Path("work"))
    command.add_argument("--disk-mb", type=int, default=2047)
    command.add_argument("--from", dest="from_stage", choices=prep.Prep.STAGES,
                         help="redo this stage and everything after it")
    command.add_argument("--watch", action="store_true", help="show the VM's screen")
    command.set_defaults(run=cmd_prep)

    command = commands.add_parser("ping", help="boot the image and talk to the agent")
    command.add_argument("--work", type=Path, default=Path("work"))
    command.set_defaults(run=cmd_ping)

    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
