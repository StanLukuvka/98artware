"""Bridge behaviour against a scripted stand-in for the agent."""

import socket
import struct
import threading
import time

import pytest
from art98 import win32
from art98.bridge import Bridge, BridgeError, BridgeTimeout, GuestCrashed
from art98.protocol import frame, parse_values, unframe


class FakeAgent:
    def __init__(self):
        self.host, self.guest = socket.socketpair()
        self.requests = []
        self.handlers = {}
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def send(self, payload: bytes):
        self.guest.sendall(frame(payload))

    def _loop(self):
        buffer = b""
        try:
            while chunk := self.guest.recv(65536):
                buffer += chunk
                *lines, buffer = buffer.split(b"\n")
                for line in lines:
                    payload = unframe(line)
                    request_id, verb, *rest = payload.split(b" ", 2)
                    args = parse_values(rest[0]) if rest else []
                    self.requests.append((verb.decode(), args))
                    self.handlers[verb.decode()](int(request_id), args)
        except OSError:
            pass  # the test closed the socket


@pytest.fixture
def pair():
    agent = FakeAgent()
    bridge = Bridge(agent.host, timeout=1.0)
    yield bridge, agent
    bridge.close()
    agent.guest.close()


def test_call_returns_value_error_and_buffers(pair):
    bridge, agent = pair
    agent.handlers["CALL"] = lambda i, a: agent.send(
        b"%d OK 4294967295 5 #0a000000" % i
    )
    result = bridge.user32.GetWindowRect(1)
    assert result.signed == -1 and result.last_error == 5
    assert result.buffers == [b"\x0a\0\0\0"]
    assert agent.requests == [("CALL", ["user32", "GetWindowRect", 1])]


def test_error_reply_raises(pair):
    bridge, agent = pair
    agent.handlers["CALL"] = lambda i, a: agent.send(b'%d ERR NOFUNC "Nope"' % i)
    with pytest.raises(BridgeError, match="NOFUNC: Nope"):
        bridge.user32.Nope()


def test_rows_arrive_before_final_reply(pair):
    bridge, agent = pair

    def windows(i, a):
        agent.send(b'%d + 16 2 1 10 20 110 220 "Notepad" "Untitled - Notepad"' % i)
        agent.send(b'%d + 17 2 0 4294967295 0 5 5 "Hidden" ""' % i)
        agent.send(b"%d OK 2" % i)

    agent.handlers["WINDOWS"] = windows
    first, second = bridge.windows()
    assert first.title == "Untitled - Notepad" and first.rect == (10, 20, 110, 220)
    assert second.rect[0] == -1 and not second.visible


def test_find_window_ignores_hidden_and_matches_substring(pair):
    bridge, agent = pair

    def windows(i, a):
        agent.send(b'%d + 16 2 0 0 0 1 1 "Notepad" "Untitled - Notepad"' % i)
        agent.send(b'%d + 17 2 1 0 0 1 1 "Notepad" "Untitled - Notepad"' % i)
        agent.send(b"%d OK 2" % i)

    agent.handlers["WINDOWS"] = windows
    assert bridge.find_window(title="untitled").hwnd == 17


def test_timeout_when_guest_stays_silent(pair):
    bridge, agent = pair
    agent.handlers["PING"] = lambda i, a: None
    with pytest.raises(BridgeTimeout):
        bridge.ping(timeout=0.05)


def test_corrupt_reply_times_out_instead_of_being_believed(pair):
    bridge, agent = pair
    agent.handlers["PING"] = lambda i, a: agent.guest.sendall(b"%d OK 1 *0000\n" % i)
    with pytest.raises(BridgeTimeout):
        bridge.ping(timeout=0.05)


def test_crash_fails_the_open_request_at_once(pair):
    bridge, agent = pair
    agent.handlers["CALL"] = lambda i, a: agent.send(b"! CRASH 3221225477 4198400")
    with pytest.raises(GuestCrashed, match="0xc0000005"):
        bridge.call("kernel32", "Boom")


def test_bad_frame_fails_the_open_request_at_once(pair):
    bridge, agent = pair
    agent.handlers["CALL"] = lambda i, a: agent.send(b"! BADFRAME")
    started = time.monotonic()
    with pytest.raises(BridgeError, match="corrupt request"):
        bridge.call("kernel32", "GetTickCount")
    assert time.monotonic() - started < 0.5  # the timeout is 1 s
    assert bridge.wait_event("BADFRAME", timeout=0) == []


def test_async_call_completes_through_an_event(pair):
    bridge, agent = pair
    agent.handlers["ACALL"] = lambda i, a: agent.send(b"%d OK %d" % (i, i))
    pending = bridge.acall("user32", "MessageBoxA", 0, "hi", "t", 0)
    assert not pending.done
    agent.send(b"! DONE %d 1 0" % pending.id)
    assert pending.wait().value == 1


def test_abandon_fails_open_requests_and_async_calls_at_once(pair):
    bridge, agent = pair
    bridge.timeout = 30
    agent.handlers["ACALL"] = lambda i, a: agent.send(b"%d OK %d" % (i, i))
    agent.handlers["CALL"] = lambda i, a: None  # never answers
    pending = bridge.acall("kernel32", "Sleep", 4000)
    blocked = []
    thread = threading.Thread(
        target=lambda: blocked.append(
            pytest.raises(BridgeError, bridge.call, "kernel32", "Sleep", 1)
        )
    )
    thread.start()
    deadline = time.monotonic() + 2
    while (
        not any(r[0] == "CALL" for r in agent.requests) and time.monotonic() < deadline
    ):
        time.sleep(0.01)
    bridge.abandon("the desktop was reverted")
    thread.join(2)
    assert blocked and "reverted" in str(blocked[0].value)
    assert pending.done
    with pytest.raises(BridgeError, match="reverted"):
        pending.wait(timeout=1)
    agent.send(b"! DONE %d 0 0" % pending.id)  # a late answer is ignored
    agent.handlers["PING"] = lambda i, a: agent.send(b"%d OK 5 1" % i)
    assert bridge.ping() == 5


def test_wait_event_picks_by_name_and_leaves_the_rest(pair):
    bridge, agent = pair
    agent.send(b"! OTHER 1")
    agent.send(b"! HELLO 1 500")
    assert bridge.wait_event("HELLO") == [1, 500]
    assert bridge.wait_event("OTHER") == [1]


def test_closed_link_fails_open_and_future_requests(pair):
    bridge, agent = pair
    agent.handlers["PING"] = lambda i, a: agent.guest.close()
    with pytest.raises(BridgeError, match="closed"):
        bridge.ping()
    with pytest.raises(BridgeError, match="closed"):
        bridge.ping()


def test_wait_ready_rejects_another_protocol_version(pair):
    bridge, agent = pair
    agent.handlers["PING"] = lambda i, a: agent.send(b"%d OK 100 99" % i)
    with pytest.raises(BridgeError, match="protocol 99"):
        bridge.wait_ready(1)


def test_file_transfer_is_chunked_both_ways(pair):
    bridge, agent = pair
    stored = bytearray()

    def put(i, a):
        _path, offset, data = a
        assert offset == len(stored)
        stored.extend(data)
        agent.send(b"%d OK %d" % (i, len(data)))

    def get(i, a):
        _path, offset, n = a
        chunk = bytes(stored[offset : offset + n])
        agent.send(b"%d OK %d #%s" % (i, len(stored), chunk.hex().encode()))

    agent.handlers["PUT"], agent.handlers["GET"] = put, get
    blob = bytes(range(256)) * 40
    bridge.put_file(r"C:\X.BIN", blob)
    assert sum(1 for r in agent.requests if r[0] == "PUT") == 3
    assert bridge.get_file(r"C:\X.BIN") == blob


def test_short_write_on_the_guest_fails_the_put(pair):
    bridge, agent = pair
    agent.handlers["PUT"] = lambda i, a: agent.send(b"%d OK %d" % (i, len(a[2]) - 1))
    with pytest.raises(BridgeError, match="wrote 4095 of 4096"):
        bridge.put_file(r"C:\FULL.BIN", bytes(10000))
    assert len(agent.requests) == 1


def test_put_of_an_empty_file_still_creates_it(pair):
    bridge, agent = pair
    agent.handlers["PUT"] = lambda i, a: agent.send(b"%d OK 0" % i)
    bridge.put_file(r"C:\EMPTY", b"")
    assert len(agent.requests) == 1


def test_set_display_mode_uses_the_drivers_own_mode(pair):
    bridge, agent = pair
    modes = [(8, 640, 480), (16, 800, 600)]
    seen = []

    def call(i, a):
        name = a[1]
        if name == "EnumDisplaySettingsA":
            index = a[3]
            if index >= len(modes):
                agent.send(b"%d OK 0 0 #00" % i)
                return
            blob = bytearray(a[4])
            struct.pack_into("<III", blob, 104, *modes[index])
            agent.send(b"%d OK 1 0 #%s" % (i, bytes(blob).hex().encode()))
        else:
            seen.append((a[2], a[3]))
            agent.send(b"%d OK 0 0 #00" % i)

    agent.handlers["CALL"] = call
    win32.set_display_mode(bridge, 800, 600, 16)
    devmode, flags = seen[0]
    assert struct.unpack_from("<III", devmode, 104) == (16, 800, 600)
    assert struct.unpack_from("<I", devmode, 40)[0] == 0x1C0000 and flags == 1


def test_missing_display_mode_is_an_error(pair):
    bridge, agent = pair
    agent.handlers["CALL"] = lambda i, a: agent.send(b"%d OK 0 0 #00" % i)
    with pytest.raises(BridgeError, match="no 800x600x16"):
        win32.set_display_mode(bridge, 800, 600, 16)
