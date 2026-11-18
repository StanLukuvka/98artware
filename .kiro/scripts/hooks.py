"""The checks behind Kiro's hooks in .kiro/hooks/. Standard library only.

Kiro passes each hook event as JSON on stdin. Exit code 0 means the check passed. Any
other code means it failed: Kiro gives stderr to the agent and, for PreToolUse, blocks
the tool call.

    python3 .kiro/scripts/hooks.py guard   PreToolUse: refuse what AGENTS.md forbids
    python3 .kiro/scripts/hooks.py stop    Stop: check the files this turn changed

The checks run at Stop rather than on each file save: measured with kiro-cli 3.3.0, a
failing PostFileSave hook never reached the agent, while a failing Stop hook did, and the
agent went on to fix what it reported.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTEST = ["uv", "run", "-q", "python", "-m", "pytest", "-q"]
UNIT_TESTS = [
    *PYTEST, "core/tests", "setup/tests", "-x",
    "--ignore=core/tests/test_stage.py", "--ignore=core/tests/test_stage_scenes.py",
    "--ignore=core/tests/test_qemu.py",
]  # fmt: skip
DOCS_TEST = [*PYTEST, "core/tests/test_anim_docs.py"]
WORK = re.compile(r"work(-[^/]*)?/")

# Shell commands AGENTS.md forbids, with what to do instead.
FORBIDDEN = [
    (
        re.compile(r"\bart98\s+(up|setup)\b"),
        (
            "art98 up and art98 setup reinstall Windows (20 to 40 minutes, the user's "
            "own disc). Ask the user to run it, or to disable this hook for the session."
        ),
    ),
    (
        re.compile(r"\bpkill\b.*qemu"),
        (
            "pkill on qemu can match the shell running it. Use `uv run art98 vm stop`, "
            "or kill the VM by its PID."
        ),
    ),
    (
        re.compile(r"\bgit\s+add\b.*(\s|/|^)work(-[^/\s]*)?(/|\s|$)"),
        "work/ holds installed copies of Windows 98 and never goes into git.",
    ),
]


def fail(message: str, code: int = 2) -> None:
    print(message, file=sys.stderr)
    sys.exit(code)


def git(*args: str) -> list[str]:
    done = subprocess.run(
        ["git", *args], check=False, cwd=ROOT, capture_output=True, text=True
    )
    return done.stdout.splitlines()


def relative(path: str) -> str | None:
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return None


def check(cmd: list[str], what: str, timeout: int) -> str | None:
    """Run one check. Returns what went wrong, with the end of its output, or None."""
    try:
        done = subprocess.run(
            cmd, check=False, cwd=ROOT, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return f"{what}: timed out after {timeout} s"
    if done.returncode == 0:
        return None
    tail = (done.stdout + done.stderr).strip().splitlines()[-40:]
    return f"{what} failed:\n" + "\n".join(tail)


def guard(event: dict) -> None:
    tool_input = event.get("tool_input") or {}
    command = tool_input.get("command")
    if isinstance(command, str):
        for pattern, why in FORBIDDEN:
            if pattern.search(command):
                fail(f"Blocked by .kiro/hooks/guard.json: {why}")
        staged = [p for p in git("diff", "--cached", "--name-only") if WORK.match(p)]
        if staged and re.search(r"\bgit\s+commit\b", command):
            fail(
                "Blocked by .kiro/hooks/guard.json: files from work/ are staged "
                f"({', '.join(staged[:5])}). Unstage them; work/ never goes into git."
            )
    path = tool_input.get("path") or tool_input.get("file_path")
    writes = re.search(
        r"write|edit|replace|create|delete|move", event.get("tool_name", "")
    )
    rel = relative(path) if isinstance(path, str) else None
    if writes and rel and WORK.match(rel):
        fail(
            "Blocked by .kiro/hooks/guard.json: work/ is the prepared Windows 98 image. "
            "Read it if you need to, but don't write there."
        )


def changed_files() -> list[str]:
    """Paths with uncommitted changes, untracked files included, that still exist."""
    paths = [
        line[3:].split(" -> ")[-1].strip('"') for line in git("status", "--porcelain")
    ]
    return [p for p in paths if (ROOT / p).is_file()]


def stop(event: dict) -> None:
    changed = changed_files()
    python = [p for p in changed if re.match(r"(core|setup|tools|recipes)/.*\.py$", p)]
    formatted = [p for p in python if re.match(r"(core|setup|tools)/", p)]
    docs = [p for p in changed if re.match(r"docs/scenes/.*\.md$", p)]
    guest = [p for p in changed if re.match(r"guest/.*\.(c|h)$|guest/Makefile$", p)]

    problems = []
    if python:
        problems.append(
            check(["uv", "run", "-q", "ruff", "check", *python], "ruff", 60)
        )
    if formatted:
        ruff_format = ["uv", "run", "-q", "ruff", "format", "--check", *formatted]
        problems.append(check(ruff_format, "ruff format", 60))
    if guest and shutil.which("i686-w64-mingw32-gcc"):
        # The two programs only: mbr.bin needs syslinux, and its source never changes.
        make = ["make", "-C", "guest", "build/agent.exe", "build/view.exe"]
        problems.append(check(make, "make -C guest", 180))
    if python:
        problems.append(check(UNIT_TESTS, "The unit tests (no VM)", 600))
    elif docs:
        problems.append(check(DOCS_TEST, "The scene docs test", 120))

    problems = [p for p in problems if p]
    if problems:
        # 1, not 2: with kiro-cli 3.3.0 a Stop hook's stderr reached the agent on exit
        # code 1, and not on 2.
        fail("\n\n".join(problems) + "\n\nFix these, then check again.", code=1)
    if python or docs or guest:
        print("Checks passed for the changed files. VM tests were not run.")


def main() -> None:
    hooks = {"guard": guard, "stop": stop}
    if len(sys.argv) != 2 or sys.argv[1] not in hooks:
        sys.exit(f"usage: hooks.py {{{'|'.join(hooks)}}}")
    raw = sys.stdin.read()
    hooks[sys.argv[1]](json.loads(raw) if raw.strip() else {})


if __name__ == "__main__":
    main()
