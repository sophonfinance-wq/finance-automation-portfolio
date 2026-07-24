"""
Fictional equity-method consolidation corpus generator.
=======================================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The parents, the subsidiaries, the members, the
company codes, the ownership percentages and every balance are fictional, and
the fiscal period is set in a fictional future. No real entity, person, project
or path appears anywhere. The generator is deterministic and takes no seed.

The baseline is derived, not typed
----------------------------------
Only the entities, the holdings, the sub results, the roll-forward opening
facts and the preferred-return period facts are stated as base facts.
Everything the engine later checks as a determination -- each holding's pickup
and distribution share, the roll-forward ending value, the elimination blocks,
the member allocation, the accrual chain, the trial-balance investment and
pickup balances -- is recomputed by :func:`rederive` from those base facts,
through the *same* :mod:`pickup_engine.pickup` kernel the engine recomputes
with. So the relationships the engine tests are the relationships that
produced the data: a defect that changes a base fact re-derives the rollup and
keeps the break confined to one control; a defect that targets a stated figure
edits that figure alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from .engine import (
    _holding_id,
    _holdings,
    _rf_by_holding,
    _subsidiaries,
    equity_holder_shares,
)
from .model import (
    DOC_ALLOCATION_SUMMARY,
    DOC_ELIMINATION_SCHEDULE,
    DOC_ENTITY_REGISTER,
    DOC_HOLDING_REGISTER,
    DOC_INVESTMENT_ROLLFORWARD,
    DOC_PREFERRED_RETURN,
    DOC_SUB_RESULTS,
    DOC_TRIAL_BALANCE,
    METHOD_COST,
    METHOD_EQUITY,
    ROLE_PARENT,
    ROLE_SUBSIDIARY,
    Context,
)
from .money import BPS_FULL
from .pickup import inclusive_days, preferred_accrual, rollforward_end

#: Fictional reporting-group labels, rotated for file identity only.
GROUPS: tuple[str, ...] = (
    "Northmoor Consolidated Reporting Group",
    "Westmere Combined Reporting Group",
    "Stonecrest Reporting Group",
    "Ardenne Field Reporting Group",
)

#: Fictional-future fiscal year the whole corpus is set in (July-June).
PERIOD = "FY2030"

#: ``(entity_id, name, entity_code, role)``. Invented entities; the numeric
#: company code is the machine link key the GL accounts embed.
ENTITIES: tuple[tuple[str, str, str, str], ...] = (
    ("PAR-100", "Northmoor Development Group", "100", ROLE_PARENT),
    ("PAR-200", "Westmere Residential Holdings", "200", ROLE_PARENT),
    ("SUB-160", "Alderpoint Terraces LLC", "160", ROLE_SUBSIDIARY),
    ("SUB-285", "Brightwater Commons LLC", "285", ROLE_SUBSIDIARY),
    ("SUB-322", "Copperfield Yards LLC", "322", ROLE_SUBSIDIARY),
    ("SUB-385", "Dunmore Flats LLC", "385", ROLE_SUBSIDIARY),
)

#: ``(holding_id, parent_id, sub_id, ownership_bps, method)``. The GL accounts
#: are derived from the entity codes by the link-key convention the engine
#: checks: Investment ``<parent>-1<sub>``, pickup ``<parent>-3<sub>``,
#: equity-parent ``<sub>-29xx``. The 50/50 joint venture exercises the
#: residual-cent rule; the cost-method holding exercises the per-holding
#: method configuration.
HOLDINGS: tuple[tuple[str, str, str, int, str], ...] = (
    ("HLD-01", "PAR-100", "SUB-285", 5000, METHOD_EQUITY),
    ("HLD-02", "PAR-200", "SUB-285", 5000, METHOD_EQUITY),
    ("HLD-03", "PAR-100", "SUB-322", 10000, METHOD_EQUITY),
    ("HLD-04", "PAR-100", "SUB-160", 6000, METHOD_EQUITY),
    ("HLD-05", "PAR-200", "SUB-160", 4000, METHOD_EQUITY),
    ("HLD-06", "PAR-200", "SUB-385", 4000, METHOD_COST),
)

#: Suffix of each parent's equity account inside the sub's books, so a sub
#: with two parents carries two distinct Equity-Parent accounts.
EQUITY_SUFFIX: dict[str, str] = {"PAR-100": "14", "PAR-200": "15"}

#: ``(sub_id, net_income_cents, distributions_declared_cents)``. SUB-285 earns
#: an odd cent so the 50/50 split exercises the residual-cent rule; SUB-160
#: runs a loss year so the shares are negative.
SUB_RESULTS: tuple[tuple[str, int, int], ...] = (
    ("SUB-160", -8_443_500, 0),
    ("SUB-285", 48_250_137, 20_000_000),
    ("SUB-322", 91_400_000, 30_000_000),
    ("SUB-385", 12_000_000, 4_000_000),
)

#: ``(holding_id, begin_cents, contributions_cents)`` -- the roll-forward base
#: facts. Pickup, distributions and end are derived.
ROLLFORWARD_BASE: tuple[tuple[str, int, int], ...] = (
    ("HLD-01", 150_000_000, 25_000_000),
    ("HLD-02", 150_000_000, 0),
    ("HLD-03", 240_000_000, 0),
    ("HLD-04", 60_000_000, 10_000_000),
    ("HLD-05", 40_000_000, 0),
    ("HLD-06", 35_000_000, 0),
)

#: ``(member_id, member_name, rate_bps, day_basis, opening_capital_cents,
#:   ((start, end, contribution_cents), ...))`` -- the preferred-return base
#: facts. Quarterly periods across the fictional fiscal year; day counts,
#: accruals and the capital chain are derived.
PREFERRED_BASE: tuple[tuple[Any, ...], ...] = (
    (
        "MBR-01",
        "Halbrook Residential Partners",
        800,
        365,
        250_000_000,
        (
            ("2029-07-01", "2029-09-30", 0),
            ("2029-10-01", "2029-12-31", 50_000_000),
            ("2030-01-01", "2030-03-31", 0),
            ("2030-04-01", "2030-06-30", 0),
        ),
    ),
    (
        "MBR-02",
        "Stonecrest Communities",
        700,
        365,
        180_000_000,
        (
            ("2029-07-01", "2029-09-30", 0),
            ("2029-10-01", "2029-12-31", 0),
            ("2030-01-01", "2030-03-31", 20_000_000),
            ("2030-04-01", "2030-06-30", 0),
        ),
    ),
)

#: ``(entity_id, account, description, balance_cents)`` -- trial-balance rows
#: that are base facts rather than derived from the holdings (the subs' own
#: opening retained earnings). Should-be and adjustment are derived.
TB_FLAVOR: tuple[tuple[str, str, str, int], ...] = (
    ("SUB-160", "160-2999", "Retained Earnings-Begin", -15_000_000),
    ("SUB-285", "285-2999", "Retained Earnings-Begin", -80_000_000),
    ("SUB-322", "322-2999", "Retained Earnings-Begin", -120_000_000),
    ("SUB-385", "385-2999", "Retained Earnings-Begin", -22_500_000),
)

_ENTITY_BY_ID = {eid: (name, code) for eid, name, code, _role in ENTITIES}


def _accounts(parent_id: str, sub_id: str) -> tuple[str, str, str]:
    """Derive the (investment, pickup, equity-parent) accounts by the link key."""
    parent_code = _ENTITY_BY_ID[parent_id][1]
    sub_code = _ENTITY_BY_ID[sub_id][1]
    return (
        f"{parent_code}-1{sub_code}",
        f"{parent_code}-3{sub_code}",
        f"{sub_code}-29{EQUITY_SUFFIX[parent_id]}",
    )


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _holding(payload: dict[str, Any], holding_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_HOLDING_REGISTER)
    assert register is not None
    for row in register["holdings"]:
        if row.get("holding_id") == holding_id:
            return row
    raise KeyError(holding_id)


def _rf_row(payload: dict[str, Any], holding_id: str) -> dict[str, Any]:
    rollforward = _doc(payload, DOC_INVESTMENT_ROLLFORWARD)
    assert rollforward is not None
    for row in rollforward["rows"]:
        if row.get("holding_id") == holding_id:
            return row
    raise KeyError(holding_id)


def _block(payload: dict[str, Any], holding_id: str) -> dict[str, Any]:
    schedule = _doc(payload, DOC_ELIMINATION_SCHEDULE)
    assert schedule is not None
    for block in schedule["blocks"]:
        if block.get("holding_id") == holding_id:
            return block
    raise KeyError(holding_id)


def _schedule(payload: dict[str, Any], member_id: str) -> dict[str, Any]:
    doc = _doc(payload, DOC_PREFERRED_RETURN)
    assert doc is not None
    for schedule in doc["schedules"]:
        if schedule.get("member_id") == member_id:
            return schedule
    raise KeyError(member_id)


def _entry(payload: dict[str, Any], sub_id: str) -> dict[str, Any]:
    summary = _doc(payload, DOC_ALLOCATION_SUMMARY)
    assert summary is not None
    for entry in summary["entries"]:
        if entry.get("sub_id") == sub_id:
            return entry
    raise KeyError(sub_id)


def _tb(payload: dict[str, Any], entity_id: str, account: str) -> dict[str, Any]:
    tb = _doc(payload, DOC_TRIAL_BALANCE)
    assert tb is not None
    for row in tb["rows"]:
        if row.get("entity_id") == entity_id and row.get("account") == account:
            return row
    raise KeyError((entity_id, account))


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def rederive(payload: dict[str, Any]) -> None:
    """Recompute every derived figure from the payload's own base facts."""
    holding_doc = _doc(payload, DOC_HOLDING_REGISTER)
    result_doc = _doc(payload, DOC_SUB_RESULTS)
    rollforward = _doc(payload, DOC_INVESTMENT_ROLLFORWARD)
    elim = _doc(payload, DOC_ELIMINATION_SCHEDULE)
    preferred = _doc(payload, DOC_PREFERRED_RETURN)
    summary = _doc(payload, DOC_ALLOCATION_SUMMARY)
    tb = _doc(payload, DOC_TRIAL_BALANCE)
    if not all((holding_doc, result_doc, rollforward, elim, preferred, summary, tb)):
        return
    assert rollforward is not None and elim is not None and preferred is not None
    assert summary is not None and tb is not None

    ctx = Context(path=Path("<generated>"), data=payload)
    holdings = sorted(_holdings(ctx), key=_holding_id)
    results = {r["sub_id"]: r for r in _doc(payload, DOC_SUB_RESULTS)["results"]}  # type: ignore[index]

    # Roll-forward: pickup and distributions are each holder's kernel share of
    # the sub's result; the ending value closes the identity.
    for row in rollforward["rows"]:
        hid = row.get("holding_id")
        holding = next((h for h in holdings if _holding_id(h) == hid), None)
        if holding is None:
            continue
        result = results.get(holding.get("sub_id"))
        if holding.get("method") == METHOD_EQUITY and result is not None:
            pickup = equity_holder_shares(
                ctx, holding["sub_id"], result["net_income_cents"]
            )[hid]
            distributions = equity_holder_shares(
                ctx, holding["sub_id"], result["distributions_declared_cents"]
            )[hid]
        else:
            pickup = 0
            distributions = 0
        row["pickup_cents"] = pickup
        row["distributions_cents"] = distributions
        row["end_cents"] = rollforward_end(
            row["begin_cents"], row["contributions_cents"], pickup, distributions
        )

    rf = _rf_by_holding(ctx)

    # Eliminations: one block per equity holding, debiting the sub's
    # Equity-Parent account and crediting the Investment account for the full
    # carrying value the roll-forward ends at.
    blocks: list[dict[str, Any]] = []
    for i, holding in enumerate(
        (h for h in holdings if h.get("method") == METHOD_EQUITY), 1
    ):
        hid = _holding_id(holding)
        row = rf.get(hid)
        if row is None:
            continue
        end = row["end_cents"]
        sub_name = _ENTITY_BY_ID.get(holding.get("sub_id"), ("?", "?"))[0]
        blocks.append(
            {
                "block_id": f"EB-{i:02d}",
                "holding_id": hid,
                "lines": [
                    {
                        "account": holding["equity_parent_account"],
                        "description": f"Eliminate equity of {sub_name}",
                        "debit_cents": end,
                        "credit_cents": 0,
                    },
                    {
                        "account": holding["investment_account"],
                        "description": f"Eliminate investment in {sub_name}",
                        "debit_cents": 0,
                        "credit_cents": end,
                    },
                ],
            }
        )
    elim["blocks"] = blocks

    # Preferred return: chain each schedule from its opening capital, deriving
    # day counts and accruals from the period dates through the kernel.
    for schedule in preferred["schedules"]:
        opening = schedule["opening_capital_cents"]
        for row in schedule["rows"]:
            start = date.fromisoformat(row["start_date"])
            end_date = date.fromisoformat(row["end_date"])
            days = inclusive_days(start, end_date)
            row["days"] = days
            row["opening_capital_cents"] = opening
            row["accrued_cents"] = preferred_accrual(
                opening, schedule["rate_bps"], days, schedule["day_basis"]
            )
            row["ending_capital_cents"] = opening + row["contribution_cents"]
            opening = row["ending_capital_cents"]

    # Allocation: every fully equity-held sub allocates its net income across
    # its holders through the shared kernel (residual cent to the final one).
    entries: list[dict[str, Any]] = []
    for sub in sorted(_subsidiaries(ctx), key=lambda e: e.get("entity_id", "")):
        sid = sub.get("entity_id")
        holders = [
            h
            for h in holdings
            if h.get("sub_id") == sid and h.get("method") == METHOD_EQUITY
        ]
        if not holders or sid not in results:
            continue
        if sum(h["ownership_bps"] for h in holders) != BPS_FULL:
            continue
        shares = equity_holder_shares(ctx, sid, results[sid]["net_income_cents"])
        members = [
            {"parent_id": h["parent_id"], "allocated_cents": shares[_holding_id(h)]}
            for h in holders
        ]
        entries.append(
            {
                "sub_id": sid,
                "members": members,
                "stated_total_cents": sum(m["allocated_cents"] for m in members),
            }
        )
    summary["entries"] = entries

    # Trial balance: the investment account carries the roll-forward ending
    # value; the pickup account carries the share of income as a credit; the
    # flavor rows carry their stated balances. Should-be and adjustment start
    # agreed and posted.
    rows: list[dict[str, Any]] = []
    for holding in holdings:
        hid = _holding_id(holding)
        row = rf.get(hid)
        if row is None:
            continue
        sub_name, sub_code = _ENTITY_BY_ID.get(holding.get("sub_id"), ("?", "?"))
        rows.append(
            {
                "entity_id": holding["parent_id"],
                "account": holding["investment_account"],
                "description": f"Investment ({sub_code}) - {sub_name}",
                "balance_cents": row["end_cents"],
                "should_be_cents": row["end_cents"],
                "adjustment_cents": 0,
            }
        )
        if holding.get("method") == METHOD_EQUITY:
            rows.append(
                {
                    "entity_id": holding["parent_id"],
                    "account": holding["pickup_account"],
                    "description": f"Share of Income from JV Investment ({sub_code})",
                    "balance_cents": -row["pickup_cents"],
                    "should_be_cents": -row["pickup_cents"],
                    "adjustment_cents": 0,
                }
            )
    for entity_id, account, description, balance in TB_FLAVOR:
        rows.append(
            {
                "entity_id": entity_id,
                "account": account,
                "description": description,
                "balance_cents": balance,
                "should_be_cents": balance,
                "adjustment_cents": 0,
            }
        )
    tb["rows"] = rows


def baseline(group: str) -> dict[str, Any]:
    """Build a clean consolidation file for ``group``."""
    payload: dict[str, Any] = {
        "file_id": "clean",
        "group": group,
        "period": PERIOD,
        "documents": [
            {
                "doc_type": DOC_ENTITY_REGISTER,
                "document_id": "ENTITIES-FY2030",
                "entities": [
                    {
                        "entity_id": entity_id,
                        "name": name,
                        "entity_code": code,
                        "role": role,
                    }
                    for entity_id, name, code, role in ENTITIES
                ],
            },
            {
                "doc_type": DOC_HOLDING_REGISTER,
                "document_id": "HOLDINGS-FY2030",
                "holdings": [
                    {
                        "holding_id": holding_id,
                        "parent_id": parent_id,
                        "sub_id": sub_id,
                        "ownership_bps": ownership_bps,
                        "method": method,
                        "investment_account": _accounts(parent_id, sub_id)[0],
                        "pickup_account": _accounts(parent_id, sub_id)[1],
                        "equity_parent_account": _accounts(parent_id, sub_id)[2],
                    }
                    for holding_id, parent_id, sub_id, ownership_bps, method in HOLDINGS
                ],
            },
            {
                "doc_type": DOC_SUB_RESULTS,
                "document_id": "RESULTS-FY2030",
                "results": [
                    {
                        "sub_id": sub_id,
                        "net_income_cents": net_income,
                        "distributions_declared_cents": distributions,
                    }
                    for sub_id, net_income, distributions in SUB_RESULTS
                ],
            },
            {
                "doc_type": DOC_INVESTMENT_ROLLFORWARD,
                "document_id": "ROLLFWD-FY2030",
                "rows": [
                    {
                        "holding_id": holding_id,
                        "begin_cents": begin,
                        "contributions_cents": contributions,
                        "pickup_cents": 0,
                        "distributions_cents": 0,
                        "end_cents": 0,
                    }
                    for holding_id, begin, contributions in ROLLFORWARD_BASE
                ],
            },
            {
                "doc_type": DOC_ELIMINATION_SCHEDULE,
                "document_id": "ELIM-FY2030",
                "blocks": [],
            },
            {
                "doc_type": DOC_PREFERRED_RETURN,
                "document_id": "PREF-FY2030",
                "schedules": [
                    {
                        "member_id": member_id,
                        "member_name": member_name,
                        "rate_bps": rate_bps,
                        "day_basis": day_basis,
                        "opening_capital_cents": opening,
                        "rows": [
                            {
                                "row_no": i,
                                "start_date": start,
                                "end_date": end,
                                "days": 0,
                                "opening_capital_cents": 0,
                                "contribution_cents": contribution,
                                "accrued_cents": 0,
                                "ending_capital_cents": 0,
                            }
                            for i, (start, end, contribution) in enumerate(periods, 1)
                        ],
                    }
                    for member_id, member_name, rate_bps, day_basis, opening, periods
                    in PREFERRED_BASE
                ],
            },
            {
                "doc_type": DOC_ALLOCATION_SUMMARY,
                "document_id": "ALLOC-FY2030",
                "entries": [],
            },
            {
                "doc_type": DOC_TRIAL_BALANCE,
                "document_id": "TB-FY2030",
                "rows": [],
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
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_TRIAL_BALANCE
    ]


def _rollforward_identity_broken(payload: dict[str, Any]) -> None:
    # A keying slip in the contributions column; the stated end no longer closes.
    _rf_row(payload, "HLD-03")["contributions_cents"] += 10_000


def _orphan_rollforward_row(payload: dict[str, Any]) -> None:
    rollforward = _doc(payload, DOC_INVESTMENT_ROLLFORWARD)
    assert rollforward is not None
    rollforward["rows"].append(
        {
            "holding_id": "HLD-99",
            "begin_cents": 0,
            "contributions_cents": 0,
            "pickup_cents": 0,
            "distributions_cents": 0,
            "end_cents": 0,
        }
    )


def _rollforward_row_missing(payload: dict[str, Any]) -> None:
    rollforward = _doc(payload, DOC_INVESTMENT_ROLLFORWARD)
    assert rollforward is not None
    rollforward["rows"] = [
        r for r in rollforward["rows"] if r.get("holding_id") != "HLD-02"
    ]


def _distributions_share_wrong(payload: dict[str, Any]) -> None:
    # The distribution slice is off its ownership share; contributions absorb
    # the same amount so the identity still closes and only the share breaks.
    row = _rf_row(payload, "HLD-01")
    row["distributions_cents"] += 50_000
    row["contributions_cents"] += 50_000


def _pickup_not_rederived(payload: dict[str, Any]) -> None:
    # The booked pickup drifts from ownership x net income; contributions
    # absorb the difference so only the re-derivation control sees it.
    row = _rf_row(payload, "HLD-04")
    row["pickup_cents"] += 10_000
    row["contributions_cents"] -= 10_000


def _cost_method_pickup_booked(payload: dict[str, Any]) -> None:
    # Equity accounting routed into a cost-method holding.
    row = _rf_row(payload, "HLD-06")
    row["pickup_cents"] += 480_000
    row["contributions_cents"] -= 480_000


def _ownership_over_allocated(payload: dict[str, Any]) -> None:
    # One holder's percentage grows past what the sub has to give; the rollup
    # is re-derived so only the bounds control sees the break.
    _holding(payload, "HLD-04")["ownership_bps"] = 10_500
    rederive(payload)


def _holding_parent_unknown(payload: dict[str, Any]) -> None:
    _holding(payload, "HLD-01")["parent_id"] = "PAR-999"
    rederive(payload)


def _elimination_unbalanced(payload: dict[str, Any]) -> None:
    _block(payload, "HLD-03")["lines"][0]["debit_cents"] += 25_000


def _elimination_missing(payload: dict[str, Any]) -> None:
    schedule = _doc(payload, DOC_ELIMINATION_SCHEDULE)
    assert schedule is not None
    schedule["blocks"] = [
        b for b in schedule["blocks"] if b.get("holding_id") != "HLD-02"
    ]


def _elimination_understated(payload: dict[str, Any]) -> None:
    # Both sides of the block still balance, but at last period's carrying
    # value -- the elimination went stale while the investment moved.
    block = _block(payload, "HLD-01")
    block["lines"][0]["debit_cents"] -= 100_000
    block["lines"][1]["credit_cents"] -= 100_000


def _orphan_elimination_block(payload: dict[str, Any]) -> None:
    schedule = _doc(payload, DOC_ELIMINATION_SCHEDULE)
    assert schedule is not None
    schedule["blocks"].append(
        {
            "block_id": "EB-99",
            "holding_id": "HLD-99",
            "lines": [
                {
                    "account": "999-2914",
                    "description": "Eliminate equity of an unheld interest",
                    "debit_cents": 5_000_000,
                    "credit_cents": 0,
                },
                {
                    "account": "999-1999",
                    "description": "Eliminate an investment nobody holds",
                    "debit_cents": 0,
                    "credit_cents": 5_000_000,
                },
            ],
        }
    )


def _account_convention_broken(payload: dict[str, Any]) -> None:
    # The investment lands in an account the code link key does not derive;
    # everything downstream is re-derived against the mislabelled account, so
    # only the link-key control sees it.
    _holding(payload, "HLD-03")["investment_account"] = "100-1999"
    rederive(payload)


def _pref_days_misstated(payload: dict[str, Any]) -> None:
    _schedule(payload, "MBR-01")["rows"][2]["days"] += 1


def _pref_accrual_overstated(payload: dict[str, Any]) -> None:
    _schedule(payload, "MBR-02")["rows"][1]["accrued_cents"] += 10_000


def _pref_capital_chain_broken(payload: dict[str, Any]) -> None:
    _schedule(payload, "MBR-01")["rows"][1]["ending_capital_cents"] += 100_000


def _pref_period_gap(payload: dict[str, Any]) -> None:
    # The third period starts two days late; the day counts, accruals and
    # chain are re-derived from the dates so only the continuity gate fires.
    _schedule(payload, "MBR-02")["rows"][2]["start_date"] = "2030-01-03"
    rederive(payload)


def _allocation_misfooted(payload: dict[str, Any]) -> None:
    _entry(payload, "SUB-322")["stated_total_cents"] += 100


def _allocation_short_of_income(payload: dict[str, Any]) -> None:
    # One member's slice shrinks and the stated total moves with it, so the
    # entry still foots -- but the income allocated is no longer the income
    # earned.
    entry = _entry(payload, "SUB-285")
    entry["members"][1]["allocated_cents"] -= 5_000
    entry["stated_total_cents"] -= 5_000


def _allocation_stranger_member(payload: dict[str, Any]) -> None:
    _entry(payload, "SUB-322")["members"].append(
        {"parent_id": "PAR-777", "allocated_cents": 0}
    )


def _tb_investment_break(payload: dict[str, Any]) -> None:
    # The ledger balance moves off the roll-forward; should-be moves with it so
    # only the tie control sees the break.
    row = _tb(payload, "PAR-100", "100-1322")
    row["balance_cents"] += 200_000
    row["should_be_cents"] += 200_000


def _tb_pickup_break(payload: dict[str, Any]) -> None:
    row = _tb(payload, "PAR-100", "100-3285")
    row["balance_cents"] += 100
    row["should_be_cents"] += 100


def _tb_adjustment_math_wrong(payload: dict[str, Any]) -> None:
    # Should-be drifts while the adjustment still claims nothing needs posting.
    _tb(payload, "SUB-285", "285-2999")["should_be_cents"] -= 300_000


def _tb_unposted_adjustment(payload: dict[str, Any]) -> None:
    # A correction derived and internally consistent -- but never posted. The
    # only defect in the corpus that is a review flag rather than a failure.
    row = _tb(payload, "SUB-322", "322-2999")
    row["should_be_cents"] += 150_000
    row["adjustment_cents"] = 150_000


def _amount_not_integer(payload: dict[str, Any]) -> None:
    row = _rf_row(payload, "HLD-01")
    row["pickup_cents"] = float(row["pickup_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "rollforward_identity_broken": ("rf_identity", _rollforward_identity_broken),
    "orphan_rollforward_row": ("rf_row_has_holding", _orphan_rollforward_row),
    "rollforward_row_missing": ("rf_coverage_complete", _rollforward_row_missing),
    "distributions_share_wrong": ("rf_distributions_rederive", _distributions_share_wrong),
    "pickup_not_rederived": ("epu_pickup_rederives", _pickup_not_rederived),
    "cost_method_pickup_booked": ("epu_cost_no_pickup", _cost_method_pickup_booked),
    "ownership_over_allocated": ("epu_ownership_bounds", _ownership_over_allocated),
    "holding_parent_unknown": ("epu_refs_resolve", _holding_parent_unknown),
    "elimination_unbalanced": ("elim_block_balances", _elimination_unbalanced),
    "elimination_missing": ("elim_pairing_complete", _elimination_missing),
    "elimination_understated": ("elim_extinguishes_investment", _elimination_understated),
    "orphan_elimination_block": ("elim_refs_known", _orphan_elimination_block),
    "account_convention_broken": ("elim_account_link_key", _account_convention_broken),
    "pref_days_misstated": ("pref_day_count", _pref_days_misstated),
    "pref_accrual_overstated": ("pref_accrual_rederives", _pref_accrual_overstated),
    "pref_capital_chain_broken": ("pref_capital_chains", _pref_capital_chain_broken),
    "pref_period_gap": ("pref_periods_contiguous", _pref_period_gap),
    "allocation_misfooted": ("alloc_foots", _allocation_misfooted),
    "allocation_short_of_income": ("alloc_ties_net_income", _allocation_short_of_income),
    "allocation_stranger_member": ("alloc_member_is_holder", _allocation_stranger_member),
    "tb_investment_break": ("alloc_tb_investment_ties", _tb_investment_break),
    "tb_pickup_break": ("alloc_tb_pickup_ties", _tb_pickup_break),
    "tb_adjustment_math_wrong": ("alloc_tb_adjustment_math", _tb_adjustment_math_wrong),
    "tb_unposted_adjustment": ("alloc_tb_unposted_adjustment", _tb_unposted_adjustment),
    "amount_not_integer": ("epu_pickup_rederives", _amount_not_integer),
}


# --------------------------------------------------------------------------- #
# Corpus writer
# --------------------------------------------------------------------------- #
def generate_corpus(folder: Path) -> list[Path]:
    """Write the fictional corpus into ``folder`` and return the paths written."""
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    files: list[dict[str, Any]] = []
    clean = baseline(GROUPS[0])
    clean["file_id"] = f"clean__{GROUPS[0].replace(' ', '_')}"
    files.append(clean)

    for i, name in enumerate(sorted(DEFECTS)):
        _rule, mutate = DEFECTS[name]
        group = GROUPS[(i + 1) % len(GROUPS)]
        f = baseline(group)
        f["file_id"] = f"{name}__{group.replace(' ', '_')}"
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
