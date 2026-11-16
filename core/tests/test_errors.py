"""Every error art98 raises on purpose inherits Art98Error, from the one leaf module."""

import ast
import importlib
import inspect
import pkgutil
from pathlib import Path

import art98
import art98_setup
import pytest
from art98 import cli, errors
from art98.base.space import PlacementError
from art98.errors import Art98Error

PACKAGES = (art98, art98_setup)


def _modules():
    for package in PACKAGES:
        yield package.__name__
        for info in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
            yield info.name


def _own_exceptions():
    """Every exception class (warnings aside) defined or imported in art98 or art98_setup."""
    found = {}
    for name in _modules():
        module = importlib.import_module(name)  # nothing here needs a VM or a tool
        for value in vars(module).values():
            if (
                inspect.isclass(value)
                and issubclass(value, BaseException)
                and not issubclass(value, Warning)
                and value.__module__.split(".")[0] in {p.__name__ for p in PACKAGES}
            ):
                found[f"{value.__module__}.{value.__qualname__}"] = value
    return found


def test_every_art98_error_inherits_Art98Error():
    found = _own_exceptions()
    assert found, "found no exception classes at all: the walk is broken"
    missing = sorted(n for n, c in found.items() if not issubclass(c, Art98Error))
    assert not missing, f"these errors must inherit art98.errors.Art98Error: {missing}"


def test_errors_py_imports_nothing_from_art98():
    tree = ast.parse(Path(errors.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "errors.py must not use a relative import"
            names = [node.module or ""]
        else:
            continue
        assert not any(n.split(".")[0] in {"art98", "art98_setup"} for n in names)


def test_art98_exports_the_base_class():
    assert art98.Art98Error is Art98Error
    assert "Art98Error" in art98.__all__


def test_the_built_in_base_still_catches():
    assert issubclass(PlacementError, ValueError)
    with pytest.raises(ValueError):
        raise PlacementError("off screen")


def test_an_error_missing_from_the_old_list_is_one_error_line(
    monkeypatch, capsys, tmp_path
):
    scene = tmp_path / "demo.py"
    scene.write_text("from art98.anim import Scene\n\n\nclass Demo(Scene):\n    pass\n")

    def render(*args, **kwargs):
        raise PlacementError("the window is off screen")

    monkeypatch.setattr(cli.freshness, "warn", lambda *a: None)
    monkeypatch.delenv("ART98_TRACE", raising=False)
    monkeypatch.setattr("art98.anim.render", render)
    monkeypatch.setattr(cli.service, "attach", lambda *a, **k: _Session())
    assert cli.main(["render", str(scene)]) == 1
    err = capsys.readouterr().err
    assert err == "error: the window is off screen\n"


class _Session:
    def __enter__(self):
        return object()

    def __exit__(self, *exc):
        return False


def test_usage_errors_keep_their_built_in_bases():
    assert issubclass(errors.UsageError, ValueError)
    assert issubclass(errors.NotFound, (errors.UsageError, KeyError, LookupError))
    assert (
        str(errors.NotFound("no window 'a'")) == "no window 'a'"
    )  # not KeyError's quoting
    with pytest.raises(ValueError):
        art98.anim.Scene().play()
    assert art98.UsageError is errors.UsageError and art98.NotFound is errors.NotFound
