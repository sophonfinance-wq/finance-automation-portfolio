"""Shared fixtures for the Finance Operations Atlas test suite.

Puts the system root on ``sys.path`` so ``atlas_data`` and ``generate``
import cleanly, renders the artifact once per session, and builds a small
structural index over the generated HTML (tag balance, ids, buttons,
sections, script bodies, footer text) that the artifact tests assert
against.
"""

from __future__ import annotations

import json
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

ATLAS_DIR = Path(__file__).resolve().parents[1]
if str(ATLAS_DIR) not in sys.path:
    sys.path.insert(0, str(ATLAS_DIR))

import atlas_data  # noqa: E402  (path set above)
import generate  # noqa: E402

ARTIFACT_PATH = ATLAS_DIR / "out" / "finance-operations-atlas.html"
README_PATH = ATLAS_DIR / "README.md"

#: HTML void elements — never pushed on the balance stack.
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}


class DocIndex(HTMLParser):
    """Structural index of the generated document."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: List[str] = []
        self.balance_errors: List[str] = []
        self.tags: List[Tuple[str, Dict[str, str]]] = []
        self.ids: List[str] = []
        self.scripts: List[str] = []
        self.buttons: List[Dict[str, str]] = []
        self.nav_buttons: List[Dict[str, str]] = []
        self.sections: List[Dict[str, str]] = []
        self.footer_text: List[str] = []
        self.title_text: List[str] = []
        self._script_buf: List[str] = []

    # -- structure -----------------------------------------------------
    def handle_starttag(self, tag: str, attrs) -> None:
        attr_map: Dict[str, str] = {}
        for key, value in attrs:
            attr_map.setdefault(key, "" if value is None else value)
        self.tags.append((tag, attr_map))
        if "id" in attr_map:
            self.ids.append(attr_map["id"])
        if tag == "button":
            self.buttons.append(attr_map)
            if "nav" in self.stack:
                self.nav_buttons.append(attr_map)
        if tag == "section":
            self.sections.append(attr_map)
        if tag == "script":
            self._script_buf = []
        if tag not in VOID_TAGS:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs) -> None:
        # Self-closed tag: record it, never push it.
        attr_map: Dict[str, str] = {}
        for key, value in attrs:
            attr_map.setdefault(key, "" if value is None else value)
        self.tags.append((tag, attr_map))
        if "id" in attr_map:
            self.ids.append(attr_map["id"])

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID_TAGS:
            return
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        else:
            self.balance_errors.append(
                "unbalanced </%s> (open: %r)" % (tag, self.stack[-4:])
            )
        if tag == "script":
            self.scripts.append("".join(self._script_buf))
            self._script_buf = []

    # -- text ----------------------------------------------------------
    def handle_data(self, data: str) -> None:
        if not self.stack:
            return
        if self.stack[-1] == "script":
            self._script_buf.append(data)
        if self.stack[-1] == "title":
            self.title_text.append(data)
        if "footer" in self.stack:
            self.footer_text.append(data)


# ---------------------------------------------------------------------------
# Session fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def rendered() -> str:
    """The document rendered in-process by the generator."""
    return generate.render()


@pytest.fixture(scope="session")
def artifact_text() -> str:
    """The committed single-file artifact."""
    return ARTIFACT_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def readme_text() -> str:
    return README_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def doc(rendered: str) -> DocIndex:
    index = DocIndex()
    index.feed(rendered)
    index.close()
    return index


@pytest.fixture(scope="session")
def payload(doc: DocIndex) -> Dict[str, Any]:
    """The JSON data payload embedded in the page's first script block."""
    source = doc.scripts[0]
    assert "window.ATLAS" in source, "first script must carry the data payload"
    body = source.split("=", 1)[1].strip().rstrip(";")
    return json.loads(body)
