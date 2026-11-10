import pytest

from art98.anim import Scene


@pytest.fixture(autouse=True)
def stock_desktop(monkeypatch):
    """The fake guests don't model the blank desktop, so scenes keep the stock
    one unless a test asks. test_desktop.py covers the blank start."""
    monkeypatch.setattr(Scene, "desktop", "stock")
