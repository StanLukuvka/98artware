"""The variable names in the checked modules follow `<scope>_<base>`, by docs/design/code-names.md.

The page lists the checked modules, the bases of each group and an example name per scope. This
test reads all three, so the rules and the check can't drift apart. Public names (functions,
classes, methods, public attributes and public class-body names) are never checked.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CODE_NAMES = ROOT / "docs" / "design" / "code-names.md"
SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _page_text() -> str:
    return CODE_NAMES.read_text(encoding="utf-8")


def _sections(text: str) -> dict[str, list[list[str]]]:
    """Each `## ` heading's table rows (raw cells), without the header and separator rows."""
    sections: dict[str, list[list[str]]] = {}
    heading = None
    header_seen = False
    for line in text.splitlines():
        if line.startswith("## "):
            heading = line[3:].strip()
            sections[heading] = []
            header_seen = False
        elif heading is not None and line.startswith("|"):
            if not header_seen:
                header_seen = True
            elif not set(line) <= set("|- "):
                cells = line.strip().strip("|").split("|")
                sections[heading].append([c.strip() for c in cells])
    return sections


def _rows(
    heading: str, text: str | None = None, allow_empty: bool = False
) -> list[list[str]]:
    """The rows under `## heading`. Fails clearly when the heading is missing, or when the
    table is empty and `allow_empty` is false."""
    sections = _sections(_page_text() if text is None else text)
    if heading not in sections:
        raise AssertionError(f"docs/design/code-names.md has no '## {heading}' heading")
    if not sections[heading] and not allow_empty:
        raise AssertionError(
            f"docs/design/code-names.md: the '## {heading}' table has no rows"
        )
    return sections[heading]


def checked_modules() -> list[tuple[str, str]]:
    """(module path, group) for each module the page checks."""
    return [(row[0].strip("`"), row[1]) for row in _rows("Checked modules")]


def bases_of(group: str) -> list[str]:
    return [row[0].strip("`") for row in _rows(f"Bases: {group}")]


def exempt_set(text: str | None = None) -> set[tuple[str, str]]:
    """(function path, parameter) for each row of the Exempt table. The table may be empty."""
    rows = _rows("Exempt", text, allow_empty=True)
    return {(row[0].strip("`"), row[1].strip("`")) for row in rows}


def scope_examples() -> list[str]:
    """Each example name in the Scopes table, without its `self.` prefix."""
    names = [n for row in _rows("Scopes") for n in re.findall(r"`([^`]+)`", row[1])]
    return [n.removeprefix("self.") for n in names]


def _snake(camel: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", camel).lower()


def _part(node: ast.AST) -> str:
    """A scope's part of its name: a class in snake_case, a dunder without its underscores."""
    if isinstance(node, ast.ClassDef):
        return _snake(node.name)
    if node.name.startswith("__") and node.name.endswith("__"):
        return node.name.strip("_")
    return node.name


def _base_of(name: str, bases: list[str]) -> str | None:
    """The longest base the name equals or ends with, so `full_main` isn't checked as `main`."""
    found = [b for b in bases if name == b or name.endswith("_" + b)]
    return max(found, key=len, default=None)


def _full_scopes(tree: ast.AST) -> set[str]:
    """The scope of every function: `resolve`, `scene_run`, `outer_inner`. Bare names are not scopes."""
    found: set[str] = set()

    def walk(node: ast.AST, path: list[str]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, SCOPE_NODES):
                inner = [*path, _part(child)]
                if not isinstance(child, ast.ClassDef):
                    found.add("_".join(inner))
                walk(child, inner)
            else:
                walk(child, path)

    walk(tree, [])
    return found


def _loop_targets(tree: ast.AST) -> set[int]:
    """The ids of the names that loop and comprehension targets bind. They are not tracked."""
    targets = [
        n
        for node in ast.walk(tree)
        if isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension))
        for n in ast.walk(node.target)
    ]
    return {id(n) for n in targets}


def _params(func) -> list[ast.arg]:
    args = func.args
    found = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    return found + [a for a in (args.vararg, args.kwarg) if a is not None]


def _own(node: ast.AST, skipped: set[int]):
    """What `node` binds itself, and the scopes it defines directly.

    Yields ("name", name, line), ("attr", name, line) for a `self._x` store, or ("scope", def, 0).
    Lambda parameters count as bindings of the scope they sit in.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, SCOPE_NODES):
            yield ("scope", child, 0)
            continue
        if isinstance(child, ast.Lambda):
            for arg in _params(child):
                yield ("name", arg.arg, arg.lineno)
            continue
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
            if id(child) not in skipped:
                yield ("name", child.id, child.lineno)
        elif isinstance(child, ast.ExceptHandler) and child.name:
            yield ("name", child.name, child.lineno)
        elif isinstance(child, ast.alias) and child.asname:
            yield ("name", child.asname, child.lineno)
        elif (
            isinstance(child, ast.Attribute)
            and isinstance(child.ctx, ast.Store)
            and isinstance(child.value, ast.Name)
            and child.value.id == "self"
        ):
            yield ("attr", child.attr, child.lineno)
        yield from _own(child, skipped)


def _problem(
    name: str,
    scope: str,
    bases: list[str],
    scopes: set[str],
    prefix: str = "",
) -> str | None:
    """Why `name`, bound in `scope`, breaks the rules, or None.

    `prefix` is "_" for a private attribute, whose name is checked without its underscore.
    A word in front of the base is allowed (`apply_state_wait_desktop_state`), but not a full
    scope in front of it (`off_children_scene_run_desktop_parts`).
    """
    shown = prefix + name
    base = _base_of(name, bases)
    if base is None:
        if name.startswith(scope + "_"):
            return f"{shown!r} starts with {scope + '_'!r} but ends in no listed base"
        return None
    right = f"{scope}_{base}"
    if name == right:
        return None
    head = name[: -len(base) - 1] if name.endswith("_" + base) else None
    if head is None or not head.startswith(scope + "_"):
        return f"{shown!r} should be {prefix + right!r}"
    middle = f"_{head[len(scope) + 1 :]}_"
    for full in scopes:
        if f"_{full}_" in middle:
            return (
                f"{shown!r} stacks the scope {full!r}; it should be {prefix + right!r}"
            )
    return None


def _constant_problem(name: str, bases: list[str]) -> str | None:
    """A module constant has its base in capitals and no scope, with a word in front allowed."""
    upper = name.upper()
    is_based = any(upper == b.upper() or upper.endswith("_" + b.upper()) for b in bases)
    if is_based and name != upper:
        return (
            f"{name!r} should be {upper!r}: a module constant has its base in capitals"
        )
    return None


def name_problems(
    source: str,
    bases: list[str],
    where: str = "source",
    exempt: set[tuple[str, str]] | None = None,
) -> list[str]:
    """Each name in `source` that breaks the rules, as `where:line: message`.

    `exempt` holds (function path, parameter) pairs that are not checked, such as `("Scene.run",
    "desktop")`. The path is the dotted qualified name of the function, with its enclosing
    classes and functions.
    """
    tree = ast.parse(source)
    skipped = _loop_targets(tree)
    scopes = _full_scopes(tree)
    exempt = exempt or set()
    problems: list[str] = []

    def report(lineno: int, message: str | None) -> None:
        if message:
            problems.append(f"{where}:{lineno}: {message}")

    def visit(
        node: ast.AST, path: list[str], class_scope: str | None, qual: list[str]
    ) -> None:
        scope = "_".join(path)
        # A `_` name that is never read is left alone; so are self and cls.
        used = {
            n.id
            for n in ast.walk(node)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
        }

        def unused_or_self(name: str) -> bool:
            return name in ("self", "cls") or (
                name.startswith("_") and name not in used
            )

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_path = ".".join(qual)
            for arg in _params(node):
                if unused_or_self(arg.arg) or (func_path, arg.arg) in exempt:
                    continue
                report(arg.lineno, _problem(arg.arg, scope, bases, scopes))
        for kind, value, lineno in _own(node, skipped):
            if kind == "scope":
                inner_class = scope if isinstance(node, ast.ClassDef) else None
                visit(
                    value,
                    [*path, _part(value)],
                    inner_class,
                    [*qual, value.name],
                )
            elif kind == "attr":
                if class_scope and value.startswith("_"):
                    report(lineno, _problem(value[1:], class_scope, bases, scopes, "_"))
            elif isinstance(node, ast.Module):
                report(lineno, _constant_problem(value, bases))
            elif isinstance(node, ast.ClassDef):
                if value.startswith("_") and len(value) > 1:
                    report(lineno, _problem(value[1:], scope, bases, scopes, "_"))
            elif not unused_or_self(value):
                report(lineno, _problem(value, scope, bases, scopes))

    visit(tree, [], None, [])
    return problems


@pytest.mark.parametrize("module,group", checked_modules())
def test_desktop_names_follow_their_scope_in_each_checked_module(module, group):
    source = (ROOT / module).read_text(encoding="utf-8")
    problems = name_problems(source, bases_of(group), module, exempt_set())
    assert problems == []


def test_the_page_lists_modules_and_bases_to_check():
    assert {module for module, _group in checked_modules()} >= {
        "core/art98/desktop.py",
        "core/art98/anim/scene.py",
        "core/art98/anim/setstate.py",
    }
    assert "desktop_parts" in bases_of("desktop")


# One case per example name in the Scopes table, with base `notes`: the good source passes, and
# the bad one binds one wrong name, which is reported with the right one.
SCOPE_CASES = {
    "resolve_notes": (
        "def resolve():\n    resolve_notes = []\n    return resolve_notes\n",
        "def resolve():\n    notes = []\n    return notes\n",
    ),
    "_resolve_notes": (
        "def _resolve():\n    _resolve_notes = []\n    return _resolve_notes\n",
        "def _resolve():\n    resolve_notes = []\n    return resolve_notes\n",
    ),
    "scene_run_notes": (
        "class Scene:\n    def run(self):\n        scene_run_notes = []\n        return scene_run_notes\n",
        "class Scene:\n    def run(self):\n        run_notes = []\n        return run_notes\n",
    ),
    "scene__apply_notes": (
        "class Scene:\n    def _apply(self):\n        scene__apply_notes = []\n        return scene__apply_notes\n",
        "class Scene:\n    def _apply(self):\n        _apply_notes = []\n        return _apply_notes\n",
    ),
    "scene_init_notes": (
        "class Scene:\n    def __init__(self):\n        scene_init_notes = []\n        return scene_init_notes\n",
        "class Scene:\n    def __init__(self):\n        scene_notes = []\n        return scene_notes\n",
    ),
    "outer_inner_notes": (
        "def outer():\n    def inner():\n        outer_inner_notes = []\n        return outer_inner_notes\n    return inner\n",
        "def outer():\n    def inner():\n        inner_notes = []\n        return inner_notes\n    return inner\n",
    ),
    "_scene_notes": (
        "class Scene:\n    def run(self):\n        self._scene_notes = []\n",
        "class Scene:\n    def run(self):\n        self._notes = []\n",
    ),
    "NOTES": ("NOTES = []\n", "notes = []\n"),
    "STOCK_NOTES": ("STOCK_NOTES = []\n", "stock_notes = []\n"),
}


def test_each_example_on_the_scopes_table_has_a_case_and_each_case_is_on_the_table():
    assert set(SCOPE_CASES) == set(scope_examples())


@pytest.mark.parametrize("name", sorted(SCOPE_CASES))
def test_a_wrong_scope_name_for_each_row_of_the_scopes_table_is_reported(name):
    good, bad = SCOPE_CASES[name]
    assert name_problems(good, ["notes"]) == []
    problems = name_problems(bad, ["notes"])
    assert len(problems) == 1
    assert repr(name) in problems[0]


# Each source binds one wrong name in one binding form; the expected name is in the message.
BINDING_FORMS = [
    pytest.param(
        "def resolve(notes):\n    return notes\n", "resolve_notes", id="parameter"
    ),
    pytest.param(
        "def resolve():\n    return lambda notes: notes\n", "resolve_notes", id="lambda"
    ),
    pytest.param("def resolve():\n    notes = 1\n", "resolve_notes", id="assignment"),
    pytest.param("def resolve():\n    notes += 1\n", "resolve_notes", id="augmented"),
    pytest.param(
        "def resolve():\n    notes: int = 1\n", "resolve_notes", id="annotated"
    ),
    pytest.param(
        "def resolve():\n    if (notes := 1):\n        pass\n",
        "resolve_notes",
        id="walrus",
    ),
    pytest.param(
        "def resolve():\n    with open('x') as notes:\n        pass\n",
        "resolve_notes",
        id="with",
    ),
    pytest.param(
        "def resolve():\n    try:\n        pass\n    except OSError as notes:\n        pass\n",
        "resolve_notes",
        id="except",
    ),
    pytest.param(
        "def resolve():\n    import os as notes\n", "resolve_notes", id="import"
    ),
    pytest.param(
        "def outer():\n    def inner():\n        notes = 1\n        return notes\n    return inner\n",
        "outer_inner_notes",
        id="function-in-function",
    ),
    pytest.param(
        "def outer():\n    class Inner:\n        def run(self):\n            notes = 1\n            return notes\n    return Inner\n",
        "outer_inner_run_notes",
        id="class-in-function",
    ),
]


@pytest.mark.parametrize("source,expected", BINDING_FORMS)
def test_a_wrong_name_in_each_binding_form_is_reported(source, expected):
    problems = name_problems(source, ["notes"])
    assert len(problems) == 1
    assert repr(expected) in problems[0]


def test_loop_comprehension_self_public_and_unused_names_are_not_reported():
    source = (
        "class Holder:\n"
        "    notes: list = []\n"
        "    if notes:\n"
        "        notes_if = 1\n"
        "    for notes_for in []:\n"
        "        pass\n"
        "    with open('x') as notes_with:\n"
        "        pass\n"
        "    notes_pair, notes_more = 1, 2\n"
        "    def run_notes(self, cls):\n"
        "        for notes_loop in []:\n"
        "            pass\n"
        "        values = [notes_comp for notes_comp in []]\n"
        "        self.desk_notes = 1\n"
        "        _notes_unused = 2\n"
        "        def _helper(_notes):\n"
        "            return 1\n"
        "        return values\n"
    )
    assert name_problems(source, ["notes", "self", "cls"]) == []


def test_a_private_class_body_name_under_if_is_checked():
    source = "class Holder:\n    if True:\n        _notes = 1\n"
    problems = name_problems(source, ["notes"])
    assert len(problems) == 1
    assert "'_holder_notes'" in problems[0]


def test_a_name_that_stacks_a_full_scope_is_reported():
    source = (
        "class Scene:\n    def run(self):\n        pass\n\n"
        "def off_children(x):\n    off_children_scene_run_desktop_parts = x\n"
    )
    problems = name_problems(source, ["desktop_parts"])
    assert len(problems) == 1
    assert "stacks the scope 'scene_run'" in problems[0]


def test_an_ordinary_word_in_front_of_a_base_is_allowed_even_with_a_method_of_that_name():
    source = (
        "class Win:\n    def wait(self):\n        pass\n\n"
        "def apply_state(x):\n    apply_state_wait_desktop_state = x\n"
    )
    assert name_problems(source, ["desktop_state"]) == []


def test_a_shortened_base_is_reported_by_the_prefix_rule():
    problems = name_problems(
        "def off_children(x):\n    off_children_parts = x\n", ["desktop_parts"]
    )
    assert len(problems) == 1
    assert "ends in no listed base" in problems[0]
    assert (
        name_problems(
            "def off_children(x):\n    off_children_desktop_parts = x\n",
            ["desktop_parts"],
        )
        == []
    )


def test_an_exempt_row_skips_exactly_its_parameter_in_its_function():
    source = (
        "def resolve(notes, other_notes):\n"  # 1
        "    def inner(notes):\n"  # 2
        "        return notes\n"  # 3
        "    return inner\n"  # 4
        "\n"  # 5
        "def other(notes):\n"  # 6
        "    return notes\n"  # 7
    )
    exempt = exempt_set(
        "## Exempt\n\n| Where | Parameter | Documented in |\n| --- | --- | --- |\n"
        "| `resolve` | `notes` | [Scene API](docs/scenes/scene-api.md) |\n"
    )
    assert exempt == {("resolve", "notes")}
    assert len(name_problems(source, ["notes"])) == 4
    lines = [
        int(p.split(":")[1])
        for p in name_problems(source, ["notes"], "src", exempt=exempt)
    ]
    # `other_notes` in resolve, `notes` in resolve.inner (a different path), and `other`.
    assert lines == [1, 2, 6]


def test_an_empty_exempt_table_loads():
    text = "## Exempt\n\n| Where | Parameter | Documented in |\n| --- | --- | --- |\n"
    assert exempt_set(text) == set()


def test_a_missing_exempt_heading_fails_clearly():
    with pytest.raises(AssertionError, match="has no '## Exempt' heading"):
        exempt_set("## Scopes\n\n| Where | Example |\n| --- | --- |\n")


def test_a_missing_or_empty_table_on_the_page_fails_clearly():
    with pytest.raises(AssertionError, match="has no '## Checked modules' heading"):
        _rows("Checked modules", "## Scopes\n\n| Where | Example |\n| --- | --- |\n")
    with pytest.raises(AssertionError, match="the '## Scopes' table has no rows"):
        _rows("Scopes", "## Scopes\n\n| Where | Example |\n| --- | --- |\n")
