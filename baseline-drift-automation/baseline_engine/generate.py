"""
Fictional corpus generator for the baseline & version drift engine.
===================================================================

Builds one clean cycle file plus one file per planted defect. The clean file is
constructed **through the same kernel the controls use** (:mod:`.budget`), so the
corpus cannot drift from the derivation the engine audits: every copy's lines,
the billing instrument's change columns, the derived schedule's instalments and
the stated totals are all re-derived here rather than typed.

Each defect file starts from a fresh baseline and applies exactly one mutation,
so a defect file demonstrates its control firing. Mutations are applied **after**
re-derivation, which is what makes them defects rather than a differently-shaped
truth. Some mutations necessarily disturb a second control -- moving one line in
one copy changes that copy's total as well as that copy's line -- and the tests
assert the targeted control fired, not that it fired alone.

Every name, category, date and amount here is invented. No real project, entity,
place or ledger appears anywhere in this package.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .budget import amortisation_schedule, budget_total
from .model import (
    CHANGE_APPROVED,
    CHANGE_PENDING,
    DOC_AGREEMENT,
    DOC_AMENDMENT_LOG,
    DOC_BUDGET_VERSION,
    DOC_DERIVED_SCHEDULE,
    DOC_FUNDING_REGISTER,
    DOC_MILESTONE_SET,
    PHASE_POST,
    PHASE_PRE,
    ROLE_BASELINE,
    ROLE_BILLING,
    ROLE_SUMMARY,
    ROLE_WORKING,
)

#: Fictional projects whose reporting cycles the corpus carries.
PROJECTS: tuple[str, ...] = (
    "Brightwater Commons",
    "Copperfield Yards",
    "Alderpoint Terraces",
    "Dunmore Flats",
)

#: The budget line set every copy of a project's budget carries.
#: ``(category, phase, amount_cents, locked)``
LINES: tuple[tuple[str, str, int, bool], ...] = (
    ("Land", PHASE_PRE, 650_000_000, True),
    ("Consultants", PHASE_PRE, 160_000_000, False),
    ("Permits", PHASE_PRE, 23_800_000, False),
    ("Legal and Accounting", PHASE_PRE, 20_000_000, False),
    ("Finance Costs", PHASE_PRE, 10_000_000, False),
    ("Site Works", PHASE_POST, 792_086_000, False),
    ("Vertical Construction", PHASE_POST, 984_603_900, False),
    ("Contingency", PHASE_POST, 128_438_800, False),
    ("Insurance", PHASE_POST, 57_800_000, False),
    ("Marketing", PHASE_POST, 23_630_200, False),
    ("Sponsor Fee", PHASE_POST, 141_781_300, False),
    ("Loan Interest", PHASE_POST, 191_318_300, False),
)

#: The single approved amendment the clean cycle carries, so the traceability
#: control is exercised by the clean file rather than only by its defect.
APPROVED_CATEGORY = "Consultants"
APPROVED_AMOUNT_CENTS = 5_000_000

#: A pending amendment that must NOT appear in the billing instrument.
PENDING_CATEGORY = "Permits"
PENDING_AMOUNT_CENTS = 2_000_000

#: Member commitments, identical in every copy that states them.
COMMITMENTS: dict[str, int] = {"investor": 500_000_000, "sponsor": 500_000_000}

EXECUTED_DATE = "2030-11-18"
PERIOD_START = "2031-04-01"
PERIOD_END = "2031-06-30"
AS_OF = "2031-07-15"

SCHEDULE_PERIODS = 22
SCHEDULE_ADVANCES_CENTS = 38_000_000
SCHEDULE_CAP_CENTS = 48_000_000


# --------------------------------------------------------------------------- #
# Baseline construction
# --------------------------------------------------------------------------- #
def _lines(with_changes: bool = False) -> list[dict[str, Any]]:
    """The shared line set; the billing copy additionally carries change columns."""
    rows: list[dict[str, Any]] = []
    for category, phase, amount, locked in LINES:
        row: dict[str, Any] = {
            "category": category,
            "phase": phase,
            "amount_cents": amount,
        }
        if locked:
            row["locked"] = True
        if with_changes:
            current = APPROVED_AMOUNT_CENTS if category == APPROVED_CATEGORY else 0
            row["approved_cents"] = amount - current
            row["previous_changes_cents"] = 0
            row["current_changes_cents"] = current
        rows.append(row)
    return rows


def _version(doc_id: str, role: str, prepared: str, **extra: Any) -> dict[str, Any]:
    version: dict[str, Any] = {
        "doc_type": DOC_BUDGET_VERSION,
        "document_id": doc_id,
        "role": role,
        "prepared_date": prepared,
        "lines": _lines(with_changes=(role == ROLE_BILLING)),
        "commitments": dict(COMMITMENTS),
    }
    version.update(extra)
    version["stated_total_cents"] = budget_total(version)
    return version


def baseline(project: str) -> dict[str, Any]:
    """Build one clean cycle file for ``project``.

    Every derived figure here is produced by the same kernel the controls use, so
    a clean file is clean because the derivation agrees, not because the numbers
    were chosen to agree.
    """
    sponsor_fee = next(amount for cat, _p, amount, _l in LINES if cat == "Sponsor Fee")
    base_cents = sponsor_fee - SCHEDULE_ADVANCES_CENTS

    documents: list[dict[str, Any]] = [
        {
            "doc_type": DOC_AGREEMENT,
            "document_id": "AGR-1",
            "executed_date": EXECUTED_DATE,
            "baseline_document_id": "BV-BASE",
            "phase": PHASE_PRE,
            "splits": {
                PHASE_PRE: {"investor": 5000, "sponsor": 5000},
                PHASE_POST: {"investor": 9000, "sponsor": 1000},
            },
        },
        _version("BV-BASE", ROLE_BASELINE, EXECUTED_DATE),
        _version("BV-WORK", ROLE_WORKING, "2031-06-20", cost_through_date=PERIOD_END),
        _version("BV-BILL", ROLE_BILLING, "2031-06-25", cost_through_date=PERIOD_END),
        _version("BV-SUMM", ROLE_SUMMARY, "2031-06-28"),
        {
            "doc_type": DOC_AMENDMENT_LOG,
            "document_id": "AMD-1",
            "amendments": [
                {
                    "amendment_id": "A-01",
                    "category": APPROVED_CATEGORY,
                    "amount_cents": APPROVED_AMOUNT_CENTS,
                    "state": CHANGE_APPROVED,
                    "approved_date": "2031-05-14",
                },
                {
                    "amendment_id": "A-02",
                    "category": PENDING_CATEGORY,
                    "amount_cents": PENDING_AMOUNT_CENTS,
                    "state": CHANGE_PENDING,
                    "approved_date": None,
                },
            ],
        },
        {
            "doc_type": DOC_MILESTONE_SET,
            "document_id": "MS-1",
            "milestones": [
                {"milestone_id": "land_closing", "date": "2032-05-01"},
                {"milestone_id": "construction_start", "date": "2032-06-01"},
                {"milestone_id": "construction_end", "date": "2034-04-01"},
                {"milestone_id": "first_delivery", "date": "2034-07-01"},
            ],
        },
        {
            "doc_type": DOC_DERIVED_SCHEDULE,
            "document_id": "DS-1",
            "schedule_id": "sponsor_fee",
            "total_cents": sponsor_fee,
            "advances_cents": SCHEDULE_ADVANCES_CENTS,
            "cap_cents": SCHEDULE_CAP_CENTS,
            "base_cents": base_cents,
            "input_milestones": ["construction_start", "construction_end"],
            "periods": SCHEDULE_PERIODS,
            "instalments_cents": amortisation_schedule(base_cents, SCHEDULE_PERIODS),
        },
        {
            "doc_type": DOC_FUNDING_REGISTER,
            "document_id": "FR-1",
            "members": [
                {
                    "member_id": "investor",
                    "commitment_cents": COMMITMENTS["investor"],
                    "contributed_cents": 249_000_000,
                    "cap_cents": 825_000_000,
                    "split_bps": 5000,
                },
                {
                    "member_id": "sponsor",
                    "commitment_cents": COMMITMENTS["sponsor"],
                    "contributed_cents": 249_000_000,
                    "cap_cents": 557_395_000,
                    "split_bps": 5000,
                },
            ],
        },
    ]

    return {
        "file_id": "",
        "project": project,
        "period": "FY2031 Q2",
        "period_start": PERIOD_START,
        "period_end": PERIOD_END,
        "as_of": AS_OF,
        "materiality_cents": 100_000,
        "stale_days": 45,
        "documents": documents,
    }


# --------------------------------------------------------------------------- #
# Mutation helpers
# --------------------------------------------------------------------------- #
def _doc(f: dict[str, Any], doc_type: str) -> dict[str, Any]:
    return next(d for d in f["documents"] if d.get("doc_type") == doc_type)


def _ver(f: dict[str, Any], doc_id: str) -> dict[str, Any]:
    return next(
        d
        for d in f["documents"]
        if d.get("doc_type") == DOC_BUDGET_VERSION and d.get("document_id") == doc_id
    )


def _line(version: dict[str, Any], category: str) -> dict[str, Any]:
    return next(r for r in version["lines"] if r.get("category") == category)


def _restate(version: dict[str, Any]) -> None:
    """Re-derive a version's stated total after a mutation, so only one control fires."""
    version["stated_total_cents"] = budget_total(version)


# --------------------------------------------------------------------------- #
# Mutators -- one per control
# --------------------------------------------------------------------------- #
def _missing_artifact(f: dict[str, Any]) -> None:
    f["documents"] = [d for d in f["documents"] if d.get("doc_type") != DOC_AMENDMENT_LOG]


def _unknown_version_role(f: dict[str, Any]) -> None:
    _ver(f, "BV-SUMM")["role"] = "draft_for_discussion"


def _two_baselines(f: dict[str, Any]) -> None:
    _ver(f, "BV-WORK")["role"] = ROLE_BASELINE


def _baseline_predates_agreement(f: dict[str, Any]) -> None:
    _ver(f, "BV-BASE")["prepared_date"] = "2030-08-04"


def _version_from_next_period(f: dict[str, Any]) -> None:
    _ver(f, "BV-SUMM")["prepared_date"] = "2031-08-12"


def _category_renamed_in_copy(f: dict[str, Any]) -> None:
    _line(_ver(f, "BV-WORK"), "Marketing")["category"] = "Marketing and Sales"


def _line_differs_materially(f: dict[str, Any]) -> None:
    v = _ver(f, "BV-WORK")
    _line(v, "Consultants")["amount_cents"] += 5_000_000
    _restate(v)


def _line_differs_immaterially(f: dict[str, Any]) -> None:
    v = _ver(f, "BV-SUMM")
    _line(v, "Permits")["amount_cents"] += 4_100
    _restate(v)


def _stated_total_typed(f: dict[str, Any]) -> None:
    _ver(f, "BV-SUMM")["stated_total_cents"] += 668_107


def _line_missing_phase(f: dict[str, Any]) -> None:
    del _line(_ver(f, "BV-WORK"), "Insurance")["phase"]


def _offsetting_reclass(f: dict[str, Any]) -> None:
    v = _ver(f, "BV-WORK")
    _line(v, "Loan Interest")["amount_cents"] += 48_487_700
    _line(v, "Finance Costs")["amount_cents"] -= 48_487_700
    _restate(v)


def _working_model_stale(f: dict[str, Any]) -> None:
    _ver(f, "BV-WORK")["cost_through_date"] = "2031-01-31"


def _summary_superseded(f: dict[str, Any]) -> None:
    _ver(f, "BV-SUMM")["prepared_date"] = "2031-05-02"


def _revised_typed_not_computed(f: dict[str, Any]) -> None:
    row = _line(_ver(f, "BV-BILL"), "Insurance")
    row["approved_cents"] -= 1_250_000


def _change_without_amendment(f: dict[str, Any]) -> None:
    row = _line(_ver(f, "BV-BILL"), "Legal and Accounting")
    row["approved_cents"] -= 3_000_000
    row["current_changes_cents"] = 3_000_000


def _pending_amendment_billed(f: dict[str, Any]) -> None:
    row = _line(_ver(f, "BV-BILL"), PENDING_CATEGORY)
    row["approved_cents"] -= PENDING_AMOUNT_CENTS
    row["current_changes_cents"] = PENDING_AMOUNT_CENTS


def _locked_line_moved(f: dict[str, Any]) -> None:
    v = _ver(f, "BV-WORK")
    _line(v, "Land")["amount_cents"] += 15_000_000
    _restate(v)


def _schedule_input_unknown(f: dict[str, Any]) -> None:
    _doc(f, DOC_DERIVED_SCHEDULE)["input_milestones"] = [
        "construction_start",
        "substantial_completion",
    ]


def _milestone_blanked(f: dict[str, Any]) -> None:
    for row in _doc(f, DOC_MILESTONE_SET)["milestones"]:
        if row["milestone_id"] == "construction_end":
            row["date"] = None


def _instalments_do_not_conserve(f: dict[str, Any]) -> None:
    _doc(f, DOC_DERIVED_SCHEDULE)["instalments_cents"][-1] += 250_000


def _base_ignores_advances(f: dict[str, Any]) -> None:
    s = _doc(f, DOC_DERIVED_SCHEDULE)
    s["base_cents"] = s["total_cents"]
    s["instalments_cents"] = amortisation_schedule(s["base_cents"], s["periods"])


def _advances_exceed_cap(f: dict[str, Any]) -> None:
    s = _doc(f, DOC_DERIVED_SCHEDULE)
    s["advances_cents"] = SCHEDULE_CAP_CENTS + 6_000_000
    s["base_cents"] = s["total_cents"] - s["advances_cents"]
    s["instalments_cents"] = amortisation_schedule(s["base_cents"], s["periods"])


def _commitment_differs_by_copy(f: dict[str, Any]) -> None:
    _ver(f, "BV-SUMM")["commitments"]["investor"] += 4_736_900


def _split_wrong_for_phase(f: dict[str, Any]) -> None:
    for m in _doc(f, DOC_FUNDING_REGISTER)["members"]:
        m["split_bps"] = 9000 if m["member_id"] == "investor" else 1000


def _contributed_over_commitment(f: dict[str, Any]) -> None:
    for m in _doc(f, DOC_FUNDING_REGISTER)["members"]:
        if m["member_id"] == "sponsor":
            m["contributed_cents"] = m["commitment_cents"] + 12_500_000


def _amount_not_integer(f: dict[str, Any]) -> None:
    _line(_ver(f, "BV-WORK"), "Marketing")["amount_cents"] = 23_630_200.5


#: ``defect name -> (rule it demonstrates, mutator)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "unknown_version_role": ("ver_versions_declared", _unknown_version_role),
    "two_baselines": ("ver_single_baseline", _two_baselines),
    "baseline_predates_agreement": (
        "ver_baseline_postdates_agreement",
        _baseline_predates_agreement,
    ),
    "version_from_next_period": ("ver_prepared_within_period", _version_from_next_period),
    "category_renamed_in_copy": ("lin_categories_reconcile", _category_renamed_in_copy),
    "line_differs_materially": ("lin_values_agree", _line_differs_materially),
    "line_differs_immaterially": (
        "lin_immaterial_drift_review",
        _line_differs_immaterially,
    ),
    "stated_total_typed": ("lin_totals_agree", _stated_total_typed),
    "line_missing_phase": ("lin_phase_totals_tie", _line_missing_phase),
    "offsetting_reclass": ("lin_reclass_review", _offsetting_reclass),
    "working_model_stale": ("stl_cost_through_current", _working_model_stale),
    "summary_superseded": ("stl_summary_not_superseded", _summary_superseded),
    "revised_typed_not_computed": (
        "amd_change_columns_foot",
        _revised_typed_not_computed,
    ),
    "change_without_amendment": ("amd_changes_trace_to_log", _change_without_amendment),
    "pending_amendment_billed": ("amd_pending_not_billed", _pending_amendment_billed),
    "locked_line_moved": ("amd_locked_lines_unchanged", _locked_line_moved),
    "schedule_input_unknown": ("drv_inputs_declared", _schedule_input_unknown),
    "milestone_blanked": ("drv_milestones_populated", _milestone_blanked),
    "instalments_do_not_conserve": (
        "drv_instalments_conserve",
        _instalments_do_not_conserve,
    ),
    "base_ignores_advances": ("drv_base_net_of_advances", _base_ignores_advances),
    "advances_exceed_cap": ("drv_cap_not_exceeded", _advances_exceed_cap),
    "commitment_differs_by_copy": ("eqt_commitments_agree", _commitment_differs_by_copy),
    "split_wrong_for_phase": ("eqt_split_matches_phase", _split_wrong_for_phase),
    "contributed_over_commitment": (
        "eqt_contributed_within_commitment",
        _contributed_over_commitment,
    ),
    "amount_not_integer": ("lin_values_agree", _amount_not_integer),
}


# --------------------------------------------------------------------------- #
# Corpus writer
# --------------------------------------------------------------------------- #
def generate_corpus(folder: Path) -> list[Path]:
    """Write the fictional corpus into ``folder`` and return the paths written."""
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    files: list[dict[str, Any]] = []
    clean = baseline(PROJECTS[0])
    clean["file_id"] = f"clean__{PROJECTS[0].replace(' ', '_')}"
    files.append(clean)

    for i, name in enumerate(sorted(DEFECTS)):
        _rule, mutate = DEFECTS[name]
        project = PROJECTS[(i + 1) % len(PROJECTS)]
        f = baseline(project)
        f["file_id"] = f"{name}__{project.replace(' ', '_')}"
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
