"""
Fictional outstanding-check aging corpus generator.
===================================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The entities, the bank accounts, the payees, the
check numbers, the amounts and the check dates are fictional, and the reporting
period is set in a fictional future. No real entity, person, bank, account
number, project or path appears anywhere. The generator is deterministic and
takes no seed.

The baseline is derived, not typed
----------------------------------
Only the bank accounts, the check register and the void register are stated as
base facts. Everything the engine later checks as a re-derivation -- the
outstanding schedule with its ages, aging bands and follow-up markers, the
escheatment schedule, the bank reconciliation's outstanding line and aging
subtotals -- is recomputed by :func:`rederive` from those base facts, through the
*same* :mod:`checkage_engine.aging` kernel the engine recomputes with. So the
relationships the engine tests are the relationships that produced the data: a
defect that changes a base fact re-derives the schedules and keeps the break
confined to one control; a defect that targets a stated schedule edits that
figure alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from .engine import (
    recompute_bucket_totals,
    recompute_escheatment,
    recompute_outstanding,
)
from .model import (
    CHECK_TYPE_MANUAL,
    CHECK_TYPE_SYSTEM,
    DEFAULT_DORMANCY_DAYS,
    DISPOSITION_STOP_PAYMENT,
    DISPOSITION_VOIDED,
    DISPOSITION_ZERO_DOLLAR,
    DOC_ACCOUNT_REGISTER,
    DOC_BANK_RECONCILIATION,
    DOC_CHECK_REGISTER,
    DOC_ESCHEATMENT_SCHEDULE,
    DOC_OUTSTANDING_SCHEDULE,
    DOC_VOID_REGISTER,
    Context,
)

#: Fictional entity labels, rotated for file identity only.
PORTFOLIOS: tuple[str, ...] = (
    "Northmoor Development Group",
    "Halbrook Residential Partners",
    "Stonecrest Communities",
    "Ardenne Field Group",
)

PERIOD = "FY2029"
#: The as-of date every age, stale-dating and dormancy test is measured to.
AS_OF = "2029-09-30"
#: Stale-dating threshold, in days. Past it an item needs a human.
STALE_DATED_DAYS = 180
#: Dormancy period, in days. Past it an item is unclaimed property.
DORMANCY_DAYS = DEFAULT_DORMANCY_DAYS


def d(dollars: float) -> int:
    """Dollars to integer cents."""
    return round(dollars * 100)


#: ``(account_id, description, escheat_jurisdiction)``. Two disbursement accounts
#: reporting unclaimed property to two invented jurisdictions, so the escheatment
#: controls have more than one destination to get right.
ACCOUNTS: tuple[tuple[str, str, str], ...] = (
    ("BNK-100", "Operating disbursement account", "State of Marran"),
    ("BNK-200", "Project trust disbursement account", "City of Kelder"),
)

#: ``(check_number, account_id, check_date, check_type, payee, check_amount,
#:   cleared_amount, cleared_date)``. Amounts in dollars; ``None`` cleared date
#: means nothing has cleared.
#:
#: The two accounts deliberately run overlapping number series -- both open at
#: CHK-4101 -- so the uniqueness control has to be scoped to the account to pass
#: at all. The outstanding population is spread across every aging band, and two
#: accounts carry items past the dormancy period so both jurisdictions appear on
#: the escheatment schedule. Three checks are withdrawn by the void register
#: below and are therefore not outstanding despite nothing having cleared.
CHECKS: tuple[tuple[Any, ...], ...] = (
    ("CHK-4101", "BNK-100", "2029-08-05", CHECK_TYPE_SYSTEM, "Brightwater Commons Association", 12_450.00, 12_450.00, "2029-08-12"),
    ("CHK-4102", "BNK-100", "2029-08-19", CHECK_TYPE_SYSTEM, "Copperfield Yards Maintenance", 3_275.50, 3_275.50, "2029-08-26"),
    ("CHK-4103", "BNK-100", "2029-09-02", CHECK_TYPE_MANUAL, "Westmere Utility Services", 8_940.00, 8_940.00, "2029-09-09"),
    ("CHK-4104", "BNK-100", "2029-09-15", CHECK_TYPE_SYSTEM, "Kettleridge Builders", 5_600.00, 0.00, None),
    ("CHK-4105", "BNK-100", "2029-08-20", CHECK_TYPE_SYSTEM, "Pinehollow Mechanical", 2_150.25, 0.00, None),
    ("CHK-4106", "BNK-100", "2029-06-28", CHECK_TYPE_MANUAL, "Vellmont Design Studio", 990.00, 0.00, None),
    ("CHK-4107", "BNK-100", "2029-02-14", CHECK_TYPE_MANUAL, "Grovewell Site Services", 1_425.75, 0.00, None),
    ("CHK-4108", "BNK-100", "2028-06-15", CHECK_TYPE_MANUAL, "Marrowfield Landscaping", 845.00, 0.00, None),
    ("CHK-4109", "BNK-100", "2029-07-10", CHECK_TYPE_MANUAL, "Harborline Freight", 4_500.00, 0.00, None),
    ("CHK-4110", "BNK-100", "2029-06-01", CHECK_TYPE_SYSTEM, "Kettleridge Builders", 15_200.00, 15_200.00, "2029-06-08"),
    ("CHK-4111", "BNK-100", "2026-01-20", CHECK_TYPE_MANUAL, "Vellmont Design Studio", 2_380.00, 0.00, None),
    ("CHK-4101", "BNK-200", "2029-09-20", CHECK_TYPE_SYSTEM, "Westmere Field Office", 3_400.00, 0.00, None),
    ("CHK-4102", "BNK-200", "2029-07-05", CHECK_TYPE_SYSTEM, "Marrowfield Landscaping", 2_750.00, 0.00, None),
    ("CHK-4103", "BNK-200", "2026-05-11", CHECK_TYPE_MANUAL, "Brightwater Commons Association", 615.40, 0.00, None),
    ("CHK-4104", "BNK-200", "2026-03-02", CHECK_TYPE_MANUAL, "Copperfield Yards Maintenance", 1_180.00, 0.00, None),
    ("CHK-4105", "BNK-200", "2029-05-01", CHECK_TYPE_SYSTEM, "Pinehollow Mechanical", 6_120.00, 6_120.00, "2029-05-08"),
    ("CHK-4106", "BNK-200", "2029-08-01", CHECK_TYPE_MANUAL, "Grovewell Site Services", 0.00, 0.00, None),
    ("CHK-4107", "BNK-200", "2029-09-05", CHECK_TYPE_MANUAL, "Harborline Freight", 7_300.00, 0.00, None),
)

#: ``(check_number, account_id, disposition, void_date, void_amount)``. Amounts in
#: dollars, signed so that the check amount plus the reversal nets to zero. One of
#: each disposition, so every withdrawal shape is exercised.
VOIDS: tuple[tuple[Any, ...], ...] = (
    ("CHK-4109", "BNK-100", DISPOSITION_VOIDED, "2029-07-12", -4_500.00),
    ("CHK-4106", "BNK-200", DISPOSITION_ZERO_DOLLAR, "2029-08-01", 0.00),
    ("CHK-4107", "BNK-200", DISPOSITION_STOP_PAYMENT, "2029-09-08", -7_300.00),
)


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _account(payload: dict[str, Any], account_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_ACCOUNT_REGISTER)
    assert register is not None
    for row in register["accounts"]:
        if row.get("account_id") == account_id:
            return row
    raise KeyError(account_id)


def _check(payload: dict[str, Any], account_id: str, check_number: str) -> dict[str, Any]:
    register = _doc(payload, DOC_CHECK_REGISTER)
    assert register is not None
    for row in register["checks"]:
        if row.get("account_id") == account_id and row.get("check_number") == check_number:
            return row
    raise KeyError((account_id, check_number))


def _void(payload: dict[str, Any], account_id: str, check_number: str) -> dict[str, Any]:
    register = _doc(payload, DOC_VOID_REGISTER)
    assert register is not None
    for row in register["entries"]:
        if row.get("account_id") == account_id and row.get("check_number") == check_number:
            return row
    raise KeyError((account_id, check_number))


def _outstanding_item(
    payload: dict[str, Any], account_id: str, check_number: str
) -> dict[str, Any]:
    schedule = _doc(payload, DOC_OUTSTANDING_SCHEDULE)
    assert schedule is not None
    for row in schedule["items"]:
        if row.get("account_id") == account_id and row.get("check_number") == check_number:
            return row
    raise KeyError((account_id, check_number))


def _escheat_item(
    payload: dict[str, Any], account_id: str, check_number: str
) -> dict[str, Any]:
    schedule = _doc(payload, DOC_ESCHEATMENT_SCHEDULE)
    assert schedule is not None
    for row in schedule["items"]:
        if row.get("account_id") == account_id and row.get("check_number") == check_number:
            return row
    raise KeyError((account_id, check_number))


def _reconciliation(payload: dict[str, Any]) -> dict[str, Any]:
    doc = _doc(payload, DOC_BANK_RECONCILIATION)
    assert doc is not None
    return doc


def _bucket(payload: dict[str, Any], label: str) -> dict[str, Any]:
    for row in _reconciliation(payload)["bucket_totals"]:
        if row.get("bucket") == label:
            return row
    raise KeyError(label)


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def rederive(payload: dict[str, Any]) -> None:
    """Recompute every derived schedule from the payload's own base facts."""
    account_doc = _doc(payload, DOC_ACCOUNT_REGISTER)
    check_doc = _doc(payload, DOC_CHECK_REGISTER)
    void_doc = _doc(payload, DOC_VOID_REGISTER)
    outstanding = _doc(payload, DOC_OUTSTANDING_SCHEDULE)
    escheatment = _doc(payload, DOC_ESCHEATMENT_SCHEDULE)
    reconciliation = _doc(payload, DOC_BANK_RECONCILIATION)
    if not all((account_doc, check_doc, void_doc, outstanding, escheatment, reconciliation)):
        return
    assert outstanding is not None
    assert escheatment is not None
    assert reconciliation is not None

    ctx = Context(path=Path("<generated>"), data=payload)
    as_of = date.fromisoformat(payload["as_of"])
    dormancy = payload.get("dormancy_days", DEFAULT_DORMANCY_DAYS)

    # Outstanding schedule: nothing cleared, nothing withdrawn, aged to as_of and
    # bucketed through the shared kernel the engine recomputes with.
    items = recompute_outstanding(ctx, as_of)
    outstanding["items"] = items

    # Escheatment schedule: the outstanding items that have run the full dormancy
    # period, addressed to their account's declared jurisdiction.
    escheatment["items"] = recompute_escheatment(ctx, as_of, dormancy)

    # Bank reconciliation: the outstanding-checks line and the aging profile,
    # both derived from the same set.
    reconciliation["outstanding_checks_cents"] = sum(
        int(item["amount_cents"]) for item in items
    )
    reconciliation["outstanding_count"] = len(items)
    reconciliation["bucket_totals"] = recompute_bucket_totals(ctx, as_of)


def baseline(portfolio: str) -> dict[str, Any]:
    """Build a clean aging file for ``portfolio``."""
    payload: dict[str, Any] = {
        "file_id": "clean",
        "portfolio": portfolio,
        "period": PERIOD,
        "as_of": AS_OF,
        "stale_dated_days": STALE_DATED_DAYS,
        "dormancy_days": DORMANCY_DAYS,
        "documents": [
            {
                "doc_type": DOC_ACCOUNT_REGISTER,
                "document_id": "ACCOUNTS-2029",
                "accounts": [
                    {
                        "account_id": account_id,
                        "description": description,
                        "escheat_jurisdiction": jurisdiction,
                    }
                    for account_id, description, jurisdiction in ACCOUNTS
                ],
            },
            {
                "doc_type": DOC_CHECK_REGISTER,
                "document_id": "CHECKS-2029",
                "checks": [
                    {
                        "check_number": check_number,
                        "account_id": account_id,
                        "check_date": check_date,
                        "check_type": check_type,
                        "payee": payee,
                        "check_amount_cents": d(check_amount),
                        "cleared_amount_cents": d(cleared_amount),
                        "cleared_date": cleared_date,
                    }
                    for (
                        check_number, account_id, check_date, check_type, payee,
                        check_amount, cleared_amount, cleared_date,
                    ) in CHECKS
                ],
            },
            {
                "doc_type": DOC_VOID_REGISTER,
                "document_id": "VOIDS-2029",
                "entries": [
                    {
                        "check_number": check_number,
                        "account_id": account_id,
                        "disposition": disposition,
                        "void_date": void_date,
                        "void_amount_cents": d(void_amount),
                    }
                    for check_number, account_id, disposition, void_date, void_amount in VOIDS
                ],
            },
            {
                "doc_type": DOC_OUTSTANDING_SCHEDULE,
                "document_id": "OUTSTANDING-2029",
                "items": [],
            },
            {
                "doc_type": DOC_ESCHEATMENT_SCHEDULE,
                "document_id": "ESCHEAT-2029",
                "items": [],
            },
            {
                "doc_type": DOC_BANK_RECONCILIATION,
                "document_id": "BANKREC-2029",
                "outstanding_checks_cents": 0,
                "outstanding_count": 0,
                "bucket_totals": [],
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
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_BANK_RECONCILIATION
    ]


def _duplicate_account_id(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_ACCOUNT_REGISTER)
    assert register is not None
    register["accounts"].append(dict(_account(payload, "BNK-100")))


def _missing_jurisdiction(payload: dict[str, Any]) -> None:
    del _account(payload, "BNK-200")["escheat_jurisdiction"]


def _check_missing_field(payload: dict[str, Any]) -> None:
    del _check(payload, "BNK-100", "CHK-4105")["payee"]


def _duplicate_check_number(payload: dict[str, Any]) -> None:
    # The same number recorded twice in one account. The duplicate is a cleared
    # check, so the outstanding set is untouched and only the uniqueness control
    # sees it.
    register = _doc(payload, DOC_CHECK_REGISTER)
    assert register is not None
    register["checks"].append(dict(_check(payload, "BNK-100", "CHK-4110")))


def _unknown_account_check(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_CHECK_REGISTER)
    assert register is not None
    register["checks"].append(
        {
            "check_number": "CHK-4301",
            "account_id": "BNK-900",
            "check_date": "2029-07-18",
            "check_type": CHECK_TYPE_SYSTEM,
            "payee": "Harborline Freight",
            "check_amount_cents": d(1_900.00),
            "cleared_amount_cents": d(1_900.00),
            "cleared_date": "2029-07-25",
        }
    )


def _bad_check_type(payload: dict[str, Any]) -> None:
    _check(payload, "BNK-100", "CHK-4103")["check_type"] = "wire"


def _check_dated_after_as_of(payload: dict[str, Any]) -> None:
    # A cleared check re-dated past the as-of date, so the negative age it would
    # produce is the whole of the defect.
    _check(payload, "BNK-100", "CHK-4110")["check_date"] = "2029-10-15"


def _cleared_without_date(payload: dict[str, Any]) -> None:
    _check(payload, "BNK-100", "CHK-4101")["cleared_date"] = None


def _cleared_amount_differs(payload: dict[str, Any]) -> None:
    # One cent short of the amount issued: the item is off the outstanding
    # schedule because something cleared, and the difference is carried nowhere.
    _check(payload, "BNK-100", "CHK-4102")["cleared_amount_cents"] -= 1


def _bad_void_disposition(payload: dict[str, Any]) -> None:
    _void(payload, "BNK-100", "CHK-4109")["disposition"] = "reissued"


def _void_listed_outstanding(payload: dict[str, Any]) -> None:
    # A withdrawn check put back on the outstanding schedule with an otherwise
    # correct age and band, so only the void control sees it.
    schedule = _doc(payload, DOC_OUTSTANDING_SCHEDULE)
    assert schedule is not None
    schedule["items"].append(
        {
            "account_id": "BNK-100",
            "check_number": "CHK-4109",
            "check_date": "2029-07-10",
            "amount_cents": d(4_500.00),
            "age_days": 82,
            "aging_bucket": "61-90",
            "follow_up_required": False,
        }
    )
    schedule["items"].sort(key=lambda e: (e["account_id"], e["check_number"]))


def _void_not_netted(payload: dict[str, Any]) -> None:
    _void(payload, "BNK-200", "CHK-4107")["void_amount_cents"] = -d(7_000.00)


def _outstanding_row_missing(payload: dict[str, Any]) -> None:
    schedule = _doc(payload, DOC_OUTSTANDING_SCHEDULE)
    assert schedule is not None
    schedule["items"] = [
        row
        for row in schedule["items"]
        if not (row["account_id"] == "BNK-100" and row["check_number"] == "CHK-4105")
    ]


def _wrong_aging_bucket(payload: dict[str, Any]) -> None:
    # 94 days is the 91-180 band; stated one band younger, which is how an item
    # drifts out of the follow-up population without its age ever changing.
    _outstanding_item(payload, "BNK-100", "CHK-4106")["aging_bucket"] = "61-90"


def _follow_up_not_flagged(payload: dict[str, Any]) -> None:
    _outstanding_item(payload, "BNK-100", "CHK-4107")["follow_up_required"] = False


def _escheatment_row_missing(payload: dict[str, Any]) -> None:
    schedule = _doc(payload, DOC_ESCHEATMENT_SCHEDULE)
    assert schedule is not None
    schedule["items"] = [
        row
        for row in schedule["items"]
        if not (row["account_id"] == "BNK-100" and row["check_number"] == "CHK-4111")
    ]


def _wrong_escheat_jurisdiction(payload: dict[str, Any]) -> None:
    _escheat_item(payload, "BNK-200", "CHK-4103")["escheat_jurisdiction"] = "State of Marran"


def _bank_rec_total_wrong(payload: dict[str, Any]) -> None:
    _reconciliation(payload)["outstanding_checks_cents"] += d(1_000.00)


def _bucket_total_overstated(payload: dict[str, Any]) -> None:
    _bucket(payload, "31-60")["amount_cents"] += d(50.00)


def _amount_not_integer(payload: dict[str, Any]) -> None:
    row = _check(payload, "BNK-100", "CHK-4104")
    row["check_amount_cents"] = float(row["check_amount_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "duplicate_account_id": ("acct_unique_ids", _duplicate_account_id),
    "missing_jurisdiction": ("acct_jurisdiction_declared", _missing_jurisdiction),
    "check_missing_field": ("chk_required_fields", _check_missing_field),
    "duplicate_check_number": ("chk_number_unique_per_account", _duplicate_check_number),
    "unknown_account_check": ("chk_account_exists", _unknown_account_check),
    "bad_check_type": ("chk_type_valid", _bad_check_type),
    "check_dated_after_as_of": ("chk_date_not_future", _check_dated_after_as_of),
    "cleared_without_date": ("chk_cleared_pairing", _cleared_without_date),
    "cleared_amount_differs": ("chk_cleared_ties_issued", _cleared_amount_differs),
    "bad_void_disposition": ("void_disposition_valid", _bad_void_disposition),
    "void_listed_outstanding": ("void_not_outstanding", _void_listed_outstanding),
    "void_not_netted": ("void_nets_to_zero", _void_not_netted),
    "outstanding_row_missing": ("age_outstanding_set_recomputes", _outstanding_row_missing),
    "wrong_aging_bucket": ("age_bucket_recomputes", _wrong_aging_bucket),
    "follow_up_not_flagged": ("age_stale_dated_flagged", _follow_up_not_flagged),
    "escheatment_row_missing": ("esc_set_recomputes", _escheatment_row_missing),
    "wrong_escheat_jurisdiction": ("esc_jurisdiction_assigned", _wrong_escheat_jurisdiction),
    "bank_rec_total_wrong": ("rpt_outstanding_total_ties", _bank_rec_total_wrong),
    "bucket_total_overstated": ("rpt_bucket_totals_tie", _bucket_total_overstated),
    "amount_not_integer": ("age_outstanding_set_recomputes", _amount_not_integer),
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
