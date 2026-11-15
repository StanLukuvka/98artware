"""The base of every error art98 raises on purpose."""

from __future__ import annotations


class Art98Error(Exception):
    """Base of every error art98 raises on purpose, so callers and the CLI catch one thing.

    Each error keeps its built-in base second (`class StateError(Art98Error, ValueError)`),
    so `except ValueError` and friends still work. Plain `ValueError` and `RuntimeError`
    raised for a programming mistake are not Art98Errors: they keep their traceback.
    """
