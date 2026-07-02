"""Confidentiality linter — deny-list sweep over every published surface.

This portfolio repository is public, so it carries a deny list of terms
that must never appear on any published surface. The list itself is
stored in a masked, reversible form (ROT13): the plaintext terms never
appear anywhere in this repository — not in the products, not in this
test file, and not in CI output (test IDs use the masked form). Each test
decodes one term at runtime and sweeps one surface with case-insensitive,
boundary-aware matching, so a single failure pinpoints exactly which term
leaked and where.

Surfaces swept:

* ``atlas_data.py``  — the data model source
* ``generate.py``    — the renderer source
* ``README.md``      — the system documentation
* ``artifact-html``  — the committed generated artifact
* ``tree-sweep``     — every text file under ``finance-atlas/``,
  including this test suite
"""

from __future__ import annotations

import codecs
import re
from typing import Dict, Pattern

import pytest

from atlas_tests.conftest import ARTIFACT_PATH, ATLAS_DIR, README_PATH

# ---------------------------------------------------------------------------
# The deny list (masked). Decode with codecs.decode(term, "rot13").
# ---------------------------------------------------------------------------

MASKED = (
    'REDACTED', 'REDACTED', 'REDACTED',
    'REDACTED', 'REDACTED', 'REDACTED',
    "REDACTED", 'REDACTED', 'REDACTED',
    'REDACTED', 'REDACTED', 'REDACTED',
    'REDACTED', 'REDACTED', 'REDACTED',
    'REDACTED', 'REDACTED', 'REDACTED',
    'REDACTED', 'REDACTED', 'REDACTED',
    'REDACTED', 'REDACTED', 'REDACTED',
    'REDACTED', 'REDACTED', 'REDACTED',
    'REDACTED', 'REDACTED', 'REDACTED',
    'REDACTED', 'REDACTED', 'REDACTED',
    'REDACTED', 'REDACTED', 'REDACTED',
    'REDACTED', 'REDACTED', 'REDACTED',
    'REDACTED', 'REDACTED', 'REDACTED',
    'REDACTED', 'REDACTED', 'REDACTED',
    'REDACTED', 'REDACTED', 'REDACTED',
    'REDACTED', 'REDACTED', 'REDACTED',
    'REDACTED', 'REDACTED', 'REDACTED',
    'REDACTED', 'REDACTED', 'REDACTED',
    'REDACTED', 'REDACTED', 'REDACTED',
    'REDACTED', 'REDACTED', 'REDACTED',
    'REDACTED', 'REDACTED', 'REDACTED',
    'REDACTED', 'REDACTED', 'REDACTED',
    'REDACTED', 'REDACTED', 'REDACTED',
    'REDACTED', 'REDACTED', 'REDACTED',
    'REDACTED', 'REDACTED', 'REDACTED',
    'REDACTED', 'REDACTED', 'REDACTED',
)

SURFACES = (
    "atlas_data.py",
    "generate.py",
    "README.md",
    "artifact-html",
    "tree-sweep",
)

#: File types included in the whole-tree sweep.
TEXT_SUFFIXES = {
    ".py", ".md", ".html", ".htm", ".txt", ".json",
    ".ini", ".cfg", ".toml", ".yml", ".yaml", ".css", ".js",
}

_SKIP_DIR_PARTS = {"__pycache__", ".pytest_cache"}


def _decode(masked: str) -> str:
    return codecs.decode(masked, "rot13")


def _normalize(text: str) -> str:
    """Fold typographic quotes so punctuation variants cannot hide a match."""
    return (
        text.replace("’", "'").replace("‘", "'")
            .replace("“", '"').replace("”", '"')
    )


def deny_pattern(term: str) -> Pattern[str]:
    """Case-insensitive matcher for one denied term.

    Word boundaries on both ends keep short tokens from false-positiving
    inside longer words (or inside hashes, for the hex tokens), and the
    gaps between words of a multi-word term tolerate line breaks, hyphens
    and underscores.
    """
    body = r"[\s\-_]+".join(re.escape(word) for word in term.split())
    return re.compile(
        r"(?<![0-9A-Za-z])" + body + r"(?![0-9A-Za-z])", re.IGNORECASE
    )


def _tree_text() -> str:
    parts = []
    for path in sorted(ATLAS_DIR.rglob("*")):
        if not path.is_file():
            continue
        if _SKIP_DIR_PARTS.intersection(path.parts):
            continue
        if path.suffix.lower() in TEXT_SUFFIXES:
            parts.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


@pytest.fixture(scope="session")
def surface_text() -> Dict[str, str]:
    return {
        "atlas_data.py": _normalize(
            (ATLAS_DIR / "atlas_data.py").read_text(encoding="utf-8")
        ),
        "generate.py": _normalize(
            (ATLAS_DIR / "generate.py").read_text(encoding="utf-8")
        ),
        "README.md": _normalize(README_PATH.read_text(encoding="utf-8")),
        "artifact-html": _normalize(
            ARTIFACT_PATH.read_text(encoding="utf-8")
        ),
        "tree-sweep": _normalize(_tree_text()),
    }


# ---------------------------------------------------------------------------
# The matrix: every denied term x every surface.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("masked", MASKED)
def test_surface_is_clean_of_denied_term(
    masked: str, surface: str, surface_text: Dict[str, str]
) -> None:
    haystack = surface_text[surface]
    match = deny_pattern(_decode(masked)).search(haystack)
    if match is not None:
        start = max(match.start() - 40, 0)
        snippet = haystack[start:match.end() + 40]
        pytest.fail(
            "denied term (masked: %r) found on surface %r near: %r"
            % (masked, surface, snippet)
        )


# ---------------------------------------------------------------------------
# Linter self-checks: the deny list is intact and the matcher works.
# ---------------------------------------------------------------------------

def test_deny_list_has_expected_size() -> None:
    assert len(MASKED) == 81


def test_deny_list_terms_are_unique() -> None:
    decoded = {_decode(m).lower() for m in MASKED}
    assert len(decoded) == len(MASKED)


def test_masking_is_effective() -> None:
    # No masked entry may equal its plaintext (else the file itself leaks).
    for masked in MASKED:
        assert _decode(masked).lower() != masked.lower(), masked


def test_every_surface_is_present_and_nonempty(
    surface_text: Dict[str, str],
) -> None:
    for surface in SURFACES:
        assert surface_text[surface].strip(), surface


def test_matcher_detects_seeded_leak_case_insensitively() -> None:
    term = _decode(MASKED[0])
    pattern = deny_pattern(term)
    assert pattern.search("x " + term.upper() + " y")
    assert pattern.search("path\\" + term.lower() + ";rest")


def test_matcher_respects_word_boundaries() -> None:
    term = _decode(MASKED[0])
    pattern = deny_pattern(term)
    assert pattern.search("prefix" + term + "suffix") is None


def test_matcher_spans_whitespace_and_separators() -> None:
    masked = next(m for m in MASKED if " " in m)
    term = _decode(masked)
    first, rest = term.split(" ", 1)
    pattern = deny_pattern(term)
    assert pattern.search(first + "\n    " + rest)
    assert pattern.search(first + "-" + rest.replace(" ", "_"))
