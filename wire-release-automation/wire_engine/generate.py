"""
Fictional wire & transfer release-control corpus generator.
===========================================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The operating entities, the signers, the banks, the
routing numbers, the beneficiaries, the amounts and the dates are fictional, and
the release period is set in a fictional future. No real entity, person, bank,
project or path appears anywhere. The generator is deterministic and takes no
seed.

The baseline is derived, not typed
----------------------------------
Only the accounts, signers, banks, beneficiary templates, wire packets and posted
log are stated as base facts. Everything the engine later checks as a rollup --
each packet's releasable determination and the releasable / blocked counts -- is
recomputed by :func:`rederive` from those base facts, through the *same*
:mod:`wire_engine.release` kernel the engine recomputes with. So the
relationships the engine tests are the relationships that produced the data.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from .engine import _wire_id, _wires, recompute_wire_releasable
from .model import (
    DOC_ACCOUNT_REGISTER,
    DOC_BANK_DIRECTORY,
    DOC_BENEFICIARY_REGISTER,
    DOC_POSTED_LOG,
    DOC_RELEASE_REPORT,
    DOC_RELEASE_SUMMARY,
    DOC_SIGNER_REGISTER,
    DOC_WIRE_REGISTER,
    REQUEST_BOOK_TRANSFER,
    REQUEST_WIRE,
    STAGE_PENDING,
    STAGE_POSTED,
    STAGE_SCHEDULED,
    Context,
)

#: Fictional operating-entity labels, rotated for file identity only.
ENTITIES: tuple[str, ...] = (
    "Northmoor Development Group",
    "Halbrook Residential",
    "Stonecrest Communities",
    "Ardenne Field Partners",
    "Westmere",
)

PERIOD = "FY2030"
#: The stated release/review date the daily log is measured to.
AS_OF = "2030-03-20"
#: Window, in days, for the duplicate-payment check.
DUPLICATE_WINDOW_DAYS = 5


def d(dollars: float) -> int:
    """Dollars to integer cents."""
    return round(dollars * 100)


#: ``(account_id, account_name, bank_name, available_dollars)``. Fictional
#: funding accounts; the available balance is the per-release-date figure the
#: sufficiency control tests each amount against.
ACCOUNTS: tuple[tuple[Any, ...], ...] = (
    ("ACCT-100", "Operating Concentration", "Harborline Bank", 5_000_000),
    ("ACCT-200", "Distributions", "Harborline Bank", 2_000_000),
    ("ACCT-300", "Payroll Funding", "Vantage Trust", 1_000_000),
)

#: ``(signer_id, name, account_id, authority_limit_dollars)``. Each used account
#: carries two signers so a packet can name two distinct authorized people.
SIGNERS: tuple[tuple[Any, ...], ...] = (
    ("SGN-01", "Rowan Ashford", "ACCT-100", 3_000_000),
    ("SGN-02", "Marlowe Quill", "ACCT-100", 3_000_000),
    ("SGN-03", "Sable Winters", "ACCT-200", 1_500_000),
    ("SGN-04", "Devin Marsh", "ACCT-200", 1_500_000),
    ("SGN-05", "Corin Vale", "ACCT-300", 1_000_000),
    ("SGN-06", "Emory Frost", "ACCT-300", 1_000_000),
)

#: ``(receiving_aba, bank_name)``. Invented banks with routing numbers that pass
#: the ABA checksum but begin with district prefixes no real routing number uses.
BANKS: tuple[tuple[str, str], ...] = (
    ("991000106", "Harborline Bank"),
    ("992000024", "Vantage Trust"),
    ("983000033", "Kelder Union Bank"),
    ("984000045", "Marran State Bank"),
    ("975000054", "Copperline Federal"),
)

#: ``(template_id, receiving_aba, beneficiary_account, beneficiary_name,
#:   receiving_bank_name)``. Each row is one approved-beneficiary whitelist entry.
TEMPLATES: tuple[tuple[str, ...], ...] = (
    ("BEN-01", "991000106", "4471180022", "Brightwater Commons LLC", "Harborline Bank"),
    ("BEN-02", "983000033", "5560294417", "Copperfield Yards Vendors LLC", "Kelder Union Bank"),
    ("BEN-03", "984000045", "6689013345", "Alderpoint Terraces LP", "Marran State Bank"),
    ("BEN-04", "975000054", "7712556690", "Dunmore Flats Escrow", "Copperline Federal"),
    ("BEN-05", "992000024", "8834200156", "Westmere Holdings LLC", "Vantage Trust"),
)

#: ``(wire_id, request_type, from_account, initiated_by, authorized_by,
#:   initiated_date, authorized_date, receiving_aba, receiving_bank_name,
#:   beneficiary_account, beneficiary_name, template_id, on_template,
#:   callback_completed, amount_dollars, stage, posted_ref, value_date)``.
#: Book transfers are internal and carry empty routing/beneficiary-template
#: fields. Every baseline packet clears every hard control.
WIRES: tuple[tuple[Any, ...], ...] = (
    ("W-1001", REQUEST_WIRE, "ACCT-100", "SGN-01", "SGN-02", "2030-03-01", "2030-03-02",
     "991000106", "Harborline Bank", "4471180022", "Brightwater Commons LLC", "BEN-01", True, True,
     1_200_000, STAGE_POSTED, "P-9001", "2030-03-03"),
    ("W-1002", REQUEST_WIRE, "ACCT-200", "SGN-03", "SGN-04", "2030-03-05", "2030-03-06",
     "983000033", "Kelder Union Bank", "5560294417", "Copperfield Yards Vendors LLC", "BEN-02", True, True,
     800_000, STAGE_SCHEDULED, "", "2030-03-08"),
    ("W-1003", REQUEST_BOOK_TRANSFER, "ACCT-100", "SGN-02", "SGN-01", "2030-03-07", "2030-03-07",
     "", "", "3300110099", "Operating to Reserve Sweep", "", True, True,
     500_000, STAGE_POSTED, "P-9003", "2030-03-07"),
    ("W-1004", REQUEST_WIRE, "ACCT-200", "SGN-04", "SGN-03", "2030-03-09", "2030-03-10",
     "984000045", "Marran State Bank", "6689013345", "Alderpoint Terraces LP", "BEN-03", True, True,
     1_000_000, STAGE_SCHEDULED, "", "2030-03-12"),
    ("W-1005", REQUEST_WIRE, "ACCT-100", "SGN-01", "SGN-02", "2030-03-11", "2030-03-12",
     "975000054", "Copperline Federal", "7712556690", "Dunmore Flats Escrow", "BEN-04", True, True,
     2_500_000, STAGE_SCHEDULED, "", "2030-03-14"),
    ("W-1006", REQUEST_BOOK_TRANSFER, "ACCT-300", "SGN-05", "SGN-06", "2030-03-13", "2030-03-13",
     "", "", "3300220088", "Payroll to Operating Sweep", "", True, True,
     400_000, STAGE_PENDING, "", "2030-03-16"),
    ("W-1007", REQUEST_WIRE, "ACCT-300", "SGN-05", "SGN-06", "2030-03-14", "2030-03-15",
     "992000024", "Vantage Trust", "8834200156", "Westmere Holdings LLC", "BEN-05", True, True,
     300_000, STAGE_POSTED, "P-9007", "2030-03-15"),
)

#: ``(posted_id, wire_id, beneficiary_account, amount_dollars, posted_date)``. One
#: execution record per posted packet in :data:`WIRES`.
POSTINGS: tuple[tuple[Any, ...], ...] = (
    ("P-9001", "W-1001", "4471180022", 1_200_000, "2030-03-03"),
    ("P-9003", "W-1003", "3300110099", 500_000, "2030-03-07"),
    ("P-9007", "W-1007", "8834200156", 300_000, "2030-03-15"),
)


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _wire(payload: dict[str, Any], wire_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_WIRE_REGISTER)
    assert register is not None
    for row in register["wires"]:
        if row.get("wire_id") == wire_id:
            return row
    raise KeyError(wire_id)


def _account_row(payload: dict[str, Any], account_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_ACCOUNT_REGISTER)
    assert register is not None
    for row in register["accounts"]:
        if row.get("account_id") == account_id:
            return row
    raise KeyError(account_id)


def _summary_row(payload: dict[str, Any], wire_id: str) -> dict[str, Any]:
    summary = _doc(payload, DOC_RELEASE_SUMMARY)
    assert summary is not None
    for row in summary["wires"]:
        if row.get("wire_id") == wire_id:
            return row
    raise KeyError(wire_id)


def _report(payload: dict[str, Any]) -> dict[str, Any]:
    report = _doc(payload, DOC_RELEASE_REPORT)
    assert report is not None
    return report


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def rederive(payload: dict[str, Any]) -> None:
    """Recompute every rollup figure from the payload's own base facts."""
    summary = _doc(payload, DOC_RELEASE_SUMMARY)
    report = _doc(payload, DOC_RELEASE_REPORT)
    if summary is None or report is None:
        return

    ctx = Context(path=Path("<generated>"), data=payload)

    # Release summary: one releasable determination per packet, recomputed through
    # the shared kernel the engine recomputes with.
    summary["wires"] = [
        {"wire_id": _wire_id(w), "releasable": recompute_wire_releasable(ctx, w)}
        for w in _wires(ctx)
    ]

    # Release report: the daily counts, derived from the summary flags.
    releasable = sum(1 for row in summary["wires"] if row["releasable"])
    total = len(summary["wires"])
    report["releasable_count"] = releasable
    report["blocked_count"] = total - releasable


def baseline(entity: str) -> dict[str, Any]:
    """Build a clean release-control file for ``entity``."""
    payload: dict[str, Any] = {
        "file_id": "clean",
        "entity": entity,
        "period": PERIOD,
        "as_of": AS_OF,
        "duplicate_window_days": DUPLICATE_WINDOW_DAYS,
        "documents": [
            {
                "doc_type": DOC_ACCOUNT_REGISTER,
                "document_id": "ACCOUNTS-2030",
                "accounts": [
                    {
                        "account_id": account_id,
                        "account_name": account_name,
                        "bank_name": bank_name,
                        "available_cents": d(available),
                    }
                    for account_id, account_name, bank_name, available in ACCOUNTS
                ],
            },
            {
                "doc_type": DOC_SIGNER_REGISTER,
                "document_id": "SIGNERS-2030",
                "signers": [
                    {
                        "signer_id": signer_id,
                        "name": name,
                        "account_id": account_id,
                        "authority_limit_cents": d(limit),
                    }
                    for signer_id, name, account_id, limit in SIGNERS
                ],
            },
            {
                "doc_type": DOC_BANK_DIRECTORY,
                "document_id": "BANKS-2030",
                "banks": [
                    {"receiving_aba": aba, "bank_name": bank_name}
                    for aba, bank_name in BANKS
                ],
            },
            {
                "doc_type": DOC_BENEFICIARY_REGISTER,
                "document_id": "BENEFICIARIES-2030",
                "templates": [
                    {
                        "template_id": template_id,
                        "receiving_aba": aba,
                        "beneficiary_account": account,
                        "beneficiary_name": name,
                        "receiving_bank_name": bank_name,
                    }
                    for template_id, aba, account, name, bank_name in TEMPLATES
                ],
            },
            {
                "doc_type": DOC_WIRE_REGISTER,
                "document_id": "WIRES-2030",
                "wires": [
                    {
                        "wire_id": wire_id,
                        "request_type": request_type,
                        "from_account": from_account,
                        "initiated_by": initiated_by,
                        "authorized_by": authorized_by,
                        "initiated_date": initiated_date,
                        "authorized_date": authorized_date,
                        "receiving_aba": aba,
                        "receiving_bank_name": bank_name,
                        "beneficiary_account": beneficiary_account,
                        "beneficiary_name": beneficiary_name,
                        "template_id": template_id,
                        "on_template": on_template,
                        "callback_completed": callback,
                        "amount_cents": d(amount),
                        "stage": stage,
                        "posted_ref": posted_ref,
                        "value_date": value_date,
                    }
                    for (
                        wire_id, request_type, from_account, initiated_by, authorized_by,
                        initiated_date, authorized_date, aba, bank_name, beneficiary_account,
                        beneficiary_name, template_id, on_template, callback, amount, stage,
                        posted_ref, value_date,
                    ) in WIRES
                ],
            },
            {
                "doc_type": DOC_POSTED_LOG,
                "document_id": "POSTED-2030",
                "postings": [
                    {
                        "posted_id": posted_id,
                        "wire_id": wire_id,
                        "beneficiary_account": beneficiary_account,
                        "amount_cents": d(amount),
                        "posted_date": posted_date,
                    }
                    for posted_id, wire_id, beneficiary_account, amount, posted_date in POSTINGS
                ],
            },
            {
                "doc_type": DOC_RELEASE_SUMMARY,
                "document_id": "SUMMARY-2030",
                "wires": [],
            },
            {
                "doc_type": DOC_RELEASE_REPORT,
                "document_id": "REPORT-2030",
                "releasable_count": 0,
                "blocked_count": 0,
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
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_RELEASE_REPORT
    ]


def _same_signer(payload: dict[str, Any]) -> None:
    # One person both initiated and authorized the packet.
    _wire(payload, "W-1005")["authorized_by"] = "SGN-01"


def _incomplete_dual_auth(payload: dict[str, Any]) -> None:
    # A scheduled packet with the second signature's date never filled in.
    _wire(payload, "W-1002")["authorized_date"] = ""


def _auth_before_init(payload: dict[str, Any]) -> None:
    # Authorized the day before it was initiated.
    _wire(payload, "W-1004")["authorized_date"] = "2030-03-08"


def _initiator_not_signer(payload: dict[str, Any]) -> None:
    # The initiator is a real signer, but on a different account.
    _wire(payload, "W-1005")["initiated_by"] = "SGN-03"


def _authorizer_not_signer(payload: dict[str, Any]) -> None:
    # The authorizer is a real signer, but not on this packet's account.
    _wire(payload, "W-1002")["authorized_by"] = "SGN-01"


def _over_authority_limit(payload: dict[str, Any]) -> None:
    # A cent over the authorizer's authority, still within the funding balance.
    _wire(payload, "W-1005")["amount_cents"] = d(3_000_000) + 1


def _template_missing(payload: dict[str, Any]) -> None:
    _wire(payload, "W-1004")["template_id"] = "BEN-999"


def _triplet_mismatch(payload: dict[str, Any]) -> None:
    # The template id is real, but the account number does not match it.
    _wire(payload, "W-1002")["beneficiary_account"] = "5560299999"


def _off_template_no_callback(payload: dict[str, Any]) -> None:
    wire = _wire(payload, "W-1005")
    wire["on_template"] = False
    wire["callback_completed"] = False


def _off_template_with_callback(payload: dict[str, Any]) -> None:
    # Off template but callback complete: a review FLAG, not a hard block.
    wire = _wire(payload, "W-1004")
    wire["on_template"] = False
    wire["callback_completed"] = True


def _book_transfer_has_aba(payload: dict[str, Any]) -> None:
    # An internal transfer carrying external routing detail it should not have.
    wire = _wire(payload, "W-1003")
    wire["receiving_aba"] = "991000106"
    wire["receiving_bank_name"] = "Harborline Bank"


def _bad_check_digit(payload: dict[str, Any]) -> None:
    # Last digit flipped so the ABA checksum fails.
    _wire(payload, "W-1007")["receiving_aba"] = "992000025"


def _bank_name_mismatch(payload: dict[str, Any]) -> None:
    # Valid routing number, but the printed bank name resolves to another bank.
    _wire(payload, "W-1002")["receiving_bank_name"] = "Copperline Federal"


def _account_missing(payload: dict[str, Any]) -> None:
    _wire(payload, "W-1006")["from_account"] = "ACCT-999"


def _funding_shortfall(payload: dict[str, Any]) -> None:
    # Drop the funding balance below a scheduled wire drawn on it.
    _account_row(payload, "ACCT-200")["available_cents"] = d(900_000)


def _duplicate_wire_id(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_WIRE_REGISTER)
    assert register is not None
    register["wires"].append(dict(_wire(payload, "W-1002")))


def _already_posted(payload: dict[str, Any]) -> None:
    # A scheduled packet that duplicates the already-posted W-1007 payment.
    register = _doc(payload, DOC_WIRE_REGISTER)
    assert register is not None
    register["wires"].append(
        {
            "wire_id": "W-1008",
            "request_type": REQUEST_WIRE,
            "from_account": "ACCT-300",
            "initiated_by": "SGN-05",
            "authorized_by": "SGN-06",
            "initiated_date": "2030-03-16",
            "authorized_date": "2030-03-16",
            "receiving_aba": "992000024",
            "receiving_bank_name": "Vantage Trust",
            "beneficiary_account": "8834200156",
            "beneficiary_name": "Westmere Holdings LLC",
            "template_id": "BEN-05",
            "on_template": True,
            "callback_completed": True,
            "amount_cents": d(300_000),
            "stage": STAGE_SCHEDULED,
            "posted_ref": "",
            "value_date": "2030-03-17",
        }
    )


def _unknown_stage(payload: dict[str, Any]) -> None:
    _wire(payload, "W-1005")["stage"] = "draft"


def _posted_no_approval(payload: dict[str, Any]) -> None:
    # A posted packet released with its second signature's date blank.
    _wire(payload, "W-1001")["authorized_date"] = ""


def _posted_ref_broken(payload: dict[str, Any]) -> None:
    _wire(payload, "W-1007")["posted_ref"] = "P-9999"


def _release_flag_wrong(payload: dict[str, Any]) -> None:
    # The stated determination contradicts the evidence; the count is moved with
    # it so only the recompute control sees the break.
    _summary_row(payload, "W-1005")["releasable"] = False
    report = _report(payload)
    report["releasable_count"] -= 1
    report["blocked_count"] += 1


def _report_count_wrong(payload: dict[str, Any]) -> None:
    _report(payload)["releasable_count"] += 1


def _amount_not_integer(payload: dict[str, Any]) -> None:
    wire = _wire(payload, "W-1001")
    wire["amount_cents"] = float(wire["amount_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "same_signer": ("sod_two_distinct_signers", _same_signer),
    "incomplete_dual_auth": ("sod_dual_auth_complete", _incomplete_dual_auth),
    "auth_before_init": ("sod_auth_not_before_init", _auth_before_init),
    "initiator_not_signer": ("sig_initiator_authorized", _initiator_not_signer),
    "authorizer_not_signer": ("sig_authorizer_authorized", _authorizer_not_signer),
    "over_authority_limit": ("sig_within_authority_limit", _over_authority_limit),
    "template_missing": ("ben_template_exists", _template_missing),
    "triplet_mismatch": ("ben_triplet_matches_template", _triplet_mismatch),
    "off_template_no_callback": ("ben_new_account_callback", _off_template_no_callback),
    "off_template_with_callback": ("ben_off_template_review", _off_template_with_callback),
    "book_transfer_has_aba": ("aba_classification_fields", _book_transfer_has_aba),
    "bad_check_digit": ("aba_check_digit_valid", _bad_check_digit),
    "bank_name_mismatch": ("aba_resolves_to_bank_name", _bank_name_mismatch),
    "account_missing": ("fund_account_exists", _account_missing),
    "funding_shortfall": ("fund_sufficient_balance", _funding_shortfall),
    "duplicate_wire_id": ("dup_wire_ids_unique", _duplicate_wire_id),
    "already_posted": ("dup_not_already_posted", _already_posted),
    "unknown_stage": ("flow_stage_valid", _unknown_stage),
    "posted_no_approval": ("flow_posted_has_approval", _posted_no_approval),
    "posted_ref_broken": ("flow_posted_ref_ties", _posted_ref_broken),
    "release_flag_wrong": ("rpt_release_flag_recomputes", _release_flag_wrong),
    "report_count_wrong": ("rpt_report_count_ties", _report_count_wrong),
    "amount_not_integer": ("fund_sufficient_balance", _amount_not_integer),
}


# --------------------------------------------------------------------------- #
# Corpus writer
# --------------------------------------------------------------------------- #
def generate_corpus(folder: Path) -> list[Path]:
    """Write the fictional corpus into ``folder`` and return the paths written."""
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    files: list[dict[str, Any]] = []
    clean = baseline(ENTITIES[0])
    clean["file_id"] = f"clean__{ENTITIES[0].replace(' ', '_')}"
    files.append(clean)

    for i, name in enumerate(sorted(DEFECTS)):
        _rule, mutate = DEFECTS[name]
        entity = ENTITIES[(i + 1) % len(ENTITIES)]
        f = baseline(entity)
        f["file_id"] = f"{name}__{entity.replace(' ', '_')}"
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
