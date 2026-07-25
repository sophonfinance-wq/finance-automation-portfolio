"""
Fictional debt term-sheet sizing corpus generator.
===================================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The borrowers, the projects, the reference indices,
the cost bases, the loan amounts, the fee rates and the term-sheet dates are
fictional, and the workbook period is set in a fictional future. No real entity,
person, lender, benchmark, project or path appears anywhere. The generator is
deterministic and takes no seed.

The baseline is derived, not typed
----------------------------------
Only the deals, the rate build-ups and the fee lines are stated as base facts.
Everything the engine later checks as a rollup -- each deal's all-in rate, each
fee line's amount, the expiry watchlist, and the portfolio count and totals -- is
recomputed by :func:`rederive` from those base facts, through the *same*
:mod:`sizing_engine.terms` kernel the engine recomputes with. So the
relationships the engine tests are the relationships that produced the data: a
defect that changes a base fact re-derives the rollup and keeps the break
confined to one control; a defect that targets a stated rollup edits that figure
alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from .engine import (
    _deal_id,
    _deals,
    _fees,
    recompute_all_in,
    recompute_expiry_watchlist,
    recompute_fee_amount,
    recompute_total_commitment,
    recompute_total_fees,
)
from .model import (
    DEFAULT_COMMITMENT_LEAD_DAYS,
    DOC_DEAL_REGISTER,
    DOC_EXPIRY_WATCHLIST,
    DOC_FEE_SCHEDULE,
    DOC_FEE_SUMMARY,
    DOC_RATE_BUILDUP,
    DOC_RATE_SUMMARY,
    DOC_TERM_SHEET_ROLLUP,
    Context,
)
from .terms import ltc_cap_cents

#: Fictional borrower labels, rotated for file identity only.
PORTFOLIOS: tuple[str, ...] = (
    "Northmoor Development Group",
    "Halbrook Residential Partners",
    "Stonecrest Communities",
    "Ardenne Field Group",
    "Westmere",
)

PERIOD = "FY2029"
#: The pricing date every term-sheet expiry test is measured to.
AS_OF = "2029-10-01"
#: Lead-time window, in days, for the term-sheet expiry watchlist.
COMMITMENT_LEAD_DAYS = 45


def d(dollars: float) -> int:
    """Dollars to integer cents."""
    return round(dollars * 100)


#: ``(deal_id, project, loan_type, index_name, recourse_type, cost_basis,
#:   max_ltc_bps, max_loan, drawn, facility, base_term_months,
#:   extension_options_months, stated_maturity_months, termsheet_expiration)``.
#: Amounts in dollars. DL-203 is sized exactly at its advance-rate cap so a
#: one-cent over-advance is the whole of a boundary defect; DL-202 is fully drawn.
DEALS: tuple[tuple[Any, ...], ...] = (
    (
        "DL-201", "Brightwater Commons", "construction", "term_reference_index",
        "full_recourse", 100_000_000, 6500, 60_000_000, 20_000_000, 5_000_000,
        36, (12, 12), 60, "2030-03-01",
    ),
    (
        "DL-202", "Copperfield Yards", "permanent", "prime_reference",
        "partial_recourse", 80_000_000, 7000, 50_000_000, 50_000_000, 2_000_000,
        120, (), 120, "2030-03-01",
    ),
    (
        "DL-203", "Ridgeline Terraces", "bridge", "overnight_index",
        "non_recourse", 40_000_000, 6000, 24_000_000, 10_000_000, 1_000_000,
        24, (6,), 30, "2030-03-01",
    ),
    (
        "DL-204", "Hollowmere Flats", "mini_perm", "fixed_swap_index",
        "full_recourse", 55_000_000, 6800, 35_000_000, 15_000_000, 3_000_000,
        60, (12,), 72, "2030-03-01",
    ),
)

#: ``(deal_id, index_bps, spread_bps, floor_bps)``. DL-202's floor governs -- the
#: index-plus-spread build-up lands below it -- so the ``max`` in the all-in rate
#: is exercised rather than assumed.
BUILDUPS: tuple[tuple[Any, ...], ...] = (
    ("DL-201", 425, 275, 650),
    ("DL-202", 380, 220, 700),
    ("DL-203", 500, 350, 800),
    ("DL-204", 410, 290, 675),
)

#: ``(fee_id, deal_id, fee_type, base_type, fee_rate_bps)``. Each deal carries an
#: origination fee on its commitment, a commitment fee on the drawn balance, an
#: unused fee on the undrawn balance and an admin fee on the facility, so every
#: fee type and every base type is exercised.
FEES: tuple[tuple[Any, ...], ...] = (
    ("FEE-201A", "DL-201", "origination", "commitment", 100),
    ("FEE-201B", "DL-201", "commitment", "drawn", 40),
    ("FEE-201C", "DL-201", "unused", "undrawn", 35),
    ("FEE-201D", "DL-201", "admin", "facility", 25),
    ("FEE-202A", "DL-202", "origination", "commitment", 100),
    ("FEE-202B", "DL-202", "commitment", "drawn", 40),
    ("FEE-202C", "DL-202", "unused", "undrawn", 35),
    ("FEE-202D", "DL-202", "admin", "facility", 25),
    ("FEE-203A", "DL-203", "origination", "commitment", 100),
    ("FEE-203B", "DL-203", "commitment", "drawn", 40),
    ("FEE-203C", "DL-203", "unused", "undrawn", 35),
    ("FEE-203D", "DL-203", "admin", "facility", 25),
    ("FEE-204A", "DL-204", "origination", "commitment", 100),
    ("FEE-204B", "DL-204", "commitment", "drawn", 40),
    ("FEE-204C", "DL-204", "unused", "undrawn", 35),
    ("FEE-204D", "DL-204", "admin", "facility", 25),
)


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _deal(payload: dict[str, Any], deal_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_DEAL_REGISTER)
    assert register is not None
    for row in register["deals"]:
        if row.get("deal_id") == deal_id:
            return row
    raise KeyError(deal_id)


def _fee(payload: dict[str, Any], fee_id: str) -> dict[str, Any]:
    schedule = _doc(payload, DOC_FEE_SCHEDULE)
    assert schedule is not None
    for row in schedule["fees"]:
        if row.get("fee_id") == fee_id:
            return row
    raise KeyError(fee_id)


def _rate_row(payload: dict[str, Any], deal_id: str) -> dict[str, Any]:
    summary = _doc(payload, DOC_RATE_SUMMARY)
    assert summary is not None
    for row in summary["rates"]:
        if row.get("deal_id") == deal_id:
            return row
    raise KeyError(deal_id)


def _fee_amount_row(payload: dict[str, Any], fee_id: str) -> dict[str, Any]:
    summary = _doc(payload, DOC_FEE_SUMMARY)
    assert summary is not None
    for row in summary["amounts"]:
        if row.get("fee_id") == fee_id:
            return row
    raise KeyError(fee_id)


def _rollup(payload: dict[str, Any]) -> dict[str, Any]:
    rollup = _doc(payload, DOC_TERM_SHEET_ROLLUP)
    assert rollup is not None
    return rollup


def _watchlist(payload: dict[str, Any]) -> dict[str, Any]:
    watchlist = _doc(payload, DOC_EXPIRY_WATCHLIST)
    assert watchlist is not None
    return watchlist


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def rederive(payload: dict[str, Any]) -> None:
    """Recompute every rollup figure from the payload's own base facts."""
    deal_doc = _doc(payload, DOC_DEAL_REGISTER)
    buildup_doc = _doc(payload, DOC_RATE_BUILDUP)
    fee_doc = _doc(payload, DOC_FEE_SCHEDULE)
    rate_summary = _doc(payload, DOC_RATE_SUMMARY)
    fee_summary = _doc(payload, DOC_FEE_SUMMARY)
    watchlist = _doc(payload, DOC_EXPIRY_WATCHLIST)
    rollup = _doc(payload, DOC_TERM_SHEET_ROLLUP)
    if not all((deal_doc, buildup_doc, fee_doc, rate_summary, fee_summary, watchlist, rollup)):
        return
    assert (
        rate_summary is not None
        and fee_summary is not None
        and watchlist is not None
        and rollup is not None
    )

    ctx = Context(path=Path("<generated>"), data=payload)
    as_of = date.fromisoformat(payload["as_of"])
    lead = payload.get("commitment_lead_days", DEFAULT_COMMITMENT_LEAD_DAYS)

    # Rate summary: one all-in rate per deal, recomputed through the shared kernel
    # the engine recomputes with.
    rates: list[dict[str, Any]] = []
    for deal in _deals(ctx):
        all_in = recompute_all_in(ctx, deal)
        if all_in is not None:
            rates.append({"deal_id": _deal_id(deal), "all_in_rate_bps": all_in})
    rate_summary["rates"] = rates

    # Fee summary: the computed amount for every priceable fee line.
    amounts: list[dict[str, Any]] = []
    for line in _fees(ctx):
        amount = recompute_fee_amount(ctx, line)
        if amount is not None:
            amounts.append(
                {
                    "fee_id": line.get("fee_id"),
                    "deal_id": line.get("deal_id"),
                    "fee_amount_cents": amount,
                }
            )
    fee_summary["amounts"] = amounts

    # Expiry watchlist: deals whose term sheet is inside the lead-time window.
    watchlist["entries"] = recompute_expiry_watchlist(ctx, as_of, lead)

    # Term-sheet rollup: the portfolio count and totals, footed from the deals.
    rollup["deal_count"] = len(_deals(ctx))
    rollup["total_commitment_cents"] = recompute_total_commitment(ctx)
    rollup["total_fees_cents"] = recompute_total_fees(ctx)


def baseline(portfolio: str) -> dict[str, Any]:
    """Build a clean sizing file for ``portfolio``."""
    payload: dict[str, Any] = {
        "file_id": "clean",
        "portfolio": portfolio,
        "period": PERIOD,
        "as_of": AS_OF,
        "commitment_lead_days": COMMITMENT_LEAD_DAYS,
        "documents": [
            {
                "doc_type": DOC_DEAL_REGISTER,
                "document_id": "DEALS-2029",
                "deals": [
                    {
                        "deal_id": deal_id,
                        "project": project,
                        "loan_type": loan_type,
                        "index_name": index_name,
                        "recourse_type": recourse_type,
                        "cost_basis_cents": d(cost_basis),
                        "max_ltc_bps": max_ltc,
                        "max_loan_amount_cents": d(max_loan),
                        "drawn_amount_cents": d(drawn),
                        "facility_limit_cents": d(facility),
                        "base_term_months": base_term,
                        "extension_options_months": list(extensions),
                        "stated_maturity_months": maturity,
                        "termsheet_expiration_date": expiration,
                    }
                    for (
                        deal_id, project, loan_type, index_name, recourse_type, cost_basis,
                        max_ltc, max_loan, drawn, facility, base_term, extensions, maturity,
                        expiration,
                    ) in DEALS
                ],
            },
            {
                "doc_type": DOC_RATE_BUILDUP,
                "document_id": "BUILDUP-2029",
                "buildups": [
                    {
                        "deal_id": deal_id,
                        "index_bps": index_bps,
                        "spread_bps": spread_bps,
                        "floor_bps": floor_bps,
                    }
                    for deal_id, index_bps, spread_bps, floor_bps in BUILDUPS
                ],
            },
            {
                "doc_type": DOC_FEE_SCHEDULE,
                "document_id": "FEES-2029",
                "fees": [
                    {
                        "fee_id": fee_id,
                        "deal_id": deal_id,
                        "fee_type": fee_type,
                        "base_type": base_type,
                        "fee_rate_bps": fee_rate_bps,
                    }
                    for fee_id, deal_id, fee_type, base_type, fee_rate_bps in FEES
                ],
            },
            {
                "doc_type": DOC_RATE_SUMMARY,
                "document_id": "RATES-2029",
                "rates": [],
            },
            {
                "doc_type": DOC_FEE_SUMMARY,
                "document_id": "FEEAMT-2029",
                "amounts": [],
            },
            {
                "doc_type": DOC_EXPIRY_WATCHLIST,
                "document_id": "WATCH-2029",
                "entries": [],
            },
            {
                "doc_type": DOC_TERM_SHEET_ROLLUP,
                "document_id": "ROLLUP-2029",
                "deal_count": 0,
                "total_commitment_cents": 0,
                "total_fees_cents": 0,
            },
        ],
    }
    rederive(payload)
    return payload


# --------------------------------------------------------------------------- #
# Planted defects -- one per registered control
# --------------------------------------------------------------------------- #
def _missing_artifact(payload: dict[str, Any]) -> None:
    payload["documents"] = [
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_TERM_SHEET_ROLLUP
    ]


def _duplicate_deal_id(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_DEAL_REGISTER)
    assert register is not None
    register["deals"].append(dict(_deal(payload, "DL-201")))
    rederive(payload)


def _bad_loan_type(payload: dict[str, Any]) -> None:
    _deal(payload, "DL-204")["loan_type"] = "revolver"


def _bad_index(payload: dict[str, Any]) -> None:
    _deal(payload, "DL-203")["index_name"] = "unlisted_index"


def _bad_recourse(payload: dict[str, Any]) -> None:
    _deal(payload, "DL-202")["recourse_type"] = "limited_recourse"


def _basis_undeclared(payload: dict[str, Any]) -> None:
    # The deal's sizing terms were never captured; its cost basis is zero.
    _deal(payload, "DL-203")["cost_basis_cents"] = 0


def _loan_over_advance(payload: dict[str, Any]) -> None:
    # The loan is sized one cent above the advance-rate cap; the rollup is
    # re-derived so only the over-advance control sees it.
    deal = _deal(payload, "DL-204")
    deal["max_loan_amount_cents"] = ltc_cap_cents(deal["cost_basis_cents"], deal["max_ltc_bps"]) + 1
    rederive(payload)


def _drawn_over_commitment(payload: dict[str, Any]) -> None:
    # The drawn balance runs one cent past the commitment; the rollup is
    # re-derived so only the draw-within-commitment control sees it.
    deal = _deal(payload, "DL-202")
    deal["drawn_amount_cents"] = deal["max_loan_amount_cents"] + 1
    rederive(payload)


def _maturity_mismatch(payload: dict[str, Any]) -> None:
    # Base term 24 plus a 6-month extension reconciles to 30, not 31.
    _deal(payload, "DL-203")["stated_maturity_months"] += 1


def _rate_buildup_missing(payload: dict[str, Any]) -> None:
    # DL-204's build-up row is gone; the deal still carries an all-in rate that
    # can no longer be sourced from an index, spread and floor.
    register = _doc(payload, DOC_RATE_BUILDUP)
    assert register is not None
    register["buildups"] = [
        r for r in register["buildups"] if r.get("deal_id") != "DL-204"
    ]


def _all_in_wrong(payload: dict[str, Any]) -> None:
    # The stated all-in rate contradicts the build-up; nothing else is touched.
    _rate_row(payload, "DL-201")["all_in_rate_bps"] = 999


def _bad_fee_type(payload: dict[str, Any]) -> None:
    _fee(payload, "FEE-201A")["fee_type"] = "exit"


def _bad_base_type(payload: dict[str, Any]) -> None:
    # The base is off its allowed list; the line drops out of the priced set on
    # re-derivation so only the base-type control sees it.
    _fee(payload, "FEE-203C")["base_type"] = "gross"
    rederive(payload)


def _fee_orphan_deal(payload: dict[str, Any]) -> None:
    schedule = _doc(payload, DOC_FEE_SCHEDULE)
    assert schedule is not None
    schedule["fees"].append(
        {
            "fee_id": "FEE-901",
            "deal_id": "DL-999",
            "fee_type": "origination",
            "base_type": "commitment",
            "fee_rate_bps": 100,
        }
    )


def _fee_amount_wrong(payload: dict[str, Any]) -> None:
    # The stated fee amount contradicts its rate on its base; the rollup total is
    # footed from the base facts, so only the fee-amount control sees it.
    _fee_amount_row(payload, "FEE-201A")["fee_amount_cents"] += d(1_000)


def _termsheet_expired(payload: dict[str, Any]) -> None:
    # The term sheet lapsed a month before the pricing date; the workbook still
    # shows its terms.
    _deal(payload, "DL-202")["termsheet_expiration_date"] = "2029-09-01"


def _termsheet_due_soon(payload: dict[str, Any]) -> None:
    # Still live but expiring inside the lead-time window; the rollup is
    # re-derived so only the lead-time FLAG remains.
    _deal(payload, "DL-201")["termsheet_expiration_date"] = "2029-10-20"
    rederive(payload)


def _deal_count_wrong(payload: dict[str, Any]) -> None:
    _rollup(payload)["deal_count"] += 1


def _commitment_total_wrong(payload: dict[str, Any]) -> None:
    _rollup(payload)["total_commitment_cents"] += d(1_000_000)


def _fee_total_wrong(payload: dict[str, Any]) -> None:
    _rollup(payload)["total_fees_cents"] += d(100)


def _watchlist_overstated(payload: dict[str, Any]) -> None:
    _watchlist(payload)["entries"].append(
        {
            "deal_id": "DL-203",
            "termsheet_expiration_date": "2030-03-01",
            "days_remaining": 151,
        }
    )


def _amount_not_integer(payload: dict[str, Any]) -> None:
    deal = _deal(payload, "DL-201")
    deal["max_loan_amount_cents"] = float(deal["max_loan_amount_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "duplicate_deal_id": ("deal_unique_ids", _duplicate_deal_id),
    "bad_loan_type": ("deal_loan_type_valid", _bad_loan_type),
    "bad_index": ("deal_index_valid", _bad_index),
    "bad_recourse": ("deal_recourse_valid", _bad_recourse),
    "basis_undeclared": ("deal_basis_declared", _basis_undeclared),
    "loan_over_advance": ("size_ltc_not_exceeded", _loan_over_advance),
    "drawn_over_commitment": ("size_drawn_within_commitment", _drawn_over_commitment),
    "maturity_mismatch": ("size_maturity_reconciles", _maturity_mismatch),
    "rate_buildup_missing": ("rate_buildup_present", _rate_buildup_missing),
    "all_in_wrong": ("rate_all_in_recomputes", _all_in_wrong),
    "bad_fee_type": ("fee_type_valid", _bad_fee_type),
    "bad_base_type": ("fee_base_type_valid", _bad_base_type),
    "fee_orphan_deal": ("fee_deal_exists", _fee_orphan_deal),
    "fee_amount_wrong": ("fee_amount_recomputes", _fee_amount_wrong),
    "termsheet_expired": ("exp_termsheet_not_expired", _termsheet_expired),
    "termsheet_due_soon": ("exp_termsheet_lead_time", _termsheet_due_soon),
    "deal_count_wrong": ("rpt_deal_count_ties", _deal_count_wrong),
    "commitment_total_wrong": ("rpt_commitment_total_ties", _commitment_total_wrong),
    "fee_total_wrong": ("rpt_fee_total_ties", _fee_total_wrong),
    "watchlist_overstated": ("rpt_expiry_watchlist_ties", _watchlist_overstated),
    "amount_not_integer": ("size_ltc_not_exceeded", _amount_not_integer),
}


# --------------------------------------------------------------------------- #
# Corpus writer
# --------------------------------------------------------------------------- #
def generate_corpus(folder: Path) -> list[Path]:
    """Write the fictional corpus into ``folder`` and return the paths written."""
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    files: list[dict[str, Any]] = []
    clean = baseline(PORTFOLIOS[0])
    clean["file_id"] = f"clean__{PORTFOLIOS[0].replace(' ', '_')}"
    files.append(clean)

    for i, name in enumerate(sorted(DEFECTS)):
        _rule, mutate = DEFECTS[name]
        portfolio = PORTFOLIOS[(i + 1) % len(PORTFOLIOS)]
        f = baseline(portfolio)
        f["file_id"] = f"{name}__{portfolio.replace(' ', '_')}"
        f["planted_defect"] = name
        mutate(f)
        files.append(f)

    for f in files:
        path = folder / f"{f['file_id']}.json"
        path.write_text(
            json.dumps(f, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return sorted(written)
