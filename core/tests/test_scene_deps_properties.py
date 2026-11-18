"""Property tests for the recorded paths and the recorded-files dict of a Scene."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from art98.cli import _load_scene
from hypothesis import given, settings
from hypothesis import strategies as st

NAME = st.text(alphabet="abcdefgh_-.0123", min_size=1, max_size=6).filter(
    lambda s: s not in (".", "..")
)
RELATIVE = st.lists(NAME, min_size=1, max_size=4).map("/".join)


def make_scene(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    file = folder / "scene_props.py"
    file.write_text("from art98.anim import *\nclass T(Scene):\n    pass\n")
    return _load_scene(file, None)()


@settings(deadline=None, max_examples=40)
@given(rel=RELATIVE)
def test_a_record_resolves_back_and_survives_moving_the_folder(rel):
    """**Validates: Requirements 1.9, 1.10**"""
    root = Path(tempfile.mkdtemp()).resolve()
    try:
        scene = make_scene(root / "one")
        record = scene._recorded_path(root / "one" / rel)
        assert record == rel
        assert "\\" not in record and not record.startswith("/")
        assert ".." not in record.split("/")
        assert scene._resolve_recorded(record) == (root / "one" / rel).resolve()
        shutil.copytree(root / "one", root / "two")
        moved = make_scene(root / "two")
        assert moved._recorded_path(root / "two" / rel) == record
        outside = root / "elsewhere" / rel
        absolute = scene._recorded_path(outside)
        assert absolute.startswith("/") or ":" in absolute
        assert scene._resolve_recorded(absolute) == outside.resolve()
    finally:
        shutil.rmtree(root, ignore_errors=True)


@settings(deadline=None, max_examples=40)
@given(names=st.lists(NAME, max_size=12))
def test_each_file_is_recorded_once_in_first_seen_order(names):
    """**Validates: Requirements 1.6, 2.5**"""
    root = Path(tempfile.mkdtemp()).resolve()
    try:
        scene = make_scene(root)
        scene._deps = {}
        for index, name in enumerate(names):
            scene._depend(root / name, f"{index:064x}")
        first = list(dict.fromkeys(names))
        assert list(scene._deps) == first
        for name in first:
            assert scene._deps[name] == f"{names.index(name):064x}"
    finally:
        shutil.rmtree(root, ignore_errors=True)
