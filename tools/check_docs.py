"""Render every Python sample in docs/scenes on the real image.

    uv run python tools/check_docs.py [--keep DIR] [word ...]

A sample that fails prints its traceback. With --keep (say out/check), each video stays in DIR
so its frames can be looked at. Words pick samples by class name.
`art98 vm start` must be running: the samples render one at a time on the VM service.
"""

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = ("README.md", "tutorial.md", "scene-api.md", "animations.md")
SAMPLE = re.compile(r"```python\n(.*?)```", re.DOTALL)
JSON = re.compile(r"```json\n(.*?)```", re.DOTALL)
SCENE = re.compile(r"^class (\w+)\(Scene\):", re.MULTILINE)


def samples() -> list[tuple[str, str, str]]:
    found = []
    for page in PAGES:
        for code in SAMPLE.findall((ROOT / "docs/scenes" / page).read_text()):
            names = SCENE.findall(code)
            if len(names) != 1:
                raise SystemExit(
                    f"{page}: a sample must hold one scene, found {names}:\n{code}"
                )
            found.append((page, names[0], code))
    return found


def lay_out_state(page: str, code: str, folder: Path) -> None:
    """The tutorial has the reader save states/desk.json and a picture beside the scene."""
    if 'state = "states/desk.json"' not in code:
        return
    picture = ROOT / "examples/mvp/assets/flower.bmp"
    text = (ROOT / "docs/scenes" / page).read_text()
    start = text.find(code)
    before = [m for m in JSON.finditer(text) if start != -1 and m.start() < start]
    if not before:
        raise SystemExit(f"{page}: no json block for states/desk.json")
    state = before[-1].group(1)
    digest = hashlib.sha256(picture.read_bytes()).hexdigest()
    (folder / "states").mkdir(exist_ok=True)
    (folder / "assets").mkdir(exist_ok=True)
    shutil.copy(picture, folder / "assets/flower.bmp")
    (folder / "states/desk.json").write_text(
        state.replace("<sha256 of the file>", digest)
    )


def check_service() -> None:
    """Stop with the service's own message unless `art98 vm status` says it is up."""
    done = subprocess.run(  # noqa: PLW1510
        [
            sys.executable,
            "-m",
            "art98.cli",
            "vm",
            "status",
            "--work",
            str(ROOT / "work"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if done.returncode != 0:
        message = (done.stdout + done.stderr).strip()
        raise SystemExit(message or "art98 vm status failed")
    print(done.stdout, end="")


def run(sample: tuple[str, str, str], folder: Path) -> tuple[str, str]:
    page, name, code = sample
    source = folder / f"{name}.py"
    source.write_text(code)
    lay_out_state(page, code, folder)
    done = subprocess.run(  # noqa: PLW1510
        [
            sys.executable,
            "-m",
            "art98.cli",
            "render",
            str(source),
            name,
            "-o",
            str(folder / f"{name}.mp4"),
            "--work",
            str(ROOT / "work"),
            "--wait",
            "900",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return f"{page}: {name}", "" if done.returncode == 0 else done.stderr[-2000:]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", type=Path)
    parser.add_argument("words", nargs="*")
    args = parser.parse_args()
    check_service()
    chosen = [s for s in samples() if not args.words or s[1] in args.words]
    with tempfile.TemporaryDirectory() as temp:
        folder = args.keep or Path(temp)
        folder.mkdir(parents=True, exist_ok=True)
        with ThreadPoolExecutor(1) as pool:  # one VM service: one render at a time
            results = list(pool.map(lambda sample: run(sample, folder), chosen))
    failures = 0
    for label, error in results:
        print(("FAIL " if error else "ok   ") + label)
        if error:
            failures += 1
            print(error)
    print(f"{len(results) - failures} of {len(results)} samples rendered")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
