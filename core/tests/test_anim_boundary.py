"""Scenes never boot or reach a VM: anim/, actions/ and base/ take a Session."""

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "art98"
FOLDERS = ("anim", "actions", "base")
MODULES = {"service", "container", "qemu"}
BOOTERS = {"stage", "boot", "boot_local"}  # names in session.py that start a VM


def forbidden(tree: ast.AST) -> list[str]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            pairs = [(alias.name, []) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            pairs = [(node.module or "", [alias.name for alias in node.names])]
        else:
            continue
        for module, names in pairs:
            parts = module.split(".")
            if MODULES & set(parts) or set(names) & MODULES:
                found.append(f"{module} {names}")
            if "session" in parts and (BOOTERS | {"*"}) & set(names):
                found.append(f"{module} {names}")
            if names and BOOTERS & set(names) and not module.split(".")[-1]:
                found.append(f"{module} {names}")  # `from . import boot`
    return found


FILES = sorted(p for folder in FOLDERS for p in (PACKAGE / folder).rglob("*.py"))


def test_there_are_files_to_check():
    assert len(FILES) > 5


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(PACKAGE)))
def test_scene_layers_do_not_import_vm_startup(path):
    assert forbidden(ast.parse(path.read_text())) == []


def test_the_check_catches_what_it_should():
    bad = "from ..session import stage\nfrom .. import service\nimport art98.qemu\n"
    assert len(forbidden(ast.parse(bad))) == 3
    assert forbidden(ast.parse("from ..session import Session\n")) == []
