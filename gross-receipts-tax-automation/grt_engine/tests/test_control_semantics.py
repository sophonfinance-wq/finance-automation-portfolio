"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one day, one cent or one status either side of the
line. A control that fires a cent early is as wrong as one that never fires, and
only a boundary test can tell the two apart.

The re-derivation and calendar cases carry the most weight. A tax struck to the
cent must pass and a cent off must fail; a rate window is closed on the day it
opens; a return filed on its due date is on time and a day later is late; a
due-soon window closes at exactly ``lead_days`` out.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from grt_engine.engine import (
    SEVERITY,
    check_cal_approval_before_filing,
    check_cal_due_date_gate,
    check_cal_due_soon,
    check_ded_base_recomputes,
    check_ded_credit_recomputes,
    check_eff_rate_matches_period,
    check_lic_renewal_current,
    check_rate_tax_before_credit_recomputes,
    check_rate_tax_due_recomputes,
    check_rev_gross_ties_ledger,
    check_rpt_report_totals_tie,
    check_rpt_summary_recomputes,
)
from grt_engine.generate import AS_OF, LEAD_DAYS, PORTFOLIOS, baseline
from grt_engine.grt import expected_credit, small_business_credit
from grt_engine.model import (
    DOC_EXCISE_REPORT,
    DOC_FILING_REGISTER,
    DOC_LICENSE_REGISTER,
    DOC_TAX_SUMMARY,
    Context,
    Status,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _payload() -> dict:
    return baseline(PORTFOLIOS[0])


def _ctx(payload: dict) -> Context:
    return Context(path=Path("in-memory.json"), data=payload)


def _doc(payload: dict, doc_type: str) -> dict:
    return next(d for d in payload["documents"] if d["doc_type"] == doc_type)


def _filing(payload: dict, filing_id: str) -> dict:
    return next(
        f for f in _doc(payload, DOC_FILING_REGISTER)["filings"]
        if f["filing_id"] == filing_id
    )


def _summary_row(payload: dict, filing_id: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_TAX_SUMMARY)["filings"]
        if r["filing_id"] == filing_id
    )


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


def _as_of() -> date:
    return date.fromisoformat(AS_OF)


# --------------------------------------------------------------------------- #
# rate_ -- the tax re-derives to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_tax_before_credit_recomputes_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _filing(payload, "FIL-01")["tax_before_credit_cents"] += delta
    assert bool(_fired(check_rate_tax_before_credit_recomputes(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_tax_due_recomputes_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _filing(payload, "FIL-01")["tax_due_cents"] += delta
    assert bool(_fired(check_rate_tax_due_recomputes(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_taxable_base_recomputes_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _filing(payload, "FIL-01")["taxable_base_cents"] += delta
    assert bool(_fired(check_ded_base_recomputes(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# eff_rate_matches_period -- the rate window is closed on the day it opens
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "period_start, should_fail",
    [("2029-09-30", False), ("2029-10-01", True)],
)
def test_rate_window_edge(period_start: str, should_fail: bool) -> None:
    """FIL-01 states 175 bps. The rate steps to 210 bps on 2029-10-01, so a period
    starting that day should carry 210, and 175 is then wrong."""
    payload = _payload()
    _filing(payload, "FIL-01")["period_start"] = period_start
    assert bool(_fired(check_eff_rate_matches_period(_ctx(payload)))) is should_fail


def test_rate_in_force_far_out_is_clean() -> None:
    """The baseline worksheets apply exactly the rate in force and raise nothing."""
    assert not _fired(check_eff_rate_matches_period(_ctx(_payload())))


# --------------------------------------------------------------------------- #
# ded_credit_recomputes -- the small-business schedule and the threshold gate
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "tax, cap, expected",
    [
        (0, 500_000, 0),
        (400_000, 500_000, 400_000),   # at or below the cap: full offset
        (500_000, 500_000, 500_000),   # exactly the cap
        (700_000, 500_000, 300_000),   # phase-out: 2*cap - tax
        (1_000_000, 500_000, 0),       # at twice the cap: no credit
        (1_500_000, 500_000, 0),
        (400_000, 0, 0),               # a jurisdiction with no cap never credits
    ],
)
def test_small_business_credit_schedule(tax: int, cap: int, expected: int) -> None:
    assert small_business_credit(tax, cap) == expected


@pytest.mark.parametrize(
    "gross, threshold, expected_is_full",
    [(9_999_999, 10_000_000, True), (10_000_000, 10_000_000, False)],
)
def test_below_threshold_wipes_the_tax(gross: int, threshold: int, expected_is_full: bool) -> None:
    """Receipts below the threshold credit the whole tax away; exactly at it, none."""
    tax = 450_000
    got = expected_credit(gross, tax, threshold, 0)
    assert (got == tax) is expected_is_full


def test_credit_control_fires_when_credit_is_overclaimed() -> None:
    payload = _payload()
    assert not _fired(check_ded_credit_recomputes(_ctx(payload)))
    _filing(payload, "FIL-01")["credit_cents"] += 1
    assert _fired(check_ded_credit_recomputes(_ctx(payload)))


# --------------------------------------------------------------------------- #
# rev_gross_ties_ledger -- the base sums the ledger
# --------------------------------------------------------------------------- #
def test_gross_must_tie_the_ledger() -> None:
    payload = _payload()
    assert not _fired(check_rev_gross_ties_ledger(_ctx(payload)))
    _filing(payload, "FIL-01")["gross_receipts_cents"] += 1
    assert _fired(check_rev_gross_ties_ledger(_ctx(payload)))


# --------------------------------------------------------------------------- #
# cal_due_date_gate -- filed on the due date is on time, a day later is late
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("offset, should_fail", [(0, False), (1, True)])
def test_filed_on_the_due_date_is_on_time(offset: int, should_fail: bool) -> None:
    payload = _payload()
    filing = _filing(payload, "FIL-08")
    due = date.fromisoformat(filing["due_date"])
    filing["filing_date"] = (due + timedelta(days=offset)).isoformat()
    assert bool(_fired(check_cal_due_date_gate(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# cal_due_soon -- the window closes at exactly lead_days out
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("offset, should_flag", [(LEAD_DAYS, True), (LEAD_DAYS + 1, False)])
def test_due_soon_window_edge(offset: int, should_flag: bool) -> None:
    """An unfiled worksheet due exactly ``lead_days`` out is inside the window; a
    day past it is not."""
    payload = _payload()
    filing = _filing(payload, "FIL-08")
    filing["filed"] = False
    filing["due_date"] = (_as_of() + timedelta(days=offset)).isoformat()
    fired = _fired(check_cal_due_soon(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


def test_due_soon_is_clean_when_all_filed() -> None:
    """The baseline worksheets are all filed, so nothing is due-soon."""
    assert not _fired(check_cal_due_soon(_ctx(_payload())))


# --------------------------------------------------------------------------- #
# cal_approval_before_filing -- approved before filed, or it fails
# --------------------------------------------------------------------------- #
def test_approval_must_precede_filing() -> None:
    payload = _payload()
    assert not _fired(check_cal_approval_before_filing(_ctx(payload)))
    filing = _filing(payload, "FIL-01")
    filing["approval_date"] = (date.fromisoformat(filing["filing_date"]) + timedelta(days=1)).isoformat()
    assert _fired(check_cal_approval_before_filing(_ctx(payload)))


def test_unsigned_approval_fails() -> None:
    payload = _payload()
    _filing(payload, "FIL-01")["approval_signed"] = False
    assert _fired(check_cal_approval_before_filing(_ctx(payload)))


# --------------------------------------------------------------------------- #
# lic_renewal_current -- the renewal window closes at lead_days out
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("offset, should_flag", [(LEAD_DAYS, True), (LEAD_DAYS + 1, False)])
def test_license_renewal_window_edge(offset: int, should_flag: bool) -> None:
    payload = _payload()
    lic = _doc(payload, DOC_LICENSE_REGISTER)["licenses"][0]
    lic["renewal_date"] = (_as_of() + timedelta(days=offset)).isoformat()
    fired = _fired(check_lic_renewal_current(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


# --------------------------------------------------------------------------- #
# rpt_ -- the rollup recomputes from the worksheets, not the other way round
# --------------------------------------------------------------------------- #
def test_summary_must_recompute() -> None:
    payload = _payload()
    assert not _fired(check_rpt_summary_recomputes(_ctx(payload)))
    _summary_row(payload, "FIL-07")["tax_due_cents"] += 1
    assert _fired(check_rpt_summary_recomputes(_ctx(payload)))


def test_report_total_must_tie_the_summary() -> None:
    payload = _payload()
    assert not _fired(check_rpt_report_totals_tie(_ctx(payload)))
    _doc(payload, DOC_EXCISE_REPORT)["total_tax_due_cents"] += 1
    assert _fired(check_rpt_report_totals_tie(_ctx(payload)))


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "ent_unique_ids": Status.FAIL,
    "ent_jurisdictions_declared": Status.FAIL,
    "jur_cadence_valid": Status.FAIL,
    "jur_rate_windows_sound": Status.FAIL,
    "rev_required_fields": Status.FAIL,
    "rev_line_unique": Status.FAIL,
    "rev_entity_known": Status.FAIL,
    "rev_ledger_mapped": Status.FAIL,
    "rev_gross_ties_ledger": Status.FAIL,
    "fil_required_fields": Status.FAIL,
    "fil_unique": Status.FAIL,
    "fil_refs_exist": Status.FAIL,
    "eff_rate_matches_period": Status.FAIL,
    "rate_tax_before_credit_recomputes": Status.FAIL,
    "rate_tax_due_recomputes": Status.FAIL,
    "ded_base_recomputes": Status.FAIL,
    "ded_nontaxable_ties_ledger": Status.FAIL,
    "ded_credit_recomputes": Status.FAIL,
    "cal_completeness": Status.FAIL,
    "cal_due_date_gate": Status.FAIL,
    "cal_due_soon": Status.FLAG,
    "cal_approval_before_filing": Status.FAIL,
    "lic_status_active": Status.FAIL,
    "lic_renewal_current": Status.FLAG,
    "rpt_summary_recomputes": Status.FAIL,
    "rpt_report_totals_tie": Status.FAIL,
}


@pytest.mark.parametrize("rule_id", sorted(DESIGNED_SEVERITY))
def test_observed_severity_matches_the_design_table(rule_id: str, reports) -> None:
    """``reports`` is requested so the whole registry has executed first."""
    assert SEVERITY[rule_id] is DESIGNED_SEVERITY[rule_id]


def test_design_table_covers_the_whole_registry(reports) -> None:
    assert set(SEVERITY) == set(DESIGNED_SEVERITY)


@pytest.mark.parametrize("rule_id", sorted(DESIGNED_SEVERITY))
def test_rule_id_prefix_matches_its_family(rule_id: str) -> None:
    assert rule_id.split("_")[0] in {
        "set", "ent", "jur", "rev", "fil", "eff", "rate", "ded", "cal", "lic", "rpt"
    }
