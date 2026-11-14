"""Settings: defaults, the file, ART98_IMAGE, --work, discovery and errors."""

import pytest
from art98 import settings
from art98.settings import SettingsError, load


@pytest.fixture(autouse=True)
def clean(monkeypatch, tmp_path):
    monkeypatch.delenv("ART98_IMAGE", raising=False)
    monkeypatch.chdir(tmp_path)


def write(folder, text):
    (folder / "art98.toml").write_text(text)


def test_defaults_without_a_file(tmp_path):
    s = load()
    assert (s.image, s.control) == ("localhost/art98:latest", 7598)
    assert s.source is None and s.work_dir == (tmp_path / "work").resolve()


def test_file_overrides_defaults(tmp_path):
    write(tmp_path, '[vm]\nimage = "x"\n[ports]\ncontrol = 7599\n')
    s = load()
    assert (s.image, s.control) == ("x", 7599)
    assert s.source == tmp_path / "art98.toml"


def test_env_image_overrides_file(tmp_path, monkeypatch):
    write(tmp_path, '[vm]\nimage = "from-file"\n')
    assert load().image == "from-file"
    monkeypatch.setenv("ART98_IMAGE", "from-env")
    assert load().image == "from-env"


def test_work_flag_overrides_file_and_resolves_against_cwd(tmp_path):
    (tmp_path / "sub").mkdir()
    write(tmp_path, '[vm]\nwork = "filework"\n')
    assert load().work_dir == (tmp_path / "filework").resolve()
    assert load("flagwork").work_dir == (tmp_path / "flagwork").resolve()


def test_discovery_walks_up_and_relative_work_follows_the_file(tmp_path, monkeypatch):
    write(tmp_path, '[vm]\nwork = "w"\n')
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    monkeypatch.chdir(deep)
    assert settings.find() == tmp_path / "art98.toml"
    assert load().work_dir == (tmp_path / "w").resolve()


@pytest.mark.parametrize(
    "text",
    [
        "[vm]\nbogus = 1\n",
        "[nope]\nx = 1\n",
        "[vm]\nimage = 3\n",
        '[ports]\ncontrol = "7598"\n',
        "[ports]\ncontrol = true\n",
        "[ports]\ncontrol = 0\n",
        "[ports]\ncontrol = 70000\n",
        # gone with compose: the container name is compose's, VNC is in the override
        '[vm]\ncontainer = "art98-vm"\n',
        '[ports]\nbind = "127.0.0.1"\n',
        "[ports]\nvnc = 5900\n",
        "[ports]\nsetup_vnc = 5998\n",
        "[vm\n",
    ],
)
def test_bad_files_raise(tmp_path, text):
    write(tmp_path, text)
    with pytest.raises(SettingsError, match="art98.toml"):
        load()


def test_the_committed_file_matches_the_defaults(monkeypatch):
    monkeypatch.chdir(settings.__file__.rsplit("/core/", 1)[0])
    s = load()
    assert s.source is not None
    assert (s.image, s.work, s.control) == (
        "localhost/art98:latest",
        "work",
        7598,
    )


def test_new_vm_keys_default_to_unset(tmp_path):
    s = load()
    assert (s.transport, s.token_file, s.connect) == (None, None, None)
    assert s.token_path == s.work_dir / "vm.token"


def test_transport_token_file_and_connect_parse(tmp_path):
    write(
        tmp_path,
        '[vm]\ntransport = "tcp"\ntoken_file = "keys/vm.token"\n'
        '[ports]\nconnect = "host.internal"\n',
    )
    s = load()
    assert (s.transport, s.connect_host) == ("tcp", "host.internal")
    assert s.token_path == tmp_path / "keys" / "vm.token"  # against the toml's folder


def test_token_file_resolves_against_the_toml_not_the_cwd(tmp_path, monkeypatch):
    write(tmp_path, '[vm]\ntoken_file = "t"\n')
    (tmp_path / "sub").mkdir()
    monkeypatch.chdir(tmp_path / "sub")
    assert load().token_path == tmp_path / "t"


def test_an_absolute_token_file_is_kept(tmp_path):
    write(tmp_path, f'[vm]\ntoken_file = "{tmp_path}/abs.token"\n')
    assert load().token_path == tmp_path / "abs.token"


def test_connect_defaults_to_loopback_where_compose_publishes():
    assert settings.Settings().connect_host == "127.0.0.1"
    assert settings.Settings(connect="vmhost").connect_host == "vmhost"


@pytest.mark.parametrize(
    "text",
    [
        '[vm]\ntransport = "pipe"\n',
        "[vm]\ntransport = 1\n",
        '[vm]\ntoken_file = ""\n',
        "[vm]\ntoken_file = 3\n",
        '[ports]\nconnect = ""\n',
        "[ports]\nconnect = 7598\n",
    ],
)
def test_bad_new_keys_raise(tmp_path, text):
    write(tmp_path, text)
    with pytest.raises(SettingsError, match="art98.toml"):
        load()
