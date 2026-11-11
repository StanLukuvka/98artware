"""The docs stay true to the code. Rendering the samples is tools/check_docs.py."""

import re
from pathlib import Path

import art98.anim
import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs" / "scenes"
PAGES = ("README.md", "tutorial.md", "scene-api.md", "animations.md")
SAMPLE = re.compile(r"```python\n(.*?)```", re.DOTALL)
LINK = re.compile(r"!\[[^\]]*\]\(([^)]+)\)|(?<!!)\[[^\]]*\]\(([^)#]+)(?:#[^)]*)?\)")
WRITTEN_ELSEWHERE = {
    "bridge.md",
    "instruction-set.md",
    "win32-recipes.md",
    "app-catalog.md",
}


def samples():
    for page in PAGES:
        for number, code in enumerate(SAMPLE.findall((DOCS / page).read_text())):
            yield pytest.param(code, id=f"{page}-{number}")


@pytest.mark.parametrize("code", list(samples()))
def test_a_sample_is_one_whole_scene(code):
    names = {}
    exec(compile(code, "sample", "exec"), names)  # noqa: S102
    scenes = [
        v
        for k, v in names.items()
        if isinstance(v, type)
        and issubclass(v, art98.anim.Scene)
        and v is not art98.anim.Scene
    ]
    assert len(scenes) == 1


def test_every_public_name_is_documented():
    text = (DOCS / "scene-api.md").read_text() + (DOCS / "animations.md").read_text()
    missing = [
        name
        for name in art98.anim.__all__
        if f"`{name}" not in text and name not in text
    ]
    assert not missing


def test_the_gallery_shows_each_source_exactly():
    text = (DOCS / "gallery.md").read_text()
    for path in re.findall(r"Source: \[[^\]]+\]\(([^)]+)\)", text):
        assert (DOCS / path).read_text().strip() in text


def test_every_gif_is_in_the_gallery_with_a_source_and_small():
    text = (DOCS / "gallery.md").read_text()
    gifs = sorted((ROOT / "docs" / "assets" / "gifs").glob("*.gif"))
    assert gifs
    for gif in gifs:
        assert f"../assets/gifs/{gif.name}" in text
        assert gif.stat().st_size < 2_000_000


@pytest.mark.parametrize("page", [*PAGES, "gallery.md"])
def test_links_lead_somewhere(page):
    for image, link in LINK.findall((DOCS / page).read_text()):
        target = image or link
        if target.startswith("http") or target in WRITTEN_ELSEWHERE:
            continue
        assert (DOCS / target).exists(), target
