"""Command line entry point."""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path

from .container.host import ContainerError
from .guestfiles import guest_build
from .session import BACKENDS, GIF_COLORS, GIF_FPS, ImageMissing, boot

KEY_SECRET_FILE = Path("/run/secrets/art98_key")


def cmd_doctor(_args) -> int:
    import shutil

    from art98_setup import builder

    missing = []
    for tool, path, package in builder.doctor():
        print(f"{tool:24} {path or 'missing'}")
        if not path:
            missing.append(tool)
    print(f"{'/dev/kvm':24} not used: Windows 98 runs under software emulation")
    name = os.environ.get("ART98_ENGINE") or "docker"
    engine = shutil.which(name)
    print(f"{name:24} {engine or 'missing'} (for `art98 up` and the container backend"
          f"{'' if engine else '; on a Podman host, install podman-docker'})")
    if missing:
        print("\nThe local backend needs the missing tools. Install them with one of:")
        for system, command, packages in builder.install_hints(missing):
            print(f"  {system:15} {command} {' '.join(packages)}")
        print("Or skip them: `art98 up` runs QEMU and setup in a container, "
              "and the host then needs only ffmpeg.")
        return 1
    return 0


def _product_key(args) -> str | None:
    if args.key or os.environ.get("ART98_PRODUCT_KEY"):
        return args.key or os.environ.get("ART98_PRODUCT_KEY")
    if KEY_SECRET_FILE.exists():  # mounted in by `art98 up`
        return KEY_SECRET_FILE.read_text().strip() or None
    return None


def cmd_setup(args) -> int:
    from art98_setup.builder import Setup, SetupError

    key = _product_key(args)
    tool = Setup(
        work=args.work, guest_build=guest_build(), iso=args.iso, product_key=key,
        disk_mb=args.disk_mb, watch=args.watch,
    )
    try:
        tool.run(args.from_stage)
    except SetupError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"Ready: {Path(args.work).resolve()}")
    return 0


# Errors from starting a stage that a message explains better than a traceback.
STAGE_ERRORS = (ImageMissing, ContainerError)


def cmd_ping(args) -> int:
    try:
        with boot(args.work, backend=args.backend) as session:
            print(f"guest tick count: {session.bridge.ping()}")
            for pid, name in session.bridge.processes():
                print(f"{pid:#010x} {name}")
    except STAGE_ERRORS as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


def _load_scene(path: Path, name: str | None) -> type:
    """Import a scene file and pick the scene class it defines."""
    from .anim import Scene

    sys.path.insert(0, str(path.resolve().parent))
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    # Registered so a scene can find its own file, for state paths beside it.
    sys.modules.setdefault(path.stem, module)
    spec.loader.exec_module(module)
    scenes = {
        key: value for key, value in vars(module).items()
        if isinstance(value, type) and issubclass(value, Scene) and value.__module__ == path.stem
    }
    if name is None and len(scenes) == 1:
        return next(iter(scenes.values()))
    if name in scenes:
        return scenes[name]
    choices = ", ".join(sorted(scenes)) or "none"
    raise SystemExit(f"error: choose a scene from {path}: {choices}")


def cmd_render(args) -> int:
    from .anim import render

    scene = _load_scene(args.file, args.scene)
    try:
        written = render(
            scene, args.output, gif=args.gif, work=args.work, gif_fps=args.gif_fps,
            gif_colors=args.gif_colors, gif_scale=args.gif_scale, gif_dither=args.gif_dither,
            backend=args.backend,
        )
    except STAGE_ERRORS as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"Wrote {written}" + (f" and {args.gif}" if args.gif else ""))
    return 0


def cmd_serve(args) -> int:
    from .container import serve

    return serve.run(args.work, port=args.port, token_file=args.token_file, vnc=args.vnc,
                     ready_timeout=args.ready_timeout, unix=args.unix)


def cmd_up(args) -> int:
    from art98_setup.up import up

    try:
        return up(args.work, iso=args.iso, watch=args.watch, rebuild=args.rebuild,
                  vnc_port=args.vnc_port, disk_mb=args.disk_mb)
    except (ContainerError, FileNotFoundError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def _backend_option(command) -> None:
    command.add_argument("--backend", choices=BACKENDS,
                         help="run QEMU here (local) or in the art98 container; "
                              "default from ART98_BACKEND, else local")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="art98")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("doctor", help="check the host tools").set_defaults(run=cmd_doctor)

    command = commands.add_parser("setup", aliases=["prep"],
                                  help="build the prepared Windows 98 image")
    command.add_argument("--iso", type=Path, help="your Windows 98 SE disc image")
    command.add_argument("--key", help="product key, or set ART98_PRODUCT_KEY")
    command.add_argument("--work", type=Path, default=Path("work"))
    command.add_argument("--disk-mb", type=int, default=2047)
    command.add_argument("--from", dest="from_stage",
                         help="redo this step and everything after it: vm, setup, init_api or "
                              "ready (the old stage names media, disk, install, patch and "
                              "harden also work)")
    command.add_argument("--watch", action="store_true", help="show the VM's screen")
    command.set_defaults(run=cmd_setup)

    command = commands.add_parser("ping", help="boot the image and talk to the agent")
    command.add_argument("--work", type=Path, default=Path("work"))
    _backend_option(command)
    command.set_defaults(run=cmd_ping)

    command = commands.add_parser("render", help="play a scene and write a video")
    command.add_argument("file", type=Path, help="Python file holding the scene")
    command.add_argument("scene", nargs="?", help="scene class, if the file has several")
    command.add_argument("-o", "--output", type=Path, help="output file, .mp4 or .gif")
    command.add_argument("--gif", type=Path, help="write a GIF as well")
    command.add_argument("--work", type=Path, default=Path("work"))
    command.add_argument("--gif-fps", type=int, default=GIF_FPS)
    command.add_argument("--gif-colors", type=int, default=GIF_COLORS)
    command.add_argument("--gif-scale", type=float, default=1.0)
    command.add_argument("--gif-dither", default="none",
                         help="ffmpeg paletteuse dither: none, bayer, sierra2_4a...")
    _backend_option(command)
    command.set_defaults(run=cmd_render)

    command = commands.add_parser(
        "up", help="from your disc and key to a working desktop, in the art98 container")
    command.add_argument("--iso", type=Path, help="your Windows 98 SE disc image, for setup")
    command.add_argument("--work", type=Path, default=Path("work"))
    command.add_argument("--watch", action="store_true",
                         help="show setup's screen over VNC on a loopback port")
    command.add_argument("--vnc-port", type=int, default=5998)
    command.add_argument("--rebuild", action="store_true", help="rebuild the container image")
    command.add_argument("--disk-mb", type=int, default=2047)
    command.set_defaults(run=cmd_up)

    command = commands.add_parser(
        "serve", help="inside the container: boot a stage and serve it to the host")
    command.add_argument("--work", type=Path, default=Path("/work"))
    command.add_argument("--port", type=int, default=7598)
    command.add_argument("--unix", type=Path, help="listen on this Unix socket instead of TCP")
    command.add_argument("--token-file", type=Path, help="default /run/secrets/art98_token")
    command.add_argument("--vnc", action="store_true", help="show the screen on VNC port 5900")
    command.add_argument("--ready-timeout", type=float, default=60.0)
    command.set_defaults(run=cmd_serve)

    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
