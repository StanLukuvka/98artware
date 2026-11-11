"""Stale-build warnings: mtimes in a temp tree, a fake container engine."""

import os
import subprocess

from art98 import freshness
from art98.freshness import parse_created, stale_warnings

OLD, NEW = 1_000_000_000, 1_900_000_000


def touch(path, when):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    os.utime(path, (when, when))


def tree(tmp_path, build=NEW, image=NEW):
    root = tmp_path / "repo"
    for built, source in freshness.PROGRAMS:
        touch(root / "guest" / source, 1_500_000_000)
        touch(root / "guest" / "build" / built, build)
    touch(root / "setup" / "Dockerfile", 1_500_000_000)
    touch(tmp_path / "work" / "image.json", image)
    return root, tmp_path / "work"


def test_current_tree_is_quiet(tmp_path):
    root, work = tree(tmp_path)
    assert stale_warnings(work, "local", root=root) == []


def test_old_guest_programs_warn_by_name(tmp_path):
    root, work = tree(tmp_path, build=OLD)
    lines = stale_warnings(work, "local", root=root)
    assert (
        len(lines) == 2 and "view.exe is older than picture_viewer/view.c" in lines[1]
    )


def test_mbr_is_not_a_render_time_check(tmp_path):
    root, work = tree(tmp_path)
    touch(root / "guest" / "boot_record" / "mbr.S", NEW + 1000)
    touch(root / "guest" / "build" / "mbr.bin", OLD)
    assert stale_warnings(work, "local", root=root) == []


def test_old_image_prints_the_remedy_only(tmp_path):
    root, work = tree(tmp_path, image=OLD)
    (line,) = stale_warnings(work, "local", root=root)
    assert "art98 setup --from vm" in line


def test_a_package_without_a_checkout_is_quiet(tmp_path):
    assert stale_warnings(tmp_path, "container", root=tmp_path / "nowhere") == []


class FakeEngine:
    def __init__(self, text, code=0):
        self.text, self.code, self.calls = text, code, []

    def __call__(self, *args, **kwargs):
        self.calls.append(args)
        return subprocess.CompletedProcess(args, self.code, stdout=self.text.encode())


def test_container_image_older_than_code_warns(tmp_path):
    root, work = tree(tmp_path)
    for created in (
        "2001-09-09T01:46:40.123456789Z",
        "2001-09-09 01:46:40.1 +0000 UTC",
    ):
        engine = FakeEngine(created)
        (line,) = stale_warnings(work, "container", engine, root)
        assert "art98 up --rebuild" in line
        assert len(engine.calls) == 1  # one inspect


def test_container_image_newer_than_code_is_quiet(tmp_path):
    root, work = tree(tmp_path)
    assert (
        stale_warnings(work, "container", FakeEngine("2090-01-01T00:00:00Z"), root)
        == []
    )


def test_unreadable_or_missing_image_is_quiet(tmp_path):
    root, work = tree(tmp_path)
    assert stale_warnings(work, "container", FakeEngine("garbage"), root) == []
    assert stale_warnings(work, "container", FakeEngine("", code=1), root) == []


def test_parse_created():
    assert parse_created("2001-09-09T01:46:40Z") == 1_000_000_000
    assert parse_created("nonsense") is None
