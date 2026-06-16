"""Core domain model for the Triangulate Orchestrator.

This module defines the immutable-by-discipline data structures that flow
through the validation pipeline:

* :class:`Severity` -- the Critical/High/Medium/Low taxonomy.
* :class:`AuthoritySource` -- the source-of-truth authority hierarchy that
  governs which evidence wins when findings conflict.
* :class:`Finding` -- a single issue flagged *by reference* (it never carries a
  mutation, only a pointer plus diagnosis).
* :class:`WorkpaperCell` / :class:`Workpaper` -- a tiny spreadsheet-like
  workpaper. The :class:`Workpaper` exposes ``frozen_snapshot`` /
  ``digest`` helpers so the orchestrator can *prove* that read-only roles did
  not mutate it (separation of duties).

All money figures and entity names in any sample data are deliberately
fictional. Nothing here references a real entity, person, or dollar amount.
"""

from __future__ import annotations

import copy
import enum
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class Severity(enum.IntEnum):
    """Issue severity taxonomy.

    Implemented as an ``IntEnum`` so severities are directly comparable and
    sortable (``Severity.CRITICAL > Severity.LOW``). The integer ordering is
    the whole point: the reconciler ranks findings and the human gate keys its
    pass/fail decision off the maximum severity present.
    """

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    @classmethod
    def from_name(cls, name: str) -> "Severity":
        """Look up a severity by case-insensitive name."""
        try:
            return cls[name.strip().upper()]
        except KeyError as exc:  # pragma: no cover - defensive
            raise ValueError(f"Unknown severity: {name!r}") from exc

    @property
    def label(self) -> str:
        """Human-friendly title-case label, e.g. ``'Critical'``."""
        return self.name.title()


class AuthoritySource(enum.IntEnum):
    """Source-of-truth authority hierarchy (higher value == more authoritative).

    Mirrors the hierarchy in the framework README::

        signed prior-year work > direct management instructions >
        meeting decisions > current-year source data >
        existing workbook formulas > AI-generated assumptions (lowest)

    When two findings disagree about the same cell, the one backed by the
    higher authority source wins.
    """

    AI_ASSUMPTION = 1
    WORKBOOK_FORMULA = 2
    CURRENT_YEAR_SOURCE = 3
    MEETING_DECISION = 4
    MANAGEMENT_INSTRUCTION = 5
    SIGNED_PRIOR_YEAR = 6

    @property
    def label(self) -> str:
        return self.name.replace("_", " ").title()


@dataclass(frozen=True)
class Finding:
    """An issue flagged against the workpaper *by reference*.

    A :class:`Finding` is intentionally inert: it points at a cell and
    describes a problem, but it carries no authority to change anything. This
    is what enforces "flag, never fix" at the type level -- a Reviewer can only
    emit ``Finding`` objects, it is never handed a mutable workpaper.
    """

    code: str
    """Stable machine code, e.g. ``"TIE_OUT_MISMATCH"``."""

    cell_ref: str
    """The cell the finding refers to, e.g. ``"B7"`` (or ``"<workpaper>"``)."""

    severity: Severity
    message: str
    raised_by: str
    """Which role/component raised it, e.g. ``"Reviewer:LLMReviewer"``."""

    authority: AuthoritySource = AuthoritySource.AI_ASSUMPTION
    """The authority backing this finding -- used to break conflicts."""

    expected: Optional[Any] = None
    actual: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "cell_ref": self.cell_ref,
            "severity": self.severity.label,
            "message": self.message,
            "raised_by": self.raised_by,
            "authority": self.authority.label,
            "expected": self.expected,
            "actual": self.actual,
        }


@dataclass
class WorkpaperCell:
    """A single cell in the workpaper.

    ``formula`` (when present) is a tiny, safe arithmetic expression over other
    cell labels, e.g. ``"=B2+B3"``. ``value`` is the *stated* value as it
    appears in the workpaper -- which may or may not actually tie to the
    formula. Catching that gap is the audit's job.
    """

    ref: str
    label: str
    value: Optional[float] = None
    formula: Optional[str] = None
    source: AuthoritySource = AuthoritySource.WORKBOOK_FORMULA

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ref": self.ref,
            "label": self.label,
            "value": self.value,
            "formula": self.formula,
            "source": self.source.label,
        }


@dataclass
class Workpaper:
    """A tiny spreadsheet-like workpaper that flows through the pipeline.

    The workpaper is the single mutable artifact in the system. Only the
    Preparer (and Specialist transforms) may legitimately mutate it. Read-only
    roles receive a :meth:`frozen_snapshot` and the orchestrator compares
    :meth:`digest` before/after to prove they did not cheat.
    """

    engagement: str
    entity: str
    period: str
    cells: Dict[str, WorkpaperCell] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    # -- construction helpers ------------------------------------------------
    def set_cell(self, cell: WorkpaperCell) -> None:
        self.cells[cell.ref] = cell

    def get(self, ref: str) -> Optional[WorkpaperCell]:
        return self.cells.get(ref)

    def ordered_cells(self) -> List[WorkpaperCell]:
        """Cells in a stable, deterministic order (by ref)."""
        return [self.cells[ref] for ref in sorted(self.cells)]

    # -- separation-of-duties helpers ---------------------------------------
    def frozen_snapshot(self) -> "ReadOnlyWorkpaperView":
        """Return a read-only view safe to hand to adversarial roles."""
        return ReadOnlyWorkpaperView(self)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engagement": self.engagement,
            "entity": self.entity,
            "period": self.period,
            "cells": {ref: c.to_dict() for ref, c in self.cells.items()},
            "notes": list(self.notes),
        }

    def digest(self) -> str:
        """Stable SHA-256 digest of the workpaper's content.

        Used to detect any mutation by a role that promised not to mutate.
        """
        blob = json.dumps(self.to_dict(), sort_keys=True, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def clone(self) -> "Workpaper":
        """Deep copy -- the Preparer works on clones, never shared state."""
        return copy.deepcopy(self)


class WorkpaperMutationError(RuntimeError):
    """Raised when a read-only role attempts to mutate the workpaper."""


class ReadOnlyWorkpaperView:
    """A read-only facade over a :class:`Workpaper`.

    Adversarial / audit roles receive *this*, not the live workpaper. Any
    attempt to set an attribute or reach in and mutate a cell raises
    :class:`WorkpaperMutationError`. This is the runtime backstop that makes
    "flag, never fix" impossible to violate by accident -- separation of duties
    enforced in code, not just in a docstring.
    """

    __slots__ = ("_wp",)

    def __init__(self, wp: Workpaper) -> None:
        # Store a deep copy so even reaching through the view cannot touch the
        # real object the Preparer holds.
        object.__setattr__(self, "_wp", wp.clone())

    # Read accessors -------------------------------------------------------
    @property
    def engagement(self) -> str:
        return self._wp.engagement

    @property
    def entity(self) -> str:
        return self._wp.entity

    @property
    def period(self) -> str:
        return self._wp.period

    @property
    def notes(self) -> List[str]:
        return list(self._wp.notes)

    def get(self, ref: str) -> Optional[WorkpaperCell]:
        cell = self._wp.get(ref)
        return copy.deepcopy(cell) if cell is not None else None

    def ordered_cells(self) -> List[WorkpaperCell]:
        return [copy.deepcopy(c) for c in self._wp.ordered_cells()]

    def digest(self) -> str:
        return self._wp.digest()

    def to_dict(self) -> Dict[str, Any]:
        return self._wp.to_dict()

    # Mutation guard -------------------------------------------------------
    def __setattr__(self, name: str, value: Any) -> None:  # noqa: D401
        raise WorkpaperMutationError(
            "Read-only roles may not mutate the workpaper "
            f"(attempted to set {name!r}). Flag issues by reference instead."
        )
