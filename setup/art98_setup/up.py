"""`art98 up`: build the container image, then the Windows image inside it.

The image is built from setup/Dockerfile, with the repository root as the build
context. Running a stage in the container afterwards is core's job, in
art98.container.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from art98.container.host import ContainerError, Engine, boot, image_name, mount_args
from art98.container.serve import VNC_PORT

KEY_SECRET = "art98_key"
ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "setup" / "Dockerfile"


def build_image(engine: Engine, image: str, context: Path = ROOT) -> None:
    """Build the image from setup/Dockerfile. Both engines read .dockerignore at the
    root of the context, which keeps work/ and its disk images out."""
    dockerfile = Path(context) / "setup" / "Dockerfile"
    if not dockerfile.exists():
        raise ContainerError(f"{dockerfile} not found; build from an art98 checkout")
    engine("build", "-t", image, "-f", str(dockerfile), str(context), capture=False)


def _read_key(engine: Engine) -> bytes | None:
    """The product key, from ART98_PRODUCT_KEY or a prompt that doesn't echo.

    None means Podman already holds the secret from an earlier, unfinished run.
    """
    key = os.environ.get("ART98_PRODUCT_KEY", "").strip()
    if not key and engine.is_podman and engine(
            "secret", "exists", KEY_SECRET, check=False).returncode == 0:
        return None
    if not key:
        import getpass

        key = getpass.getpass("Windows 98 product key (not shown): ").strip()
    if not key:
        raise ContainerError("setup needs your product key: set ART98_PRODUCT_KEY or type it")
    return key.encode()


def setup_argv(engine: Engine, work: Path, iso: Path, image: str, secret: list[str],
               watch: bool = False, vnc_port: int = 5998, disk_mb: int = 2047) -> list[str]:
    watching = (["-p", f"127.0.0.1:{vnc_port}:{VNC_PORT}",
                 "-e", f"ART98_WATCH_DISPLAY=vnc=0.0.0.0:{VNC_PORT - 5900}"] if watch else [])
    return [
        engine.path, "run", "--rm", "--init", *mount_args(work),
        "-v", f"{iso.resolve()}:/media/win98.iso:ro", *secret, *watching,
        image, "setup", "--work", "/work", "--iso", "/media/win98.iso",
        "--disk-mb", str(disk_mb), *(["--watch"] if watch else []),
    ]


def up(work: Path | str = "work", iso: Path | str | None = None, watch: bool = False,
       rebuild: bool = False, vnc_port: int = 5998, disk_mb: int = 2047,
       engine: Engine | None = None, log=print) -> int:
    """`art98 up`: image, key, setup and a first boot, skipping what is done."""
    engine = engine or Engine()
    image = image_name()
    work = Path(work).resolve()
    if rebuild or not engine.has_image(image):
        log(f"[up] building {image} with {engine.name}")
        build_image(engine, image)
    else:
        log(f"[up] image {image} is built")

    guest = ROOT / "guest" / "build"
    if not (guest / "view.exe").exists():
        # Scenes copy VIEW.EXE to the guest from the host, so the host needs it too.
        log(f"[up] copying the guest programs out of the image into {guest}")
        engine.copy_out(image, "/opt/art98/guest/build", guest)

    if not (work / "image.json").exists():
        if iso is None:
            raise ContainerError(f"{work} has no prepared image yet; pass --iso with your disc")
        iso = Path(iso)
        if not iso.is_file():
            raise FileNotFoundError(f"{iso} not found")
        work.mkdir(parents=True, exist_ok=True)
        key = _read_key(engine)
        if key is None:
            log(f"[up] using the product key already stored as the secret {KEY_SECRET}")
            secret, cleanup = ["--secret", f"{KEY_SECRET},target={KEY_SECRET}"], lambda: None
        else:
            secret, cleanup = engine.secret_args(KEY_SECRET, key, KEY_SECRET, keep=True)
        if watch:
            log(f"[up] watch setup with a VNC viewer at 127.0.0.1:{vnc_port}")
        log("[up] running setup in the container; this takes about 40 minutes")
        try:
            code = subprocess.run(setup_argv(engine, work, iso, image, secret, watch,
                                             vnc_port, disk_mb)).returncode
        finally:
            cleanup()
        if code != 0:
            log(f"[up] setup stopped with status {code}; run `art98 up` again to resume")
            return code
        # The key is in the finished image; the secret store needn't keep a copy.
        engine.remove_secret(KEY_SECRET)
    else:
        log(f"[up] {work / 'image.json'} exists, so setup is done")

    log("[up] booting a stage in the container")
    with boot(work, engine=engine) as session:
        log(f"[up] the agent answered: guest tick count {session.bridge.ping()}")
    log(f"[up] ready. Render with: ART98_BACKEND=container art98 render SCENE.py --work {work}")
    return 0
