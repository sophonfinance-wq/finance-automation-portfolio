"""
Fictional G&A expense allocation corpus generator.
==================================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The holding entity, the operating entities, the
projects, the GL accounts, the driver counts, the cost pools and the postage
meter readings are fictional, and the fiscal year is set in a fictional future.
No real entity, person, project, account or path appears anywhere. The generator
is deterministic and takes no seed.

The baseline is derived, not typed
----------------------------------
Only the month calendar, the recipient lookup, the driver counts, the two
discretionary pool components and the postage meter readings are stated as base
facts. Everything the engine later checks as a derivation -- each recipient's
share in basis points, each allocated amount, the per-code postage split, the
pool's postage component and total, the journal entry, the year-to-date rollup --
is recomputed by :func:`rederive` from those base facts, through the *same*
:mod:`gaalloc_engine.allocation` kernel the engine re-derives with. So the
relationships the engine tests are the relationships that produced the data: a
defect that changes a base fact re-derives everything below it and keeps the
break confined to one control; a defect that targets a derived figure edits that
figure alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .engine import (
    _periods,
    _recipient_ids,
    recompute_allocation,
    recompute_journal,
    recompute_postage_codes,
    recompute_rollup,
    recompute_shares,
)
from .model import (
    DEFAULT_VARIANCE_FLAG_BPS,
    DOC_ALLOCATION_JOURNAL,
    DOC_ALLOCATION_REPORT,
    DOC_ALLOCATION_SCHEDULE,
    DOC_COST_POOL_LEDGER,
    DOC_DRIVER_TABLE,
    DOC_PERIOD_CALENDAR,
    DOC_POSTAGE_LOG,
    DOC_RECIPIENT_REGISTER,
    RECIPIENT_OPERATING_ENTITY,
    RECIPIENT_PROJECT,
    Context,
)

#: Fictional group labels, rotated for file identity only.
PORTFOLIOS: tuple[str, ...] = (
    "Northmoor Development Group",
    "Halbrook Residential Partners",
    "Stonecrest Communities",
    "Ardenne Field Group",
)

FISCAL_YEAR = "FY2031"
#: The month the workbook opens on.
FIRST_PERIOD = "2031-01"
#: The management/holding entity whose G&A is pushed out every month.
HOLDING_ENTITY_ID = "HOLD-1"
HOLDING_ENTITY_NAME = "Westmere Holdings"
#: The account the holding entity's relief is credited to.
HOLDING_CREDIT_ACCOUNT = "8910"
#: Month-over-month band, in basis points, above which a pool step is flagged.
VARIANCE_FLAG_BPS = DEFAULT_VARIANCE_FLAG_BPS

#: ``(period, accounting_date)``. Six month tabs, each stamped to its month end.
CALENDAR: tuple[tuple[str, str], ...] = (
    ("2031-01", "2031-01-31"),
    ("2031-02", "2031-02-28"),
    ("2031-03", "2031-03-31"),
    ("2031-04", "2031-04-30"),
    ("2031-05", "2031-05-31"),
    ("2031-06", "2031-06-30"),
)

#: ``(recipient_id, name, kind, gl_account)``. Fictional operating entities and
#: projects; the entities carry the corporate G&A account, the projects the
#: project-overhead one.
RECIPIENTS: tuple[tuple[str, ...], ...] = (
    ("ENT-201", "Northmoor Development Group", RECIPIENT_OPERATING_ENTITY, "7100"),
    ("ENT-202", "Halbrook Residential Partners", RECIPIENT_OPERATING_ENTITY, "7100"),
    ("ENT-203", "Stonecrest Communities", RECIPIENT_OPERATING_ENTITY, "7100"),
    ("ENT-204", "Ardenne Field Group", RECIPIENT_OPERATING_ENTITY, "7100"),
    ("PRJ-301", "Brightwater Commons", RECIPIENT_PROJECT, "7150"),
    ("PRJ-302", "Copperfield Yards", RECIPIENT_PROJECT, "7150"),
)

#: Driver counts (headcount-equivalents) per period, in recipient order. The
#: totals are deliberately not round, so every month's share column lands on a
#: fractional basis point and the largest-remainder split is exercised rather
#: than skirted.
DRIVER_COUNTS: dict[str, tuple[int, ...]] = {
    "2031-01": (42, 31, 27, 18, 9, 6),
    "2031-02": (43, 31, 27, 18, 9, 7),
    "2031-03": (44, 32, 26, 19, 10, 7),
    "2031-04": (44, 33, 26, 19, 10, 8),
    "2031-05": (45, 33, 27, 20, 10, 8),
    "2031-06": (46, 34, 27, 20, 11, 8),
}

#: ``period -> (shared_overhead_cents, corporate_ga_cents)``. The third component,
#: postage, is not stated: it is read off the meter by :func:`rederive`.
POOL_COMPONENTS: dict[str, tuple[int, int]] = {
    "2031-01": (18_450_000, 9_625_000),
    "2031-02": (18_690_000, 9_540_000),
    "2031-03": (18_930_000, 9_710_000),
    "2031-04": (18_775_000, 9_860_000),
    "2031-05": (19_120_000, 9_785_000),
    "2031-06": (19_360_000, 9_930_000),
}

#: ``period -> (begin_meter_cents, end_meter_cents)``. A cumulative counter: each
#: month opens exactly where the last one closed.
METER_READINGS: dict[str, tuple[int, int]] = {
    "2031-01": (1_250_000, 1_298_450),
    "2031-02": (1_298_450, 1_349_725),
    "2031-03": (1_349_725, 1_396_545),
    "2031-04": (1_396_545, 1_449_685),
    "2031-05": (1_449_685, 1_499_900),
    "2031-06": (1_499_900, 1_551_880),
}


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _require(payload: dict[str, Any], doc_type: str) -> dict[str, Any]:
    doc = _doc(payload, doc_type)
    assert doc is not None
    return doc


def _calendar_row(payload: dict[str, Any], period: str) -> dict[str, Any]:
    for row in _require(payload, DOC_PERIOD_CALENDAR)["periods"]:
        if row.get("period") == period:
            return row
    raise KeyError(period)


def _recipient(payload: dict[str, Any], recipient_id: str) -> dict[str, Any]:
    for row in _require(payload, DOC_RECIPIENT_REGISTER)["recipients"]:
        if row.get("recipient_id") == recipient_id:
            return row
    raise KeyError(recipient_id)


def _driver(payload: dict[str, Any], period: str, recipient_id: str) -> dict[str, Any]:
    for row in _require(payload, DOC_DRIVER_TABLE)["drivers"]:
        if row.get("period") == period and row.get("recipient_id") == recipient_id:
            return row
    raise KeyError((period, recipient_id))


def _pool(payload: dict[str, Any], period: str) -> dict[str, Any]:
    for row in _require(payload, DOC_COST_POOL_LEDGER)["pools"]:
        if row.get("period") == period:
            return row
    raise KeyError(period)


def _allocation(payload: dict[str, Any], period: str, recipient_id: str) -> dict[str, Any]:
    for row in _require(payload, DOC_ALLOCATION_SCHEDULE)["allocations"]:
        if row.get("period") == period and row.get("recipient_id") == recipient_id:
            return row
    raise KeyError((period, recipient_id))


def _entry(payload: dict[str, Any], period: str) -> dict[str, Any]:
    for row in _require(payload, DOC_ALLOCATION_JOURNAL)["entries"]:
        if row.get("period") == period:
            return row
    raise KeyError(period)


def _entry_line(payload: dict[str, Any], period: str, entity_id: str) -> dict[str, Any]:
    for line in _entry(payload, period)["lines"]:
        if line.get("entity_id") == entity_id:
            return line
    raise KeyError((period, entity_id))


def _meter(payload: dict[str, Any], period: str) -> dict[str, Any]:
    for row in _require(payload, DOC_POSTAGE_LOG)["meters"]:
        if row.get("period") == period:
            return row
    raise KeyError(period)


def _report(payload: dict[str, Any]) -> dict[str, Any]:
    return _require(payload, DOC_ALLOCATION_REPORT)


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def rederive(payload: dict[str, Any]) -> None:
    """Recompute every derived figure from the payload's own base facts.

    The order matters and mirrors the workbook: the meter sets the postage
    component, the components set the pool total, the drivers set the shares, the
    shares and the pool set the amounts, the amounts set the entry, and the entry
    year sets the rollup.
    """
    needed = (
        DOC_PERIOD_CALENDAR,
        DOC_RECIPIENT_REGISTER,
        DOC_DRIVER_TABLE,
        DOC_COST_POOL_LEDGER,
        DOC_ALLOCATION_SCHEDULE,
        DOC_ALLOCATION_JOURNAL,
        DOC_POSTAGE_LOG,
        DOC_ALLOCATION_REPORT,
    )
    if any(_doc(payload, doc_type) is None for doc_type in needed):
        return

    ctx = Context(path=Path("<generated>"), data=payload)
    periods = _periods(ctx)

    # 1. Postage: the meter delta, split by policy weight, and the pool component
    #    it sets.
    for period in periods:
        codes = recompute_postage_codes(ctx, period)
        if codes is None:
            continue
        _meter(payload, period)["allocations"] = codes
        _pool(payload, period)["postage_cents"] = sum(row["amount_cents"] for row in codes)

    # 2. Cost pool: the total the allocation divides is the sum of its components.
    for period in periods:
        pool = _pool(payload, period)
        pool["pool_total_cents"] = (
            pool["shared_overhead_cents"] + pool["corporate_ga_cents"] + pool["postage_cents"]
        )

    # 3. Allocation schedule: driver shares, then pool x share by largest remainder.
    schedule = _require(payload, DOC_ALLOCATION_SCHEDULE)
    rows: list[dict[str, Any]] = []
    for period in periods:
        shares = recompute_shares(ctx, period)
        amounts = recompute_allocation(ctx, period)
        for recipient_id in _recipient_ids(ctx):
            rows.append(
                {
                    "period": period,
                    "recipient_id": recipient_id,
                    "share_bps": shares.get(recipient_id, 0),
                    "allocated_cents": amounts.get(recipient_id, 0),
                }
            )
    schedule["allocations"] = rows

    # 4. Journal: one debit per recipient, one credit relieving the holding entity.
    journal = _require(payload, DOC_ALLOCATION_JOURNAL)
    entries: list[dict[str, Any]] = []
    for period in periods:
        entry = recompute_journal(ctx, period)
        if entry is not None:
            entries.append(entry)
    journal["entries"] = entries

    # 5. Rollup: the year-to-date figures the close package reads.
    rollup = recompute_rollup(ctx)
    report = _report(payload)
    report["period_count"] = rollup.period_count
    report["recipient_count"] = rollup.recipient_count
    report["pool_total_cents"] = rollup.pool_total_cents
    report["allocated_total_cents"] = rollup.allocated_total_cents


def baseline(portfolio: str) -> dict[str, Any]:
    """Build a clean allocation file for ``portfolio``."""
    payload: dict[str, Any] = {
        "file_id": "clean",
        "portfolio": portfolio,
        "fiscal_year": FISCAL_YEAR,
        "first_period": FIRST_PERIOD,
        "holding_entity_id": HOLDING_ENTITY_ID,
        "holding_entity_name": HOLDING_ENTITY_NAME,
        "holding_credit_account": HOLDING_CREDIT_ACCOUNT,
        "variance_flag_bps": VARIANCE_FLAG_BPS,
        "documents": [
            {
                "doc_type": DOC_PERIOD_CALENDAR,
                "document_id": "CALENDAR-2031",
                "periods": [
                    {"period": period, "accounting_date": accounting_date}
                    for period, accounting_date in CALENDAR
                ],
            },
            {
                "doc_type": DOC_RECIPIENT_REGISTER,
                "document_id": "LOOKUP-2031",
                "recipients": [
                    {
                        "recipient_id": recipient_id,
                        "name": name,
                        "kind": kind,
                        "gl_account": gl_account,
                    }
                    for recipient_id, name, kind, gl_account in RECIPIENTS
                ],
            },
            {
                "doc_type": DOC_DRIVER_TABLE,
                "document_id": "DRIVERS-2031",
                "driver_basis": "headcount_equivalent",
                "drivers": [
                    {
                        "period": period,
                        "recipient_id": RECIPIENTS[i][0],
                        "driver_count": count,
                    }
                    for period, _accounting_date in CALENDAR
                    for i, count in enumerate(DRIVER_COUNTS[period])
                ],
            },
            {
                "doc_type": DOC_COST_POOL_LEDGER,
                "document_id": "POOL-2031",
                "pools": [
                    {
                        "period": period,
                        "shared_overhead_cents": POOL_COMPONENTS[period][0],
                        "corporate_ga_cents": POOL_COMPONENTS[period][1],
                        "postage_cents": 0,
                        "pool_total_cents": 0,
                    }
                    for period, _accounting_date in CALENDAR
                ],
            },
            {
                "doc_type": DOC_ALLOCATION_SCHEDULE,
                "document_id": "SCHEDULE-2031",
                "allocations": [],
            },
            {
                "doc_type": DOC_ALLOCATION_JOURNAL,
                "document_id": "JOURNAL-2031",
                "entries": [],
            },
            {
                "doc_type": DOC_POSTAGE_LOG,
                "document_id": "POSTAGE-2031",
                "meters": [
                    {
                        "period": period,
                        "begin_meter_cents": METER_READINGS[period][0],
                        "end_meter_cents": METER_READINGS[period][1],
                        "allocations": [],
                    }
                    for period, _accounting_date in CALENDAR
                ],
            },
            {
                "doc_type": DOC_ALLOCATION_REPORT,
                "document_id": "ROLLUP-2031",
                "period_count": 0,
                "recipient_count": 0,
                "pool_total_cents": 0,
                "allocated_total_cents": 0,
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
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_ALLOCATION_REPORT
    ]


def _relabel_period(payload: dict[str, Any], old: str, new: str, accounting_date: str) -> None:
    """Move every artifact for ``old`` onto ``new``, restamping the date with it."""
    row = _calendar_row(payload, old)
    row["period"] = new
    row["accounting_date"] = accounting_date
    for doc_type, key in (
        (DOC_DRIVER_TABLE, "drivers"),
        (DOC_COST_POOL_LEDGER, "pools"),
        (DOC_ALLOCATION_SCHEDULE, "allocations"),
        (DOC_POSTAGE_LOG, "meters"),
    ):
        for record in _require(payload, doc_type)[key]:
            if record.get("period") == old:
                record["period"] = new
    for entry in _require(payload, DOC_ALLOCATION_JOURNAL)["entries"]:
        if entry.get("period") == old:
            entry["period"] = new
            entry["je_no"] = f"GA-{new}"
            entry["accounting_date"] = accounting_date


def _period_gap(payload: dict[str, Any]) -> None:
    # The closing tab was rolled a month too far: the year runs to July with June
    # never allocated. Every artifact moves with the tab, so only the sequence
    # control sees it.
    _relabel_period(payload, "2031-06", "2031-07", "2031-07-31")


def _missing_period_tab(payload: dict[str, Any]) -> None:
    log = _require(payload, DOC_POSTAGE_LOG)
    log["meters"] = [row for row in log["meters"] if row.get("period") != "2031-05"]


def _duplicate_recipient_id(payload: dict[str, Any]) -> None:
    register = _require(payload, DOC_RECIPIENT_REGISTER)
    register["recipients"].append(dict(_recipient(payload, "ENT-203")))


def _bad_recipient_kind(payload: dict[str, Any]) -> None:
    _recipient(payload, "PRJ-302")["kind"] = "department"


def _holding_as_recipient(payload: dict[str, Any]) -> None:
    register = _require(payload, DOC_RECIPIENT_REGISTER)
    register["recipients"].append(
        {
            "recipient_id": HOLDING_ENTITY_ID,
            "name": HOLDING_ENTITY_NAME,
            "kind": RECIPIENT_OPERATING_ENTITY,
            "gl_account": "7100",
        }
    )


def _negative_driver_count(payload: dict[str, Any]) -> None:
    # A reversal was entered into a basis column; the share it would produce takes
    # cost off a recipient rather than putting it on.
    _driver(payload, "2031-03", "ENT-204")["driver_count"] = -19


def _driver_row_missing(payload: dict[str, Any]) -> None:
    table = _require(payload, DOC_DRIVER_TABLE)
    table["drivers"] = [
        row
        for row in table["drivers"]
        if not (row.get("period") == "2031-02" and row.get("recipient_id") == "PRJ-301")
    ]


def _pool_components_drift(payload: dict[str, Any]) -> None:
    # The overhead component is restated without the total beside it moving, so
    # the figure under review and the figure being allocated part company.
    _pool(payload, "2031-04")["shared_overhead_cents"] += 30_000


def _pool_step_change(payload: dict[str, Any]) -> None:
    # A real step in the group's cost base. Everything below it is re-derived, so
    # only the review flag remains.
    _pool(payload, "2031-04")["shared_overhead_cents"] += 4_000_000
    rederive(payload)


def _allocation_row_missing(payload: dict[str, Any]) -> None:
    schedule = _require(payload, DOC_ALLOCATION_SCHEDULE)
    schedule["allocations"] = [
        row
        for row in schedule["allocations"]
        if not (row.get("period") == "2031-02" and row.get("recipient_id") == "PRJ-302")
    ]


def _shares_overstated(payload: dict[str, Any]) -> None:
    # One share is typed over and nothing offsets it, so the column sums past
    # 100.00% and the month over-relieves the holding entity.
    _allocation(payload, "2031-01", "ENT-201")["share_bps"] += 25


def _share_drift(payload: dict[str, Any]) -> None:
    # Two shares are moved against each other: the column still sums to exactly
    # 100.00%, and only re-deriving from the driver counts shows the split is not
    # the one the drivers support.
    _allocation(payload, "2031-01", "ENT-201")["share_bps"] += 25
    _allocation(payload, "2031-01", "ENT-202")["share_bps"] -= 25


def _allocation_over_pool(payload: dict[str, Any]) -> None:
    _allocation(payload, "2031-05", "ENT-202")["allocated_cents"] += 500_000


def _allocation_swapped(payload: dict[str, Any]) -> None:
    # Two recipients' amounts are transposed. The column still ties the pool to
    # the cent; only the per-recipient re-derivation shows the cost landed on the
    # wrong books.
    first = _allocation(payload, "2031-01", "ENT-201")
    second = _allocation(payload, "2031-01", "ENT-202")
    first["allocated_cents"], second["allocated_cents"] = (
        second["allocated_cents"],
        first["allocated_cents"],
    )


def _journal_unbalanced(payload: dict[str, Any]) -> None:
    # The credit side is overstated in one month and understated in another by the
    # same figure, so the year still nets to zero at consolidation while neither
    # entry balances on its own.
    _entry_line(payload, "2031-02", HOLDING_ENTITY_ID)["credit_cents"] += 500_000
    _entry_line(payload, "2031-05", HOLDING_ENTITY_ID)["credit_cents"] -= 500_000


def _journal_off_schedule(payload: dict[str, Any]) -> None:
    # One debit is retyped and the credit is moved with it, so the entry still
    # balances; only reading it against the re-derived allocation shows the drift.
    _entry_line(payload, "2031-03", "ENT-203")["debit_cents"] -= 300_000
    _entry_line(payload, "2031-03", HOLDING_ENTITY_ID)["credit_cents"] -= 300_000


def _journal_self_wash(payload: dict[str, Any]) -> None:
    # A gross-up pair on one entity: the entry balances, the recipient's net is
    # unchanged, and both sides of the entry are inflated by cost that never moved.
    _entry(payload, "2031-04")["lines"].extend(
        [
            {
                "entity_id": "ENT-202",
                "account": "1490",
                "debit_cents": 4_000_000,
                "credit_cents": 0,
            },
            {
                "entity_id": "ENT-202",
                "account": "1490",
                "debit_cents": 0,
                "credit_cents": 4_000_000,
            },
        ]
    )


def _meter_runs_backward(payload: dict[str, Any]) -> None:
    _meter(payload, "2031-03")["end_meter_cents"] = 1_320_000


def _postage_code_overstated(payload: dict[str, Any]) -> None:
    _meter(payload, "2031-02")["allocations"][1]["amount_cents"] += 1_500


def _postage_component_drift(payload: dict[str, Any]) -> None:
    # The postage line is restated and the corporate G&A line absorbs it, so the
    # pool total is untouched and only the meter shows the component is wrong.
    pool = _pool(payload, "2031-06")
    pool["postage_cents"] += 20_000
    pool["corporate_ga_cents"] -= 20_000


def _report_total_wrong(payload: dict[str, Any]) -> None:
    _report(payload)["pool_total_cents"] += 100_000


def _amount_not_integer(payload: dict[str, Any]) -> None:
    row = _allocation(payload, "2031-01", "ENT-203")
    row["allocated_cents"] = float(row["allocated_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "period_gap": ("per_months_consecutive", _period_gap),
    "missing_period_tab": ("per_tab_continuity", _missing_period_tab),
    "duplicate_recipient_id": ("rcp_unique_ids", _duplicate_recipient_id),
    "bad_recipient_kind": ("rcp_rows_wellformed", _bad_recipient_kind),
    "holding_as_recipient": ("rcp_holding_not_recipient", _holding_as_recipient),
    "negative_driver_count": ("drv_counts_whole", _negative_driver_count),
    "driver_row_missing": ("drv_coverage_complete", _driver_row_missing),
    "pool_components_drift": ("pol_components_sum", _pool_components_drift),
    "pool_step_change": ("pol_month_over_month_variance", _pool_step_change),
    "allocation_row_missing": ("alc_recipient_coverage", _allocation_row_missing),
    "shares_overstated": ("alc_shares_sum_to_full", _shares_overstated),
    "share_drift": ("alc_shares_rederive", _share_drift),
    "allocation_over_pool": ("alc_amounts_tie_pool", _allocation_over_pool),
    "allocation_swapped": ("alc_amounts_rederive", _allocation_swapped),
    "journal_unbalanced": ("je_balanced", _journal_unbalanced),
    "journal_off_schedule": ("je_ties_allocation", _journal_off_schedule),
    "journal_self_wash": ("je_consolidation_nets_zero", _journal_self_wash),
    "meter_runs_backward": ("pst_meter_rolls_forward", _meter_runs_backward),
    "postage_code_overstated": (
        "pst_allocations_tie_meter_delta",
        _postage_code_overstated,
    ),
    "postage_component_drift": ("pst_pool_component_ties", _postage_component_drift),
    "report_total_wrong": ("rpt_rollup_ties", _report_total_wrong),
    "amount_not_integer": ("alc_amounts_tie_pool", _amount_not_integer),
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
