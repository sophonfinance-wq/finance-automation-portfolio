"""Confidentiality sweep over the generated datasheet page (atlas digest machinery)."""
from __future__ import annotations

import sys

import generate_datasheets as gen

# Reuse the atlas deny-list digests + n-gram matcher without duplicating them.
ATLAS_TESTS = gen.REPO / "finance-atlas" / "atlas_tests"
if str(ATLAS_TESTS) not in sys.path:
    sys.path.insert(0, str(ATLAS_TESTS))
if str(gen.REPO / "finance-atlas") not in sys.path:
    sys.path.insert(0, str(gen.REPO / "finance-atlas"))

import test_deny_list as atlas_deny  # noqa: E402


def test_generated_page_is_clean_of_denied_terms():
    page = gen.render("triangulate")
    grams = atlas_deny.ngram_digests(page)
    for digest, nwords in atlas_deny.DENYLIST:
        assert digest not in grams.get(nwords, set()), (
            f"denied term (digest {digest[:12]}...) found on the generated page"
        )
