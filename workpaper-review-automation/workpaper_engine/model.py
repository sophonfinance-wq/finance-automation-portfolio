"""
Data model for the workpaper review & handback engine.
======================================================

The engine consumes **package files**: one JSON file per entity workpaper
package, carrying the cells that were keyed for the current year, the citations
that claim to support them, the presentation rules the prior-year master sets,
the question block the reviewer must answer, and the cover note that goes out
with it.

Scope: whether the package can be *traced*, not whether it foots
---------------------------------------------------------------
Whether taxable income is arithmetically correct is a within-document question
and other engines own it. This engine starts after the numbers are agreed. Its
subject is the handback: a package whose figures are right but which a reviewer
cannot verify without re-doing the preparer's work.

Why that is worth an engine
---------------------------
Every failure mode here survives a footing check.

**A figure is correct and untraceable.** A current-year amount typed onto a
consolidation foots perfectly. Nothing inside the workbook says where it came
from, so the reviewer's only options are to trust it or rebuild it.

**A citation resolves to a plausible wrong number.** The reference is valid, the
cell exists, a believable figure comes back -- and it is the wrong cell. A tax
adjustment cited where the book pickup was meant; a residual cited to a cell
holding a different residual. The closer the wrong figure is to the right one,
the longer it survives. Rounding-sized differences are the dangerous ones.

**A scan repairs something that was never broken.** Dates are stored as integers,
so every amount in a date-shaped range looks like a date to a sweep. Reformatting
a genuine dollar amount as a date corrupts the tab silently and the file still
foots, because the underlying value never changed.

**A dependant is orphaned.** A block is moved or deleted after checking that no
*other* document references it. Same-document references carry no document name,
so the check misses them, and a formula that depended on the block returns an
error or, worse, a stale value.

**The cover note and the workbook disagree.** The note says three open questions;
the file carries fifteen. Both are internally consistent. Only comparing them
finds it.

**A residual is silenced rather than disclosed.** A known, accepted, immaterial
difference is plugged to zero. The package now looks cleaner than it is.

So the controls here are traceability controls: every current-year input must
name a source record, every citation is verified by the amount it returns rather
than by whether it resolves, every date reclassification must carry corroborating
context, every dependant is proven re-pointed, the note's counts are reconciled
against the question block, and disclosed residuals are proven still disclosed.

All data shipped with this package is **fictional**. No real entity, person,
place, figure or path appears anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "DOC_TYPES",
    "SOURCED",
    "TYPED",
    "DERIVED",
    "WorkpaperCell",
    "Citation",
    "PresentationRule",
    "QuestionRow",
    "CoverNote",
    "Package",
    "ModelError",
    "parse_package",
]

DOC_TYPES = ("workpaper_package",)

#: A cell whose value points at a source record inside the package.
SOURCED = "sourced"
#: A cell whose value was typed directly. Current-year typed values are findings.
TYPED = "typed"
#: A cell computed from other cells in the same document.
DERIVED = "derived"

ORIGINS = (SOURCED, TYPED, DERIVED)

#: Excel serial range that a date in the covered fiscal years would occupy.
#: A value inside it is a date *candidate*, never a date on its own evidence.
DATE_SERIAL_LOW = 45_000
DATE_SERIAL_HIGH = 47_500


class ModelError(ValueError):
    """A package file does not satisfy the model contract."""


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ModelError(msg)


def _req_str(d: dict[str, Any], key: str, where: str) -> str:
    v = d.get(key)
    _require(isinstance(v, str) and v != "", "%s: %r must be a non-empty string" % (where, key))
    return v  # type: ignore[return-value]


def _req_int(d: dict[str, Any], key: str, where: str) -> int:
    v = d.get(key)
    _require(
        isinstance(v, int) and not isinstance(v, bool),
        "%s: %r must be an integer, got %r" % (where, key, v),
    )
    return v  # type: ignore[return-value]


@dataclass(frozen=True)
class WorkpaperCell:
    """One keyed cell on a workpaper tab.

    ``origin`` says how the value got there. ``source_ref`` is the identifier of
    the source record backing it, and is required when ``origin`` is
    :data:`SOURCED`. ``is_current_year`` separates figures we keyed this year
    from inherited prior-year content, because only the former must be sourced.

    ``display_kind`` is what the cell is presented as -- ``"amount"`` or
    ``"date"``. It is the corroborating context the date control requires: a
    value inside the date-serial range presented as an amount is an amount.

    ``feeds_total`` records whether the cell is an addend in a total elsewhere in
    the document. It is the structural proof the date control leans on, because a
    value inside the date-serial band is indistinguishable from a date by its own
    value -- but **a date is never an addend**. A cell that is summed into a total
    and is also presented as a date has been misread, and no footing check will
    say so, because the underlying number never changed.
    """

    sheet: str
    cell: str
    label: str
    value_cents: int
    origin: str
    is_current_year: bool
    display_kind: str = "amount"
    feeds_total: bool = False
    source_ref: str | None = None

    @property
    def address(self) -> str:
        return "%s!%s" % (self.sheet, self.cell)

    @property
    def in_date_serial_range(self) -> bool:
        """True when the whole-dollar value falls in the date-shaped band."""
        if self.value_cents % 100 != 0:
            return False
        whole = self.value_cents // 100
        return DATE_SERIAL_LOW <= whole <= DATE_SERIAL_HIGH


@dataclass(frozen=True)
class Citation:
    """A claim that a stated figure is supported at a named address.

    ``quoted_cents`` is the figure written beside the citation -- what the note
    says the source shows. ``resolves_to`` is the address the citation points at.
    The control compares the quoted figure to what that address actually holds.
    """

    citation_id: str
    describes: str
    quoted_cents: int
    resolves_to: str
    document: str | None = None
    page: int | None = None


@dataclass(frozen=True)
class PresentationRule:
    """A presentation property the prior-year master sets on a cell.

    ``kind`` distinguishes ``"font_underline"`` from ``"cell_border"``. They look
    identical to a reader and are different properties; conflating them is how a
    presentation sweep reports success while the file still looks wrong.
    """

    sheet: str
    cell: str
    kind: str
    present_in_master: bool
    present_in_current: bool


@dataclass(frozen=True)
class QuestionRow:
    """One open item on the package's question block."""

    cell: str
    kind: str  # "decide" | "confirm"
    summary: str


@dataclass(frozen=True)
class CoverNote:
    """The note that goes out with the package."""

    stated_decisions: int
    stated_confirmations: int
    attachment_sha256: str
    claims_all_evidence_embedded: bool = False


@dataclass(frozen=True)
class Package:
    """One entity workpaper package presented for handback."""

    doc_type: str
    package_id: str
    entity: str
    period_label: str
    attachment_sha256: str
    cells: tuple[WorkpaperCell, ...] = ()
    citations: tuple[Citation, ...] = ()
    presentation: tuple[PresentationRule, ...] = ()
    questions: tuple[QuestionRow, ...] = ()
    cover_note: CoverNote | None = None
    disclosed_residuals: tuple[str, ...] = ()
    plugged_residuals: tuple[str, ...] = ()
    moved_blocks: tuple[dict[str, Any], ...] = ()
    meta: dict[str, Any] = field(default_factory=dict)

    def cell_at(self, address: str) -> WorkpaperCell | None:
        for c in self.cells:
            if c.address == address:
                return c
        return None


def parse_package(raw: dict[str, Any]) -> Package:
    """Validate and build a :class:`Package` from a decoded JSON object."""
    _require(isinstance(raw, dict), "package must be a JSON object")
    doc_type = _req_str(raw, "doc_type", "package")
    _require(doc_type in DOC_TYPES, "package: unknown doc_type %r" % (doc_type,))

    cells: list[WorkpaperCell] = []
    for i, c in enumerate(raw.get("cells", []) or []):
        where = "cells[%d]" % i
        _require(isinstance(c, dict), "%s must be an object" % where)
        origin = _req_str(c, "origin", where)
        _require(origin in ORIGINS, "%s: unknown origin %r" % (where, origin))
        src = c.get("source_ref")
        _require(
            origin != SOURCED or (isinstance(src, str) and src != ""),
            "%s: origin 'sourced' requires a source_ref" % where,
        )
        kind = c.get("display_kind", "amount")
        _require(kind in ("amount", "date"), "%s: display_kind %r" % (where, kind))
        cells.append(
            WorkpaperCell(
                sheet=_req_str(c, "sheet", where),
                cell=_req_str(c, "cell", where),
                label=_req_str(c, "label", where),
                value_cents=_req_int(c, "value_cents", where),
                origin=origin,
                is_current_year=bool(c.get("is_current_year", True)),
                display_kind=kind,
                feeds_total=bool(c.get("feeds_total", False)),
                source_ref=src if isinstance(src, str) else None,
            )
        )

    citations: list[Citation] = []
    for i, c in enumerate(raw.get("citations", []) or []):
        where = "citations[%d]" % i
        _require(isinstance(c, dict), "%s must be an object" % where)
        page = c.get("page")
        _require(page is None or (isinstance(page, int) and not isinstance(page, bool)),
                 "%s: page must be an integer or null" % where)
        citations.append(
            Citation(
                citation_id=_req_str(c, "citation_id", where),
                describes=_req_str(c, "describes", where),
                quoted_cents=_req_int(c, "quoted_cents", where),
                resolves_to=_req_str(c, "resolves_to", where),
                document=c.get("document"),
                page=page,
            )
        )

    presentation: list[PresentationRule] = []
    for i, p in enumerate(raw.get("presentation", []) or []):
        where = "presentation[%d]" % i
        _require(isinstance(p, dict), "%s must be an object" % where)
        kind = _req_str(p, "kind", where)
        _require(kind in ("font_underline", "cell_border"), "%s: kind %r" % (where, kind))
        presentation.append(
            PresentationRule(
                sheet=_req_str(p, "sheet", where),
                cell=_req_str(p, "cell", where),
                kind=kind,
                present_in_master=bool(p.get("present_in_master", False)),
                present_in_current=bool(p.get("present_in_current", False)),
            )
        )

    questions: list[QuestionRow] = []
    for i, q in enumerate(raw.get("questions", []) or []):
        where = "questions[%d]" % i
        _require(isinstance(q, dict), "%s must be an object" % where)
        kind = _req_str(q, "kind", where)
        _require(kind in ("decide", "confirm"), "%s: kind %r" % (where, kind))
        questions.append(
            QuestionRow(cell=_req_str(q, "cell", where), kind=kind,
                        summary=_req_str(q, "summary", where))
        )

    note_raw = raw.get("cover_note")
    note: CoverNote | None = None
    if note_raw is not None:
        _require(isinstance(note_raw, dict), "cover_note must be an object")
        note = CoverNote(
            stated_decisions=_req_int(note_raw, "stated_decisions", "cover_note"),
            stated_confirmations=_req_int(note_raw, "stated_confirmations", "cover_note"),
            attachment_sha256=_req_str(note_raw, "attachment_sha256", "cover_note"),
            claims_all_evidence_embedded=bool(note_raw.get("claims_all_evidence_embedded", False)),
        )

    moved = tuple(dict(m) for m in (raw.get("moved_blocks", []) or []))
    for i, m in enumerate(moved):
        _require(isinstance(m.get("block"), str), "moved_blocks[%d]: block must be a string" % i)

    return Package(
        doc_type=doc_type,
        package_id=_req_str(raw, "package_id", "package"),
        entity=_req_str(raw, "entity", "package"),
        period_label=_req_str(raw, "period_label", "package"),
        attachment_sha256=_req_str(raw, "attachment_sha256", "package"),
        cells=tuple(cells),
        citations=tuple(citations),
        presentation=tuple(presentation),
        questions=tuple(questions),
        cover_note=note,
        disclosed_residuals=tuple(raw.get("disclosed_residuals", []) or []),
        plugged_residuals=tuple(raw.get("plugged_residuals", []) or []),
        moved_blocks=moved,
        meta=dict(raw.get("meta", {}) or {}),
    )
