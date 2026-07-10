"""THE test: independent verification catches the overclaim.

Runs the full pipeline (ingest -> classify -> scope -> report) on the demo
dataset and asserts the verifier's gate semantics: a faithful report gets
GO; deleting a single account from the report's scope reconciliation flips
the verdict to NO_GO *naming that account*. This is the check that would
have caught a real-world overclaim, so it is tested harder than anything
else in the suite.
"""

from __future__ import annotations

import copy
import inspect
import os
import shutil
from types import SimpleNamespace

import pytest

import ccengine.verify as verify_module
from ccengine.ingest import load_registers, load_trial_balance
from ccengine.reconcile import classify_exceptions
from ccengine.report import build_report
from ccengine.scope import build_scope_reconciliation
from ccengine.verify import derive_population, independent_verify
from tests.conftest import (
    ALL_REGISTER_GLS,
    BANK_LEGACY,
    ENTITY_A,
    GL_A,
    GL_B,
    GL_D,
    GL_PHANTOM,
    GL_RESOLVED,
    GL_TIED,
    write_register_csv,
)

#: Closed legacy account absent from the TB but still holding real cash --
#: the fourth coverage signal (used only by the hidden-cash regression test).
GL_HIDDEN = "424-006-1133"
ENTITY_HIDDEN = "Wrenfield 28 Development LLC"
BALANCE_HIDDEN = 500000.00


@pytest.fixture()
def pipeline(demo_dataset):
    """Run the full preparer pipeline once on the demo dataset."""
    registers = load_registers(demo_dataset.registers_dir)
    tb_rows = load_trial_balance(demo_dataset.tb_path)
    exceptions, phantoms = classify_exceptions(registers, tb_rows)
    scope = build_scope_reconciliation(registers, exceptions)
    report = build_report(
        registers, tb_rows, exceptions, scope, phantom_rows=phantoms
    )
    return SimpleNamespace(
        registers=registers,
        tb_rows=tb_rows,
        exceptions=exceptions,
        phantoms=phantoms,
        scope=scope,
        report=report,
        registers_dir=demo_dataset.registers_dir,
        tb_path=demo_dataset.tb_path,
    )


def _findings_text(verdict) -> str:
    return " | ".join(f["finding"] for f in verdict.findings)


# ---------------------------------------------------------------------------
# The faithful report ships
# ---------------------------------------------------------------------------


def test_faithful_report_gets_go(pipeline):
    verdict = independent_verify(
        pipeline.registers_dir, pipeline.tb_path, pipeline.report
    )
    assert verdict.status == "GO", _findings_text(verdict)
    # A GO verdict still explains itself.
    assert any(f["severity"] == "info" for f in verdict.findings)


def test_report_covers_every_class_before_the_go(pipeline):
    kinds = {e.kind for e in pipeline.exceptions}
    assert kinds == {
        "A_UNMAPPED_SUCCESSOR",
        "B_STALE_CLOSEOUT",
        "C_TIMING",
        "D_UNEXPLAINED",
    }
    assert [r.gl_norm for r in pipeline.phantoms] == [GL_PHANTOM]
    assert pipeline.report["scope_reconciliation"]["problems"] == []


# ---------------------------------------------------------------------------
# The overclaim: one deleted account flips the verdict, by name
# ---------------------------------------------------------------------------


def test_deleting_one_account_from_the_report_is_no_go_naming_it(pipeline):
    tampered = copy.deepcopy(pipeline.report)
    tampered["scope_reconciliation"]["buckets"]["exceptions_A"].remove(GL_A)
    verdict = independent_verify(
        pipeline.registers_dir, pipeline.tb_path, tampered
    )
    assert verdict.status == "NO_GO"
    text = _findings_text(verdict)
    assert GL_A in text  # the omitted account is NAMED
    assert ENTITY_A in text  # and attributed to its entity
    assert any(
        f["severity"] == "critical" and "missing from the report scope" in f["finding"]
        for f in verdict.findings
    )


@pytest.mark.parametrize("gl", [GL_TIED, GL_B, GL_D, GL_RESOLVED])
def test_no_account_is_safe_to_omit(pipeline, gl):
    tampered = copy.deepcopy(pipeline.report)
    buckets = tampered["scope_reconciliation"]["buckets"]
    removed = False
    for members in buckets.values():
        if gl in members:
            members.remove(gl)
            removed = True
    assert removed, f"{gl} should have been in the faithful report's scope"
    verdict = independent_verify(
        pipeline.registers_dir, pipeline.tb_path, tampered
    )
    assert verdict.status == "NO_GO"
    assert gl in _findings_text(verdict)


def test_double_counted_account_is_no_go(pipeline):
    tampered = copy.deepcopy(pipeline.report)
    tampered["scope_reconciliation"]["buckets"]["tb_matched_ties"].append(GL_A)
    verdict = independent_verify(
        pipeline.registers_dir, pipeline.tb_path, tampered
    )
    assert verdict.status == "NO_GO"
    assert any(
        "more than one scope bucket" in f["finding"] and GL_A in f["finding"]
        for f in verdict.findings
    )


def test_claiming_a_nonexistent_account_is_no_go(pipeline):
    tampered = copy.deepcopy(pipeline.report)
    tampered["scope_reconciliation"]["buckets"]["tb_matched_ties"].append(
        "999-999-9999"
    )
    verdict = independent_verify(
        pipeline.registers_dir, pipeline.tb_path, tampered
    )
    assert verdict.status == "NO_GO"
    assert "999-999-9999" in _findings_text(verdict)


def test_bucket_total_that_does_not_re_add_is_no_go(pipeline):
    tampered = copy.deepcopy(pipeline.report)
    tampered["scope_reconciliation"]["totals"]["exceptions_C"] -= 500.00
    verdict = independent_verify(
        pipeline.registers_dir, pipeline.tb_path, tampered
    )
    assert verdict.status == "NO_GO"
    assert any(
        "exceptions_C" in f["finding"] and "re-add" in f["finding"]
        for f in verdict.findings
    )


def test_suppressing_an_exception_is_no_go(pipeline):
    tampered = copy.deepcopy(pipeline.report)
    tampered["exceptions"] = [
        e for e in tampered["exceptions"] if e["gl_norm"] != GL_D
    ]
    verdict = independent_verify(
        pipeline.registers_dir, pipeline.tb_path, tampered
    )
    assert verdict.status == "NO_GO"
    assert any(
        "not surfaced" in f["finding"] and GL_D in f["finding"]
        for f in verdict.findings
    )


def test_hiding_a_closed_off_tb_account_inside_ties_is_no_go(
    demo_dataset, tmp_path
):
    """Regression: closed + absent from TB + cash at the bank must be caught.

    Mirrors ``test_suppressing_an_exception_is_no_go`` for the fourth
    coverage signal. The doctored report parks the hidden account inside
    ``tb_matched_ties`` with a CONSISTENT total (it re-adds to the cent) and
    drops its exception row, so the population check and the totals check
    both pass -- only the closed-off-TB coverage signal can flip the gate.
    Before that signal existed, this exact probe got a clean GO: real money
    at the bank, fully outside the ledger, certified as a tie.
    """
    registers_dir = str(tmp_path / "registers")
    shutil.copytree(demo_dataset.registers_dir, registers_dir)
    write_register_csv(
        os.path.join(registers_dir, "wrenfield28_legacy_forgotten.csv"),
        entity=ENTITY_HIDDEN,
        bank=BANK_LEGACY,
        account_no="000988773",
        gl=GL_HIDDEN,
        status="closed",
        as_of="2026-06-30",
        rows=[
            ("2026-06-01", "Opening balance", "0.00", f"{BALANCE_HIDDEN:.2f}", ""),
        ],
    )

    registers = load_registers(registers_dir)
    tb_rows = load_trial_balance(demo_dataset.tb_path)
    exceptions, phantoms = classify_exceptions(registers, tb_rows)
    # The preparer itself classifies this account D_UNEXPLAINED...
    assert any(
        e.gl_norm == GL_HIDDEN and e.kind == "D_UNEXPLAINED" for e in exceptions
    )
    scope = build_scope_reconciliation(registers, exceptions)
    report = build_report(
        registers, tb_rows, exceptions, scope, phantom_rows=phantoms
    )
    # ...and the faithful report ships.
    faithful = independent_verify(registers_dir, demo_dataset.tb_path, report)
    assert faithful.status == "GO", _findings_text(faithful)

    # The doctoring: drop the exception, move the account into the ties
    # bucket, and keep both bucket totals internally consistent.
    tampered = copy.deepcopy(report)
    tampered["exceptions"] = [
        e for e in tampered["exceptions"] if e["gl_norm"] != GL_HIDDEN
    ]
    buckets = tampered["scope_reconciliation"]["buckets"]
    totals = tampered["scope_reconciliation"]["totals"]
    buckets["exceptions_D"].remove(GL_HIDDEN)
    buckets["tb_matched_ties"].append(GL_HIDDEN)
    totals["exceptions_D"] = round(totals["exceptions_D"] - BALANCE_HIDDEN, 2)
    totals["tb_matched_ties"] = round(
        totals["tb_matched_ties"] + BALANCE_HIDDEN, 2
    )

    verdict = independent_verify(registers_dir, demo_dataset.tb_path, tampered)
    assert verdict.status == "NO_GO"
    assert any(
        f["severity"] == "critical"
        and "not surfaced" in f["finding"]
        and GL_HIDDEN in f["finding"]
        and "closed account absent from the TB" in f["finding"]
        for f in verdict.findings
    )
    # The entity is named too -- a NO_GO must be actionable.
    assert ENTITY_HIDDEN in _findings_text(verdict)


# ---------------------------------------------------------------------------
# Gate semantics and degraded inputs
# ---------------------------------------------------------------------------


def test_report_without_exception_list_is_go_with_fixes(pipeline):
    tampered = copy.deepcopy(pipeline.report)
    del tampered["exceptions"]
    verdict = independent_verify(
        pipeline.registers_dir, pipeline.tb_path, tampered
    )
    assert verdict.status == "GO_WITH_FIXES"
    severities = {f["severity"] for f in verdict.findings}
    assert "critical" not in severities
    assert "warning" in severities


def test_missing_registers_dir_is_no_go(pipeline, tmp_path):
    verdict = independent_verify(
        str(tmp_path / "nope"), pipeline.tb_path, pipeline.report
    )
    assert verdict.status == "NO_GO"


def test_missing_trial_balance_is_no_go(pipeline, tmp_path):
    verdict = independent_verify(
        pipeline.registers_dir, str(tmp_path / "missing_tb.csv"), pipeline.report
    )
    assert verdict.status == "NO_GO"
    assert "trial balance not found" in _findings_text(verdict)


def test_empty_scope_is_no_go(pipeline):
    verdict = independent_verify(
        pipeline.registers_dir, pipeline.tb_path, {}
    )
    assert verdict.status == "NO_GO"


# ---------------------------------------------------------------------------
# Independence of the verifier itself
# ---------------------------------------------------------------------------


def test_verifier_re_derives_the_population_from_raw_inputs(demo_dataset):
    population, problems = derive_population(demo_dataset.registers_dir)
    assert problems == []
    assert set(population) == set(ALL_REGISTER_GLS)


def test_verifier_does_not_import_the_preparers_logic():
    """The crown-jewel constraint: the auditor must not reuse preparer code.

    If the verifier imported the shared normalizer/parser/classifier, a bug
    there would hide the same account from both the report AND the check.
    """
    src = inspect.getsource(verify_module)
    for banned in (
        "from .reconcile",
        "from .ingest",
        "from .normalize",
        "from ccengine.reconcile",
        "from ccengine.ingest",
        "from ccengine.normalize",
        "import reconcile",
        "import ingest",
    ):
        assert banned not in src, f"verify.py must not depend on {banned!r}"
