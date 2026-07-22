"""Shared fixtures + package-wide marker for the datasheet test suite."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


HERE = Path(__file__).resolve().parent


def pytest_collection_modifyitems(items):
    """Every datasheet test is site tooling, not an engine test.

    NOTE: this hook receives the WHOLE session's items (pytest calls it once,
    with everything collected — not just this directory), so the marker must
    be scoped by path or a repo-root run would mark all engine tests too.
    """
    for item in items:
        try:
            item_path = Path(str(item.fspath)).resolve()
        except OSError:
            continue
        if item_path.is_relative_to(HERE):
            item.add_marker("site_tooling")


import datasheet_spec as ds  # noqa: E402
import generate_datasheets as gen  # noqa: E402
import pytest  # noqa: E402

#: Canonical §4 roster (design spec) — the single source of engine identity, so every
#: spec that lands (Triangulate now; the other eight in phase 2) is checked against one
#: authority. `engine_dir` is where that engine's own pytest suite lives (for the live
#: test-count cross-check).
ROSTER: dict[str, dict] = {
    "close":       {"num": 1, "part_no": "SFS-E01-CLS", "mnemonic": "CLS", "family": "Close Automation",           "name": "Month-End Close",             "engine_dir": "monthly-close-automation"},
    "recon":       {"num": 2, "part_no": "SFS-E02-RCN", "mnemonic": "RCN", "family": "Reconciliation",             "name": "Cash & Debt Reconciliation",  "engine_dir": "cash-reconciliation"},
    "tax":         {"num": 3, "part_no": "SFS-E03-PTX", "mnemonic": "PTX", "family": "Partnership Tax",            "name": "Partnership Tax · Form 1065", "engine_dir": "partnership-1065-automation"},
    "validation":  {"num": 4, "part_no": "SFS-E04-VAL", "mnemonic": "VAL", "family": "Read-Only Validation",       "name": "Validation Engine",           "engine_dir": "audit-automation"},
    "surplus":     {"num": 5, "part_no": "SFS-E05-SRP", "mnemonic": "SRP", "family": "Cross-Border Tax",           "name": "Tax Surplus / ACB",           "engine_dir": "tax-surplus-engine"},
    "triangulate": {"num": 6, "part_no": "SFS-E06-TRI", "mnemonic": "TRI", "family": "AI Validation",              "name": "Triangulate",                 "engine_dir": "ai-validation-framework"},
    "brain":       {"num": 7, "part_no": "SFS-E07-KBN", "mnemonic": "KBN", "family": "Cited Knowledge",            "name": "Knowledge Brain",             "engine_dir": "knowledge-brain-engine"},
    "atlas":       {"num": 8, "part_no": "SFS-E08-ATL", "mnemonic": "ATL", "family": "Documentation-as-Artifact",  "name": "Finance Operations Atlas",    "engine_dir": "finance-atlas"},
    "cash":        {"num": 9, "part_no": "SFS-E09-CSH", "mnemonic": "CSH", "family": "Cash Controls",              "name": "Cash Management",             "engine_dir": "cash-management"},
    "ap":          {"num": 10, "part_no": "SFS-E10-APX", "mnemonic": "APX", "family": "Payables Controls",        "name": "Accounts Payable",            "engine_dir": "accounts-payable-automation"},
    "draw":        {"num": 11, "part_no": "SFS-E11-DRW", "mnemonic": "DRW", "family": "Draw Controls",           "name": "Project Draw",                "engine_dir": "project-draw-automation"},
}

SPECS_DIR = ROOT / "specs"


def present_slugs() -> list[str]:
    """Slugs that actually have a committed spec JSON (so tests cover new engines
    automatically as their specs land, without failing on the ones not built yet)."""
    return sorted(p.stem for p in SPECS_DIR.glob("*.json"))


@pytest.fixture(scope="session")
def spec() -> dict:
    return ds.load_spec("triangulate")


@pytest.fixture(scope="session")
def rendered() -> str:
    return gen.render("triangulate")
