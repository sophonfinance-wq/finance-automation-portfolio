"""
Fictional draw-package generator.
=================================

Builds a byte-stable corpus of draw packages for the engine to analyze. One
package is clean; every other carries exactly **one** planted defect, so a test
can assert that a given rule fires on its own package and that no other rule
fires spuriously alongside it.

Everything here is invented. The projects, lenders, vendors, signers and cost
codes are fictional, the periods are set in a fictional future, and no real
document, entity, person, bank or path appears anywhere. The generator is
deterministic and takes no seed: given the same source it writes byte-identical
files, which is what lets the committed report be diffed meaningfully.

The baseline is arithmetically self-consistent by construction
------------------------------------------------------------
Building a package that passes 30+ interlocking tie-outs by hand is error-prone,
so the baseline is *derived* rather than typed: line disbursements are chosen,
and every dependent figure -- previous applications, remaining funds, column
totals, the reconciliation, the transaction detail -- is computed from them. A
defect is then applied as a single surgical mutation. That way a planted defect
is guaranteed to be the only thing wrong, and the clean package cannot silently
rot as rules are added.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .model import (
    DOC_COST_DETAIL,
    DOC_CYCLE_CALENDAR,
    DOC_DRAW_REQUEST,
    DOC_FUNDING_LEDGER,
    DOC_JC_RECONCILIATION,
    DOC_SUPPORT_INDEX,
)

# --------------------------------------------------------------------------- #
# Fictional constants
# --------------------------------------------------------------------------- #
PROJECTS: tuple[str, ...] = (
    "Alderpoint Terraces",
    "Brightwater Commons",
    "Copperfield Yards",
    "Dunmore Flats",
)
LENDER = "Meridian Sandbox Bank, N.A."
SIGNERS = ("A. Whitfield", "R. Castellanos")
PERIOD = "2027-04"
DRAW_NUMBER = 14


def d(dollars: int) -> int:
    """Dollars to integer cents. The generator thinks in dollars; the engine does not."""
    return dollars * 100


#: ``(code, name, cost_class, is_contingency, original_budget, disbursed_to_date,
#:   request_this_period, gross_costs_to_date, retention_withheld)``
#:
#: Hard non-contingency progress is 4,000,000 of 10,000,000 == 40.00%, so the
#: 500,000 hard contingency may carry at most 200,000; it carries 150,000.
#: Soft non-contingency progress is 900,000 of 1,300,000 == 69.23%, so the
#: 200,000 soft contingency may carry at most 138,460; it carries 100,000.
LINES: tuple[tuple[str, str, str, bool, int, int, int, int, int], ...] = (
    ("01-100", "Site work", "hard", False,
     d(2_000_000), d(1_600_000), d(120_000), d(1_660_000), d(-60_000)),
    ("02-100", "Vertical construction", "hard", False,
     d(8_000_000), d(2_400_000), d(380_000), d(2_490_000), d(-90_000)),
    ("03-900", "Hard cost contingency", "hard", True,
     d(500_000), d(150_000), d(15_000), d(150_000), 0),
    ("10-100", "Design and engineering", "soft", False,
     d(900_000), d(700_000), d(40_000), d(730_000), d(-30_000)),
    ("11-100", "Permits and fees", "soft", False,
     d(400_000), d(200_000), d(10_000), d(220_000), d(-20_000)),
    ("19-900", "Soft cost contingency", "soft", True,
     d(200_000), d(100_000), d(5_000), d(100_000), 0),
)

#: Current-period transactions, split so each category's subtotal equals its
#: ``request_this_period``. ``(txn_id, code, amount, vendor, accrual, immediate)``
TRANSACTIONS: tuple[tuple[str, str, int, str, bool, bool], ...] = (
    ("T-0001", "01-100", d(70_000), "Rockbourne Sitework Co", False, False),
    ("T-0002", "01-100", d(50_000), "Rockbourne Sitework Co", False, False),
    ("T-0003", "02-100", d(200_000), "Halveston Framing LLC", False, False),
    ("T-0004", "02-100", d(180_000), "Pemberton Concrete Inc", False, False),
    ("T-0005", "03-900", d(15_000), "Halveston Framing LLC", False, False),
    ("T-0006", "10-100", d(40_000), "Ashgrove Design Studio", False, False),
    # A permit accrual: below the materiality threshold, but exempt because it
    # has to be paid immediately. This exercises the accrual policy's exemption
    # branch rather than only its failure branch.
    ("T-0007", "11-100", d(10_000), "Municipal Permit Authority", True, True),
    ("T-0008", "19-900", d(5_000), "Ashgrove Design Studio", False, False),
)

FUNDINGS: tuple[tuple[str, str, int], ...] = (
    ("2026-11", "equity", d(500_000)),
    ("2026-12", "debt", d(1_500_000)),
    ("2027-01", "equity", d(650_000)),
    ("2027-02", "debt", d(1_200_000)),
    ("2027-03", "debt", d(1_300_000)),
)

BACKUP_THRESHOLD = d(5_000)
ACCRUAL_MATERIALITY = d(25_000)
WORKING_CAPITAL_FLOOR = d(50_000)
WORKING_CAPITAL_BALANCE = d(75_000)

RECIPIENTS = (
    "draws@meridian-sandbox-bank.example",
    "treasury@sandbox-developer.example",
    "controller@sandbox-developer.example",
)


# --------------------------------------------------------------------------- #
# Baseline construction (everything derived, nothing typed twice)
# --------------------------------------------------------------------------- #
def _draw_request() -> dict[str, Any]:
    """The lender-facing form, derived from :data:`LINES`."""
    lines: list[dict[str, Any]] = []
    for code, name, klass, is_cont, budget, disbursed, request, _c, _r in LINES:
        lines.append({
            "code": code,
            "name": name,
            "cost_class": klass,
            "is_contingency": is_cont,
            "original_budget_cents": budget,
            "budget_adjustments_cents": 0,
            "revised_budget_cents": budget,
            "previous_applications_cents": disbursed - request,
            "request_this_period_cents": request,
            "total_disbursed_to_date_cents": disbursed,
            "remaining_funds_cents": budget - disbursed,
        })
    keys = ("original_budget_cents", "budget_adjustments_cents", "revised_budget_cents",
            "previous_applications_cents", "request_this_period_cents",
            "total_disbursed_to_date_cents", "remaining_funds_cents")
    return {
        "doc_type": DOC_DRAW_REQUEST,
        "document_id": f"DRF-{PERIOD}-{DRAW_NUMBER:04d}",
        "period": PERIOD,
        "lender": LENDER,
        "lines": lines,
        "totals": {k: sum(line[k] for line in lines) for k in keys},
        "signed_by": SIGNERS[0],
        "signature_date": "2027-05-12",
    }


def _reconciliation() -> dict[str, Any]:
    """The project accountant's working paper, derived from :data:`LINES`."""
    categories: list[dict[str, Any]] = []
    for code, name, klass, _ic, _b, disbursed, request, gross, retention in LINES:
        released = d(25_000) if code == "01-100" else 0
        categories.append({
            "code": code,
            "name": name,
            "cost_class": klass,
            "prior_funding_cents": disbursed - request,
            "current_draw_cents": request,
            "costs_to_date_cents": gross,
            "retention_withheld_cents": retention,
            "retention_billed_current_cents": released,
            "retention_release_reflected_in_current": bool(released),
        })
    prior = sum(c["prior_funding_cents"] for c in categories)
    current = sum(c["current_draw_cents"] for c in categories)
    gross_costs = sum(c["costs_to_date_cents"] for c in categories)
    retention = sum(c["retention_withheld_cents"] for c in categories)
    equity = sum(a for _m, s, a in FUNDINGS if s == "equity")
    debt = sum(a for _m, s, a in FUNDINGS if s == "debt")
    return {
        "doc_type": DOC_JC_RECONCILIATION,
        "document_id": f"JCR-{PERIOD}-{DRAW_NUMBER:04d}",
        "period": PERIOD,
        "categories": categories,
        "totals": {
            "prior_funding_cents": prior,
            "current_draw_cents": current,
            "total_draws_to_date_cents": prior + current,
            "costs_to_date_cents": gross_costs,
            "retention_withheld_cents": retention,
            # Retention is carried negative, so netting it is an addition.
            "costs_to_date_net_retention_cents": gross_costs + retention,
        },
        "variance_cents": 0,
        "variance_explanation": None,
        "ledger_equity_funding_cents": equity,
        "ledger_debt_funding_cents": debt,
    }


def _cost_detail() -> dict[str, Any]:
    """Current-period transactions, subtotaling to each line's request."""
    txns = []
    for i, (txn_id, code, amount, vendor, accrual, immediate) in enumerate(TRANSACTIONS):
        day = 6 + i * 3  # spread across April, all inside the period
        txns.append({
            "txn_id": txn_id,
            "code": code,
            "cost_class": next(k for c, _n, k, *_ in LINES if c == code),
            "amount_cents": amount,
            "vendor": vendor,
            "invoice_number": f"INV-{7100 + i}",
            "accounting_date": f"2027-04-{day:02d}",
            "posted_date": f"2027-05-{1 + (i % 3):02d}",
            "approval_notice_date": f"2027-04-{day:02d}",
            "approval_completed_date": f"2027-04-{day + 1:02d}",
            "is_accrual": accrual,
            "payment_required_immediately": immediate,
        })
    return {
        "doc_type": DOC_COST_DETAIL,
        "document_id": f"CTD-{PERIOD}-{DRAW_NUMBER:04d}",
        "period": PERIOD,
        "transactions": txns,
    }


def _funding_ledger() -> dict[str, Any]:
    """Funding events plus the ledger and trial-balance figures they must tie to."""
    equity = sum(a for _m, s, a in FUNDINGS if s == "equity")
    debt = sum(a for _m, s, a in FUNDINGS if s == "debt")
    previous = sum(dis - req for _c, _n, _k, _i, _b, dis, req, _g, _r in LINES)
    return {
        "doc_type": DOC_FUNDING_LEDGER,
        "document_id": f"FDL-{PERIOD}-{DRAW_NUMBER:04d}",
        "period": PERIOD,
        "fundings": [
            {"month": m, "source": s, "amount_cents": a} for m, s, a in FUNDINGS
        ],
        "gl_equity_balance_cents": equity,
        "gl_debt_balance_cents": debt,
        "trial_balance_previous_applications_cents": previous,
        "working_capital_balance_cents": WORKING_CAPITAL_BALANCE,
        "working_capital_floor_cents": WORKING_CAPITAL_FLOOR,
    }


def _support_index() -> dict[str, Any]:
    """Signatures, invoice backup coverage and distribution."""
    over = [t[0] for t in TRANSACTIONS if abs(t[2]) >= BACKUP_THRESHOLD]
    return {
        "doc_type": DOC_SUPPORT_INDEX,
        "document_id": f"SDI-{PERIOD}-{DRAW_NUMBER:04d}",
        "period": PERIOD,
        "invoice_backup_threshold_cents": BACKUP_THRESHOLD,
        "backup_provided_txn_ids": over,
        "schedule_of_values_required": True,
        "schedule_of_values_attached": True,
        "authorized_signers": list(SIGNERS),
        "required_recipients": list(RECIPIENTS),
        "actual_recipients": list(RECIPIENTS),
    }


def _cycle_calendar() -> dict[str, Any]:
    """The dated milestones of the cycle."""
    return {
        "doc_type": DOC_CYCLE_CALENDAR,
        "document_id": f"DCC-{PERIOD}-{DRAW_NUMBER:04d}",
        "period": PERIOD,
        "window_opens": "2027-04-25",
        "cost_cutoff": "2027-04-30",
        "posting_deadline": "2027-05-03",
        "prep_start": "2027-05-04",
        "submitted": "2027-05-12",
        "target_submit_by": "2027-05-15",
        "funded": "2027-05-22",
        "target_funded_by": "2027-05-25",
        "lender_funding_days_max": 14,
        "approval_sla_days": 2,
        "accrual_materiality_cents": ACCRUAL_MATERIALITY,
        "followup_logged": False,
        "prior_period_accruals": [
            {"txn_id": "T-9901", "amount_cents": d(48_000), "reversed": True},
        ],
    }


def baseline(project: str) -> dict[str, Any]:
    """A complete, internally consistent draw package that passes every control."""
    return {
        "package_id": f"{project.replace(' ', '_')}__{PERIOD}__draw{DRAW_NUMBER}",
        "project": project,
        "period": PERIOD,
        "draw_number": DRAW_NUMBER,
        "lender": LENDER,
        "documents": [
            _reconciliation(),
            _draw_request(),
            _cost_detail(),
            _funding_ledger(),
            _support_index(),
            _cycle_calendar(),
        ],
    }


# --------------------------------------------------------------------------- #
# Defect mutations -- exactly one surgical change each
# --------------------------------------------------------------------------- #
def _doc(pkg: dict[str, Any], doc_type: str) -> dict[str, Any]:
    return next(d_ for d_ in pkg["documents"] if d_["doc_type"] == doc_type)


def _line(pkg: dict[str, Any], code: str) -> dict[str, Any]:
    return next(l for l in _doc(pkg, DOC_DRAW_REQUEST)["lines"] if l["code"] == code)


def _cat(pkg: dict[str, Any], code: str) -> dict[str, Any]:
    return next(c for c in _doc(pkg, DOC_JC_RECONCILIATION)["categories"]
                if c["code"] == code)


def _txn(pkg: dict[str, Any], txn_id: str) -> dict[str, Any]:
    return next(t for t in _doc(pkg, DOC_COST_DETAIL)["transactions"]
                if t["txn_id"] == txn_id)


def _drop_document(pkg: dict[str, Any]) -> None:
    pkg["documents"] = [d_ for d_ in pkg["documents"]
                        if d_["doc_type"] != DOC_SUPPORT_INDEX]


def _period_drift(pkg: dict[str, Any]) -> None:
    _doc(pkg, DOC_COST_DETAIL)["period"] = "2027-03"


def _recon_break(pkg: dict[str, Any]) -> None:
    _doc(pkg, DOC_JC_RECONCILIATION)["totals"]["costs_to_date_net_retention_cents"] += d(12_500)


def _total_mismatch(pkg: dict[str, Any]) -> None:
    _doc(pkg, DOC_JC_RECONCILIATION)["totals"]["total_draws_to_date_cents"] += d(4_000)


def _category_no_foot(pkg: dict[str, Any]) -> None:
    _cat(pkg, "02-100")["costs_to_date_cents"] += d(9_000)


def _retention_positive(pkg: dict[str, Any]) -> None:
    cat = _cat(pkg, "10-100")
    cat["retention_withheld_cents"] = abs(cat["retention_withheld_cents"])


def _retention_not_moved(pkg: dict[str, Any]) -> None:
    _cat(pkg, "01-100")["retention_release_reflected_in_current"] = False


def _funding_off_ledger(pkg: dict[str, Any]) -> None:
    _doc(pkg, DOC_JC_RECONCILIATION)["ledger_debt_funding_cents"] += d(30_000)


def _funding_rows_off(pkg: dict[str, Any]) -> None:
    _doc(pkg, DOC_FUNDING_LEDGER)["fundings"][1]["amount_cents"] += d(15_000)


def _variance_unexplained(pkg: dict[str, Any]) -> None:
    _doc(pkg, DOC_JC_RECONCILIATION)["variance_cents"] = d(1_200)


def _line_no_crossfoot(pkg: dict[str, Any]) -> None:
    _line(pkg, "10-100")["total_disbursed_to_date_cents"] += d(2_000)


def _remaining_wrong(pkg: dict[str, Any]) -> None:
    _line(pkg, "02-100")["remaining_funds_cents"] -= d(7_500)


def _budget_not_derived(pkg: dict[str, Any]) -> None:
    _line(pkg, "11-100")["revised_budget_cents"] += d(5_000)


def _column_no_foot(pkg: dict[str, Any]) -> None:
    _doc(pkg, DOC_DRAW_REQUEST)["totals"]["request_this_period_cents"] += d(3_000)


def _form_vs_recon(pkg: dict[str, Any]) -> None:
    _doc(pkg, DOC_DRAW_REQUEST)["totals"]["total_disbursed_to_date_cents"] += d(6_000)


def _previous_vs_tb(pkg: dict[str, Any]) -> None:
    _doc(pkg, DOC_FUNDING_LEDGER)["trial_balance_previous_applications_cents"] += d(11_000)


def _request_vs_detail(pkg: dict[str, Any]) -> None:
    _txn(pkg, "T-0003")["amount_cents"] += d(8_000)


def _negative_remaining(pkg: dict[str, Any]) -> None:
    line = _line(pkg, "11-100")
    line["total_disbursed_to_date_cents"] = line["revised_budget_cents"] + d(20_000)
    line["previous_applications_cents"] = (
        line["total_disbursed_to_date_cents"] - line["request_this_period_cents"])
    line["remaining_funds_cents"] = (
        line["revised_budget_cents"] - line["total_disbursed_to_date_cents"])


def _contingency_ahead(pkg: dict[str, Any]) -> None:
    # 40.00% hard progress caps the 500,000 contingency at 200,000; take 260,000.
    line = _line(pkg, "03-900")
    line["total_disbursed_to_date_cents"] = d(260_000)
    line["previous_applications_cents"] = (
        line["total_disbursed_to_date_cents"] - line["request_this_period_cents"])
    line["remaining_funds_cents"] = (
        line["revised_budget_cents"] - line["total_disbursed_to_date_cents"])


def _contingency_exhausted(pkg: dict[str, Any]) -> None:
    # 95% of the soft contingency consumed -- still inside the percent-complete
    # ceiling is impossible here, so this package trips the headroom flag only by
    # raising both the ceiling and the draw together.
    for code in ("10-100", "11-100"):
        line = _line(pkg, code)
        line["total_disbursed_to_date_cents"] = line["revised_budget_cents"]
        line["previous_applications_cents"] = (
            line["total_disbursed_to_date_cents"] - line["request_this_period_cents"])
        line["remaining_funds_cents"] = 0
    line = _line(pkg, "19-900")
    line["total_disbursed_to_date_cents"] = d(190_000)
    line["previous_applications_cents"] = (
        line["total_disbursed_to_date_cents"] - line["request_this_period_cents"])
    line["remaining_funds_cents"] = (
        line["revised_budget_cents"] - line["total_disbursed_to_date_cents"])


def _cost_outside_period(pkg: dict[str, Any]) -> None:
    _txn(pkg, "T-0004")["accounting_date"] = "2027-03-28"


def _posted_late(pkg: dict[str, Any]) -> None:
    _txn(pkg, "T-0006")["posted_date"] = "2027-05-09"


def _approval_slow(pkg: dict[str, Any]) -> None:
    _txn(pkg, "T-0002")["approval_completed_date"] = "2027-04-22"


def _milestones_disordered(pkg: dict[str, Any]) -> None:
    _doc(pkg, DOC_CYCLE_CALENDAR)["prep_start"] = "2027-05-01"


def _submitted_late(pkg: dict[str, Any]) -> None:
    cal = _doc(pkg, DOC_CYCLE_CALENDAR)
    cal["submitted"] = "2027-05-19"
    cal["funded"] = "2027-05-29"


def _immaterial_accrual(pkg: dict[str, Any]) -> None:
    txn = _txn(pkg, "T-0007")
    txn["payment_required_immediately"] = False


def _accrual_not_reversed(pkg: dict[str, Any]) -> None:
    _doc(pkg, DOC_CYCLE_CALENDAR)["prior_period_accruals"][0]["reversed"] = False


def _unsigned(pkg: dict[str, Any]) -> None:
    _doc(pkg, DOC_DRAW_REQUEST)["signed_by"] = ""


def _signer_unauthorized(pkg: dict[str, Any]) -> None:
    _doc(pkg, DOC_DRAW_REQUEST)["signed_by"] = "T. Aldington"


def _backup_missing(pkg: dict[str, Any]) -> None:
    idx = _doc(pkg, DOC_SUPPORT_INDEX)
    idx["backup_provided_txn_ids"] = [
        t for t in idx["backup_provided_txn_ids"] if t != "T-0003"]


def _sov_missing(pkg: dict[str, Any]) -> None:
    _doc(pkg, DOC_SUPPORT_INDEX)["schedule_of_values_attached"] = False


def _distribution_gap(pkg: dict[str, Any]) -> None:
    idx = _doc(pkg, DOC_SUPPORT_INDEX)
    idx["actual_recipients"] = idx["actual_recipients"][:-1]


def _funding_overdue(pkg: dict[str, Any]) -> None:
    cal = _doc(pkg, DOC_CYCLE_CALENDAR)
    cal["funded"] = "2027-06-05"
    cal["followup_logged"] = True


def _no_followup(pkg: dict[str, Any]) -> None:
    cal = _doc(pkg, DOC_CYCLE_CALENDAR)
    cal["funded"] = None
    cal["followup_logged"] = False


def _working_capital_low(pkg: dict[str, Any]) -> None:
    _doc(pkg, DOC_FUNDING_LEDGER)["working_capital_balance_cents"] = d(18_000)


def _amount_not_integer(pkg: dict[str, Any]) -> None:
    # A float where integer cents belong: the engine must report AMOUNT_INVALID
    # rather than coerce it, and must contain the damage to the one row.
    _line(pkg, "01-100")["request_this_period_cents"] = 12000000.5


#: ``name -> (rule the package is built to trip, mutation)``. The rule id is
#: recorded so a test can assert the intended rule actually fires.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _drop_document),
    "period_drift": ("set_period_aligned", _period_drift),
    "recon_break": ("recon_draws_tie_costs", _recon_break),
    "total_mismatch": ("recon_total_is_prior_plus_current", _total_mismatch),
    "category_no_foot": ("recon_categories_foot", _category_no_foot),
    "retention_positive": ("recon_retention_sign", _retention_positive),
    "retention_not_moved": ("recon_retention_release_moved", _retention_not_moved),
    "funding_off_ledger": ("recon_funding_ties_ledger", _funding_off_ledger),
    "funding_rows_off": ("recon_funding_rows_foot", _funding_rows_off),
    "variance_unexplained": ("recon_variance_explained", _variance_unexplained),
    "line_no_crossfoot": ("form_lines_crossfoot", _line_no_crossfoot),
    "remaining_wrong": ("form_remaining_is_budget_less_disbursed", _remaining_wrong),
    "budget_not_derived": ("form_revised_budget_is_original_plus_adjustments",
                           _budget_not_derived),
    "column_no_foot": ("form_columns_foot", _column_no_foot),
    "form_vs_recon": ("form_disbursed_ties_recon", _form_vs_recon),
    "previous_vs_tb": ("form_previous_ties_trial_balance", _previous_vs_tb),
    "request_vs_detail": ("form_request_ties_cost_detail", _request_vs_detail),
    "negative_remaining": ("form_no_negative_remaining", _negative_remaining),
    "contingency_ahead": ("cont_within_percent_complete", _contingency_ahead),
    "contingency_exhausted": ("cont_not_negative", _contingency_exhausted),
    "cost_outside_period": ("cut_costs_inside_period", _cost_outside_period),
    "posted_late": ("cut_posted_by_deadline", _posted_late),
    "approval_slow": ("cut_approvals_within_sla", _approval_slow),
    "milestones_disordered": ("cut_cycle_milestones_ordered", _milestones_disordered),
    "submitted_late": ("cut_submitted_by_target", _submitted_late),
    "immaterial_accrual": ("acc_only_material", _immaterial_accrual),
    "accrual_not_reversed": ("acc_prior_period_reversed", _accrual_not_reversed),
    "unsigned": ("doc_signed", _unsigned),
    "signer_unauthorized": ("doc_signed", _signer_unauthorized),
    "backup_missing": ("doc_backup_over_threshold", _backup_missing),
    "sov_missing": ("doc_schedule_of_values", _sov_missing),
    "distribution_gap": ("doc_distribution_complete", _distribution_gap),
    "funding_overdue": ("fund_within_agreement_days", _funding_overdue),
    "no_followup": ("fund_overdue_followed_up", _no_followup),
    "working_capital_low": ("fund_working_capital_floor", _working_capital_low),
    "amount_not_integer": ("form_lines_crossfoot", _amount_not_integer),
}


# --------------------------------------------------------------------------- #
# Corpus writer
# --------------------------------------------------------------------------- #
def generate_corpus(folder: Path) -> list[Path]:
    """Write the fictional corpus into ``folder`` and return the paths written.

    One clean package plus one per entry in :data:`DEFECTS`. Projects are dealt
    round-robin so the corpus reads like several projects in one month rather
    than one project with an implausible number of problems.

    Files are written with sorted keys and a trailing newline, so a regenerated
    corpus is byte-identical and a real change shows up as a real diff.
    """
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    packages: list[tuple[str, dict[str, Any]]] = []
    clean = baseline(PROJECTS[0])
    clean["package_id"] = f"clean__{PROJECTS[0].replace(' ', '_')}"
    packages.append(("clean", clean))

    for i, name in enumerate(sorted(DEFECTS)):
        _rule, mutate = DEFECTS[name]
        project = PROJECTS[(i + 1) % len(PROJECTS)]
        pkg = baseline(project)
        pkg["package_id"] = f"{name}__{project.replace(' ', '_')}"
        pkg["planted_defect"] = name
        mutate(pkg)
        packages.append((name, pkg))

    for name, pkg in packages:
        path = folder / f"{pkg['package_id']}.json"
        path.write_text(
            json.dumps(pkg, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return sorted(written)
