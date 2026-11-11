"""guestfiles: where the guest programs are."""

from art98 import guestfiles


def test_art98_guest_build_overrides_the_checkout_folder(tmp_path, monkeypatch):
    monkeypatch.delenv("ART98_GUEST_BUILD", raising=False)
    assert guestfiles.guest_build().parts[-2:] == ("guest", "build")
    monkeypatch.setenv("ART98_GUEST_BUILD", str(tmp_path))
    assert guestfiles.guest_build() == tmp_path
