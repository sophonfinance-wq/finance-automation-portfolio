"""
Fictional equity-waterfall deal-file corpus generator.
======================================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The sponsors, the members, the projects, the
contributions, the rates and the proceeds are fictional, and every period is a
month index in a fictional future. No real entity, person, project or path
appears anywhere. The generator is deterministic and takes no seed.

The baseline is derived, not typed
----------------------------------
Only the deal terms, the member register (with each member's funded
contributions) and the default/loan/syndicate inputs are stated as base facts.
Everything the engine later checks as a rollup -- each capital account, the
distribution schedule, the realized-returns summary, the loan repayment, the
dilution recompute, the syndicate draw -- is recomputed by :func:`rederive` from
those base facts, through the *same* :mod:`waterfall_engine.waterfall` kernel the
engine recomputes with. So the relationships the engine tests are the
relationships that produced the data: a defect that changes a base fact
re-derives the rollup and keeps the break confined to one control; a defect that
targets a stated rollup edits that figure alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .engine import (
    recompute_accounts,
    recompute_dilution,
    recompute_hurdle_target,
    recompute_loan,
    recompute_syndicate_draw,
    recompute_waterfall,
)
from .model import (
    DILUTION_PENALTY_BPS,
    DOC_CAPITAL_LEDGER,
    DOC_DEAL_TERMS,
    DOC_DILUTION_WORKSHEET,
    DOC_LOAN_COVENANT,
    DOC_MEMBER_REGISTER,
    DOC_RETURNS_SUMMARY,
    DOC_WATERFALL_SCHEDULE,
    METHOD_RATIO,
    ROLE_DEVELOPER,
    ROLE_INVESTOR,
    SYNDICATE_CALL_BPS,
    TIER_CAPITAL,
    TIER_PREF,
    Context,
)
from .waterfall import equity_multiple_bps

#: Fictional sponsor labels, rotated for file identity only.
SPONSORS: tuple[str, ...] = (
    "Northmoor Development Group",
    "Halbrook Residential Partners",
    "Stonecrest Communities",
    "Ardenne Field Partners",
)

#: Fictional project labels, rotated for file identity only.
PROJECTS: tuple[str, ...] = (
    "Brightwater Commons",
    "Copperfield Yards",
    "Alderpoint Terraces",
    "Dunmore Flats",
)

PERIOD = "FY2041-Q2"
#: Month index every accrual and covenant window is measured to.
AS_OF_PERIOD = 24
MATURITY_LEAD_PERIODS = 6
REPORT_LEAD_PERIODS = 3

#: The two members. ``(member_id, name, role, commitment_cents, contributions)``
#: where each contribution is ``(period, amount_cents)``.
INVESTOR_ID = "MBR-INV"
DEVELOPER_ID = "MBR-DEV"


def d(dollars: float) -> int:
    """Dollars to integer cents."""
    return round(dollars * 100)


MEMBERS: tuple[tuple[Any, ...], ...] = (
    (
        INVESTOR_ID,
        "Westmere Capital Fund II",
        ROLE_INVESTOR,
        d(12_000_000),
        ((0, d(8_000_000)), (6, d(1_000_000))),
    ),
    (
        DEVELOPER_ID,
        "Ardenne Field Partners",
        ROLE_DEVELOPER,
        d(3_000_000),
        ((0, d(1_000_000)),),
    ),
)

#: Deal-terms base facts. Rates in basis points; proceeds in cents.
DEAL_TERMS: dict[str, Any] = {
    "pref_rate_bps": 1000,          # 10.00% preferred, compounded monthly
    "hurdle_rate_bps": 1600,        # 16.00% investor hurdle
    "member_loan_rate_bps": 1400,   # 14.00% member loan
    "default_loan_rate_bps": 2100,  # 21.00% default / deficit loan
    "tier_c_investor_bps": 7000,    # 70 / 30 hurdle split
    "tier_c_developer_bps": 3000,
    "tier_d_investor_bps": 5000,    # 50 / 50 promote split
    "tier_d_developer_bps": 5000,
    "dilution_penalty_bps": DILUTION_PENALTY_BPS,
    "syndicate_call_bps": SYNDICATE_CALL_BPS,
    "proceeds_cents": d(18_000_000),
}

#: Loan / covenant / syndicate base facts (the derived fields are filled by
#: :func:`rederive`).
LOAN_COVENANT: dict[str, Any] = {
    "member_loan_principal_cents": d(500_000),
    "member_loan_periods": 12,
    "senior_loan_cents": d(12_000_000),
    "total_cost_cents": d(16_000_000),
    "max_ltc_bps": 7700,            # LTC cap 77.00%; actual 75.00%
    "maturity_period": 60,
    "syndicate_commitment_cents": d(500_000),
    "report_due_period": 40,
}

#: Dilution default-event base facts.
DILUTION_INPUTS: dict[str, Any] = {
    "defaulting_member_id": DEVELOPER_ID,
    "funding_member_id": INVESTOR_ID,
    "shortfall_cents": d(400_000),
    "method": METHOD_RATIO,
}


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _member(payload: dict[str, Any], member_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_MEMBER_REGISTER)
    assert register is not None
    for row in register["members"]:
        if row.get("member_id") == member_id:
            return row
    raise KeyError(member_id)


def _ledger_row(payload: dict[str, Any], member_id: str) -> dict[str, Any]:
    ledger = _doc(payload, DOC_CAPITAL_LEDGER)
    assert ledger is not None
    for row in ledger["accounts"]:
        if row.get("member_id") == member_id:
            return row
    raise KeyError(member_id)


def _returns_row(payload: dict[str, Any], member_id: str) -> dict[str, Any]:
    summary = _doc(payload, DOC_RETURNS_SUMMARY)
    assert summary is not None
    for row in summary["members"]:
        if row.get("member_id") == member_id:
            return row
    raise KeyError(member_id)


def _schedule(payload: dict[str, Any]) -> dict[str, Any]:
    schedule = _doc(payload, DOC_WATERFALL_SCHEDULE)
    assert schedule is not None
    return schedule


def _loan(payload: dict[str, Any]) -> dict[str, Any]:
    loan = _doc(payload, DOC_LOAN_COVENANT)
    assert loan is not None
    return loan


def _worksheet(payload: dict[str, Any]) -> dict[str, Any]:
    work = _doc(payload, DOC_DILUTION_WORKSHEET)
    assert work is not None
    return work


def _terms_doc(payload: dict[str, Any]) -> dict[str, Any]:
    terms = _doc(payload, DOC_DEAL_TERMS)
    assert terms is not None
    return terms


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def rederive(payload: dict[str, Any]) -> None:
    """Recompute every rollup figure from the payload's own base facts."""
    ctx = Context(path=Path("<generated>"), data=payload)
    accounts = recompute_accounts(ctx)
    result = recompute_waterfall(ctx)
    loan = recompute_loan(ctx)
    draw = recompute_syndicate_draw(ctx)
    dil = recompute_dilution(ctx)
    ledger = _doc(payload, DOC_CAPITAL_LEDGER)
    schedule = _doc(payload, DOC_WATERFALL_SCHEDULE)
    summary = _doc(payload, DOC_RETURNS_SUMMARY)
    loan_doc = _doc(payload, DOC_LOAN_COVENANT)
    work = _doc(payload, DOC_DILUTION_WORKSHEET)
    if None in (accounts, result, loan, draw, dil):
        return
    if None in (ledger, schedule, summary, loan_doc, work):
        return
    assert accounts is not None and result is not None and loan is not None
    assert dil is not None and ledger is not None and schedule is not None
    assert summary is not None and loan_doc is not None and work is not None

    inv, dev = INVESTOR_ID, DEVELOPER_ID

    # Per-tier receipts, for the ending capital-account roll-forward.
    pref_paid = {inv: 0, dev: 0}
    cap_paid = {inv: 0, dev: 0}
    for tier, mid, amt in result.entries:
        if tier == TIER_PREF:
            pref_paid[mid] += amt
        elif tier == TIER_CAPITAL:
            cap_paid[mid] += amt

    # Capital ledger: one roll-forward row per member.
    ledger["accounts"] = [
        {
            "member_id": mid,
            "contribution_account_cents": accounts[mid].contribution_account_cents,
            "investment_return_account_cents": accounts[mid].investment_return_account_cents,
            "ending_contribution_account_cents": (
                accounts[mid].contribution_account_cents - cap_paid[mid]
            ),
            "ending_investment_return_account_cents": (
                accounts[mid].investment_return_account_cents - pref_paid[mid]
            ),
        }
        for mid in (inv, dev)
    ]

    # Waterfall schedule: the entries and their tie-out figures.
    schedule["entries"] = [
        {"tier": tier, "member_id": mid, "amount_cents": amt}
        for tier, mid, amt in result.entries
    ]
    schedule["per_member"] = [
        {"member_id": mid, "total_cents": result.per_member[mid]} for mid in (inv, dev)
    ]
    schedule["hurdle_target_cents"] = result.hurdle_target_cents
    schedule["promote_split_cents"] = result.promote[dev]
    schedule["proceeds_cents"] = DEAL_TERMS["proceeds_cents"]
    schedule["loan_repayment_cents"] = loan["repayment"]
    schedule["proceeds_after_loans_cents"] = (
        _terms_doc(payload)["proceeds_cents"] - loan["repayment"]
    )
    schedule["total_distributed_cents"] = result.total_distributed_cents

    # Returns summary: the realized returns, from the waterfall.
    summary["members"] = [
        {
            "member_id": mid,
            "total_contributions_cents": accounts[mid].contribution_account_cents,
            "total_distributions_cents": result.per_member[mid],
            "equity_multiple_bps": equity_multiple_bps(
                result.per_member[mid], accounts[mid].contribution_account_cents
            ),
            "preferred_return_cents": result.preferred[mid],
            "profit_split_cents": result.promote[mid],
        }
        for mid in (inv, dev)
    ]

    # Loan covenant: the derived interest, repayment and syndicate draw.
    loan_doc["member_loan_interest_cents"] = loan["interest"]
    loan_doc["member_loan_repayment_cents"] = loan["repayment"]
    loan_doc["syndicate_draw_cents"] = draw

    # Dilution worksheet: the derived substitute, penalty and diluted interest.
    work["substitute_contribution_cents"] = dil["substitute"]
    work["penalized_substitute_cents"] = dil["penalized"]
    work["aggregate_contributions_cents"] = dil["aggregate"]
    work["defaulting_prior_contribution_cents"] = dil["defaulting_prior"]
    work["funding_prior_contribution_cents"] = dil["funding_prior"]
    work["diluted_interest_bps"] = dil["diluted_interest_bps"]


def baseline(sponsor: str, project: str) -> dict[str, Any]:
    """Build a clean deal file for ``sponsor`` / ``project``."""
    payload: dict[str, Any] = {
        "file_id": "clean",
        "sponsor": sponsor,
        "project": project,
        "period": PERIOD,
        "as_of_period": AS_OF_PERIOD,
        "maturity_lead_periods": MATURITY_LEAD_PERIODS,
        "report_lead_periods": REPORT_LEAD_PERIODS,
        "documents": [
            {
                "doc_type": DOC_DEAL_TERMS,
                "document_id": "TERMS-2041",
                **DEAL_TERMS,
            },
            {
                "doc_type": DOC_MEMBER_REGISTER,
                "document_id": "MEMBERS-2041",
                "members": [
                    {
                        "member_id": member_id,
                        "name": name,
                        "role": role,
                        "commitment_cents": commitment,
                        "contributions": [
                            {"period": period, "amount_cents": amount}
                            for period, amount in contributions
                        ],
                    }
                    for member_id, name, role, commitment, contributions in MEMBERS
                ],
            },
            {
                "doc_type": DOC_CAPITAL_LEDGER,
                "document_id": "LEDGER-2041",
                "accounts": [],
            },
            {
                "doc_type": DOC_WATERFALL_SCHEDULE,
                "document_id": "WATERFALL-2041",
                "entries": [],
            },
            {
                "doc_type": DOC_DILUTION_WORKSHEET,
                "document_id": "DILUTION-2041",
                **DILUTION_INPUTS,
            },
            {
                "doc_type": DOC_RETURNS_SUMMARY,
                "document_id": "RETURNS-2041",
                "members": [],
            },
            {
                "doc_type": DOC_LOAN_COVENANT,
                "document_id": "COVENANT-2041",
                **LOAN_COVENANT,
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
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_RETURNS_SUMMARY
    ]


def _duplicate_member_id(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_MEMBER_REGISTER)
    assert register is not None
    register["members"].append(dict(_member(payload, INVESTOR_ID)))


def _bad_role(payload: dict[str, Any]) -> None:
    # A third member carries an unknown role; the investor and developer are still
    # both present, so only the role-validity control sees it.
    register = _doc(payload, DOC_MEMBER_REGISTER)
    assert register is not None
    register["members"].append(
        {
            "member_id": "MBR-ADV",
            "name": "Kelder Advisory Group",
            "role": "sponsor",
            "commitment_cents": d(500_000),
            "contributions": [],
        }
    )


def _extra_investor(payload: dict[str, Any]) -> None:
    # A second investor with no funded capital: the venture is no longer the
    # two-sided one the waterfall is written for.
    register = _doc(payload, DOC_MEMBER_REGISTER)
    assert register is not None
    register["members"].append(
        {
            "member_id": "MBR-INV2",
            "name": "Marran Growth Partners",
            "role": ROLE_INVESTOR,
            "commitment_cents": d(1_000_000),
            "contributions": [],
        }
    )


def _commitment_exceeded(payload: dict[str, Any]) -> None:
    # The investor funded more than it committed.
    _member(payload, INVESTOR_ID)["commitment_cents"] = d(5_000_000)


def _pref_rate_zero(payload: dict[str, Any]) -> None:
    _terms_doc(payload)["pref_rate_bps"] = 0


def _pref_accrual_wrong(payload: dict[str, Any]) -> None:
    _ledger_row(payload, INVESTOR_ID)["investment_return_account_cents"] += d(100_000)


def _contribution_account_wrong(payload: dict[str, Any]) -> None:
    _ledger_row(payload, DEVELOPER_ID)["contribution_account_cents"] += d(50_000)


def _ending_not_zero(payload: dict[str, Any]) -> None:
    _ledger_row(payload, INVESTOR_ID)["ending_contribution_account_cents"] += d(100_000)


def _tier_out_of_order(payload: dict[str, Any]) -> None:
    # Move the first promote-tier entry to the front of the schedule.
    schedule = _schedule(payload)
    entries = schedule["entries"]
    idx = next(i for i, e in enumerate(entries) if e["tier"].startswith("D_"))
    entries.insert(0, entries.pop(idx))


def _pari_passu_broken(payload: dict[str, Any]) -> None:
    # Shift a cent block from developer to investor inside the preferred tier,
    # keeping the tier total but breaking the pari-passu split.
    schedule = _schedule(payload)
    inv_a = next(
        e for e in schedule["entries"] if e["tier"] == TIER_PREF and e["member_id"] == INVESTOR_ID
    )
    dev_a = next(
        e for e in schedule["entries"] if e["tier"] == TIER_PREF and e["member_id"] == DEVELOPER_ID
    )
    inv_a["amount_cents"] += d(10_000)
    dev_a["amount_cents"] -= d(10_000)


def _allocation_wrong(payload: dict[str, Any]) -> None:
    # Perturb a hurdle-tier allocation so it no longer recomputes.
    schedule = _schedule(payload)
    entry = next(e for e in schedule["entries"] if e["tier"].startswith("C_"))
    entry["amount_cents"] += d(25_000)


def _hurdle_rate_too_low(payload: dict[str, Any]) -> None:
    _terms_doc(payload)["hurdle_rate_bps"] = 500


def _hurdle_target_wrong(payload: dict[str, Any]) -> None:
    _schedule(payload)["hurdle_target_cents"] += d(250_000)


def _split_does_not_sum(payload: dict[str, Any]) -> None:
    _terms_doc(payload)["tier_d_developer_bps"] = 4000  # 5000 + 4000 != 10000


def _promote_carry_wrong(payload: dict[str, Any]) -> None:
    _schedule(payload)["promote_split_cents"] += d(75_000)


def _loan_rate_inverted(payload: dict[str, Any]) -> None:
    _terms_doc(payload)["default_loan_rate_bps"] = 1000  # below the 1400 member rate


def _loan_repayment_wrong(payload: dict[str, Any]) -> None:
    _loan(payload)["member_loan_repayment_cents"] += d(10_000)


def _dilution_method_unknown(payload: dict[str, Any]) -> None:
    _worksheet(payload)["method"] = "handshake_method"


def _dilution_penalty_wrong(payload: dict[str, Any]) -> None:
    _terms_doc(payload)["dilution_penalty_bps"] = 15000  # 150%, not the statutory 200%


def _dilution_interest_wrong(payload: dict[str, Any]) -> None:
    _worksheet(payload)["diluted_interest_bps"] += 25


def _distribution_leaks(payload: dict[str, Any]) -> None:
    _schedule(payload)["total_distributed_cents"] += d(100)


def _distribution_over_available(payload: dict[str, Any]) -> None:
    schedule = _schedule(payload)
    schedule["total_distributed_cents"] = schedule["proceeds_after_loans_cents"] + d(200_000)


def _multiple_wrong(payload: dict[str, Any]) -> None:
    _returns_row(payload, INVESTOR_ID)["equity_multiple_bps"] += 50


def _preferred_return_wrong(payload: dict[str, Any]) -> None:
    _returns_row(payload, INVESTOR_ID)["preferred_return_cents"] += d(20_000)


def _profit_split_wrong(payload: dict[str, Any]) -> None:
    _returns_row(payload, DEVELOPER_ID)["profit_split_cents"] += d(30_000)


def _maturity_soon(payload: dict[str, Any]) -> None:
    # The financing matures inside the warning window; the rollups are untouched so
    # only the maturity FLAG remains.
    _loan(payload)["maturity_period"] = AS_OF_PERIOD + 3


def _ltc_over_max(payload: dict[str, Any]) -> None:
    _loan(payload)["senior_loan_cents"] = d(12_500_000)  # 78.125% > 77.00% cap


def _syndicate_draw_wrong(payload: dict[str, Any]) -> None:
    _loan(payload)["syndicate_draw_cents"] += d(5_000)


def _report_due_soon(payload: dict[str, Any]) -> None:
    _loan(payload)["report_due_period"] = AS_OF_PERIOD + 2


def _amount_not_integer(payload: dict[str, Any]) -> None:
    schedule = _schedule(payload)
    schedule["total_distributed_cents"] = float(schedule["total_distributed_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "duplicate_member_id": ("mbr_unique_ids", _duplicate_member_id),
    "bad_role": ("mbr_role_valid", _bad_role),
    "extra_investor": ("mbr_roles_complete", _extra_investor),
    "commitment_exceeded": ("mbr_commitment_honored", _commitment_exceeded),
    "pref_rate_zero": ("pref_rate_valid", _pref_rate_zero),
    "pref_accrual_wrong": ("pref_accrual_recomputes", _pref_accrual_wrong),
    "contribution_account_wrong": ("cap_contribution_recomputes", _contribution_account_wrong),
    "ending_not_zero": ("cap_rollforward_zeroes", _ending_not_zero),
    "tier_out_of_order": ("wf_tier_order_valid", _tier_out_of_order),
    "pari_passu_broken": ("wf_pari_passu_split", _pari_passu_broken),
    "allocation_wrong": ("wf_tier_allocation_recomputes", _allocation_wrong),
    "hurdle_rate_too_low": ("hurdle_rate_valid", _hurdle_rate_too_low),
    "hurdle_target_wrong": ("hurdle_boundary_recomputes", _hurdle_target_wrong),
    "split_does_not_sum": ("promo_split_ratios_valid", _split_does_not_sum),
    "promote_carry_wrong": ("promo_carry_recomputes", _promote_carry_wrong),
    "loan_rate_inverted": ("loan_rate_valid", _loan_rate_inverted),
    "loan_repayment_wrong": ("loan_repaid_before_distribution", _loan_repayment_wrong),
    "dilution_method_unknown": ("dil_method_valid", _dilution_method_unknown),
    "dilution_penalty_wrong": ("dil_penalty_multiplier", _dilution_penalty_wrong),
    "dilution_interest_wrong": ("dil_recompute", _dilution_interest_wrong),
    "distribution_leaks": ("dist_no_leakage", _distribution_leaks),
    "distribution_over_available": ("dist_within_available", _distribution_over_available),
    "multiple_wrong": ("ret_multiple_recomputes", _multiple_wrong),
    "preferred_return_wrong": ("ret_preferred_ties", _preferred_return_wrong),
    "profit_split_wrong": ("ret_profit_split_ties", _profit_split_wrong),
    "maturity_soon": ("cov_maturity_window", _maturity_soon),
    "ltc_over_max": ("cov_ltc_within_max", _ltc_over_max),
    "syndicate_draw_wrong": ("syn_capital_call_ratio", _syndicate_draw_wrong),
    "report_due_soon": ("syn_report_due", _report_due_soon),
    "amount_not_integer": ("dist_no_leakage", _amount_not_integer),
}


# --------------------------------------------------------------------------- #
# Corpus writer
# --------------------------------------------------------------------------- #
def generate_corpus(folder: Path) -> list[Path]:
    """Write the fictional corpus into ``folder`` and return the paths written."""
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    files: list[dict[str, Any]] = []
    clean = baseline(SPONSORS[0], PROJECTS[0])
    clean["file_id"] = f"clean__{SPONSORS[0].replace(' ', '_')}"
    files.append(clean)

    for i, name in enumerate(sorted(DEFECTS)):
        _rule, mutate = DEFECTS[name]
        sponsor = SPONSORS[(i + 1) % len(SPONSORS)]
        project = PROJECTS[(i + 1) % len(PROJECTS)]
        f = baseline(sponsor, project)
        f["file_id"] = f"{name}__{sponsor.replace(' ', '_')}"
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
