"""
Fictional earnest-money deposit corpus generator.
=================================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The developers, the projects, the buyers, the
escrow agent, the lender, the units and every amount and date are fictional,
and the reporting period is set in a fictional future. No real entity, person,
bank, escrow agent, project or path appears anywhere. The generator is
deterministic and takes no seed.

The baseline is derived, not typed
----------------------------------
Only the deposit ledger, the agent's statement, the loan register, the
cancellation register and the sales prices are stated as base facts.
Everything the engine later checks as a determination -- each unit's variance
and exception flag, the total variance, the posting-bucket totals, the trust
balances and each net sale price -- is recomputed by :func:`rederive` from
those base facts, through the *same* :mod:`deposit_engine.reconcile` kernel
the engine recomputes with. So the relationships the engine tests are the
relationships that produced the data: a defect that changes a base fact
re-derives the rollup and keeps the break confined to one control; a defect
that targets a stated determination edits that figure alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .engine import (
    recompute_bucket_totals,
    recompute_forfeiture_income,
    recompute_recon_units,
    recompute_upgrade_bank,
)
from .model import (
    CONCESSION_REVENUE_ACCOUNT,
    DOC_CANCELLATION_REGISTER,
    DOC_DEPOSIT_LEDGER,
    DOC_ESCROW_STATEMENT,
    DOC_PAYDOWN_REGISTER,
    DOC_RECON_SUMMARY,
    DOC_SALES_MATRIX,
    DOC_TRUST_BALANCES,
    FORFEITURE_ACCOUNT,
    KIND_PAYDOWN,
    KIND_REVERSAL,
    STATE_ACTIVE,
    STATE_CANCELLED,
    STATUS_ALREADY_POSTED,
    STATUS_BUCKETS,
    STATUS_NEED_TO_POST,
    STATUS_UNIT_CLOSED,
    Context,
)
from .reconcile import net_sale

#: Fictional developer labels, rotated for file identity only.
PORTFOLIOS: tuple[str, ...] = (
    "Northmoor Development Group",
    "Halbrook Residential",
    "Stonecrest Communities",
    "Ardenne Field Partners",
    "Westmere",
)

#: The fictional for-sale project whose deposit trust the corpus records.
PROJECT = "Alderpoint Terraces"
#: The fictional escrow/closing agent holding the earnest money.
ESCROW_AGENT = "Harborline Title & Escrow"
#: The fictional construction lender whose loan the deposits pay down.
LENDER = "Kestrel Ridge Lending"
#: The fictional jurisdiction the trust rules are drawn under.
JURISDICTION = "State of Marran"

PERIOD = "FY2030"
#: The ledger cut-off date the reconciliation is drawn at.
AS_OF = "2030-03-31"


def d(dollars: float) -> int:
    """Dollars to integer cents."""
    return round(dollars * 100)


#: ``(deposit_id, unit_id, buyer, receipt_date, amount, upgrade, em, status,
#:   state)``. Amounts in dollars. Invented buyers. UNIT-101 carries two
#: deposits (an initial and an additional earnest-money receipt) so the
#: per-unit tie-out has a real multi-deposit unit to foot; UNIT-104 is a
#: cancelled buyer whose sweep must reverse; UNIT-106 cancelled before its
#: deposit ever posted; UNIT-103 has closed and left the pre-close world.
DEPOSITS: tuple[tuple[Any, ...], ...] = (
    ("DEP-1001", "UNIT-101", "A. Fenholt", "2030-01-12", 25_000, 5_000, 20_000, STATUS_ALREADY_POSTED, STATE_ACTIVE),
    ("DEP-1002", "UNIT-102", "R. Quarrow", "2030-02-03", 15_000, 0, 15_000, STATUS_NEED_TO_POST, STATE_ACTIVE),
    ("DEP-1003", "UNIT-103", "M. Corvale", "2029-11-20", 30_000, 8_000, 22_000, STATUS_UNIT_CLOSED, STATE_ACTIVE),
    ("DEP-1004", "UNIT-104", "T. Marbeck", "2029-12-08", 18_000, 3_000, 15_000, STATUS_ALREADY_POSTED, STATE_CANCELLED),
    ("DEP-1005", "UNIT-105", "S. Hadrell", "2030-01-30", 22_500, 2_500, 20_000, STATUS_ALREADY_POSTED, STATE_ACTIVE),
    ("DEP-1006", "UNIT-101", "A. Fenholt", "2030-03-05", 10_000, 0, 10_000, STATUS_NEED_TO_POST, STATE_ACTIVE),
    ("DEP-1007", "UNIT-106", "L. Tessing", "2030-02-14", 12_000, 2_000, 10_000, STATUS_NEED_TO_POST, STATE_CANCELLED),
)

#: ``(unit_id, agent_deposit)`` -- the escrow agent's open-escrow record, in
#: dollars. Only pre-close units appear: UNIT-103 closed and UNIT-104/106
#: cancelled, so the agent no longer holds their money.
AGENT_ENTRIES: tuple[tuple[str, int], ...] = (
    ("UNIT-101", 30_000),
    ("UNIT-102", 15_000),
    ("UNIT-105", 20_000),
)

#: ``(paydown_id, deposit_id, unit_id, payment_date, kind, principal)``.
#: Amounts in dollars. DEP-1004's paydown carries its reversal beside it, so
#: the cancelled buyer's unit nets to zero on the loan leg.
MOVEMENTS: tuple[tuple[Any, ...], ...] = (
    ("PDN-2001", "DEP-1001", "UNIT-101", "2030-01-20", KIND_PAYDOWN, 20_000),
    ("PDN-2002", "DEP-1003", "UNIT-103", "2029-11-28", KIND_PAYDOWN, 22_000),
    ("PDN-2003", "DEP-1004", "UNIT-104", "2029-12-15", KIND_PAYDOWN, 15_000),
    ("PDN-2004", "DEP-1004", "UNIT-104", "2030-02-10", KIND_REVERSAL, 15_000),
    ("PDN-2005", "DEP-1005", "UNIT-105", "2030-02-06", KIND_PAYDOWN, 20_000),
)

#: ``(cancellation_id, deposit_id, termination_fee, refund)``. Amounts in
#: dollars; every fee books to the forfeitures account. Each split sums back
#: to the cancelled deposit's earnest money.
CANCELLATIONS: tuple[tuple[Any, ...], ...] = (
    ("CXL-3001", "DEP-1004", 5_000, 10_000),
    ("CXL-3002", "DEP-1007", 2_500, 7_500),
)

#: ``(unit_id, list_price, sales_price, concession)``. Dollars; concessions
#: are non-positive. The net sale price is derived, never typed.
SALES: tuple[tuple[Any, ...], ...] = (
    ("UNIT-101", 500_000, 495_000, -5_000),
    ("UNIT-102", 450_000, 450_000, 0),
    ("UNIT-103", 520_000, 515_000, -2_500),
    ("UNIT-104", 480_000, 480_000, 0),
    ("UNIT-105", 610_000, 605_000, -10_000),
    ("UNIT-106", 430_000, 430_000, 0),
)


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _deposit(payload: dict[str, Any], deposit_id: str) -> dict[str, Any]:
    ledger = _doc(payload, DOC_DEPOSIT_LEDGER)
    assert ledger is not None
    for row in ledger["deposits"]:
        if row.get("deposit_id") == deposit_id:
            return row
    raise KeyError(deposit_id)


def _agent_entry(payload: dict[str, Any], unit_id: str) -> dict[str, Any]:
    statement = _doc(payload, DOC_ESCROW_STATEMENT)
    assert statement is not None
    for row in statement["entries"]:
        if row.get("unit_id") == unit_id:
            return row
    raise KeyError(unit_id)


def _movement(payload: dict[str, Any], paydown_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_PAYDOWN_REGISTER)
    assert register is not None
    for row in register["movements"]:
        if row.get("paydown_id") == paydown_id:
            return row
    raise KeyError(paydown_id)


def _cancellation(payload: dict[str, Any], cancellation_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_CANCELLATION_REGISTER)
    assert register is not None
    for row in register["cancellations"]:
        if row.get("cancellation_id") == cancellation_id:
            return row
    raise KeyError(cancellation_id)


def _sales_row(payload: dict[str, Any], unit_id: str) -> dict[str, Any]:
    matrix = _doc(payload, DOC_SALES_MATRIX)
    assert matrix is not None
    for row in matrix["units"]:
        if row.get("unit_id") == unit_id:
            return row
    raise KeyError(unit_id)


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = _doc(payload, DOC_RECON_SUMMARY)
    assert summary is not None
    return summary


def _summary_unit(payload: dict[str, Any], unit_id: str) -> dict[str, Any]:
    for row in _summary(payload)["units"]:
        if row.get("unit_id") == unit_id:
            return row
    raise KeyError(unit_id)


def _trust(payload: dict[str, Any]) -> dict[str, Any]:
    trust = _doc(payload, DOC_TRUST_BALANCES)
    assert trust is not None
    return trust


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def rederive(payload: dict[str, Any]) -> None:
    """Recompute every stated determination from the payload's own base facts."""
    ledger = _doc(payload, DOC_DEPOSIT_LEDGER)
    statement = _doc(payload, DOC_ESCROW_STATEMENT)
    register = _doc(payload, DOC_PAYDOWN_REGISTER)
    cancellations = _doc(payload, DOC_CANCELLATION_REGISTER)
    trust = _doc(payload, DOC_TRUST_BALANCES)
    matrix = _doc(payload, DOC_SALES_MATRIX)
    summary = _doc(payload, DOC_RECON_SUMMARY)
    if not all((ledger, statement, register, cancellations, trust, matrix, summary)):
        return
    assert trust is not None and matrix is not None and summary is not None

    ctx = Context(path=Path("<generated>"), data=payload)

    # Sales matrix: the net sale price is derived through the shared kernel.
    for row in matrix["units"]:
        row["net_sale_cents"] = net_sale(row["sales_price_cents"], row["concession_cents"])

    # Trust balances: the upgrade bank and forfeiture income, recomputed
    # through the same functions the engine ties them with.
    trust["upgrade_bank_balance_cents"] = recompute_upgrade_bank(ctx)
    trust["forfeiture_income_cents"] = recompute_forfeiture_income(ctx)

    # Reconciliation summary: one row per unit either side names, plus the
    # footed total and the posting-bucket totals.
    units = recompute_recon_units(ctx)
    summary["units"] = units
    summary["total_variance_cents"] = sum(r["variance_cents"] for r in units)
    buckets = recompute_bucket_totals(ctx)
    summary["bucket_totals"] = {
        f"{bucket}_cents": buckets[bucket] for bucket in STATUS_BUCKETS
    }


def baseline(portfolio: str) -> dict[str, Any]:
    """Build a clean deposit file for ``portfolio``."""
    payload: dict[str, Any] = {
        "file_id": "clean",
        "portfolio": portfolio,
        "project": PROJECT,
        "jurisdiction": JURISDICTION,
        "period": PERIOD,
        "as_of": AS_OF,
        "documents": [
            {
                "doc_type": DOC_DEPOSIT_LEDGER,
                "document_id": "LEDGER-2030",
                "deposits": [
                    {
                        "deposit_id": deposit_id,
                        "unit_id": unit_id,
                        "buyer": buyer,
                        "receipt_date": receipt_date,
                        "amount_cents": d(amount),
                        "upgrade_cents": d(upgrade),
                        "em_cents": d(em),
                        "status": status,
                        "state": state,
                    }
                    for (
                        deposit_id, unit_id, buyer, receipt_date, amount, upgrade,
                        em, status, state,
                    ) in DEPOSITS
                ],
            },
            {
                "doc_type": DOC_ESCROW_STATEMENT,
                "document_id": "AGENT-2030",
                "escrow_agent": ESCROW_AGENT,
                "entries": [
                    {"unit_id": unit_id, "agent_deposit_cents": d(amount)}
                    for unit_id, amount in AGENT_ENTRIES
                ],
            },
            {
                "doc_type": DOC_PAYDOWN_REGISTER,
                "document_id": "LOAN-2030",
                "lender": LENDER,
                "movements": [
                    {
                        "paydown_id": paydown_id,
                        "deposit_id": deposit_id,
                        "unit_id": unit_id,
                        "payment_date": payment_date,
                        "kind": kind,
                        "principal_cents": d(principal),
                    }
                    for (
                        paydown_id, deposit_id, unit_id, payment_date, kind, principal,
                    ) in MOVEMENTS
                ],
            },
            {
                "doc_type": DOC_CANCELLATION_REGISTER,
                "document_id": "CXL-2030",
                "cancellations": [
                    {
                        "cancellation_id": cancellation_id,
                        "deposit_id": deposit_id,
                        "termination_fee_cents": d(fee),
                        "refund_cents": d(refund),
                        "fee_account": FORFEITURE_ACCOUNT,
                    }
                    for cancellation_id, deposit_id, fee, refund in CANCELLATIONS
                ],
            },
            {
                "doc_type": DOC_TRUST_BALANCES,
                "document_id": "TRUST-2030",
                "bank_account": f"Cash - Upgrade Deposits ({LENDER})",
                "upgrade_bank_balance_cents": 0,
                "forfeiture_income_cents": 0,
            },
            {
                "doc_type": DOC_SALES_MATRIX,
                "document_id": "SALES-2030",
                "units": [
                    {
                        "unit_id": unit_id,
                        "list_price_cents": d(list_price),
                        "sales_price_cents": d(sales_price),
                        "concession_cents": d(concession),
                        "net_sale_cents": 0,
                        "concession_account": CONCESSION_REVENUE_ACCOUNT,
                    }
                    for unit_id, list_price, sales_price, concession in SALES
                ],
            },
            {
                "doc_type": DOC_RECON_SUMMARY,
                "document_id": "RECON-2030",
                "units": [],
                "total_variance_cents": 0,
                "bucket_totals": {},
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
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_RECON_SUMMARY
    ]


def _duplicate_deposit_id(payload: dict[str, Any]) -> None:
    # The duplicate is an exact copy, so first-wins deduplication keeps every
    # recomputed sum unchanged and only the uniqueness control sees the break.
    ledger = _doc(payload, DOC_DEPOSIT_LEDGER)
    assert ledger is not None
    ledger["deposits"].append(dict(_deposit(payload, "DEP-1001")))


def _deposit_missing_field(payload: dict[str, Any]) -> None:
    del _deposit(payload, "DEP-1002")["receipt_date"]


def _amount_split_broken(payload: dict[str, Any]) -> None:
    # The cash amount no longer equals upgrade + earnest money; the components
    # themselves are untouched, so every recomputed sum still stands.
    _deposit(payload, "DEP-1001")["amount_cents"] += d(1_000)


def _negative_component(payload: dict[str, Any]) -> None:
    # A negative upgrade component "balancing" a padded earnest-money figure:
    # the split still sums, which is exactly why the sign control must exist.
    # The agent's record moves with the padded figure and the rollup is
    # re-derived, so only the sign control sees the break.
    deposit = _deposit(payload, "DEP-1006")
    deposit["upgrade_cents"] = d(-2_000)
    deposit["em_cents"] = d(12_000)
    _agent_entry(payload, "UNIT-101")["agent_deposit_cents"] = d(32_000)
    rederive(payload)


def _agent_ledger_variance(payload: dict[str, Any]) -> None:
    # The agent holds less than the books support -- an over-release. The
    # summary is re-derived so it honestly reports the variance and only the
    # tie-out control fails.
    _agent_entry(payload, "UNIT-105")["agent_deposit_cents"] = d(19_000)
    rederive(payload)


def _agent_unknown_unit(payload: dict[str, Any]) -> None:
    # The agent holds money for a unit our ledger has never heard of: the
    # classic completeness gap.
    statement = _doc(payload, DOC_ESCROW_STATEMENT)
    assert statement is not None
    statement["entries"].append({"unit_id": "UNIT-999", "agent_deposit_cents": d(5_000)})
    rederive(payload)


def _agent_missing_unit(payload: dict[str, Any]) -> None:
    # The booked deposit for UNIT-102 is gone from the agent's statement: the
    # funds have left escrow on paper only.
    statement = _doc(payload, DOC_ESCROW_STATEMENT)
    assert statement is not None
    statement["entries"] = [
        e for e in statement["entries"] if e.get("unit_id") != "UNIT-102"
    ]
    rederive(payload)


def _paydown_leg_short(payload: dict[str, Any]) -> None:
    # The sweep exists and pairs correctly, but the principal is a thousand
    # short of the earnest money it applied.
    _movement(payload, "PDN-2005")["principal_cents"] = d(19_000)


def _sweep_missing(payload: dict[str, Any]) -> None:
    # DEP-1001 is marked posted but its paydown row is gone.
    register = _doc(payload, DOC_PAYDOWN_REGISTER)
    assert register is not None
    register["movements"] = [
        m for m in register["movements"] if m.get("paydown_id") != "PDN-2001"
    ]


def _orphan_paydown(payload: dict[str, Any]) -> None:
    # Principal moved with no receipt behind it.
    register = _doc(payload, DOC_PAYDOWN_REGISTER)
    assert register is not None
    register["movements"].append(
        {
            "paydown_id": "PDN-2999",
            "deposit_id": "DEP-9999",
            "unit_id": "UNIT-105",
            "payment_date": "2030-03-12",
            "kind": KIND_PAYDOWN,
            "principal_cents": d(5_000),
        }
    )


def _premature_sweep(payload: dict[str, Any]) -> None:
    # DEP-1002 is still queued need-to-post, yet the loan already carries its
    # paydown -- the next posting run would sweep the same money twice.
    register = _doc(payload, DOC_PAYDOWN_REGISTER)
    assert register is not None
    register["movements"].append(
        {
            "paydown_id": "PDN-2006",
            "deposit_id": "DEP-1002",
            "unit_id": "UNIT-102",
            "payment_date": "2030-03-15",
            "kind": KIND_PAYDOWN,
            "principal_cents": d(15_000),
        }
    )


def _cancellation_orphan(payload: dict[str, Any]) -> None:
    # A forfeiture split for a deposit that was never receipted. The zero
    # amounts keep every recomputed income figure standing, so only the join
    # control sees the break.
    register = _doc(payload, DOC_CANCELLATION_REGISTER)
    assert register is not None
    register["cancellations"].append(
        {
            "cancellation_id": "CXL-3999",
            "deposit_id": "DEP-8888",
            "termination_fee_cents": 0,
            "refund_cents": 0,
            "fee_account": FORFEITURE_ACCOUNT,
        }
    )


def _forfeiture_split_broken(payload: dict[str, Any]) -> None:
    # The retained fee grew without the refund shrinking; the split no longer
    # accounts for the deposit. The trust rollup is re-derived so only the
    # split gate fails.
    _cancellation(payload, "CXL-3001")["termination_fee_cents"] = d(6_000)
    rederive(payload)


def _reversal_missing(payload: dict[str, Any]) -> None:
    # The cancelled buyer's paydown was never unwound; the loan still carries
    # principal funded by money that was refunded and forfeited.
    register = _doc(payload, DOC_PAYDOWN_REGISTER)
    assert register is not None
    register["movements"] = [
        m for m in register["movements"] if m.get("paydown_id") != "PDN-2004"
    ]


def _fee_account_wrong(payload: dict[str, Any]) -> None:
    _cancellation(payload, "CXL-3001")["fee_account"] = "5010 Construction Cost of Sales"


def _bad_status_bucket(payload: dict[str, Any]) -> None:
    # An unknown bucket cannot be placed on any side of the reconciliation.
    # The rollup is re-derived (the kernel excludes the unclassifiable row),
    # so only the bucket control fires.
    _deposit(payload, "DEP-1002")["status"] = "pending"
    rederive(payload)


def _closed_unit_on_agent(payload: dict[str, Any]) -> None:
    # UNIT-103 closed months ago, yet the agent's open-escrow statement still
    # lists its money. The summary is re-derived, so it honestly carries the
    # resulting variance and only the staleness FLAG remains.
    statement = _doc(payload, DOC_ESCROW_STATEMENT)
    assert statement is not None
    statement["entries"].append({"unit_id": "UNIT-103", "agent_deposit_cents": d(22_000)})
    rederive(payload)


def _upgrade_bank_short(payload: dict[str, Any]) -> None:
    _trust(payload)["upgrade_bank_balance_cents"] -= d(1_000)


def _forfeiture_income_wrong(payload: dict[str, Any]) -> None:
    _trust(payload)["forfeiture_income_cents"] += d(500)


def _net_sale_wrong(payload: dict[str, Any]) -> None:
    _sales_row(payload, "UNIT-105")["net_sale_cents"] += d(1_000)


def _concession_positive(payload: dict[str, Any]) -> None:
    # The concession flipped sign, raising the net sale price. The identity is
    # kept so only the sign control sees the break.
    row = _sales_row(payload, "UNIT-102")
    row["concession_cents"] = d(2_000)
    row["net_sale_cents"] = net_sale(row["sales_price_cents"], row["concession_cents"])


def _concession_misbooked(payload: dict[str, Any]) -> None:
    _sales_row(payload, "UNIT-101")["concession_account"] = "5010 Construction Cost of Sales"


def _summary_variance_wrong(payload: dict[str, Any]) -> None:
    _summary_unit(payload, "UNIT-105")["variance_cents"] = d(1_000)


def _exception_flag_wrong(payload: dict[str, Any]) -> None:
    _summary_unit(payload, "UNIT-101")["exception_flag"] = True


def _total_variance_wrong(payload: dict[str, Any]) -> None:
    _summary(payload)["total_variance_cents"] = d(4_200)


def _bucket_totals_wrong(payload: dict[str, Any]) -> None:
    _summary(payload)["bucket_totals"]["need_to_post_cents"] += d(1_000)


def _amount_not_integer(payload: dict[str, Any]) -> None:
    entry = _agent_entry(payload, "UNIT-101")
    entry["agent_deposit_cents"] = float(entry["agent_deposit_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "duplicate_deposit_id": ("led_unique_ids", _duplicate_deposit_id),
    "deposit_missing_field": ("led_required_fields", _deposit_missing_field),
    "amount_split_broken": ("seg_amount_splits", _amount_split_broken),
    "negative_component": ("seg_components_nonnegative", _negative_component),
    "agent_ledger_variance": ("tie_agent_variance_zero", _agent_ledger_variance),
    "agent_unknown_unit": ("tie_agent_completeness", _agent_unknown_unit),
    "agent_missing_unit": ("tie_ledger_completeness", _agent_missing_unit),
    "paydown_leg_short": ("tie_loan_leg_zero", _paydown_leg_short),
    "sweep_missing": ("swp_posted_has_paydown", _sweep_missing),
    "orphan_paydown": ("swp_paydown_has_deposit", _orphan_paydown),
    "premature_sweep": ("swp_need_to_post_not_swept", _premature_sweep),
    "cancellation_orphan": ("cxl_row_joins", _cancellation_orphan),
    "forfeiture_split_broken": ("cxl_split_sums", _forfeiture_split_broken),
    "reversal_missing": ("cxl_reversal_matches_sweep", _reversal_missing),
    "fee_account_wrong": ("cxl_fee_account", _fee_account_wrong),
    "bad_status_bucket": ("sts_valid_bucket", _bad_status_bucket),
    "closed_unit_on_agent": ("sts_closed_excluded_from_agent", _closed_unit_on_agent),
    "upgrade_bank_short": ("bnk_upgrade_bank_ties", _upgrade_bank_short),
    "forfeiture_income_wrong": ("bnk_forfeiture_income_ties", _forfeiture_income_wrong),
    "net_sale_wrong": ("net_sale_recomputes", _net_sale_wrong),
    "concession_positive": ("net_concession_sign", _concession_positive),
    "concession_misbooked": ("net_concession_account", _concession_misbooked),
    "summary_variance_wrong": ("rpt_unit_variance_recomputes", _summary_variance_wrong),
    "exception_flag_wrong": ("rpt_exception_flags_tie", _exception_flag_wrong),
    "total_variance_wrong": ("rpt_total_variance_ties", _total_variance_wrong),
    "bucket_totals_wrong": ("rpt_bucket_totals_tie", _bucket_totals_wrong),
    "amount_not_integer": ("tie_agent_variance_zero", _amount_not_integer),
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
