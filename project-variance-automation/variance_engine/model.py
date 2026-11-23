"""
Data model for the project variance and business-plan compare control engine.
=============================================================================

The engine consumes **project reports**: one JSON file per developer's periodic
development-project report, carrying the artifacts that report emits. Each source
artifact is modelled as a typed document -- a dict with a ``doc_type``
discriminator and typed fields -- so the whole engine stays stdlib-only,
deterministic and byte-stable.

Scope: restatement, not underwriting
------------------------------------
On a fixed periodic calendar every development project's proforma is re-issued as
a project report. Dedicated tabs restate the current period's economics against
two frozen comparatives: the prior period, and the approved Business Plan
baseline. Gross revenue, net project revenue, total project expense, project
profit, margin on cost and project IRR each get a Current / Prior / Plan column
and two variance columns. A budget-variance tab breaks each cost line into Total
Budget / Cost to Date / Cost to Complete, and a milestone block reports each
schedule milestone Current vs Prior vs Variance against a frozen baseline
schedule, with ``+`` meaning ahead.

Nothing here underwrites a project or re-forecasts one. Whether the proforma's
assumptions are the right assumptions is somebody else's question. The question
here is narrower and entirely arithmetic: does the report that went out foot to
the figures underneath it, and is the plan column still the approved plan?

Why that is worth an engine
---------------------------
A project report is a wide grid re-keyed every period from a longer model, and it
drifts in ways nobody re-foots.

Three things go wrong, and none of them look wrong in a tidy side-by-side grid.

**A variance column is typed, not derived.** The Current-vs-Prior or
Current-vs-Plan column is carried forward from last period's workbook, or nudged
to explain a number, so the variance no longer equals the difference of the two
columns it sits between. The grid still adds up left to right and the variance is
wrong.

**Cost to Complete stops being the remainder.** Total Budget minus Cost to Date
is the only definition Cost to Complete has. When the column is maintained beside
the budget rather than derived from it, an overrun hides as a Cost to Complete
that was never re-struck, and the project reports a budget it has already spent
past.

**The plan column is no longer the plan.** The Business Plan baseline is frozen
at an approved version named in the tab header. A baseline quietly re-based to a
later revision makes every plan variance smaller, and the report reads as on-plan
against a plan nobody approved.

So the controls here are arithmetic controls. Every derived column is recomputed
from the figures underneath it and compared.

Severity model
--------------
- ``FAIL`` -- a hard control failure (a Cost to Complete that is not the
  remainder, a variance column that does not re-foot, a profit or margin that
  does not re-derive, a milestone variance with the wrong sign, a plan column
  struck against an unapproved plan version, a rollup that does not foot).
- ``FLAG`` -- a human-review signal (a milestone behind the frozen baseline
  beyond the file's own tolerance, a slippage watchlist that does not tie the
  schedule).
- ``PASS`` -- the rule ran and the control held.

A project report with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs
roll up to ``REVIEW``; everything clean is ``PASS``.

All shipped data is fictional. The engine never writes to a source artifact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Document type vocabulary
# --------------------------------------------------------------------------- #
#: Every development project in the report, with the plan and schedule versions
#: it is measured against.
DOC_PROJECT_REGISTER = "project_register"
#: The budget-variance tab: Total Budget / Cost to Date / Cost to Complete.
DOC_BUDGET_VARIANCE = "budget_variance"
#: Current-period economics, one row per project.
DOC_CURRENT_ECONOMICS = "current_period_economics"
#: The prior period's economics as re-issued, one row per project.
DOC_PRIOR_ECONOMICS = "prior_period_economics"
#: The frozen approved Business Plan baseline, one row per project.
DOC_PLAN_BASELINE = "business_plan_baseline"
#: The variance tab: Current / Prior / Plan and the two variance columns.
DOC_VARIANCE_SUMMARY = "variance_summary"
#: The milestone block: Current vs Prior vs baseline, with variance in days.
DOC_MILESTONE_SCHEDULE = "milestone_schedule"
#: Milestones behind the frozen baseline beyond the file's own tolerance.
DOC_SLIPPAGE_WATCHLIST = "slippage_watchlist"
#: The report rollup across all projects.
DOC_REPORT_ROLLUP = "report_rollup"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_PROJECT_REGISTER,
    DOC_BUDGET_VARIANCE,
    DOC_CURRENT_ECONOMICS,
    DOC_PRIOR_ECONOMICS,
    DOC_PLAN_BASELINE,
    DOC_VARIANCE_SUMMARY,
    DOC_MILESTONE_SCHEDULE,
    DOC_SLIPPAGE_WATCHLIST,
    DOC_REPORT_ROLLUP,
)

# --------------------------------------------------------------------------- #
# Project-reporting vocabulary
# --------------------------------------------------------------------------- #
#: Development product types. All fictional labels; adding one is a value in the
#: register, never a control.
PROJECT_FOR_SALE = "for_sale_residential"
PROJECT_RENTAL = "rental_residential"
PROJECT_MIXED_USE = "mixed_use"
PROJECT_LAND = "land_development"
PROJECT_TYPES: tuple[str, ...] = (
    PROJECT_FOR_SALE,
    PROJECT_RENTAL,
    PROJECT_MIXED_USE,
    PROJECT_LAND,
)

#: Cost categories the budget-variance tab breaks a project into.
COST_LAND = "land"
COST_HARD = "hard_cost"
COST_SOFT = "soft_cost"
COST_FINANCING = "financing_cost"
COST_CONTINGENCY = "contingency"
COST_CATEGORIES: tuple[str, ...] = (
    COST_LAND,
    COST_HARD,
    COST_SOFT,
    COST_FINANCING,
    COST_CONTINGENCY,
)

#: Schedule milestones the frozen baseline schedule names.
MILESTONE_ENTITLEMENT = "entitlement"
MILESTONE_PERMIT = "permit_issuance"
MILESTONE_CONSTRUCTION_START = "construction_start"
MILESTONE_TOPPING_OUT = "topping_out"
MILESTONE_FIRST_CLOSING = "first_closing"
MILESTONE_COMPLETION = "project_completion"
MILESTONE_NAMES: tuple[str, ...] = (
    MILESTONE_ENTITLEMENT,
    MILESTONE_PERMIT,
    MILESTONE_CONSTRUCTION_START,
    MILESTONE_TOPPING_OUT,
    MILESTONE_FIRST_CLOSING,
    MILESTONE_COMPLETION,
)

#: Units a variance row can be struck in. Money rows are integer cents; ratio
#: rows are integer basis points.
UNIT_CENTS = "cents"
UNIT_BPS = "bps"

#: Metrics the variance tab restates. Each is ``(metric, economics field, unit)``
#: so the tab and the economics documents cannot drift apart on field naming.
METRIC_GROSS_REVENUE = "gross_revenue"
METRIC_NET_REVENUE = "net_project_revenue"
METRIC_TOTAL_EXPENSE = "total_project_expense"
METRIC_PROFIT = "project_profit"
METRIC_MARGIN = "margin_on_cost"
METRIC_IRR = "project_irr"
METRIC_FIELDS: tuple[tuple[str, str, str], ...] = (
    (METRIC_GROSS_REVENUE, "gross_revenue_cents", UNIT_CENTS),
    (METRIC_NET_REVENUE, "net_project_revenue_cents", UNIT_CENTS),
    (METRIC_TOTAL_EXPENSE, "total_project_expense_cents", UNIT_CENTS),
    (METRIC_PROFIT, "project_profit_cents", UNIT_CENTS),
    (METRIC_MARGIN, "margin_on_cost_bps", UNIT_BPS),
    (METRIC_IRR, "irr_bps", UNIT_BPS),
)
#: Metric ids in variance-tab order.
METRICS: tuple[str, ...] = tuple(metric for metric, _f, _u in METRIC_FIELDS)

#: Default schedule tolerance, in days, when a file does not carry its own. A
#: milestone behind the frozen baseline by more than this is a FLAG, not a
#: failure -- the date has moved, the project has not missed anything yet.
DEFAULT_SLIPPAGE_TOLERANCE_DAYS = 5


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a project report or the whole run."""

    PASS = "PASS"  # every control held
    REVIEW = "REVIEW"  # at least one FLAG, no FAILs
    FAIL = "FAIL"  # at least one FAIL


@dataclass(frozen=True)
class Finding:
    """A single observation produced by a check.

    Attributes
    ----------
    rule:
        Stable identifier of the rule that produced the finding (e.g.
        ``"bud_cost_to_complete_foots"``).
    status:
        :class:`Status` of this finding.
    location:
        Where the finding applies -- ``"<doc_type>:<document_id>/<field path>"``
        for document fields, or ``"-"`` when not field-specific.
    message:
        Human-readable explanation. Messages carry the control rationale, so an
        exception teaches the reason rather than only the verdict.
    """

    rule: str
    status: Status
    location: str
    message: str

    def to_dict(self) -> dict:
        """Return a JSON-serialisable representation of the finding."""
        return {
            "rule": self.rule,
            "status": self.status.value,
            "location": self.location,
            "message": self.message,
        }


@dataclass
class Context:
    """Everything a check needs about one project report.

    The context is a thin, read-only view over the parsed JSON. It never copies or
    rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the project report (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def portfolio(self) -> str:
        """Fictional developer whose project report the file carries."""
        value = self.data.get("portfolio")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future reporting period label."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def prior_period(self) -> str:
        """The period the Prior column restates."""
        value = self.data.get("prior_period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def as_of(self) -> str:
        """The report date every schedule test is measured to."""
        value = self.data.get("as_of")
        return str(value) if isinstance(value, str) else "-"

    @property
    def slippage_tolerance_days(self) -> int:
        """Schedule tolerance, in days, before a milestone reaches the watchlist.

        Read from the file when present so the band comes from the data, falling
        back to :data:`DEFAULT_SLIPPAGE_TOLERANCE_DAYS` when it is absent or
        malformed.
        """
        value = self.data.get("slippage_tolerance_days")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return DEFAULT_SLIPPAGE_TOLERANCE_DAYS
        return value

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the project report, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A project report carries exactly one of each artifact. Returning ``None``
        rather than raising lets ``set_complete`` own the "missing artifact"
        finding, so every downstream rule reports absence the same way.
        """
        found = self.docs(doc_type)
        return found[0] if found else None

    def loc(self, doc: dict[str, Any], field_path: str) -> str:
        """Build a stable ``location`` string for a field inside ``doc``."""
        doc_type = doc.get("doc_type", "?")
        doc_id = doc.get("document_id", "?")
        return f"{doc_type}:{doc_id}/{field_path}"


@dataclass
class DocumentReport:
    """All findings for one project report plus its rolled-up verdict."""

    document: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def verdict(self) -> Verdict:
        """Roll findings up into a single :class:`Verdict`."""
        if any(f.status is Status.FAIL for f in self.findings):
            return Verdict.FAIL
        if any(f.status is Status.FLAG for f in self.findings):
            return Verdict.REVIEW
        return Verdict.PASS

    def counts(self) -> dict[str, int]:
        """Return a ``{status: count}`` tally across findings."""
        out = {s.value: 0 for s in Status}
        for f in self.findings:
            out[f.status.value] += 1
        return out

    def rules_fired(self) -> list[str]:
        """Rule ids that produced a non-PASS finding, in first-seen order."""
        out: list[str] = []
        for f in self.findings:
            if f.status is not Status.PASS and f.rule not in out:
                out.append(f.rule)
        return out

    def to_dict(self) -> dict:
        """Return a JSON-serialisable representation of the report."""
        return {
            "document": self.document,
            "verdict": self.verdict.value,
            "counts": self.counts(),
            "findings": [f.to_dict() for f in self.findings],
        }
