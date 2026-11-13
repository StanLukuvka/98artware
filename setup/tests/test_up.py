"""`art98 up` without an engine: its compose calls, the disc and key checks, and the
host tool hints."""

import json
import subprocess

import pytest
from art98.container.host import ContainerError, Engine
from art98.settings import Settings
from art98_setup import builder, up


def fake_engine(monkeypatch, name):
    monkeypatch.setattr(
        "art98.container.host.shutil.which", lambda tool: f"/usr/bin/{tool}"
    )
    return Engine(name)


def test_install_hints_cover_fedora_and_debian():
    hints = {
        system: packages
        for system, _, packages in builder.install_hints(
            ["qemu-img", "i686-w64-mingw32-gcc"]
        )
    }
    assert hints["Fedora"] == ["qemu-img", "mingw32-gcc"]
    assert hints["Debian, Ubuntu"] == ["qemu-utils", "gcc-mingw-w64-i686"]


def scripted_engine(monkeypatch, config=None, stored=True, code=0):
    """A docker that records compose calls (with their env), answers `config` with
    `config` as JSON, holds an image only if `stored`, and exits `code` from `run`."""
    engine = fake_engine(monkeypatch, "docker")
    calls = []

    def run(self, *args, env=None, **kw):
        calls.append((args, env))
        out = subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")
        if "run" in args:
            out.returncode = code
        if "config" in args:
            out.stdout = json.dumps(config).encode()
        return out

    monkeypatch.setattr(Engine, "__call__", run)
    monkeypatch.setattr(Engine, "has_image", lambda self, image: stored)
    return engine, calls


def test_the_image_builds_through_compose_and_must_be_stored(monkeypatch):
    engine, calls = scripted_engine(monkeypatch)
    up.build_image(engine, Settings(image="art98:test"))
    assert calls[0][0][:1] + calls[0][0][-2:] == ("compose", "build", "vm")
    assert calls[0][1]["ART98_IMAGE"] == "art98:test"
    assert (up.ROOT / ".dockerignore").read_text().splitlines()[1] == "work/"
    engine, _ = scripted_engine(monkeypatch, stored=False)
    with pytest.raises(ContainerError, match="did not store it"):
        up.build_image(engine, Settings(image="art98:test"))


def setup_config(disc, key=None):
    """What `compose config` says about the setup service: the disc mount and the key."""
    secret = {"file": str(key)} if key else {"environment": "ART98_PRODUCT_KEY"}
    volumes = [{"source": "/w", "target": "/work"}]
    volumes += [{"source": str(disc), "target": up.DISC}] if disc else []
    return {
        "services": {"setup": {"volumes": volumes}},
        "secrets": {"art98_key": secret},
    }


def test_setup_inputs_take_iso_and_the_key_from_the_environment(tmp_path, monkeypatch):
    iso = tmp_path / "win98.iso"
    iso.write_bytes(b"x")
    monkeypatch.setenv("ART98_PRODUCT_KEY", "AAAAA-BBBBB")
    engine, calls = scripted_engine(monkeypatch, setup_config(iso))
    extra = up.setup_inputs(engine, Settings(root=tmp_path), iso, 2047)
    assert extra == {"ART98_DISK_MB": "2047", "ART98_ISO": str(iso)}  # no key in it
    assert calls[0][0][-5:] == ("--profile", "setup", "config", "--format", "json")
    assert calls[0][1]["ART98_ISO"] == str(iso)


def test_setup_inputs_prompt_for_the_key_without_env_or_file(tmp_path, monkeypatch):
    iso = tmp_path / "win98.iso"
    iso.write_bytes(b"x")
    monkeypatch.delenv("ART98_PRODUCT_KEY", raising=False)
    monkeypatch.setattr("builtins.input", lambda p="": "AAAAA-BBBBB")
    engine, _ = scripted_engine(monkeypatch, setup_config(iso))
    extra = up.setup_inputs(engine, Settings(root=tmp_path), None, 2047)
    assert extra["ART98_PRODUCT_KEY"] == "AAAAA-BBBBB"  # compose's environment secret


def test_setup_inputs_check_the_override_key_file_and_disc(tmp_path, monkeypatch):
    monkeypatch.delenv("ART98_PRODUCT_KEY", raising=False)
    monkeypatch.setattr("builtins.input", lambda p="": pytest.fail("prompted"))
    iso, key = tmp_path / "mine.iso", tmp_path / "product-key.txt"
    settings = Settings(root=tmp_path)
    engine, _ = scripted_engine(monkeypatch, setup_config(iso, key))
    with pytest.raises(FileNotFoundError, match="no disc at .*mine.iso.*--iso"):
        up.setup_inputs(engine, settings, None, 2047)
    iso.write_bytes(b"x")
    with pytest.raises(FileNotFoundError, match="no product key file"):
        up.setup_inputs(engine, settings, None, 2047)
    key.write_text("AAAAA-BBBBB\n")
    assert up.setup_inputs(engine, settings, None, 2047) == {"ART98_DISK_MB": "2047"}
    with pytest.raises(ContainerError, match="drop --iso or that mount"):
        up.setup_inputs(engine, settings, tmp_path / "other.iso", 2047)


def test_setup_inputs_without_any_disc_say_how_to_give_one(tmp_path, monkeypatch):
    engine, _ = scripted_engine(monkeypatch, setup_config(None))
    with pytest.raises(FileNotFoundError, match="pass --iso"):
        up.setup_inputs(engine, Settings(root=tmp_path), None, 2047)


def test_up_warns_when_it_reuses_an_old_image(tmp_path, monkeypatch):
    engine = fake_engine(monkeypatch, "docker")
    monkeypatch.setattr(up, "inspect_created", lambda eng, image: (True, 1.0))
    monkeypatch.setattr(up, "container_warning", lambda created, image: ["old image"])
    (tmp_path / "image.json").write_text("{}")
    lines = []
    monkeypatch.setattr(up, "ROOT", tmp_path)  # the guest programs are "there"
    (tmp_path / "guest" / "build").mkdir(parents=True)
    (tmp_path / "guest" / "build" / "view.exe").write_bytes(b"x")
    (tmp_path / "guest" / "build" / "sources.sha256").write_text("")
    calls = []
    monkeypatch.setattr(Engine, "__call__", lambda self, *a, **k: calls.append(a))
    assert up.up(tmp_path, engine=engine, log=lines.append) == 0
    assert calls == []  # setup is done: no run/start/snapshot of any VM
    assert not hasattr(up, "boot")
    assert "[up] warning: old image" in lines
    assert "art98 vm start" in lines[-1]


def test_up_copies_out_when_the_digest_file_is_missing(tmp_path, monkeypatch):
    engine = fake_engine(monkeypatch, "docker")
    monkeypatch.setattr(up, "inspect_created", lambda eng, image: (True, 1.0))
    monkeypatch.setattr(up, "container_warning", lambda created, image: [])
    monkeypatch.setattr(up, "ROOT", tmp_path)
    (tmp_path / "guest" / "build").mkdir(parents=True)
    (tmp_path / "guest" / "build" / "view.exe").write_bytes(b"x")  # an old build
    (tmp_path / "image.json").write_text("{}")
    copied = []
    monkeypatch.setattr(Engine, "copy_out", lambda self, *a: copied.append(a))
    assert up.up(tmp_path, engine=engine, log=lambda _: None) == 0
    assert len(copied) == 1


def test_up_resolves_a_missing_work_through_art98_toml(tmp_path, monkeypatch):
    (tmp_path / "art98.toml").write_text('[vm]\nwork = "elsewhere"\n')
    monkeypatch.chdir(tmp_path)
    engine = fake_engine(monkeypatch, "docker")
    monkeypatch.setattr(up, "inspect_created", lambda eng, image: (True, 1.0))
    monkeypatch.setattr(up, "container_warning", lambda created, image: [])
    monkeypatch.setattr(up, "ROOT", tmp_path)
    (tmp_path / "guest" / "build").mkdir(parents=True)
    (tmp_path / "guest" / "build" / "view.exe").write_bytes(b"x")
    (tmp_path / "guest" / "build" / "sources.sha256").write_text("")
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "image.json").write_text("{}")
    lines = []
    assert up.up(engine=engine, log=lines.append) == 0
    assert f"{tmp_path / 'elsewhere'}/image.json exists" in lines[-2]


def test_the_key_prompt_is_visible_and_stripped(monkeypatch):
    monkeypatch.delenv("ART98_PRODUCT_KEY", raising=False)
    prompts = []
    monkeypatch.setattr(
        "builtins.input", lambda p="": prompts.append(p) or " AAAAA-BBBBB \n"
    )
    assert up._read_key() == "AAAAA-BBBBB"
    assert prompts == ["Windows 98 product key: "]


def ready_to_set_up(tmp_path, monkeypatch, code):
    monkeypatch.setattr(up, "inspect_created", lambda eng, image: (True, 1.0))
    monkeypatch.setattr(up, "container_warning", lambda created, image: [])
    monkeypatch.setattr(up, "ROOT", tmp_path)
    (tmp_path / "guest" / "build").mkdir(parents=True)
    (tmp_path / "guest" / "build" / "view.exe").write_bytes(b"x")
    (tmp_path / "guest" / "build" / "sources.sha256").write_text("")
    iso = tmp_path / "win98.iso"
    iso.write_bytes(b"x")
    monkeypatch.delenv("ART98_PRODUCT_KEY", raising=False)
    monkeypatch.setattr("builtins.input", lambda p="": "AAAAA-BBBBB-CCCCC-DDDDD-EEEEE")
    engine, calls = scripted_engine(monkeypatch, setup_config(iso), code=code)
    return engine, calls, iso


def test_up_runs_the_setup_service_with_the_key_only_in_its_environment(
    tmp_path, monkeypatch
):
    engine, calls, iso = ready_to_set_up(tmp_path, monkeypatch, 0)
    assert up.up(tmp_path / "work", iso, engine=engine, log=lambda _: None) == 0
    args, env = calls[-1]
    assert args[-4:] == ("run", "--rm", "--service-ports", "setup")
    assert env["ART98_PRODUCT_KEY"] == "AAAAA-BBBBB-CCCCC-DDDDD-EEEEE"
    assert env["ART98_ISO"] == str(iso) and env["ART98_DISK_MB"] == "2047"
    assert not any("AAAAA" in a for args, _ in calls for a in args)


def test_a_failed_setup_hint_does_not_promise_a_clean_resume(tmp_path, monkeypatch):
    engine, _, iso = ready_to_set_up(tmp_path, monkeypatch, 3)
    lines = []
    assert up.up(tmp_path / "work", iso, engine=engine, log=lines.append) == 3
    assert "see the error above" in lines[-1]
    assert "to resume" not in lines[-1]
