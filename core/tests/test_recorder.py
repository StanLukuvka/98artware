"""The Recorder: clips, cut(), the ffmpeg exit check and the size check.

Most tests drive the real ffmpeg with tiny generated frames and no VM.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from art98 import recorder as recorder_module
from art98.anim import Scene
from art98.anim import renderer as render_module
from art98.recorder import Recorder, RecorderError, ppm_size
from art98.session import Session

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")


def ppm(width=16, height=12, shade=0):
    return f"P6\n{width} {height}\n255\n".encode() + bytes([shade % 256]) * (
        width * height * 3
    )


class Screen:
    """A VM and bridge in one: screenshot writes a PPM of the current size."""

    def __init__(self):
        self.size = (16, 12)
        self.shots = 0

    def sync(self):
        pass

    def screenshot(self, path, format="ppm"):
        self.shots += 1
        Path(path).write_bytes(ppm(*self.size, shade=self.shots * 20))
        return Path(path)

    def close(self):
        pass


@pytest.fixture
def screen():
    return Screen()


@pytest.fixture
def session(screen):
    return Session(screen, screen)


def frames(path: Path) -> int:
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=nb_read_frames",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return int(probe.stdout.strip())


def test_ppm_size_reads_the_header():
    assert ppm_size(ppm(800, 600)) == (800, 600)
    with pytest.raises(RecorderError):
        ppm_size(b"P5\n1 1\n255\n\x00")


# ---- clip naming ----


@needs_ffmpeg
def test_a_run_without_cuts_writes_one_file_under_its_own_name(session, tmp_path):
    out = tmp_path / "out.mp4"
    with session.record(out, fps=10) as video:
        video.frame(hold=3)
    assert video.clips == [out] and frames(out) == 3
    assert sorted(p.name for p in tmp_path.iterdir()) == ["out.mp4"]


@needs_ffmpeg
def test_cuts_number_the_clips_after_the_output(session, tmp_path):
    out = tmp_path / "out.mp4"
    with session.record(out, fps=10) as video:
        video.frame(hold=2)
        first = video.cut()
        assert video.path == tmp_path / "out-02.mp4"
        assert video.count == 0 and video.total == 2
        video.frame(hold=3)
        second = video.cut()
        video.frame()
    assert first == tmp_path / "out-01.mp4" and second == tmp_path / "out-02.mp4"
    assert video.clips == [first, second, tmp_path / "out-03.mp4"]
    assert video.total == 6
    assert [frames(clip) for clip in video.clips] == [2, 3, 1]
    assert not out.exists()  # the first clip was renamed, the output is for join
    video.join(out)
    assert frames(out) == 6


@needs_ffmpeg
def test_cut_takes_a_path_for_the_next_clip(session, tmp_path):
    with session.record(tmp_path / "out.mp4", fps=10) as video:
        video.frame()
        video.cut(tmp_path / "intro.mp4")
        video.frame()
        video.cut()
        video.frame()
    assert [clip.name for clip in video.clips] == [
        "out-01.mp4",
        "intro.mp4",
        "out-03.mp4",
    ]


@needs_ffmpeg
def test_a_cut_with_nothing_recorded_makes_no_empty_clip(session, tmp_path):
    with session.record(tmp_path / "out.mp4", fps=10) as video:
        assert video.cut() is None
        assert video.cut(tmp_path / "first.mp4") is None
        video.frame()
        video.cut()
        assert video.cut() is None
        video.frame()
    assert [clip.name for clip in video.clips] == ["first.mp4", "out-02.mp4"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["first.mp4", "out-02.mp4"]


def test_a_lossless_recorder_writes_matroska(session, tmp_path, monkeypatch):
    commands = []

    class FakePopen:
        def __init__(self, command, stdin=None, stderr=None):
            commands.append(command)
            self.stdin = open(command[-1], "wb")  # noqa: SIM115

        def wait(self):
            return 0

    monkeypatch.setattr(recorder_module.subprocess, "Popen", FakePopen)
    with session.record(tmp_path / "a.mp4", lossless=True) as video:
        video.frame()
        video.cut(tmp_path / "b.mp4")
        video.frame()
    with session.record(tmp_path / "c.mp4") as video:
        video.frame()
    assert "ffv1" in commands[0] and commands[0][-1] == str(tmp_path / "a.part.mkv")
    assert (tmp_path / "a-01.mkv").exists()
    assert commands[1][-1] == str(tmp_path / "b.part.mkv")
    assert "libx264" in commands[2] and commands[2][-1] == str(tmp_path / "c.part.mp4")


def test_live_stops_on_its_condition(session, tmp_path, monkeypatch):
    recorder = Recorder(session, tmp_path / "x.mp4", fps=1000)
    monkeypatch.setattr(
        recorder,
        "_capture",
        lambda hold: setattr(recorder, "count", recorder.count + hold),
    )
    recorder.live(1, stop_condition=lambda: recorder.count >= 3)
    assert recorder.count == 3
    recorder.close()


# ---- ffmpeg's exit code ----


class FailingFfmpeg:
    """Takes every frame, then exits 1 with a message on its stderr."""

    def __init__(self, command, stdin=None, stderr=None):
        self.stdin = open(command[-1], "wb")  # the part file  # noqa: SIM115
        self._stderr = stderr

    def terminate(self):
        pass

    def wait(self):
        self._stderr.write(b"Encoder did not like it\n")
        self._stderr.flush()
        return 1


def test_close_raises_when_ffmpeg_failed(session, tmp_path, monkeypatch):
    monkeypatch.setattr(recorder_module.subprocess, "Popen", FailingFfmpeg)
    video = session.record(tmp_path / "out.mp4")
    video.frame()
    with pytest.raises(RecorderError, match=r"exit 1.*Encoder did not like it"):
        video.close()
    assert video.clips == []
    assert not list(tmp_path.glob("out*"))  # neither out.mp4 nor out.part.mp4


def test_cut_raises_when_the_clip_it_closes_failed(session, tmp_path, monkeypatch):
    monkeypatch.setattr(recorder_module.subprocess, "Popen", FailingFfmpeg)
    video = session.record(tmp_path / "out.mp4")
    video.frame()
    with pytest.raises(RecorderError, match="ffmpeg failed writing"):
        video.cut()
    video.close()
    assert not list(tmp_path.glob("out*"))


def test_the_scenes_own_error_is_not_replaced(session, tmp_path, monkeypatch):
    monkeypatch.setattr(recorder_module.subprocess, "Popen", FailingFfmpeg)
    with (
        pytest.raises(KeyError, match="the scene's own"),
        session.record(tmp_path / "out.mp4") as video,
    ):
        video.frame()
        raise KeyError("the scene's own")
    assert not list(tmp_path.glob("out*"))  # abort() left no half clip


@needs_ffmpeg
def test_a_good_close_does_not_raise_and_a_second_close_is_harmless(session, tmp_path):
    video = session.record(tmp_path / "out.mp4", fps=10)
    video.frame()
    video.close()
    video.close()
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "out.mp4"
    ]  # final name, no .part
    with pytest.raises(RecorderError, match="closed"):
        video.cut()


# ---- the screen size ----


@needs_ffmpeg
def test_a_size_change_inside_a_clip_raises_and_suggests_cut(session, screen, tmp_path):
    with (
        pytest.raises(RecorderError, match=r"16x12 to 32x24.*cut\(\)"),
        session.record(tmp_path / "out.mp4", fps=10) as video,
    ):
        video.frame()
        screen.size = (32, 24)
        video.frame()
    assert (
        video.clips == [] and list(tmp_path.iterdir()) == []
    )  # the half clip was dropped


@needs_ffmpeg
def test_a_size_change_after_a_cut_records_but_the_join_names_the_sizes(
    session, screen, tmp_path
):
    with session.record(tmp_path / "out.mp4", fps=10) as video:
        video.frame()
        video.cut()
        screen.size = (32, 24)
        video.frame()
    assert len(video.clips) == 2
    with pytest.raises(RecorderError, match=r"out-01.mp4 16x12, out-02.mp4 32x24"):
        video.join(tmp_path / "out.mp4")


# ---- the scene and render ----


def test_scene_cut_reaches_the_recorder_and_time_counts_every_clip(
    session, tmp_path, monkeypatch
):
    class Fake:
        total, cuts = 45, []

        def cut(self, path=None):
            self.cuts.append(path)
            return "closed"

    scene = Scene()
    scene.recorder = Fake()
    assert scene.video is scene.recorder
    assert scene.cut("x.mp4") == "closed" and scene.recorder.cuts == ["x.mp4"]
    assert scene.time == pytest.approx(1.5)


class Cutting:
    """Enough of a scene for render: two cuts, three clips of 2, 3 and 1 frames."""

    fps = 10

    def __init__(self, path=None):
        self.path = path

    def run(self, session, video):
        video.frame(hold=2)
        video.cut()
        video.frame(hold=3)
        video.cut(self.path)
        video.frame()


@pytest.fixture
def staged(session):
    return session


@needs_ffmpeg
def test_render_joins_the_clips_and_keeps_them_beside_the_output(staged, tmp_path):
    out = render_module.render(Cutting(), tmp_path / "out.mp4", session=staged)
    assert frames(out) == 6
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "out-01.mp4",
        "out-02.mp4",
        "out-03.mp4",
        "out.mp4",
    ]


@needs_ffmpeg
def test_render_keep_clips_false_leaves_only_the_output(staged, tmp_path):
    render_module.render(
        Cutting(), tmp_path / "out.mp4", keep_clips=False, session=staged
    )
    assert sorted(p.name for p in tmp_path.iterdir()) == ["out.mp4"]


@needs_ffmpeg
def test_a_gif_render_makes_one_gif_and_keeps_the_clips_as_mp4(staged, tmp_path):
    named = tmp_path / "named.mp4"
    out = render_module.render(Cutting(named), tmp_path / "out.gif", session=staged)
    assert out == tmp_path / "out.gif"
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "named.mp4",
        "out-01.mp4",
        "out-02.mp4",
        "out.gif",
    ]
    assert [
        frames(tmp_path / n) for n in ("out-01.mp4", "out-02.mp4", "named.mp4")
    ] == [2, 3, 1]


@needs_ffmpeg
def test_a_gif_and_mp4_render_with_keep_clips_false(staged, tmp_path):
    render_module.render(
        Cutting(),
        tmp_path / "out.mp4",
        gif=tmp_path / "out.gif",
        keep_clips=False,
        session=staged,
    )
    assert sorted(p.name for p in tmp_path.iterdir()) == ["out.gif", "out.mp4"]
    assert frames(tmp_path / "out.mp4") == 6


@needs_ffmpeg
def test_render_without_cuts_is_unchanged(staged, tmp_path):
    class Plain:
        fps = 10

        def run(self, session, video):
            video.frame(hold=4)

    render_module.render(Plain(), tmp_path / "out.mp4", session=staged)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["out.mp4"]
    assert frames(tmp_path / "out.mp4") == 4


def test_render_of_a_scene_with_no_frames_says_so(staged, tmp_path):
    class Empty:
        fps = 10

        def run(self, session, video):
            pass

    with pytest.raises(RecorderError, match="recorded no frames"):
        render_module.render(Empty(), tmp_path / "out.mp4", session=staged)


# ---- hardening: part files, abort, ffmpeg errors, stale clips ----


@needs_ffmpeg
def test_a_scene_error_leaves_no_partial_clip(session, tmp_path):
    with (
        pytest.raises(KeyError),
        session.record(tmp_path / "out.mp4", fps=10) as video,
    ):
        video.frame()
        video.cut()
        video.frame()
        raise KeyError("scene")
    assert video.clips == [] and list(tmp_path.iterdir()) == []  # finished parts go too


class Failing(Cutting):
    def run(self, session, video):
        super().run(session, video)
        raise KeyError("scene")


@needs_ffmpeg
def test_render_deletes_its_clips_when_the_scene_fails(staged, tmp_path):
    with pytest.raises(KeyError):
        render_module.render(Failing(), tmp_path / "out.mp4", session=staged)
    assert list(tmp_path.iterdir()) == []


def earlier(tmp_path):
    """An earlier render's output and clip, to check a failed render leaves them."""
    old = {"out.mp4": b"old output", "out-01.mp4": b"old clip one"}
    for name, data in old.items():
        (tmp_path / name).write_bytes(data)
    return old


def untouched(tmp_path, old):
    """Only the earlier files remain, byte for byte: no .part, no staging file."""
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == old


@needs_ffmpeg
def test_a_scene_that_cuts_then_fails_leaves_the_earlier_render_alone(staged, tmp_path):
    old = earlier(tmp_path)
    with pytest.raises(KeyError):
        render_module.render(Failing(), tmp_path / "out.mp4", session=staged)
    untouched(tmp_path, old)


@needs_ffmpeg
def test_a_failed_join_leaves_the_earlier_render_alone(staged, tmp_path, monkeypatch):
    old = earlier(tmp_path)
    real = subprocess.run

    def run(command, **kwargs):
        if "concat" in command:
            return subprocess.CompletedProcess(command, 1, "", "join boom")
        return real(command, **kwargs)

    monkeypatch.setattr(recorder_module.subprocess, "run", run)
    with pytest.raises(RecorderError, match="join boom"):
        render_module.render(Cutting(), tmp_path / "out.mp4", session=staged)
    untouched(tmp_path, old)


@needs_ffmpeg
def test_a_failed_clip_encode_leaves_the_earlier_render_alone(
    staged, tmp_path, monkeypatch
):
    old = earlier(tmp_path)
    real, calls = render_module._encode, []

    def encode(source, output):
        calls.append(output)
        if len(calls) == 2:  # clip 1 is encoded and staged by now
            raise RecorderError("encode boom")
        real(source, output)

    monkeypatch.setattr(render_module, "_encode", encode)
    with pytest.raises(RecorderError, match="encode boom"):
        render_module.render(Cutting(), tmp_path / "out.gif", session=staged)
    assert len(calls) == 2
    untouched(tmp_path, old)


@needs_ffmpeg
def test_a_successful_render_replaces_the_earlier_files_with_final_names(
    staged, tmp_path
):
    earlier(tmp_path)
    render_module.render(Cutting(), tmp_path / "out.mp4", session=staged)
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "out-01.mp4",
        "out-02.mp4",
        "out-03.mp4",
        "out.mp4",
    ]
    assert frames(tmp_path / "out-01.mp4") == 2 and frames(tmp_path / "out.mp4") == 6


def failing_run(monkeypatch):
    def run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, "", "boom")

    monkeypatch.setattr(recorder_module.subprocess, "run", run)


def test_gif_encode_and_join_failures_raise_recorder_error_with_ffmpegs_message(
    session, tmp_path, monkeypatch
):
    failing_run(monkeypatch)
    with pytest.raises(RecorderError, match=r"making the GIF failed.*boom"):
        render_module.write_gif(tmp_path / "in.mkv", tmp_path / "out.gif")
    with pytest.raises(RecorderError, match=r"encoding out.mp4 failed.*boom"):
        render_module._encode(tmp_path / "in.mkv", tmp_path / "out.mp4")
    video = session.record(tmp_path / "x.mp4")
    video.clips = video.parts = [tmp_path / "a.mp4"]
    video._sizes = [(16, 12)]
    with pytest.raises(RecorderError, match=r"joining 1 clips.*exit 1.*boom"):
        video.join(tmp_path / "x.mp4")
    assert not list(tmp_path.glob("*.part.*"))
    video.clips = video.parts = []  # the fake clip was never a file
    video.close()


def test_missing_ffmpeg_raises_recorder_error(session, tmp_path, monkeypatch):
    monkeypatch.setattr(recorder_module.shutil, "which", lambda name: None)
    with pytest.raises(RecorderError, match="ffmpeg isn't on PATH"):
        render_module.render(Cutting(), tmp_path / "out.mp4", session=session)

    def missing(*args, **kwargs):
        raise FileNotFoundError("ffmpeg")

    monkeypatch.setattr(recorder_module.subprocess, "Popen", missing)
    video = session.record(tmp_path / "out.mp4")
    with pytest.raises(RecorderError, match="ffmpeg isn't on PATH"):
        video.frame()
    video.close()


@needs_ffmpeg
def test_stale_clips_are_reported_not_deleted(staged, tmp_path, capsys):
    (tmp_path / "out-05.mp4").write_bytes(b"old")
    (tmp_path / "other-01.mp4").write_bytes(b"mine")
    render_module.render(Cutting(), tmp_path / "out.mp4", session=staged)
    assert (tmp_path / "out-05.mp4").read_bytes() == b"old"
    err = capsys.readouterr().err
    assert "out-05.mp4" in err and "other-01" not in err and "out-01" not in err


@needs_ffmpeg
def test_render_records_on_a_given_session_and_does_not_close_it(session, tmp_path):
    out = render_module.render(Cutting(), tmp_path / "out.mp4", session=session)
    assert frames(out) == 6
    assert not getattr(session, "closed", False)
