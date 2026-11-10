"""Render every Python sample in docs/scenes on the real image.

    uv run python artware_experiments/check_docs.py [--keep DIR] [word ...]

A sample that fails prints its traceback. With --keep, each video stays in DIR
so its frames can be looked at. Words pick samples by class name.
"""

import argparse
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = ("README.md", "tutorial.md", "scene-api.md", "animations.md")
SAMPLE = re.compile(r"```python\n(.*?)```", re.S)
SCENE = re.compile(r"^class (\w+)\(Scene\):", re.M)


def samples() -> list[tuple[str, str, str]]:
    found = []
    for page in PAGES:
        for code in SAMPLE.findall((ROOT / "docs/scenes" / page).read_text()):
            names = SCENE.findall(code)
            if len(names) != 1:
                raise SystemExit(f"{page}: a sample must hold one scene, found {names}:\n{code}")
            found.append((page, names[0], code))
    return found


def run(sample: tuple[str, str, str], folder: Path) -> tuple[str, str]:
    page, name, code = sample
    source = folder / f"{name}.py"
    source.write_text(code)
    done = subprocess.run(
        [sys.executable, "-m", "art98.cli", "render", str(source), name,
         "-o", str(folder / f"{name}.mp4"), "--work", str(ROOT / "work")],
        cwd=ROOT, capture_output=True, text=True,
    )
    return f"{page}: {name}", "" if done.returncode == 0 else done.stderr[-2000:]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", type=Path)
    parser.add_argument("words", nargs="*")
    args = parser.parse_args()
    chosen = [s for s in samples() if not args.words or s[1] in args.words]
    with tempfile.TemporaryDirectory() as temp:
        folder = args.keep or Path(temp)
        folder.mkdir(parents=True, exist_ok=True)
        with ThreadPoolExecutor(3) as pool:
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
