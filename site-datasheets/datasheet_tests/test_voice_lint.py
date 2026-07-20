"""Voice lint: banned phrases absent; no '!' in body copy; orchestration framing."""
from __future__ import annotations

import re
from pathlib import Path

import generate_datasheets as gen

TERMS_FILE = Path(__file__).resolve().parent / "voice_lint_terms.txt"
ORCH = ("an optional orchestration layer for approved, agent-enabled environments; "
        "the platform runs fully without it")


def _terms():
    return [t.strip().lower() for t in TERMS_FILE.read_text(encoding="utf-8").splitlines()
            if t.strip()]


def test_no_banned_phrases():
    body = gen.render("triangulate").lower()
    for term in _terms():
        assert term not in body, f"banned phrase present: {term!r}"


def test_no_exclamation_in_body_copy():
    html = gen.render("triangulate")
    # Body copy only: strip inline JS/CSS (legitimately use "!"), the
    # <pre>/<code> CLI samples where "!" would be part of real output, and
    # markup-level constructs (doctype, comments) that are not copy at all.
    stripped = re.sub(r"<script>.*?</script>", "", html, flags=re.S)
    stripped = re.sub(r"<style>.*?</style>", "", stripped, flags=re.S)
    stripped = re.sub(r"<code>.*?</code>", "", stripped, flags=re.S)
    stripped = re.sub(r"<pre>.*?</pre>", "", stripped, flags=re.S)
    stripped = re.sub(r"<!doctype[^>]*>", "", stripped, flags=re.I)
    stripped = re.sub(r"<!--.*?-->", "", stripped, flags=re.S)
    assert "!" not in stripped


def test_orchestration_framing_is_verbatim_when_agent_mode_present():
    html = gen.render("triangulate")
    if "agent-enabled" in html or "agent-accelerated" in html.lower():
        assert ORCH in html, "agent mode described without the verbatim orchestration sentence"


def test_no_hands_free_claim():
    assert "hands-free" not in gen.render("triangulate").lower()
