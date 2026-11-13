"""`art98 up`: build the container image, then the Windows image inside it.

Both run through compose (see compose.yaml and art98.container.compose): the
image is built from setup/Dockerfile with the repository root as the build
context, and the install runs once in the `setup` service. Running the VM
afterwards is core's job, in art98.service.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from art98.container import compose
from art98.container.host import ContainerError, Engine
from art98.freshness import container_warning, inspect_created
from art98.settings import Settings, load

KEY_ENV = "ART98_PRODUCT_KEY"
DISC = "/media/win98.iso"  # where the setup service mounts the disc
ROOT = compose.ROOT


def build_image(engine: Engine, settings: Settings) -> None:
    """Build the image from setup/Dockerfile. .dockerignore at the root of the
    context keeps work/ and its disk images out.

    A build that leaves no image under the name fails loudly: Docker's CLI against
    a Podman socket used to keep the result in a buildx builder's cache."""
    compose.run(engine, settings, "build", "vm", capture=False)
    if not engine.has_image(settings.image):
        raise ContainerError(
            f"{engine.name} built {settings.image} but did not store it; point "
            "DOCKER_HOST at the engine that should hold the image"
        )


def _read_key() -> str:
    """The product key from a visible prompt. Nothing keeps it between runs, so
    resuming a setup asks again, unless compose.override.yaml names a key file."""
    key = input("Windows 98 product key: ").strip()
    if not key:
        raise ContainerError(
            f"setup needs your product key: type it, set {KEY_ENV}, or name a key "
            "file in compose.override.yaml"
        )
    return key


def setup_inputs(engine: Engine, settings: Settings, iso, disk_mb: int) -> dict:
    """The variables `compose run setup` needs, once the disc and key are known to
    be there. Compose would otherwise fail half way and leave a container behind.

    The disc is --iso, or the mount in compose.override.yaml. The key is the key
    file compose.override.yaml names, else ART98_PRODUCT_KEY, else a prompt."""
    extra = {"ART98_DISK_MB": str(disk_mb)}
    if iso is not None:
        extra["ART98_ISO"] = str(Path(iso).resolve())
    done = compose.run(
        engine, settings, "--profile", "setup", "config", "--format", "json",
        extra=extra,
    )  # fmt: skip
    config = json.loads(done.stdout)
    disc = next(
        (v.get("source") for v in config["services"]["setup"].get("volumes", [])
         if v.get("target") == DISC),
        None,
    )  # fmt: skip
    if iso is not None and disc != extra["ART98_ISO"]:
        raise ContainerError(
            f"compose.override.yaml mounts the disc {disc}; drop --iso or that mount"
        )
    if not disc or not Path(disc).is_file():
        raise FileNotFoundError(
            f"no disc at {disc}: pass --iso with your Windows 98 SE disc image, or "
            "mount it in compose.override.yaml"
        )
    secret = config.get("secrets", {}).get("art98_key", {})
    if "file" in secret:
        if not Path(secret["file"]).is_file():
            raise FileNotFoundError(
                f"no product key file at {secret['file']}, which "
                "compose.override.yaml names"
            )
    elif not os.environ.get(KEY_ENV, "").strip():
        extra[KEY_ENV] = _read_key()  # compose.yaml's art98_key reads KEY_ENV
    return extra


def up(
    work: Path | str | None = None,
    iso: Path | str | None = None,
    rebuild: bool = False,
    disk_mb: int = 2047,
    engine: Engine | None = None,
    log=print,
) -> int:
    """`art98 up`: image, key and setup, skipping what is done."""
    engine = engine or Engine()
    settings = load(work=work)  # None: [vm] work from art98.toml
    image, work = settings.image, settings.work_dir
    exists, created = inspect_created(
        engine, image
    )  # one inspect: has_image would be a second
    if rebuild or not exists:
        log(f"[up] building {image} with {engine.name} compose")
        build_image(engine, settings)
    else:
        log(f"[up] image {image} is built")
        for line in container_warning(created, image):
            log(f"[up] warning: {line}")

    guest = ROOT / "guest" / "build"
    if not (guest / "view.exe").exists() or not (guest / "sources.sha256").exists():
        # Scenes copy VIEW.EXE to the guest from the host, so the host needs it too.
        log(f"[up] copying the guest programs out of the image into {guest}")
        engine.copy_out(image, "/opt/art98/guest/build", guest)

    if (work / "image.json").exists():
        log(f"[up] {work / 'image.json'} exists, so setup is done")
    else:
        extra = setup_inputs(engine, settings, iso, disk_mb)
        work.mkdir(parents=True, exist_ok=True)
        log(
            "[up] running setup in the container; this usually takes 20 to 30 minutes, longer on a busy host"
        )
        code = compose.run(
            engine, settings, "run", "--rm", "--service-ports", "setup",
            extra=extra, check=False, capture=False,
        ).returncode  # fmt: skip
        if code != 0:
            log(
                f"[up] setup stopped with status {code}; see the error above, then run "
                "`art98 up` again"
            )
            return code

    log(f"[up] ready. Start the VM with: art98 vm start --work {work}")
    return 0
