"""Page engineering: size budget and that every local asset/link path exists."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import datasheet_spec as ds
import generate_datasheets as gen

from datasheet_tests.conftest import present_slugs

MAX_BYTES = 150 * 1024


def test_pages_within_size_budget():
    for slug in present_slugs():
        size = len(gen.render(slug).encode("utf-8"))
        assert size <= MAX_BYTES, f"{slug}: {size} bytes exceeds {MAX_BYTES}"


def test_every_declared_media_asset_exists_on_disk():
    docs_engines = gen.OUT_DIR  # docs/engines
    for slug in present_slugs():
        spec = ds.load_spec(slug)
        paths = [spec["media"][key] for key in ("poster", "motion")]
        paths.extend(crop["path"] for crop in spec["media"]["crops"])
        for rel in paths:
            resolved = (docs_engines / rel).resolve()
            assert resolved.is_file(), f"{slug}: missing media asset: {rel} -> {resolved}"


def test_internal_tests_link_route_exists():
    # links.tests points at /tests/ — the docs/tests/ directory must exist
    assert (gen.REPO / "docs" / "tests").is_dir()
    for slug in present_slugs():
        assert ds.load_spec(slug)["links"]["tests"] == "/tests/", slug


class _LocalRefs(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.refs: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        for name, value in attrs:
            if value and name in {"href", "src", "data-video"}:
                self.refs.append(value)


def _target_for(ref: str, page_path: Path) -> tuple[Path, str]:
    parsed = urlsplit(ref)
    raw_path = unquote(parsed.path)
    if not raw_path:
        target = page_path
    elif raw_path.startswith("/"):
        target = gen.REPO / "docs" / raw_path.lstrip("/")
    else:
        target = page_path.parent / raw_path
    if raw_path.endswith("/") or target.is_dir():
        target = target / "index.html"
    return target.resolve(), parsed.fragment


def test_every_internal_href_and_media_reference_resolves():
    for slug in present_slugs():
        html = gen.render(slug)
        page_path = (gen.OUT_DIR / f"{slug}.html").resolve()
        parser = _LocalRefs()
        parser.feed(html)
        for ref in parser.refs:
            parsed = urlsplit(ref)
            if parsed.scheme in {"http", "https", "mailto", "tel", "data"} or parsed.netloc:
                continue
            target, fragment = _target_for(ref, page_path)
            assert target.is_file(), f"{slug}: broken internal reference: {ref} -> {target}"
            if fragment:
                target_html = html if target == page_path else target.read_text(encoding="utf-8")
                pattern = rf'\bid=["\']{re.escape(fragment)}["\']'
                assert re.search(pattern, target_html), (
                    f"{slug}: missing fragment target: {ref} -> {target}#{fragment}"
                )
