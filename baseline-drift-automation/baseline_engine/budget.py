"""
Derivation kernel for the baseline & version drift engine.
==========================================================

This module is the single place that knows how a budget version is read, how two
versions are paired, and how a derived schedule is amortised. Both the corpus
generator and the controls import it, so a control and the corpus it audits
cannot quietly disagree about what agreement means.

Everything here is a pure function over parsed JSON: no I/O, no clock, no
randomness. Amounts are integer cents throughout.

The pairing rule is the load-bearing part
-----------------------------------------
Comparing two budgets is not comparing two lists of numbers. Lines get renamed,
split and merged between copies, so a comparison that walks one version's lines
and looks each up in the other silently skips whatever moved. :func:`pair_lines`
therefore reconciles the *category sets* first and reports three disjoint groups
-- paired, present-only-in-A, present-only-in-B -- and the controls treat the
second and third as findings in their own right rather than as absences to skip.

Reclassification is a different fact from change
------------------------------------------------
When two lines move by equal and opposite amounts and the total does not budge,
the money was re-carved, not changed. :func:`detect_reclassifications` finds
those pairs so the engine can grade them as review signals rather than burying
the genuine changes among them.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .money import require_cents, split_evenly

__all__ = [
    "amortisation_schedule",
    "budget_lines",
    "budget_total",
    "detect_reclassifications",
    "milestone_dates",
    "pair_lines",
    "parse_iso",
    "phase_totals",
    "revised_from_changes",
    "schedule_inputs",
    "version_by_role",
    "versions",
]


# --------------------------------------------------------------------------- #
# Parsing helpers
# --------------------------------------------------------------------------- #
def parse_iso(value: Any) -> date | None:
    """Parse an ISO ``YYYY-MM-DD`` string, returning ``None`` if unreadable.

    Returning ``None`` rather than raising is deliberate: a malformed date is a
    finding for the control that owns it, not an exception that stops every other
    control from running.
    """
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Version access
# --------------------------------------------------------------------------- #
def versions(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every budget-version document, in file order."""
    return [d for d in docs if isinstance(d, dict)]


def version_by_role(docs: list[dict[str, Any]], role: str) -> list[dict[str, Any]]:
    """Every version carrying ``role``, in file order.

    Returns a list rather than a single document because "exactly one baseline"
    is a control, not an assumption. A caller that needs the single baseline
    asks for the list and reports what it finds.
    """
    return [d for d in versions(docs) if d.get("role") == role]


def budget_lines(version: dict[str, Any] | None) -> dict[str, int]:
    """``{category: amount_cents}`` for one version, in file order.

    A duplicated category is summed rather than overwritten: two rows carrying
    the same category is a shape the source systems genuinely produce, and
    silently keeping the last one would make the total disagree with the lines.
    """
    if not isinstance(version, dict):
        return {}
    rows = version.get("lines")
    if not isinstance(rows, list):
        return {}
    out: dict[str, int] = {}
    vid = version.get("document_id", "?")
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        cat = row.get("category")
        if not isinstance(cat, str):
            continue
        amount = require_cents(
            f"budget_version[{vid}]/lines[{idx}]/amount_cents", row.get("amount_cents")
        )
        out[cat] = out.get(cat, 0) + amount
    return out


def budget_total(version: dict[str, Any] | None) -> int:
    """Sum of every line in a version. Derived, never read from a stated total."""
    return sum(budget_lines(version).values())


def phase_totals(version: dict[str, Any] | None) -> dict[str, int]:
    """``{phase: amount_cents}`` summed across a version's lines.

    A line with no phase is attributed to no phase, so the phase totals sum to
    the budget total only when every line carries one -- which is the control.
    """
    if not isinstance(version, dict):
        return {}
    rows = version.get("lines")
    if not isinstance(rows, list):
        return {}
    out: dict[str, int] = {}
    vid = version.get("document_id", "?")
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        phase = row.get("phase")
        if not isinstance(phase, str):
            continue
        amount = require_cents(
            f"budget_version[{vid}]/lines[{idx}]/amount_cents", row.get("amount_cents")
        )
        out[phase] = out.get(phase, 0) + amount
    return out


# --------------------------------------------------------------------------- #
# Pairing
# --------------------------------------------------------------------------- #
def pair_lines(
    left: dict[str, int], right: dict[str, int]
) -> tuple[list[str], list[str], list[str]]:
    """Reconcile two category sets before any value is compared.

    Args:
        left: ``{category: cents}`` from the first version.
        right: ``{category: cents}`` from the second.

    Returns:
        ``(paired, left_only, right_only)`` -- three disjoint sorted lists of
        category names. ``left_only`` and ``right_only`` are findings in their
        own right: a category that exists in one copy and not the other is the
        exact shape a renamed or split line takes, and pairing on names alone
        would skip it in silence.
    """
    lk, rk = set(left), set(right)
    return sorted(lk & rk), sorted(lk - rk), sorted(rk - lk)


def detect_reclassifications(
    left: dict[str, int], right: dict[str, int]
) -> list[tuple[str, str, int]]:
    """Find offsetting movements between two versions whose total is unchanged.

    A reclassification is two categories moving by equal and opposite amounts
    while every other category and the grand total stay put. It is a re-carve of
    the same money, and grading it as a budget change buries the genuine ones.

    Args:
        left: ``{category: cents}`` from the earlier version.
        right: ``{category: cents}`` from the later version.

    Returns:
        A sorted list of ``(from_category, to_category, amount_cents)`` triples,
        each with a positive amount. Empty when the totals differ -- if the total
        moved, the movement is a change, not a re-carve, whatever its shape.
    """
    paired, _lo, _ro = pair_lines(left, right)
    if sum(left.values()) != sum(right.values()):
        return []
    deltas = {c: right[c] - left[c] for c in paired if right[c] != left[c]}
    if not deltas:
        return []
    ups = sorted((c for c, d in deltas.items() if d > 0), key=lambda c: (-deltas[c], c))
    downs = sorted((c for c, d in deltas.items() if d < 0), key=lambda c: (deltas[c], c))
    out: list[tuple[str, str, int]] = []
    for down in downs:
        for up in ups:
            if deltas[down] == -deltas[up] and deltas[up] > 0:
                out.append((down, up, deltas[up]))
                deltas[down] = 0
                deltas[up] = 0
                break
    return sorted(out)


# --------------------------------------------------------------------------- #
# Amendment arithmetic
# --------------------------------------------------------------------------- #
def revised_from_changes(row: dict[str, Any], vid: str, idx: int) -> int:
    """Re-derive a billing row's revised figure from its own change columns.

    The billing instrument carries ``approved + previous_changes +
    current_changes = revised``. Re-deriving it is the only way to catch a
    revised figure that was typed rather than computed.
    """
    approved = require_cents(
        f"budget_version[{vid}]/lines[{idx}]/approved_cents", row.get("approved_cents")
    )
    previous = require_cents(
        f"budget_version[{vid}]/lines[{idx}]/previous_changes_cents",
        row.get("previous_changes_cents"),
    )
    current = require_cents(
        f"budget_version[{vid}]/lines[{idx}]/current_changes_cents",
        row.get("current_changes_cents"),
    )
    return approved + previous + current


# --------------------------------------------------------------------------- #
# Milestones and derived schedules
# --------------------------------------------------------------------------- #
def milestone_dates(milestone_set: dict[str, Any] | None) -> dict[str, date | None]:
    """``{milestone_id: date or None}``.

    A milestone present but undated maps to ``None`` rather than being dropped.
    That distinction is the whole point: a schedule whose milestone row exists
    but carries no date is not a schedule missing a row, it is a schedule whose
    input was blanked, and the two need different findings.
    """
    if not isinstance(milestone_set, dict):
        return {}
    rows = milestone_set.get("milestones")
    if not isinstance(rows, list):
        return {}
    out: dict[str, date | None] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        mid = row.get("milestone_id")
        if isinstance(mid, str):
            out[mid] = parse_iso(row.get("date"))
    return out


def schedule_inputs(schedule: dict[str, Any] | None) -> list[str]:
    """Milestone ids a derived schedule declares it depends on."""
    if not isinstance(schedule, dict):
        return []
    ins = schedule.get("input_milestones")
    if not isinstance(ins, list):
        return []
    return [m for m in ins if isinstance(m, str)]


def amortisation_schedule(total_cents: int, periods: int) -> list[int]:
    """Amortise a total into ``periods`` equal instalments, conserving the total.

    Thin wrapper over :func:`~baseline_engine.money.split_evenly` so the
    generator and the controls derive an instalment stream through one
    implementation. A schedule the engine re-derives differently from the way it
    was built is a schedule the engine cannot audit.

    Args:
        total_cents: Amount to amortise.
        periods: Number of instalments (must be >= 1).

    Returns:
        A list of ``periods`` integer-cent instalments summing to ``total_cents``.

    Raises:
        ValueError: If ``periods`` < 1.
    """
    return split_evenly(total_cents, periods)
