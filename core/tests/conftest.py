import pytest
from art98 import freshness
from art98.anim import Scene


@pytest.fixture(autouse=True)
def stock_desktop(monkeypatch):
    """The fake guests don't model the blank desktop, so scenes keep the stock
    one unless a test asks. test_desktop.py covers the blank start."""
    monkeypatch.setattr(Scene, "desktop", "stock")


@pytest.fixture(autouse=True)
def quiet_freshness(request, monkeypatch):
    """Stale-build warnings go to stderr, which breaks the exact-stderr CLI tests.
    test_freshness.py keeps the real warn."""
    if request.node.path.name == "test_freshness.py":
        return
    monkeypatch.setattr(freshness, "warn", lambda *a, **k: None)
