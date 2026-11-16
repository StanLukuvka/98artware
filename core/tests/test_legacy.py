"""art98.legacy: the names the Hermes plugin (art98 frozen at 94f0fd3) uses, and the wire
exchange of that old client against today's serve. Delete with legacy.py when the plugin is
re-vendored. The recorded requests below are the shapes the 94f0fd3 client sends; the test
does not read git history."""

import json
import socket

import pytest
from art98 import legacy
from art98.anim.scene import Scene
from art98.errors import UsageError
from art98.settings import Settings
from serve_harness import TOKEN, Served

# ---- names ----


def test_old_module_paths_are_the_new_modules():
    import art98.service as old_service
    import art98.win32 as old_win32
    from art98.container import service
    from art98.guest import win32

    assert old_service is service and old_win32 is win32
    from art98 import service as via_package
    from art98 import win32 as win32_via_package

    assert via_package is service and win32_via_package is win32


def test_every_name_desk_py_uses_exists():
    from art98 import service
    from art98.actions.keyboard import KEY_HOLD_MS, KEY_SETTLE, char_chord, key_chord
    from art98.cli import main
    from art98.win32 import mouse_button

    for name in ("attach", "_connect", "_read_status", "_address", "_token", "Busy",
                 "NotRunning", "ServiceError"):  # fmt: skip
        assert callable(getattr(service, name))
    assert all(callable(f) for f in (char_chord, key_chord, main, mouse_button))
    assert KEY_HOLD_MS and KEY_SETTLE
    assert legacy.MODULES  # the table the aliases come from


def test_settings_still_take_the_old_source_keyword(tmp_path):
    from art98 import settings

    toml = tmp_path / "art98.toml"
    toml.write_text('[vm]\ntransport = "tcp"\n')
    assert settings.find(tmp_path) == toml
    found = Settings(**settings._read(toml), source=toml, root=toml.parent, token="t")
    assert found.transport == "tcp" and found.token == "t"
    assert not hasattr(found, "source")


def test_fps_sets_output_fps():
    assert type("Old", (Scene,), {"fps": 24}).output_fps == 24


def test_fps_subclass_overrides_an_inherited_output_fps():
    base = type("Base", (Scene,), {"output_fps": 60})
    assert type("Sub", (base,), {"fps": 24}).output_fps == 24


def test_fps_agreeing_with_output_fps_is_fine_and_disagreeing_is_refused():
    assert type("Same", (Scene,), {"fps": 24, "output_fps": 24}).output_fps == 24
    with pytest.raises(UsageError, match="Both.*both fps and output_fps"):
        type("Both", (Scene,), {"fps": 24, "output_fps": 30})


def test_a_scene_without_fps_keeps_the_default():
    assert type("Plain", (Scene,), {}).output_fps == Scene.output_fps
    assert legacy.scene_fps(type("Plain2", (Scene,), {})) is None


# ---- the 94f0fd3 client's wire exchange against today's serve ----
# Recorded from art98/container/host.py and service.py at 94f0fd3: every connection sends
# "<token>\n<channel>\n"; status answers one JSON line, control and agent answer "ok\n".


@pytest.fixture
def served(tmp_path):
    s = Served(tmp_path)
    yield s
    s.close()


def old_connect(served, channel, token=TOKEN):
    sock = socket.create_connection(served.address, 3)
    sock.sendall(f"{token}\n{channel}\n".encode())
    return sock, sock.makefile("rb")


def test_old_client_status_read(served):
    sock, reader = old_connect(served, "status")
    reply = json.loads(reader.readline())
    sock.close()
    assert reply["ok"] is True
    # the keys 94f0fd3's service._connect and desk.py read
    assert reply["snapshots"] == ["ready"]
    assert reply["busy"] is False and reply["paused"] in (True, False)
    assert "started_at" in reply


def test_old_client_status_with_a_bad_token_is_not_ok(served):
    sock, reader = old_connect(served, "status", token="wrong")
    line = reader.readline().decode()
    sock.close()
    assert line.startswith(
        "error"
    )  # the old client raises Unhealthy("... refused ...")


def test_old_client_control_session(served):
    sock, reader = old_connect(served, "control")
    assert reader.readline() == b"ok\n"

    def ask(**request):
        sock.sendall(json.dumps(request).encode() + b"\n")
        reply = json.loads(reader.readline())
        extra = reader.read(reply["size"]) if reply.get("size") else b""
        return reply, extra

    assert ask(op="resume")[0]["ok"] is True
    assert ask(op="revert", snapshot="ready")[0]["ok"] is True
    assert ask(op="send_keys", keys=["ctrl", "a"], hold_ms=40)[0]["ok"] is True
    reply, png = ask(op="screenshot", format="png", shared=False)
    assert reply["ok"] is True and png.startswith(b"\x89PNG")
    # a second control client while this one holds the lock: "error busy..." (the old
    # client turns any non-"ok" answer into a ContainerError)
    other, other_reader = old_connect(served, "control")
    assert other_reader.readline().startswith(b"error busy")
    other.close()
    assert ask(op="pause")[0]["ok"] is True
    sock.shutdown(socket.SHUT_WR)
    reader.read()  # the container closes its end last, after releasing
    sock.close()
    names = [call[0] for call in served.vm.calls]
    wanted = ("resume", "load_snapshot", "send_keys", "pause")
    assert [n for n in names if n in wanted][:4] == list(wanted)
    assert ("send_keys", ("ctrl", "a"), 40) in served.vm.calls


def test_old_client_agent_channel_relays_a_ping(served):
    from art98.guest.protocol import frame, unframe

    control, control_reader = old_connect(
        served, "control"
    )  # the agent needs the lock held
    assert control_reader.readline() == b"ok\n"
    sock, reader = old_connect(served, "agent")
    assert reader.readline() == b"ok\n"
    sock.sendall(frame(b"1 PING") + b"\n")
    answer = unframe(reader.readline().rstrip(b"\n"))
    sock.close()
    control.close()
    assert answer.startswith(b"1 OK")


def test_protocol_version_is_the_one_94f0fd3_checked():
    from art98.guest.protocol import PROTOCOL_VERSION

    assert PROTOCOL_VERSION == 1
