"""serve's single mode: the owner slot, release cleanup, status, no VM needed."""

import json
import socket
import threading
import time

import pytest
from art98.bridge import Bridge
from art98.container.host import ContainerError
from art98.qemu import QemuError, parse_snapshots
from serve_harness import TOKEN, Served


@pytest.fixture
def served(tmp_path):
    served = Served(tmp_path)
    yield served
    served.close()


def talk(served, channel, token=TOKEN):
    """One raw handshake: everything the server sends back, up to a newline."""
    sock = socket.create_connection(served.address, 2)
    sock.sendall(f"{token}\n{channel}\n".encode())
    line = sock.makefile("rb").readline().decode()
    return sock, line.strip()


def status(served):
    sock, line = talk(served, "status")
    sock.close()
    return json.loads(line)


def wait_for(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.01)


def test_exactly_one_of_many_simultaneous_handshakes_wins(served):
    count = 12
    barrier = threading.Barrier(count)
    answers, socks = [], []

    def knock():
        sock = socket.create_connection(served.address, 2)
        socks.append(sock)
        barrier.wait()
        sock.sendall(f"{TOKEN}\ncontrol\n".encode())
        answers.append(sock.makefile("rb").readline().decode().strip())

    threads = [threading.Thread(target=knock) for _ in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)
    assert answers.count("ok") == 1
    assert all(a.startswith("error busy") for a in answers if a != "ok")
    assert len(answers) == count
    for sock in socks:
        sock.close()


def test_the_busy_reply_says_who_holds_the_channel(served):
    first, line = talk(served, "control")
    assert line == "ok"
    second, line = talk(served, "control")
    assert line == "error busy: the control channel is held by another client"
    first.close()
    second.close()


def test_release_cleans_up_in_order_and_frees_the_slot_last(served):
    drops = served.server._drop_relay

    def recording():
        served.vm.calls.append(("drop_relay",))
        drops()

    served.server._drop_relay = recording
    owner, line = talk(served, "control")
    assert line == "ok"
    bridge = Bridge(served.channel("agent"), timeout=2)
    assert bridge.ping() == 1
    served.vm.calls.clear()
    served.vm.gates["pause"] = threading.Event()  # hold the cleanup at its last step
    owner.close()
    wait_for(lambda: ("pause",) in served.vm.calls)
    assert served.vm.calls == [("drop_relay",), ("eject_disc",), ("pause",)]
    # the slot is still taken: a waiter is refused and nothing of it reaches the VM
    waiter, line = talk(served, "control")
    assert line.startswith("error busy")
    with pytest.raises(ContainerError, match="busy"):
        served.channel("control")
    with pytest.raises(ContainerError, match="no control connection"):
        served.channel("agent")
    assert served.vm.calls == [("drop_relay",), ("eject_disc",), ("pause",)]
    assert status(served)["busy"] is True
    served.vm.gates["pause"].set()
    wait_for(lambda: status(served)["busy"] is False)
    next_owner = served.remote_when_free()
    assert served.vm.calls == [("drop_relay",), ("eject_disc",), ("pause",)]
    next_owner.close()
    waiter.close()
    bridge.close()


@pytest.mark.parametrize("failing", ["eject_disc", "pause"])
def test_a_cleanup_step_that_raises_still_frees_the_slot(served, failing):
    served.vm.fail[failing] = QemuError("boom")
    served.channel("control").close()
    again = served.remote_when_free()
    assert any(
        f"{failing.split('_')[0]}" in line and "boom" in line for line in served.logs
    )
    assert ("pause",) in served.vm.calls
    served.vm.fail.clear()
    again.pause()
    again.close()


def test_status_reports_server_state_and_makes_no_vm_call(served):
    assert status(served) == {
        "ok": True,
        "busy": False,
        "paused": False,
        "snapshots": ["ready"],
        "started_at": "2026-11-11T20:00:00Z",
    }
    vm = served.remote()
    vm.pause()
    served.vm.calls.clear()
    with served.server._vm_lock:  # a busy VM thread must not hold a status request up
        reply = status(served)
    assert reply["busy"] is True and reply["paused"] is True
    vm.resume()
    assert status(served)["paused"] is False
    served.vm.calls.clear()
    status(served)
    assert served.vm.calls == []
    vm.close()
    wait_for(lambda: status(served)["busy"] is False)
    assert status(served)["paused"] is True  # release pauses


def test_status_needs_the_token(served):
    sock, line = talk(served, "status", token="guess")
    sock.close()
    assert line == "error wrong token"


def test_revert_ejects_the_disc_before_loading_the_snapshot(served):
    vm = served.remote()
    vm.insert_disc(b"ISO")
    vm.load_snapshot("ready")
    assert served.vm.calls[-2:] == [("eject_disc",), ("load_snapshot", "ready")]
    assert served.vm.disc is False
    vm.close()


def test_the_removed_ops_are_refused(served):
    vm = served.remote()
    with pytest.raises(QemuError, match="not served"):
        vm._request("save_snapshot", snapshot="ready")
    with pytest.raises(QemuError, match="unknown op"):
        vm._request("quit")
    vm.pause()  # the link is still up
    vm.close()


def test_release_does_not_stop_serve(served):
    served.remote().close()
    wait_for(lambda: status(served)["busy"] is False)
    assert served.thread.is_alive()
    served.remote_when_free().close()
    assert served.thread.is_alive()


def test_serve_exits_when_the_vm_dies(served):
    served.vm.running = False
    served.thread.join(5)
    assert not served.thread.is_alive()
    assert "the VM is gone; quitting" in served.logs


CANNED = """List of snapshots present on all disks:
ID        TAG               VM SIZE                DATE     VM CLOCK     ICOUNT
--        ready           1.07 GiB 2026-11-11 20:00:00 00:01:02.345          --
--        warm              1 GiB  2026-11-11 20:05:00 00:02:00.000          --
"""


def test_snapshot_tags_are_parsed_from_info_snapshots():
    assert parse_snapshots(CANNED) == ["ready", "warm"]
    assert parse_snapshots("There is no snapshot available.\n") == []
    assert parse_snapshots("") == []


def test_close_returns_only_after_the_slot_is_free(served):
    vm = served.remote()
    served.vm.gates["pause"] = gate = threading.Event()  # a slow release
    threading.Timer(0.3, gate.set).start()
    vm.close()
    reply = status(served)
    assert reply["busy"] is False
    assert reply["paused"] is True
    served.remote().close()  # an immediate reconnect is not refused


def _keepalive_on(sock):
    assert sock.getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE)
    if hasattr(socket, "TCP_KEEPIDLE"):
        assert sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE) <= 30
        assert sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT) <= 5


def test_client_and_accepted_tcp_sockets_have_keepalive(served, monkeypatch):
    from art98.container import serve

    accepted = []
    real = serve.keepalive
    monkeypatch.setattr(serve, "keepalive", lambda s: accepted.append(s) or real(s))
    client = served.channel("control")
    try:
        _keepalive_on(client)
        assert accepted
        _keepalive_on(accepted[0])
    finally:
        client.close()
