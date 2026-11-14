"""Stale-build warnings: digests and git commit time in a temp tree, a fake container engine."""

import os
import subprocess

from art98 import freshness
from art98.freshness import (
    container_warning,
    digests,
    inspect_created,
    parse_created,
    stale_warnings,
)

OLD, NEW = 1_000_000_000, 1_900_000_000


def touch(path, when):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    os.utime(path, (when, when))


def digest_file(root):
    """Write guest/build/sources.sha256 for the current sources."""
    lines = [
        f"{freshness.source_digest(root / 'guest' / src)}  {src}"
        for _, src in freshness.PROGRAMS
    ]
    (root / "guest" / "build" / "sources.sha256").write_text("\n".join(lines))


def tree(tmp_path, build=NEW, image=NEW):
    root = tmp_path / "repo"
    for built, source in freshness.PROGRAMS:
        touch(root / "guest" / source, 1_500_000_000)
        touch(root / "guest" / "build" / built, build)
    touch(root / "setup" / "Dockerfile", 1_500_000_000)
    touch(tmp_path / "work" / "image.json", image)
    digest_file(root)
    return root, tmp_path / "work"


def git(root, *args, when=None):
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
    }
    if when:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = f"{when} +0000"
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
        env=env,
    )


def committed(root, when):
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "a", when=when)


def test_current_tree_is_quiet(tmp_path):
    root, work = tree(tmp_path)
    assert stale_warnings(work, root=root) == []


def test_exe_older_than_source_by_mtime_but_digest_matches_is_quiet(tmp_path):
    root, work = tree(tmp_path, build=OLD)  # the source mtimes are newer than the exes
    assert stale_warnings(work, root=root) == []


def test_edited_source_warns_by_name(tmp_path):
    root, work = tree(tmp_path)
    (root / "guest" / "picture_viewer" / "view.c").write_bytes(b"edited")
    (line,) = stale_warnings(work, root=root)
    assert "view.exe was built from an older picture_viewer/view.c" in line


def test_no_digest_file_is_quiet(tmp_path):
    root, work = tree(tmp_path, build=OLD)
    (root / "guest" / "build" / "sources.sha256").unlink()
    assert stale_warnings(work, root=root) == []


def test_digests_parser(tmp_path):
    f = tmp_path / "s"
    f.write_text("ab12  call_proxy/agent.c\ncd34 picture_viewer/view.c\njunk\n")
    assert digests(f) == {"call_proxy/agent.c": "ab12"}  # needs sha256sum's two spaces
    assert digests(tmp_path / "missing") is None


def test_mbr_is_not_a_render_time_check(tmp_path):
    root, work = tree(tmp_path)
    touch(root / "guest" / "build" / "mbr.bin", OLD)
    assert stale_warnings(work, root=root) == []


def test_git_pull_resets_mtimes_but_not_commit_time(tmp_path):
    root, work = tree(tmp_path, image=1_700_000_000)
    agent = root / "guest" / "call_proxy" / "agent.c"
    committed(root, 1_600_000_000)  # before image.json
    touch(agent, NEW)  # what a pull does: newer mtime, same content
    assert stale_warnings(work, root=root) == []
    agent.write_bytes(b"new agent")
    git(root, "commit", "-qam", "b", when=1_800_000_000)  # after image.json
    os.utime(agent, (OLD, OLD))
    digest_file(root)
    (line,) = stale_warnings(work, root=root)
    assert "art98 setup --from vm" in line


def test_a_pure_move_is_not_a_change_but_an_edit_after_it_is(tmp_path):
    root, _ = tree(tmp_path, image=1_700_000_000)
    committed(root, 1_600_000_000)
    (root / "guest" / "moved").mkdir()
    git(root, "mv", "guest/call_proxy/agent.c", "guest/moved/agent.c")
    git(root, "commit", "-qm", "move", when=1_800_000_000)  # after image.json
    moved = root / "guest" / "moved" / "agent.c"
    os.utime(moved, (OLD, OLD))
    assert not freshness.code_changed_since(
        root, ["guest/moved/agent.c"], 1_700_000_000
    )
    moved.write_bytes(b"edited")
    git(root, "commit", "-qam", "edit", when=1_900_000_000)
    os.utime(moved, (OLD, OLD))
    assert freshness.code_changed_since(root, ["guest/moved/agent.c"], 1_700_000_000)


def test_git_uncommitted_edit_warns_by_mtime(tmp_path):
    root, work = tree(tmp_path, image=1_700_000_000)
    agent = root / "guest" / "call_proxy" / "agent.c"
    committed(root, 1_600_000_000)
    agent.write_bytes(b"edit")
    os.utime(agent, (1_800_000_000, 1_800_000_000))
    digest_file(root)
    assert len(stale_warnings(work, root=root)) == 1


def test_a_copy_inside_another_repo_does_not_read_its_history(tmp_path):
    root, work = tree(tmp_path, image=1_700_000_000)
    committed(
        tmp_path, 1_800_000_000
    )  # the parent repo owns repo/, root is not its toplevel
    assert stale_warnings(work, root=root) == []  # mtime fallback: sources are older


def test_without_git_the_mtime_rule_has_a_60s_margin(tmp_path):
    root, work = tree(tmp_path)
    agent = root / "guest" / "call_proxy" / "agent.c"
    os.utime(agent, (NEW + 30, NEW + 30))
    assert stale_warnings(work, root=root) == []  # not a git dir, within the margin
    os.utime(agent, (NEW + 120, NEW + 120))
    assert len(stale_warnings(work, root=root)) == 1


def test_a_package_without_a_checkout_is_quiet(tmp_path):
    assert stale_warnings(tmp_path, root=tmp_path / "nowhere") == []


class FakeEngine:
    def __init__(self, text, code=0):
        self.text, self.code, self.calls = text, code, []

    def __call__(self, *args, **kwargs):
        self.calls.append(args)
        return subprocess.CompletedProcess(args, self.code, stdout=self.text.encode())


def test_container_image_older_than_code_warns(tmp_path):
    root, _ = tree(tmp_path)
    for created in (
        "2001-09-09T01:46:40.123456789Z",
        "2001-09-09 01:46:40.1 +0000 UTC",
    ):
        engine = FakeEngine(created)
        exists, when = inspect_created(engine, "img")
        assert exists and len(engine.calls) == 1  # one inspect
        (line,) = container_warning(when, "img", root)
        assert "art98 up --rebuild" in line


def test_container_image_newer_than_code_is_quiet(tmp_path):
    root, _ = tree(tmp_path)
    when = inspect_created(FakeEngine("2090-01-01T00:00:00Z"), "img")[1]
    assert container_warning(when, "img", root) == []


def test_unreadable_or_missing_image_is_quiet(tmp_path):
    root, _ = tree(tmp_path)
    assert (
        container_warning(inspect_created(FakeEngine("garbage"), "i")[1], "i", root)
        == []
    )
    assert inspect_created(FakeEngine("", code=1), "i") == (False, None)


def test_parse_created():
    assert parse_created("2001-09-09T01:46:40Z") == 1_000_000_000
    assert parse_created("nonsense") is None
