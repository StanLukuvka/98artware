"""art98.service: start/stop argv with a fake Engine, attach/status against the real
serve.Server (serve_harness) over loopback TCP. No docker, no VM."""

import os
import socket
import stat
import threading
import time
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
import serve_harness
from art98 import service
from art98.container.host import ContainerError
from art98.qemu import QemuError
from art98.session import ImageMissing
from art98.settings import Settings
from serve_harness import TOKEN, Served

CID = "c0ffee" * 10


class FakeEngine:
    """Records every argv. `running` and `stopped` are the container ids `ps` reports;
    `labels` maps an id to its art98.work label."""

    path = "/usr/bin/docker"
    name = "docker"

    def __init__(self, work, running=(), stopped=(), label=None, image=True, fail=()):
        self.calls = []
        self.work = str(work)
        self.running = list(running)
        self.stopped = list(stopped)
        self.label = self.work if label is None else label
        self.image = image
        self.alive = True
        self.fail = set(fail)  # verbs that exit non-zero
        self.cidfile_existed = None

    def __call__(self, *args, check=True, input=None, capture=True):
        self.calls.append(args)
        out = b""
        if args[0] == "ps":
            if "-aq" in args:
                out = " ".join(self.running + self.stopped).encode()
            elif any(a.startswith("label=") for a in args):
                out = " ".join(self.running).encode()
            else:
                out = b"x" if self.alive else b""
        elif args[0] == "run":
            path = args[args.index("--cidfile") + 1]
            self.cidfile_existed = os.path.exists(path)
            Path(path).write_text(CID)
        elif args[0] == "inspect":
            out = self.label.encode()
        code = 1 if args[0] in self.fail else 0
        return SimpleNamespace(returncode=code, stdout=out, stderr=b"")

    def has_image(self, image):
        return self.image

    def port(self, container, port):
        raise ContainerError("no port")

    def verbs(self):
        return [c[0] for c in self.calls]

    def first(self, verb):
        return next(c for c in self.calls if c[0] == verb)


@pytest.fixture(autouse=True)
def tcp(monkeypatch, tmp_path):
    monkeypatch.setenv("ART98_TRANSPORT", "tcp")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    monkeypatch.setattr(service, "BUSY_POLL", 0.05)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def make_settings(tmp_path, port=7598, **kw):
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    (work / "image.json").write_text("{}")
    (work / "vm.token").write_text(TOKEN)
    return Settings(work=str(work), control=port, root=tmp_path, **kw)


@pytest.fixture
def served(tmp_path):
    s = Served(tmp_path)
    yield s
    s.close()


@pytest.fixture
def live(tmp_path, served):
    """Settings pointing at the running harness server."""
    return make_settings(tmp_path, port=served.address[1])


# ---- start: argv ----


def test_start_runs_a_labelled_detached_container_without_rm(tmp_path, served, live):
    engine = FakeEngine(live.work_dir)
    service.start(live, vnc=True, engine=engine, log=lambda m: None)
    argv = list(engine.first("run"))
    work = str(live.work_dir)
    assert argv[:3] == ["run", "-d", "--init"]
    assert "--rm" not in argv
    assert argv[argv.index("--name") + 1] == "art98-vm"
    assert argv[argv.index("--label") + 1] == f"art98.work={work}"
    assert argv[argv.index("--cidfile") + 1] == f"{work}/vm.cid"
    assert f"{work}:/work" in argv
    assert not any("art98_token" in a or "secrets" in a for a in argv)  # no token mount
    tail = argv[argv.index(live.image) :]
    assert tail[:6] == [
        "localhost/art98:latest",
        "serve",
        "--work",
        "/work",
        "--token-file",
        "/work/vm.token",
    ]
    assert tail[-1] == "--vnc"
    assert f"127.0.0.1:{live.control}:7598" in argv
    assert "127.0.0.1:5900:5900" in argv
    assert "--unix" not in argv
    assert engine.cidfile_existed is False


def test_start_takes_names_and_ports_from_settings(tmp_path, served):
    settings = make_settings(
        tmp_path, port=served.address[1], container="other", image="img:1", vnc=5901
    )
    engine = FakeEngine(settings.work_dir)
    service.start(settings, vnc=True, engine=engine, log=lambda m: None)
    argv = list(engine.first("run"))
    assert argv[argv.index("--name") + 1] == "other"
    assert "img:1" in argv
    assert "127.0.0.1:5901:5900" in argv


def test_start_without_vnc_publishes_no_vnc_port(tmp_path, served, live):
    engine = FakeEngine(live.work_dir)
    service.start(live, engine=engine, log=lambda m: None)
    argv = list(engine.first("run"))
    assert "--vnc" not in argv
    assert not any(a.endswith(":5900") for a in argv)


def test_start_on_unix_mounts_the_socket_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("ART98_TRANSPORT", "unix")
    monkeypatch.setattr(service, "START_TIMEOUT", 0.5)
    settings = make_settings(tmp_path)
    engine = FakeEngine(settings.work_dir)
    with pytest.raises(service.ServiceError):
        service.start(settings, engine=engine, log=lambda m: None)
    argv = list(engine.first("run"))
    folder = service.socket_dir(settings)
    assert f"{folder}:/run/art98" in argv
    assert argv[argv.index("--unix") + 1] == "/run/art98/serve.sock"
    assert not any(a.startswith("127.0.0.1:") for a in argv)  # no published port
    assert folder.parent == tmp_path / "run" / "art98"
    assert (
        folder.name.startswith("art98-vm-") and len(folder.name) == len("art98-vm-") + 8
    )


def test_start_needs_the_prepared_image_and_the_container_image(tmp_path, live):
    (live.work_dir / "image.json").unlink()
    with pytest.raises(ImageMissing, match="art98 up"):
        service.start(live, engine=FakeEngine(live.work_dir))
    (live.work_dir / "image.json").write_text("{}")
    with pytest.raises(ContainerError, match="art98 up"):
        service.start(live, engine=FakeEngine(live.work_dir, image=False))


# ---- start: what it deletes ----


def runs(settings):
    folder = settings.work_dir / "runs"
    (folder / "vm-old").mkdir(parents=True)
    (folder / "render-keep").mkdir()
    return folder


def test_start_deletes_run_copies_and_a_stale_cidfile_when_nothing_runs(served, live):
    folder = runs(live)
    (live.work_dir / "vm.cid").write_text("stale")
    engine = FakeEngine(live.work_dir, stopped=["dead1"])
    service.start(live, engine=engine, log=lambda m: None)
    assert not (folder / "vm-old").exists()
    assert (folder / "render-keep").exists()  # only vm-* goes
    assert engine.cidfile_existed is False
    # the stopped one was removed by id, after `stop -t`
    assert ("stop", "-t", "20", "dead1") in engine.calls
    assert (
        engine.verbs().index("stop")
        < engine.verbs().index("rm")
        < engine.verbs().index("run")
    )


def test_start_keeps_run_copies_while_a_labelled_container_answers(served, live):
    folder = runs(live)
    engine = FakeEngine(live.work_dir, running=["live1"])
    logs = []
    service.start(live, engine=engine, log=logs.append)
    assert "already running" in logs
    assert (folder / "vm-old").exists()
    assert "run" not in engine.verbs() and "rm" not in engine.verbs()


def test_start_replaces_a_running_container_that_does_not_answer(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "START_TIMEOUT", 0.3)
    settings = make_settings(tmp_path, port=free_port())
    engine = FakeEngine(settings.work_dir, running=["sick1"])
    with pytest.raises(service.ServiceError):  # the new one never answers either
        service.start(settings, engine=engine, log=lambda m: None)
    assert ("stop", "-t", "20", "sick1") in engine.calls


# ---- start: failures ----


def old_serve(port_holder):
    """A listener that answers like a serve without the status channel."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(5)
    port_holder.append(listener.getsockname()[1])

    def loop():
        while True:
            try:
                conn, _ = listener.accept()
            except OSError:
                return
            conn.recv(4096)
            conn.sendall(b"error unknown channel 'status'\n")
            conn.close()

    threading.Thread(target=loop, daemon=True).start()
    return listener


def test_an_old_image_fails_start_at_once_with_the_image_older_message(tmp_path):
    port = []
    listener = old_serve(port)
    try:
        settings = make_settings(tmp_path, port=port[0])
        engine = FakeEngine(settings.work_dir)
        began = time.monotonic()
        with pytest.raises(service.Unhealthy, match="older than the code.*--rebuild"):
            service.start(settings, engine=engine, log=lambda m: None)
        assert time.monotonic() - began < 10  # not a 120 s poll
        assert ("stop", "-t", "20", CID) in engine.calls  # and the container is gone
    finally:
        listener.close()


def test_start_without_a_ready_snapshot_stops_the_container(tmp_path):
    served = Served(tmp_path, snapshots=())
    try:
        settings = make_settings(tmp_path, port=served.address[1])
        engine = FakeEngine(settings.work_dir)
        with pytest.raises(service.Unhealthy, match="no `ready` snapshot"):
            service.start(settings, engine=engine, log=lambda m: None)
        assert "rm" in engine.verbs()
    finally:
        served.close()


# ---- stop ----


def test_stop_stops_before_rm_by_id_and_keeps_the_token(live):
    cid_file = live.work_dir / "vm.cid"
    cid_file.write_text("abc123")
    folder = service.socket_dir(live)
    folder.mkdir(parents=True)
    engine = FakeEngine(live.work_dir)
    service.stop(live, engine=engine, log=lambda m: None)
    assert ("stop", "-t", "20", "abc123") in engine.calls
    assert ("rm", "abc123") in engine.calls
    assert engine.verbs().index("stop") < engine.verbs().index("rm")
    assert not any(
        "art98-vm" in a for c in engine.calls for a in c
    )  # never the bare name
    assert not cid_file.exists() and not folder.exists()
    assert (live.work_dir / "vm.token").exists()


def test_stop_refuses_a_container_labelled_for_another_work_dir(live):
    (live.work_dir / "vm.cid").write_text("abc123")
    engine = FakeEngine(live.work_dir, label="/somewhere/else")
    with pytest.raises(service.ServiceError, match="refusing to stop abc123"):
        service.stop(live, engine=engine, log=lambda m: None)
    assert "stop" not in engine.verbs() and "rm" not in engine.verbs()
    assert (live.work_dir / "vm.cid").exists()


def test_stop_without_a_cidfile_finds_the_container_by_label(live):
    engine = FakeEngine(live.work_dir, running=["byLabel"])
    service.stop(live, engine=engine, log=lambda m: None)
    assert ("stop", "-t", "20", "byLabel") in engine.calls


# ---- attach ----


def test_a_dead_port_is_not_running_within_seconds(tmp_path):
    settings = make_settings(tmp_path, port=free_port())
    began = time.monotonic()
    with (
        pytest.raises(service.NotRunning, match="art98 vm start"),
        service.attach(settings),
    ):
        pass
    assert time.monotonic() - began < 10


def test_a_silent_listener_is_not_running_after_the_connect_timeout(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(service, "CONNECT_TIMEOUT", 0.3)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(5)  # accepts into the backlog, never answers
    try:
        settings = make_settings(tmp_path, port=listener.getsockname()[1])
        began = time.monotonic()
        with pytest.raises(service.NotRunning), service.attach(settings):
            pass
        assert time.monotonic() - began < 10
    finally:
        listener.close()


def test_a_missing_token_or_unix_socket_is_not_running_at_once(tmp_path, monkeypatch):
    settings = make_settings(tmp_path)
    (settings.work_dir / "vm.token").unlink()
    with pytest.raises(service.NotRunning), service.attach(settings):
        pass
    (settings.work_dir / "vm.token").write_text(TOKEN)
    monkeypatch.setenv("ART98_TRANSPORT", "unix")
    began = time.monotonic()
    with pytest.raises(service.NotRunning), service.attach(settings):
        pass
    assert time.monotonic() - began < 1


def test_no_ready_snapshot_is_unhealthy(tmp_path):
    served = Served(tmp_path, snapshots=("other",))
    try:
        settings = make_settings(tmp_path, port=served.address[1])
        with (
            pytest.raises(service.Unhealthy, match="no `ready` snapshot"),
            service.attach(settings),
        ):
            pass
    finally:
        served.close()


def test_attach_resumes_reverts_then_pings_and_releases_paused(served, live):
    with service.attach(live) as session:
        names = [c[0] for c in served.vm.calls]
        assert "resume" in names and "load_snapshot" in names
        assert names.index("resume") < names.index("load_snapshot")
        assert session.bridge.ping() >= 1
    deadline = time.monotonic() + 5
    while not service.status(live, engine=FakeEngine(live.work_dir))["paused"]:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    assert served.thread.is_alive()  # release leaves serve running
    assert ("pause",) in served.vm.calls


@pytest.fixture
def ping_after_revert(monkeypatch):
    """A guest that answers PING only once the snapshot has been loaded."""
    original = serve_harness.FakeSerial._serve

    def serve(self, conn, client):
        if not hasattr(self, "reverted"):
            return original(self, conn, client)
        self.reverted.wait(5)
        return original(self, conn, client)

    monkeypatch.setattr(serve_harness.FakeSerial, "_serve", serve)


def test_the_revert_comes_before_the_ping(ping_after_revert, tmp_path):
    served = Served(tmp_path)
    try:
        reverted = threading.Event()
        original = served.vm.load_snapshot
        served.vm.load_snapshot = lambda name: (original(name), reverted.set())
        served.serial.reverted = reverted
        settings = make_settings(tmp_path, port=served.address[1])
        with service.attach(settings) as session:
            assert reverted.is_set()
            assert session.bridge.ping() >= 1
    finally:
        served.close()


def test_without_revert_attach_resumes_and_pings_only(served, live):
    with service.attach(live, revert=False) as session:
        assert session.bridge.ping() >= 1
    names = [c[0] for c in served.vm.calls]
    assert "resume" in names and "load_snapshot" not in names


def test_a_second_attach_is_busy_and_the_first_is_untouched(served, live):
    with service.attach(live) as first:
        with (
            pytest.raises(service.Busy, match="another render holds it"),
            service.attach(live),
        ):
            pass
        assert first.bridge.ping() >= 1


def test_a_second_attach_races_the_control_handshake_into_busy(
    served, live, monkeypatch
):
    """Status said free, but another client won the slot before our control handshake."""
    real = service._read_status
    monkeypatch.setattr(
        service, "_read_status", lambda *a, **k: {**real(*a, **k), "busy": False}
    )
    with service.attach(live), pytest.raises(service.Busy), service.attach(live):
        pass


def test_wait_retries_busy_until_the_first_attach_releases(served, live):
    stack = ExitStack()
    stack.enter_context(service.attach(live))
    threading.Timer(0.3, stack.close).start()
    began = time.monotonic()
    with service.attach(live, wait=5) as second:
        assert second.bridge.ping() >= 1
    assert 0.2 < time.monotonic() - began < 4


def test_wait_raises_busy_when_the_first_never_releases(served, live):
    with service.attach(live):
        began = time.monotonic()
        with pytest.raises(service.Busy), service.attach(live, wait=0.4):
            pass
        assert time.monotonic() - began >= 0.4


def test_wait_never_retries_not_running(tmp_path):
    settings = make_settings(tmp_path, port=free_port())
    began = time.monotonic()
    with pytest.raises(service.NotRunning), service.attach(settings, wait=5):
        pass
    assert time.monotonic() - began < 2


def test_wait_never_retries_unhealthy(tmp_path):
    served = Served(tmp_path, snapshots=())
    try:
        settings = make_settings(tmp_path, port=served.address[1])
        began = time.monotonic()
        with pytest.raises(service.Unhealthy), service.attach(settings, wait=5):
            pass
        assert time.monotonic() - began < 2
    finally:
        served.close()


# ---- status ----


def test_status_takes_no_lock_while_a_render_holds_the_vm(served, live):
    engine = FakeEngine(live.work_dir)
    with service.attach(live):
        reply = service.status(live, engine=engine)
        assert reply["running"] and reply["busy"] and not reply["paused"]
        assert reply["snapshots"] == ["ready"]
        assert reply["started_at"] == "2026-11-11T20:00:00Z"
        assert reply["vnc"] is None


def test_status_of_a_dead_port_is_down_not_an_error(tmp_path):
    settings = make_settings(tmp_path, port=free_port())
    reply = service.status(settings, engine=FakeEngine(settings.work_dir))
    assert reply["running"] is False


# ---- a failed attach frees the slot ----


@pytest.fixture(autouse=True)
def keep_alive(monkeypatch):
    """Hold every RemoteVM and Bridge so a leaked socket is not closed by the garbage
    collector, which would hide a missing close() in service.py."""
    held = []
    real_vm, real_bridge = service.RemoteVM, service.Bridge
    monkeypatch.setattr(
        service, "RemoteVM", lambda *a, **k: held.append(real_vm(*a, **k)) or held[-1]
    )
    monkeypatch.setattr(
        service, "Bridge", lambda *a, **k: held.append(real_bridge(*a, **k)) or held[-1]
    )
    return held


def free_again(served, live):
    """The slot is released by the server after the client hangs up."""
    deadline = time.monotonic() + 5
    while True:
        try:
            with service.attach(live):
                return
        except service.Busy:
            assert time.monotonic() < deadline, "the slot was never freed"
            time.sleep(0.02)


def test_a_failed_agent_channel_frees_the_slot(served, live, monkeypatch):
    real = service.open_channel

    def only_control(address, token, channel, timeout):
        if channel == "agent":
            raise ContainerError("no agent")
        return real(address, token, channel, timeout)

    monkeypatch.setattr(service, "open_channel", only_control)
    with pytest.raises(service.Unhealthy), service.attach(live):
        pass
    monkeypatch.setattr(service, "open_channel", real)
    free_again(served, live)


def test_a_failed_resume_frees_the_slot(served, live):
    served.vm.resume = lambda: (_ for _ in ()).throw(RuntimeError("resume failed"))
    # the server answers the control op with an error, which RemoteVM raises
    with pytest.raises(QemuError, match="resume"), service.attach(live):
        pass
    served.vm.resume = lambda: served.vm.calls.append(("resume",))
    free_again(served, live)


def test_a_failed_ping_after_the_revert_frees_the_slot(
    ping_after_revert, tmp_path, monkeypatch
):
    served = Served(tmp_path)
    try:
        served.serial.reverted = threading.Event()  # the guest stays silent
        real = service.Bridge
        monkeypatch.setattr(service, "Bridge", lambda sock: real(sock, 0.3))
        settings = make_settings(tmp_path, port=served.address[1])
        with (
            pytest.raises(service.Unhealthy, match="did not answer"),
            service.attach(settings),
        ):
            pass
        served.serial.reverted.set()  # now the guest answers
        free_again(served, settings)
    finally:
        served.close()


# ---- the token ----


def test_start_creates_the_token_0600(served, tmp_path):
    settings = make_settings(tmp_path, port=served.address[1])
    token = settings.work_dir / "vm.token"
    token.write_text(TOKEN)  # the harness serves this token; recreate it below
    token.unlink()
    # start creates a random token, which the harness rejects: it must still be 0600
    with pytest.raises(service.ServiceError):
        service.start(
            settings, engine=FakeEngine(settings.work_dir), log=lambda m: None
        )
    assert stat.S_IMODE(token.stat().st_mode) == 0o600


# ---- stop and remove safety ----


def test_remove_treats_a_failed_inspect_as_already_gone(live):
    engine = FakeEngine(live.work_dir, fail={"inspect"})
    service._remove(engine, "gone1", live.work_dir, log=lambda m: None)
    assert "stop" not in engine.verbs() and "rm" not in engine.verbs()


def test_start_refuses_a_label_mismatch_and_keeps_the_run_copies(served, live):
    folder = runs(live)
    engine = FakeEngine(live.work_dir, stopped=["other1"], label="/somewhere/else")
    with pytest.raises(service.ServiceError, match="refusing to stop other1"):
        service.start(live, engine=engine, log=lambda m: None)
    assert (folder / "vm-old").exists()
    assert "run" not in engine.verbs() and "stop" not in engine.verbs()


def test_stop_falls_back_to_rm_f_when_stop_times_out(live):
    (live.work_dir / "vm.cid").write_text("abc123")
    engine = FakeEngine(live.work_dir, fail={"stop"})
    service.stop(live, engine=engine, log=lambda m: None)
    assert ("rm", "-f", "abc123") in engine.calls
    assert ("rm", "abc123") not in engine.calls


@pytest.mark.parametrize(
    "revert, said",
    [(True, "after the revert"), (False, "to the ping")],
)
def test_an_unanswering_guest_is_named_for_the_step_that_failed(
    served, live, monkeypatch, revert, said
):
    def silent(self, *args, **kwargs):
        raise service.BridgeError("silence")

    monkeypatch.setattr("art98.bridge.Bridge.ping", silent)
    monkeypatch.setattr(service.Session, "revert", silent)
    with (
        pytest.raises(service.Unhealthy) as caught,
        service.attach(live, revert=revert),
    ):
        pass
    assert f"did not answer {said}" in str(caught.value)
    assert ("after the revert" in str(caught.value)) is revert


# ---- container clients: connect host, token_file, transport ----


def test_a_client_dials_the_connect_host_not_bind(tmp_path):
    s = make_settings(tmp_path, bind="0.0.0.0", connect="vm.example")
    assert service._address(s) == ("vm.example", 7598)
    assert service._address(make_settings(tmp_path, bind="0.0.0.0")) == (
        "127.0.0.1",
        7598,
    )


def test_the_settings_transport_picks_unix_and_the_env_still_wins(
    tmp_path, monkeypatch
):
    s = make_settings(tmp_path, transport="unix")
    monkeypatch.delenv("ART98_TRANSPORT")
    assert isinstance(service._address(s), str)
    monkeypatch.setenv("ART98_TRANSPORT", "tcp")
    assert isinstance(service._address(s), tuple)


def test_start_writes_the_token_to_token_file_and_mounts_it(served, tmp_path):
    outside = tmp_path / "keys" / "deep" / "vm.token"
    settings = make_settings(tmp_path, port=served.address[1], token_file=str(outside))
    (settings.work_dir / "vm.token").unlink()
    engine = FakeEngine(settings.work_dir)
    with pytest.raises(service.ServiceError):  # the harness rejects a random token
        service.start(settings, engine=engine, log=lambda m: None)
    assert stat.S_IMODE(outside.stat().st_mode) == 0o600
    assert not (settings.work_dir / "vm.token").exists()
    argv = list(engine.first("run"))
    assert f"{outside}:/run/secrets/art98_token:ro" in argv
    assert argv[argv.index("--token-file") + 1] == "/run/secrets/art98_token"


def test_attach_reads_the_token_from_token_file_without_work(served, tmp_path):
    outside = tmp_path / "elsewhere.token"
    outside.write_text(TOKEN)
    settings = Settings(
        work=str(tmp_path / "no-work-here"),
        control=served.address[1],
        token_file=str(outside),
        root=tmp_path,
    )
    assert not settings.work_dir.exists()
    with service.attach(settings, revert=False) as session:
        assert session.bridge.ping() is not None
    assert service.status(settings, engine=FakeEngine(tmp_path))["running"]


def test_a_given_token_beats_the_env_and_the_file(served, tmp_path, monkeypatch):
    settings = Settings(
        work=str(tmp_path / "no-work-here"),
        control=served.address[1],
        token_file=str(tmp_path / "missing.token"),
        root=tmp_path,
    )
    monkeypatch.setenv(
        "ART98_TOKEN", TOKEN
    )  # how a host program hands a child its token
    with service.attach(settings, revert=False) as session:
        assert session.bridge.ping() is not None
    monkeypatch.setenv("ART98_TOKEN", "wrong")
    assert service._token(replace(settings, token=TOKEN)) == TOKEN
    assert TOKEN not in repr(replace(settings, token=TOKEN))


def test_not_running_names_the_connect_host_and_port(tmp_path):
    s = make_settings(tmp_path, port=free_port(), connect="127.0.0.1", bind="0.0.0.0")
    with (
        pytest.raises(service.NotRunning, match=rf"127\.0\.0\.1:{s.control}\b"),
        service.attach(s),
    ):
        pass
