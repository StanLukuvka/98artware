"""The real agent.exe, run under Wine, with a pty standing in for COM1.

This is not Windows 98, but it does run the shipped binary through its real
serial, parsing, proxy and crash paths. Set ART98_TEST_WINEPREFIX to reuse a
prefix, because making a new one takes a minute.
"""

import os
import pty
import shutil
import socket
import struct
import subprocess
import threading
import time
import tty
from pathlib import Path

import pytest

from art98.bridge import Bridge, BridgeError, GuestCrashed
from art98.guestfiles import guest_build
from art98.protocol import Out

AGENT = guest_build() / "agent.exe"
pytestmark = [
    pytest.mark.skipif(shutil.which("wine") is None, reason="needs Wine"),
    pytest.mark.skipif(not AGENT.exists(), reason="agent not built"),
]

WS_POPUP_VISIBLE = 0x90000000
SWP_NOZORDER_NOACTIVATE = 0x14


def relay(source: int, sink: socket.socket) -> None:
    try:
        while data := os.read(source, 4096):
            sink.sendall(data)
    except OSError:
        pass


def relay_back(source: socket.socket, sink: int) -> None:
    try:
        while data := source.recv(4096):
            os.write(sink, data)
    except OSError:
        pass


@pytest.fixture(scope="module")
def prefix(tmp_path_factory):
    path = os.environ.get("ART98_TEST_WINEPREFIX") or tmp_path_factory.mktemp("wine")
    env = {k: v for k, v in os.environ.items() if k not in ("DISPLAY", "WAYLAND_DISPLAY")}
    env["WINEPREFIX"] = str(path)
    if not (Path(path) / "drive_c").exists():
        subprocess.run(["wine", "cmd", "/c", "ver"], env=env, check=True, capture_output=True,
                       timeout=240)
    # The agent needs a window, and these tests must not need a display.
    subprocess.run(["wine", "reg", "add", r"HKCU\Software\Wine\Drivers", "/v", "Graphics",
                    "/d", "null", "/f"], env=env, check=True, capture_output=True, timeout=60)
    return Path(path), env


@pytest.fixture
def agent(prefix, tmp_path):
    path, env = prefix
    master, slave = pty.openpty()
    tty.setraw(master)
    tty.setraw(slave)
    com1 = path / "dosdevices" / "com1"
    com1.unlink(missing_ok=True)
    com1.symlink_to(os.ttyname(slave))
    ours, theirs = socket.socketpair()
    threading.Thread(target=relay, args=(master, theirs), daemon=True).start()
    threading.Thread(target=relay_back, args=(theirs, master), daemon=True).start()
    bridge = Bridge(ours, timeout=15)
    binary = tmp_path / "agent.exe"
    shutil.copy(AGENT, binary)
    process = subprocess.Popen(["wine", str(binary)], env=env, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    bridge.wait_ready(45)
    yield bridge
    try:
        bridge.request("QUIT", timeout=3)
    except BridgeError:
        pass
    process.kill()
    process.wait()
    bridge.close()
    os.close(master)
    os.close(slave)


def test_announces_itself(agent):
    version, ticks = agent.wait_event("HELLO", timeout=10)
    assert version == 1 and ticks > 0


def test_ping_returns_ticks_that_advance(agent):
    first = agent.ping()
    time.sleep(0.1)
    assert agent.ping() > first


def test_string_argument_reaches_the_call(agent):
    assert agent.kernel32.lstrlenA("hello world").value == 11


def test_out_buffer_comes_back(agent):
    result = agent.kernel32.GetSystemDirectoryA(Out(260), 260)
    assert b"system32" in result.buffers[0].lower()


def test_in_out_buffer_is_written_and_returned(agent):
    result = agent.user32.SetRect(struct.pack("<4i", 9, 9, 9, 9), 1, 2, 3, 4)
    assert struct.unpack("<4i", result.buffers[0]) == (1, 2, 3, 4)


def test_cdecl_function_leaves_the_stack_balanced(agent):
    result = agent.user32.wsprintfA(Out(64), "%d-%s", 42, "ok")
    assert result.value == 5 and result.buffers[0].startswith(b"42-ok\0")
    assert agent.kernel32.lstrlenA("still alive").value == 11


def test_strings_with_quotes_and_newlines_survive(agent):
    text = 'say "hi"\r\n\\done\t!'
    assert agent.kernel32.lstrlenA(text).value == len(text)


def test_last_error_is_reported(agent):
    result = agent.kernel32.GetFileAttributesA(r"C:\does\not\exist")
    assert result.signed == -1 and result.last_error in (2, 3)


def test_unknown_dll_and_function_are_errors(agent):
    with pytest.raises(BridgeError, match="NODLL"):
        agent.call("nosuch", "Thing")
    with pytest.raises(BridgeError, match="NOFUNC"):
        agent.user32.NoSuchFunction()


def test_unknown_verb_is_an_error(agent):
    with pytest.raises(BridgeError, match="BADVERB"):
        agent.request("DANCE")


def test_window_can_be_created_found_moved_and_measured(agent):
    hwnd = agent.user32.CreateWindowExA(
        0, "STATIC", "art98 test", WS_POPUP_VISIBLE, 10, 20, 100, 50, 0, 0, 0, 0).value
    assert hwnd
    window = agent.find_window(title="art98 test")
    assert window.hwnd == hwnd and window.class_name.lower() == "static"
    agent.user32.SetWindowPos(hwnd, 0, 200, 150, 320, 240, SWP_NOZORDER_NOACTIVATE)
    assert agent.sync(hwnd) > 0
    rect = agent.user32.GetWindowRect(hwnd, Out(16)).buffers[0]
    assert struct.unpack("<4i", rect) == (200, 150, 520, 390)
    agent.user32.DestroyWindow(hwnd)


def test_agent_hides_its_own_window(agent):
    assert not [w for w in agent.windows() if w.class_name == "Art98Agent"]


def test_spawn_and_process_list(agent):
    pid = agent.spawn(r"C:\windows\system32\cmd.exe /c ping -n 3 127.0.0.1 > NUL")
    assert pid
    assert pid in [p for p, _ in agent.processes()]


def test_spawn_failure_is_an_error(agent):
    with pytest.raises(BridgeError, match="SPAWN"):
        agent.spawn(r"C:\does\not\exist.exe")


def test_file_round_trip(agent):
    blob = bytes(range(256)) * 20
    agent.put_file(r"C:\art98-test.bin", blob)
    assert agent.get_file(r"C:\art98-test.bin") == blob
    agent.kernel32.DeleteFileA(r"C:\art98-test.bin")


def test_missing_file_is_an_error(agent):
    with pytest.raises(BridgeError, match="FILE"):
        agent.get_file(r"C:\does\not\exist")


def test_async_call_leaves_the_agent_responsive(agent):
    pending = agent.acall("kernel32", "Sleep", 1500)
    started = time.monotonic()
    agent.ping()
    assert time.monotonic() - started < 1.0 and not pending.done
    pending.wait(5)


def test_async_call_returns_out_buffers(agent):
    result = agent.acall("kernel32", "GetSystemDirectoryA", Out(260), 260).wait(5)
    assert b"system32" in result.buffers[0].lower()


def test_corrupt_frame_is_reported_and_harmless(agent):
    agent.clear_events()
    agent._sock.sendall(b"99 PING *0000\n")
    agent.wait_event("BADFRAME", timeout=5)
    agent.ping()


def test_malformed_argument_is_an_error(agent):
    from art98.protocol import frame

    agent._sock.sendall(frame(b'77 CALL "unterminated'))
    agent._sock.sendall(frame(b"78 CALL &999999"))
    agent.ping()


def test_crash_is_reported_and_the_agent_comes_back(agent):
    agent.wait_event("HELLO", timeout=10)
    with pytest.raises(GuestCrashed, match="0xe0001234"):
        agent.kernel32.RaiseException(0xE0001234, 0, 0, 0)
    agent.wait_event("HELLO", timeout=30)
    agent.wait_ready(10)
    assert agent.kernel32.lstrlenA("back").value == 4
