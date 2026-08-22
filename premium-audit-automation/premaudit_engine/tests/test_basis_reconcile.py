"""Focused coverage for dual-basis reconcile and deliverable split."""
import datetime as dt
import json

from ..engine import build_package
from ..generate import generate_report
from ..model import CostLine, LedgerRow, PeriodBasis, Triage, TranType
from ..parse import parse_report
from ..reconcile import divergence, reconcile
from ..report import DELIVERABLE_FIELDS, deliverable_json, deliverable_leaks
from ..triage import triage_line


def _line(*, job="7100-99", cost_code="86-104", acctg=dt.date(2026, 1, 15),
          amount=1000, txn=None, tran=TranType.AP, desc="X",
          cost_code_desc="Warranty - Third Party Repairs",
          vendor_id="ACME01", vendor_name="ACME CONCRETE CUTTING INC") -> CostLine:
    return CostLine(
        job=job, job_name="Fictional Warranty", cost_code=cost_code,
        cost_code_desc=cost_code_desc, tran_type=tran, acctg_date=acctg,
        vendor_id=vendor_id, vendor_name=vendor_name, invoice="INV1",
        description=desc, amount_cents=amount, txn_date=txn)


def _ledger(*, job="7100-99", cost_code="86-104", acctg=dt.date(2026, 1, 15),
            amount=1000, txn=dt.date(2026, 1, 10),
            tran=TranType.AP) -> LedgerRow:
    return LedgerRow(job=job, cost_code=cost_code, tran_type=tran,
                     txn_date=txn, acctg_date=acctg, amount_cents=amount)


def test_reconcile_duplicates_match_positionally_never_merged():
    """Two identical-looking costs are two costs; collapsing would halve a total."""
    a = _line(amount=5000)
    b = _line(amount=5000)
    ledger = (
        _ledger(amount=5000, txn=dt.date(2025, 12, 1)),
        _ledger(amount=5000, txn=dt.date(2026, 2, 1)),
    )
    rec = reconcile([a, b], ledger)
    assert rec.matched == 2 and rec.unmatched == 0
    assert rec.unused_ledger_rows == 0
    assert rec.complete
    assert rec.lines[0].txn_date == dt.date(2025, 12, 1)
    assert rec.lines[1].txn_date == dt.date(2026, 2, 1)
    assert sum(l.amount_cents for l in rec.lines) == 10_000


def test_reconcile_unmatched_leaves_txn_date_unknown():
    line = _line(amount=999)
    rec = reconcile([line], [])
    assert rec.matched == 0 and rec.unmatched == 1
    assert rec.lines[0].txn_date is None
    assert not rec.complete
    assert rec.coverage_pct == 0.0


def test_divergence_classifies_moved_in_and_moved_out(window):
    moved_out = _line(acctg=dt.date(2026, 1, 15), txn=dt.date(2025, 9, 1),
                      amount=2000)
    moved_in = _line(acctg=dt.date(2025, 9, 1), txn=dt.date(2026, 1, 15),
                     amount=3000, cost_code="99-202")
    stay = _line(acctg=dt.date(2026, 2, 1), txn=dt.date(2026, 2, 1),
                 amount=1000, cost_code="99-106")
    div = divergence([moved_out, moved_in, stay], window)
    assert div.moved_out == (moved_out,)
    assert div.moved_in == (moved_in,)
    assert set(div.movers) == {moved_out, moved_in}
    assert div.accounting_cents == 2000 + 1000
    assert div.transaction_cents == 3000 + 1000
    assert div.delta_cents == div.transaction_cents - div.accounting_cents


def test_deliverable_is_in_window_only_and_allow_listed(window, policy):
    gen = generate_report(21)
    pkg = build_package(gen.text, gen.company, window, policy, gen.coverage)
    payload = json.loads(deliverable_json(pkg))
    assert set(payload) == {"period", "total_cents", "lines"}
    assert payload["period"] == {"start": window.start.isoformat(),
                                 "end": window.end.isoformat()}
    assert payload["total_cents"] == sum(l["amount_cents"] for l in payload["lines"])
    for line in payload["lines"]:
        assert set(line) <= set(DELIVERABLE_FIELDS)
        assert set(line) == set(DELIVERABLE_FIELDS)
    assert deliverable_leaks(pkg) == []


def test_deliverable_leaks_reports_foreign_fields(window, policy, monkeypatch):
    from .. import report as report_mod

    gen = generate_report(7)
    pkg = build_package(gen.text, gen.company, window, policy, gen.coverage)
    real = report_mod.deliverable_json

    def polluted(pkg_):
        payload = json.loads(real(pkg_))
        for line in payload["lines"]:
            line["vendor_id"] = "LEAK"
            line["acctg_date"] = "2099-01-01"
        return json.dumps(payload)

    monkeypatch.setattr(report_mod, "deliverable_json", polluted)
    assert report_mod.deliverable_leaks(pkg) == ["acctg_date", "vendor_id"]


def test_professional_cost_code_precedes_journal_entry(window, policy):
    jc_legal = CostLine(
        job="7100-99", job_name="F", cost_code="99-203",
        cost_code_desc="Warranty - Legal", tran_type=TranType.JC,
        acctg_date=dt.date(2026, 1, 1), vendor_id="", vendor_name="",
        invoice="", description="cc", amount_cents=500)
    assert triage_line(jc_legal, policy, [], window) is Triage.PROFESSIONAL


def test_generate_passes_ledger_and_reconcile_covers(window):
    gen = generate_report(42, jobs=2)
    assert len(gen.ledger) == gen.line_count
    parsed = parse_report(gen.text, gen.company)
    rec = reconcile(parsed.lines, gen.ledger)
    assert rec.complete
    assert all(l.txn_date is not None for l in rec.lines)
    # date_on returns the txn date after reconcile
    assert rec.lines[0].date_on(PeriodBasis.TRANSACTION) == rec.lines[0].txn_date
    assert rec.lines[0].date_on(PeriodBasis.ACCOUNTING) == rec.lines[0].acctg_date
