"""Property tests for a capture's meta file: reading it and checking its dependency files."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import pytest
from art98.anim.scene import _read_meta
from art98.cli import _load_scene
from art98.errors import MissingFile, UsageError
from hypothesis import given, settings
from hypothesis import strategies as st

HEX = st.text(alphabet="0123456789abcdef", min_size=64, max_size=64)
NAME = st.text(alphabet="abcdefgh_-.0123", min_size=1, max_size=6).filter(
    lambda s: s not in (".", "..")
)
RELATIVE = st.lists(NAME, min_size=1, max_size=3).map("/".join)
ABSOLUTE = RELATIVE.map(lambda s: "/outside/" + s)
RECORDS = st.lists(
    st.tuples(st.one_of(RELATIVE, ABSOLUTE), HEX), max_size=6, unique_by=lambda r: r[0]
)
HASHES = st.dictionaries(NAME, st.one_of(st.none(), HEX), max_size=4)
TIME = st.floats(min_value=0, max_value=1e6, allow_nan=False)


def meta_text(time, hashes, capture, records) -> str:
    meta = {
        "time": time,
        "hashes": hashes,
        "capture": capture,
        "files": [{"path": p, "sha256": h} for p, h in records],
    }
    return json.dumps(meta, indent=2, sort_keys=True) + "\n"


def read(text: str):
    folder = Path(tempfile.mkdtemp())
    try:
        path = folder / "m.json"
        path.write_text(text)
        return _read_meta(path, "b", folder)
    finally:
        shutil.rmtree(folder, ignore_errors=True)


@settings(deadline=None, max_examples=60)
@given(time=TIME, hashes=HASHES, capture=HEX, records=RECORDS)
def test_a_meta_file_reads_back_as_written_with_the_same_bytes(
    time, hashes, capture, records
):
    """**Validates: Requirements 1.8, 2.5**"""
    text = meta_text(time, hashes, capture, records)
    got = read(text)
    assert got == (time, hashes, capture, records)
    assert meta_text(*got[:2], got[2], got[3]) == text


JSON = st.recursive(
    st.none() | st.booleans() | st.integers(-5, 5) | st.text(max_size=5) | HEX,
    lambda inner: (
        st.lists(inner, max_size=3)
        | st.dictionaries(st.text(max_size=5), inner, max_size=3)
    ),
    max_leaves=6,
)
ENTRY = st.one_of(
    JSON,
    st.fixed_dictionaries(
        {"path": st.one_of(RELATIVE, ABSOLUTE, JSON), "sha256": st.one_of(HEX, JSON)}
    ),
)
FIELD = st.one_of(
    st.just(None),  # absent
    JSON,
)


@settings(deadline=None, max_examples=200)
@given(
    time=st.one_of(TIME, FIELD),
    hashes=st.one_of(HASHES, FIELD),
    capture=st.one_of(HEX, FIELD),
    files=st.one_of(st.lists(ENTRY, max_size=4), FIELD),
)
def test_a_malformed_meta_file_never_crashes_the_reader(time, hashes, capture, files):
    """**Validates: Requirements 3.1, 3.2**"""
    meta = {"time": time, "hashes": hashes, "capture": capture, "files": files}
    present = {k: v for k, v in meta.items() if v is not None}
    try:
        got = read(json.dumps(present))
    except (MissingFile, UsageError):
        return
    assert isinstance(got[0], float) and isinstance(got[1], dict)
    assert isinstance(got[2], str) and len(got[3]) == len({p for p, _ in got[3]})


@pytest.mark.parametrize("text", ["", "not json", "[]", "3", "null", '"x"', "{"])
def test_a_meta_file_that_is_not_an_object_is_no_capture(text):
    with pytest.raises(MissingFile):
        read(text)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@settings(deadline=None, max_examples=60)
@given(
    states=st.lists(st.sampled_from(["same", "changed", "deleted"]), max_size=6),
    data=st.data(),
)
def test_the_first_changed_file_in_recorded_order_is_the_one_named(states, data):
    """**Validates: Requirements 2.2, 2.3, 2.5**"""
    root = Path(tempfile.mkdtemp()).resolve()
    try:
        scene_file = root / "scene_meta_props.py"
        scene_file.write_text("from art98.anim import *\nclass T(Scene):\n    pass\n")
        scene = _load_scene(scene_file, None)()
        scene.captures, scene._earlier = root / "caps", []
        scene._set_state = lambda state: None
        scene.captures.mkdir()
        capture = scene.captures / "02-b.state.json"
        capture.write_bytes(b"{}")
        names = [f"d{i}.bin" for i in range(len(states))]
        records = []
        for name in names:
            body = data.draw(st.binary(max_size=8))
            (root / name).write_bytes(body)
            records.append((name, sha(body)))
        for name, state in zip(names, states):
            if state == "changed":
                (root / name).write_bytes(b"\xffchanged")
            elif state == "deleted":
                (root / name).unlink()
        (scene.captures / "02-b.meta.json").write_text(
            meta_text(1.0, scene._hashes(), sha(capture.read_bytes()), records)
        )
        # the model: the first file that is not unchanged, and how
        bad = [(n, s) for n, s in zip(names, states) if s != "same"]
        if not bad:
            scene._start_from_capture(2, "b")
            return
        name, state = bad[0]
        how = "changed" if state == "changed" else "was moved or deleted"
        with pytest.raises(UsageError) as stale:
            scene._start_from_capture(2, "b")
        assert f"before {name} {how}:" in str(stale.value)
    finally:
        shutil.rmtree(root, ignore_errors=True)
