"""`art98 up`: build the container image, then the Windows image inside it.

The image is built from setup/Dockerfile, with the repository root as the build
context. Running a stage in the container afterwards is core's job, in
art98.container.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from art98.container.host import ContainerError, Engine, image_name, mount_args
from art98.container.serve import VNC_PORT
from art98.freshness import container_warning, inspect_created
from art98.settings import load

KEY_SECRET = "art98_key"
ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "setup" / "Dockerfile"


def build_image(engine: Engine, image: str, context: Path = ROOT) -> None:
    """Build the image from setup/Dockerfile. .dockerignore at the root of the
    context keeps work/ and its disk images out.

    Docker CE's CLI talking to a Podman socket builds in a buildx container
    builder and keeps the result in its cache, exit code 0. So the build asks
    for --load where the CLI has it (Podman's own CLI has no such flag), and
    afterwards the engine's image must carry the ID the build reported."""
    dockerfile = Path(context) / "setup" / "Dockerfile"
    if not dockerfile.exists():
        raise ContainerError(f"{dockerfile} not found; build from an art98 checkout")
    load = (
        ["--load"] if b"--load" in engine("build", "--help", check=False).stdout else []
    )
    with tempfile.TemporaryDirectory(prefix="art98-build-") as folder:
        iidfile = Path(folder) / "iid"
        engine(
            "build",
            *load,
            "--iidfile",
            str(iidfile),
            "-t",
            image,
            "-f",
            str(dockerfile),
            str(context),
            capture=False,
        )
        built = iidfile.read_text().strip() if iidfile.exists() else ""
    have = engine("image", "inspect", "--format", "{{.Id}}", image, check=False)
    if not built or have.returncode or _bare(have.stdout.decode()) != _bare(built):
        raise ContainerError(
            f"{engine.name} built {image} but did not store it: its image is not the one just "
            f"built. Docker's CLI against a Podman socket needs buildx's --load; try "
            f"`podman build -t {image} -f {dockerfile} {context}`, or point DOCKER_HOST at the "
            f"engine that should hold the image"
        )


def _bare(image_id: str) -> str:
    return image_id.strip().removeprefix("sha256:")


def _read_key() -> bytes:
    """The product key, from ART98_PRODUCT_KEY or a prompt that doesn't echo.

    Nothing keeps it between runs, so resuming a setup asks again.
    """
    key = os.environ.get("ART98_PRODUCT_KEY", "").strip()
    if not key:
        import getpass

        key = getpass.getpass("Windows 98 product key (not shown): ").strip()
    if not key:
        raise ContainerError(
            "setup needs your product key: set ART98_PRODUCT_KEY or type it"
        )
    return key.encode()


def setup_argv(
    engine: Engine,
    work: Path,
    iso: Path,
    image: str,
    secret: list[str],
    watch: bool = False,
    vnc_port: int | None = None,
    disk_mb: int = 2047,
) -> list[str]:
    vnc_port = vnc_port or load().setup_vnc
    watching = (
        [
            "-p",
            f"{load().bind}:{vnc_port}:{VNC_PORT}",
            "-e",
            f"ART98_WATCH_DISPLAY=vnc=0.0.0.0:{VNC_PORT - 5900}",
        ]
        if watch
        else []
    )
    return [
        engine.path,
        "run",
        "--rm",
        "--init",
        *mount_args(work),
        "-v",
        f"{iso.resolve()}:/media/win98.iso:ro",
        *secret,
        *watching,
        image,
        "setup",
        "--work",
        "/work",
        "--iso",
        "/media/win98.iso",
        "--disk-mb",
        str(disk_mb),
        *(["--watch"] if watch else []),
    ]


def up(
    work: Path | str | None = None,
    iso: Path | str | None = None,
    watch: bool = False,
    rebuild: bool = False,
    vnc_port: int | None = None,
    disk_mb: int = 2047,
    engine: Engine | None = None,
    log=print,
) -> int:
    """`art98 up`: image, key and setup, skipping what is done."""
    engine = engine or Engine()
    image = image_name()
    vnc_port = vnc_port or load().setup_vnc
    work = load(work=work).work_dir  # None: [vm] work from art98.toml
    exists, created = inspect_created(
        engine, image
    )  # one inspect: has_image would be a second
    if rebuild or not exists:
        log(f"[up] building {image} with {engine.name}")
        build_image(engine, image)
    else:
        log(f"[up] image {image} is built")
        for line in container_warning(created, image):
            log(f"[up] warning: {line}")

    guest = ROOT / "guest" / "build"
    if not (guest / "view.exe").exists():
        # Scenes copy VIEW.EXE to the guest from the host, so the host needs it too.
        log(f"[up] copying the guest programs out of the image into {guest}")
        engine.copy_out(image, "/opt/art98/guest/build", guest)

    if not (work / "image.json").exists():
        if iso is None:
            raise ContainerError(
                f"{work} has no prepared image yet; pass --iso with your disc"
            )
        iso = Path(iso)
        if not iso.is_file():
            raise FileNotFoundError(f"{iso} not found")
        work.mkdir(parents=True, exist_ok=True)
        secret, cleanup = engine.secret_args(_read_key(), KEY_SECRET)
        if watch:
            log(f"[up] watch setup with a VNC viewer at {load().bind}:{vnc_port}")
        log("[up] running setup in the container; this takes about 40 minutes")
        try:
            code = subprocess.run(  # noqa: PLW1510
                setup_argv(engine, work, iso, image, secret, watch, vnc_port, disk_mb)
            ).returncode
        finally:
            cleanup()
        if code != 0:
            log(
                f"[up] setup stopped with status {code}; run `art98 up` again to resume"
            )
            return code
    else:
        log(f"[up] {work / 'image.json'} exists, so setup is done")

    log(f"[up] ready. Start the VM with: art98 vm start --work {work}")
    return 0
