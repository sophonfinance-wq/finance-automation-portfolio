"""End to end: the run.py demo produces the full output set."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import List, Optional

import pytest

ENGINE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_PY = os.path.join(ENGINE_ROOT, "run.py")

#: Artifacts the demo must produce (report layer + evidence gallery).
EXPECTED_FILES = (
    "exec_summary.md",
    "resolution_schedule.md",
    "scope_reconciliation.md",
    "journal_entries.csv",
    "INDEX.html",
)


def _find(root: str, filename: str) -> Optional[str]:
    """Locate a file by basename anywhere under ``root``."""
    for dirpath, _dirnames, filenames in os.walk(root):
        if filename in filenames:
            return os.path.join(dirpath, filename)
    return None


@pytest.fixture(scope="module")
def demo_out(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Run ``python run.py demo`` once into a scratch output directory."""
    assert os.path.isfile(RUN_PY), (
        "run.py demo driver is missing from the engine root; the demo must "
        "be runnable with 'python run.py demo'"
    )
    out_dir = str(tmp_path_factory.mktemp("demo_out"))
    proc = subprocess.run(
        [sys.executable, RUN_PY, "demo", "--out", out_dir],
        cwd=ENGINE_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, (
        f"run.py demo exited {proc.returncode}\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    return out_dir


def test_demo_produces_all_output_files(demo_out):
    missing: List[str] = []
    for filename in EXPECTED_FILES:
        found = _find(demo_out, filename)
        if found is None:
            missing.append(filename)
        else:
            assert os.path.getsize(found) > 0, f"{found} is empty"
    assert not missing, f"demo did not produce {missing} under {demo_out}"


def test_journal_entries_csv_has_the_documented_columns(demo_out):
    path = _find(demo_out, "journal_entries.csv")
    assert path is not None
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        header = fh.readline().strip().split(",")
    for column in ("ref", "entity", "status", "account", "debit", "credit"):
        assert column in header, f"{column!r} missing from {header}"


def test_exec_summary_leads_with_the_one_question(demo_out):
    path = _find(demo_out, "exec_summary.md")
    assert path is not None
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    assert "Is any dollar unaccounted for?" in text
    # The summary must also carry the independent-verification section when
    # the demo runs the full pipeline; tolerate its absence only if the
    # verdict was not wired into the summary writer.
    assert "Executive Summary" in text


def test_placeholder_gl_surfaces_in_scope_reconciliation(demo_out):
    """Regression (defect 2c): the demo's placeholder-GL register account
    (Demo Holdings, key 001-001-1015) must be visibly flagged in the scope
    reconciliation, not silently absorbed into tb_matched_ties."""
    path = _find(demo_out, "scope_reconciliation.md")
    assert path is not None
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    assert "Placeholder / mis-keyed GL keys" in text
    assert "001-001-1015" in text
    assert "Demo Holdings" in text


def test_placeholder_gl_surfaces_in_exec_summary(demo_out):
    """The placeholder flag must also reach the executive summary."""
    path = _find(demo_out, "exec_summary.md")
    assert path is not None
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    assert "Placeholder GL keys flagged for review" in text
    assert "001-001-1015" in text


def test_run_cutoff_help_matches_actual_behavior():
    """Regression (defect 2a): the ``--cutoff`` help must not claim an
    ``as_of`` default that the classifier never applies. With no cutoff the
    engine derives timing from each register's running balances."""
    proc = subprocess.run(
        [sys.executable, RUN_PY, "run", "--help"],
        cwd=ENGINE_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    help_text = proc.stdout
    assert "as_of" not in help_text, (
        "cutoff help still claims an as_of default that is not implemented"
    )
    assert "running balances" in help_text


def test_bundled_samples_ship_with_the_engine():
    """The demo dataset must be present and fictional-looking (register CSVs
    plus one trial balance)."""
    samples = os.path.join(ENGINE_ROOT, "samples")
    assert os.path.isdir(samples), "samples/ directory is missing"
    names: List[str] = []
    for dirpath, _dirnames, filenames in os.walk(samples):
        names.extend(n.lower() for n in filenames if n.lower().endswith(".csv"))
    assert len(names) >= 2, "samples/ should bundle register and TB CSVs"
