"""
Controls for the workpaper review & handback engine.
====================================================

Eight controls, each a pure function of one :class:`~workpaper_engine.model.Package`.
Nothing here writes, mutates its input, reads the clock, or consults the network.
Ordering is deterministic: findings sort by control id then by address.

Severity
--------
``FAIL`` a hard control failure -- the package must not go out as it stands.
``FLAG`` a human must look, but the engine will not call it wrong on its own.

The verdict is the worst severity present, and doubles as the process exit code.

Why these eight
---------------
Each one exists because the defect it catches survives a footing check and had
already reached a reviewer at least once before the control was written.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from typing import Any, Callable, Iterable

from .model import (
    DERIVED,
    SOURCED,
    TYPED,
    Package,
    parse_package,
)

__all__ = [
    "FAIL",
    "FLAG",
    "PASS",
    "Finding",
    "REGISTRY",
    "analyze_package",
    "analyze_document",
    "analyze_folder",
    "verdict_for",
    "EXIT_CODES",
]

FAIL = "FAIL"
FLAG = "FLAG"
PASS = "PASS"

_SEVERITY_RANK = {PASS: 0, FLAG: 1, FAIL: 2}

EXIT_CODES = {PASS: 0, FLAG: 1, FAIL: 2}


@dataclass(frozen=True)
class Finding:
    """One control exception."""

    control: str
    severity: str
    address: str
    message: str
    detail: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def sort_key(self) -> tuple[str, str, str]:
        return (self.control, self.address, self.message)


# --------------------------------------------------------------------------
# UNSOURCED_INPUT
# --------------------------------------------------------------------------
def control_unsourced_input(pkg: Package) -> list[Finding]:
    """A current-year amount typed in rather than pointing at a source record.

    The figure may be perfectly correct. That is not the point: a typed number on
    a consolidation gives the reviewer no way to verify it short of rebuilding
    the preparer's work. Prior-year inherited content is exempt -- it was sourced
    in the year it was keyed.
    """
    out: list[Finding] = []
    for c in pkg.cells:
        if c.origin == TYPED and c.is_current_year:
            out.append(
                Finding(
                    "UNSOURCED_INPUT",
                    FAIL,
                    c.address,
                    "current-year amount is typed, not linked to a source record",
                    {"label": c.label, "value_cents": c.value_cents},
                )
            )
    return out


# --------------------------------------------------------------------------
# CITATION_MISMATCH
# --------------------------------------------------------------------------
def control_citation_mismatch(pkg: Package) -> list[Finding]:
    """A citation resolves, but not to the figure quoted beside it.

    Verified by amount, never by whether the reference resolves. A citation that
    lands on a real cell holding a believable number is the failure mode this
    control exists for, and the smaller the difference the longer it survives --
    so a rounding-sized gap is reported at the same severity as a large one.
    """
    out: list[Finding] = []
    for cite in pkg.citations:
        target = pkg.cell_at(cite.resolves_to)
        if target is None:
            out.append(
                Finding(
                    "CITATION_MISMATCH",
                    FAIL,
                    cite.resolves_to,
                    "citation %s points at an address not present in the package" % cite.citation_id,
                    {"citation_id": cite.citation_id, "describes": cite.describes},
                )
            )
            continue
        if target.value_cents != cite.quoted_cents:
            delta = target.value_cents - cite.quoted_cents
            out.append(
                Finding(
                    "CITATION_MISMATCH",
                    FAIL,
                    cite.resolves_to,
                    "citation %s quotes a figure the address does not hold" % cite.citation_id,
                    {
                        "citation_id": cite.citation_id,
                        "describes": cite.describes,
                        "quoted_cents": cite.quoted_cents,
                        "resolved_cents": target.value_cents,
                        "difference_cents": delta,
                        "rounding_sized": abs(delta) <= 100,
                    },
                )
            )
    return out


# --------------------------------------------------------------------------
# DATE_MISREAD
# --------------------------------------------------------------------------
def control_date_misread(pkg: Package) -> list[Finding]:
    """A value presented as an amount was reclassified as a date.

    Dates are stored as integers, so every amount in a date-shaped band looks
    like a date to a sweep. The corroborating context is the cell's own
    presentation: a value inside the band that the workpaper presents as an
    amount is an amount, and turning it into a date corrupts the tab without
    changing anything that would fail a footing check.
    """
    out: list[Finding] = []
    for c in pkg.cells:
        if c.display_kind == "date" and c.feeds_total:
            out.append(
                Finding(
                    "DATE_MISREAD",
                    FAIL,
                    c.address,
                    "cell is presented as a date but is an addend in a total; a date is never an addend",
                    {"label": c.label, "value_cents": c.value_cents, "feeds_total": True},
                )
            )
        elif c.display_kind == "date" and not c.in_date_serial_range:
            out.append(
                Finding(
                    "DATE_MISREAD",
                    FAIL,
                    c.address,
                    "cell is presented as a date but its value is outside the date-serial range",
                    {"label": c.label, "value_cents": c.value_cents},
                )
            )
        elif c.display_kind == "amount" and c.in_date_serial_range:
            out.append(
                Finding(
                    "DATE_MISREAD",
                    FLAG,
                    c.address,
                    "amount falls in the date-serial range; confirm before any date reformat",
                    {
                        "label": c.label,
                        "value_cents": c.value_cents,
                        "protected": True,
                    },
                )
            )
    return out


# --------------------------------------------------------------------------
# ORPHANED_DEPENDANT
# --------------------------------------------------------------------------
def control_orphaned_dependant(pkg: Package) -> list[Finding]:
    """A moved or deleted block left a dependant behind.

    Same-document references carry no document name, so a search for other
    documents referencing the block misses every one of them. Each moved block
    declares its dependants and whether each was re-pointed; any that was not is
    a hard failure, because the formula either errors or, worse, keeps a stale
    value.
    """
    out: list[Finding] = []
    for m in pkg.moved_blocks:
        block = m.get("block", "?")
        for dep in m.get("dependants", []) or []:
            addr = dep.get("address", "?") if isinstance(dep, dict) else str(dep)
            repointed = bool(dep.get("repointed", False)) if isinstance(dep, dict) else False
            if not repointed:
                out.append(
                    Finding(
                        "ORPHANED_DEPENDANT",
                        FAIL,
                        addr,
                        "dependant of moved block %r was not re-pointed" % block,
                        {"block": block},
                    )
                )
    return out


# --------------------------------------------------------------------------
# QUESTION_COUNT_MISMATCH
# --------------------------------------------------------------------------
def control_question_count(pkg: Package) -> list[Finding]:
    """The cover note's counts must equal the workbook's own question block.

    Both documents are internally consistent; only comparing them finds the
    disagreement. The count is taken from the file, never from a tracker, because
    a tracker records what was asked and the file records what is still open.
    """
    if pkg.cover_note is None:
        return []
    decide = sum(1 for q in pkg.questions if q.kind == "decide")
    confirm = sum(1 for q in pkg.questions if q.kind == "confirm")
    note = pkg.cover_note
    out: list[Finding] = []
    if note.stated_decisions != decide or note.stated_confirmations != confirm:
        out.append(
            Finding(
                "QUESTION_COUNT_MISMATCH",
                FAIL,
                "cover_note",
                "cover note states %d/%d; the question block carries %d/%d"
                % (note.stated_decisions, note.stated_confirmations, decide, confirm),
                {
                    "stated_decisions": note.stated_decisions,
                    "stated_confirmations": note.stated_confirmations,
                    "block_decisions": decide,
                    "block_confirmations": confirm,
                },
            )
        )
    return out


# --------------------------------------------------------------------------
# ATTACHMENT_DRIFT
# --------------------------------------------------------------------------
def control_attachment_drift(pkg: Package) -> list[Finding]:
    """The note must carry the hash of the file it actually attaches."""
    if pkg.cover_note is None:
        return []
    if pkg.cover_note.attachment_sha256 != pkg.attachment_sha256:
        return [
            Finding(
                "ATTACHMENT_DRIFT",
                FAIL,
                "cover_note",
                "cover note attachment hash does not match the package",
                {
                    "note_sha256": pkg.cover_note.attachment_sha256,
                    "package_sha256": pkg.attachment_sha256,
                },
            )
        ]
    return []


# --------------------------------------------------------------------------
# RESIDUAL_PLUGGED
# --------------------------------------------------------------------------
def control_residual_plugged(pkg: Package) -> list[Finding]:
    """A residual that was disclosed is now silenced.

    A known, accepted, immaterial difference is worth more disclosed than zeroed.
    Plugging it makes the package look cleaner than it is and destroys the only
    record that the difference was ever considered.
    """
    out: list[Finding] = []
    for name in pkg.plugged_residuals:
        out.append(
            Finding(
                "RESIDUAL_PLUGGED",
                FAIL,
                name,
                "residual was plugged rather than disclosed",
                {"residual": name},
            )
        )
    return out


# --------------------------------------------------------------------------
# PRESENTATION_DRIFT
# --------------------------------------------------------------------------
def control_presentation_drift(pkg: Package) -> list[Finding]:
    """Presentation is matched against the prior-year master in both directions.

    A rule the master carries and the current file does not is missing; a rule
    the current file carries and the master does not is stray. Underlines and
    borders are reported as the distinct properties they are, because they look
    identical to a reader and are fixed differently -- conflating them is how a
    sweep reports success while the file still looks wrong.
    """
    out: list[Finding] = []
    for r in pkg.presentation:
        if r.present_in_master and not r.present_in_current:
            out.append(
                Finding(
                    "PRESENTATION_DRIFT",
                    FLAG,
                    "%s!%s" % (r.sheet, r.cell),
                    "%s present in the prior-year master, missing here" % r.kind,
                    {"kind": r.kind, "direction": "missing"},
                )
            )
        elif r.present_in_current and not r.present_in_master:
            out.append(
                Finding(
                    "PRESENTATION_DRIFT",
                    FLAG,
                    "%s!%s" % (r.sheet, r.cell),
                    "%s present here, absent from the prior-year master" % r.kind,
                    {"kind": r.kind, "direction": "stray"},
                )
            )
    return out


# --------------------------------------------------------------------------
# EVIDENCE_OVERCLAIM
# --------------------------------------------------------------------------
def control_evidence_overclaim(pkg: Package) -> list[Finding]:
    """The note must not claim complete evidence while citations are unresolved.

    Claiming every exhibit links to its page, when some do not, is the kind of
    sentence that costs a package its credibility the first time the reviewer
    clicks one.
    """
    if pkg.cover_note is None or not pkg.cover_note.claims_all_evidence_embedded:
        return []
    unresolved = [c for c in pkg.citations if pkg.cell_at(c.resolves_to) is None]
    if unresolved:
        return [
            Finding(
                "EVIDENCE_OVERCLAIM",
                FAIL,
                "cover_note",
                "note claims all evidence is embedded; %d citation(s) do not resolve"
                % len(unresolved),
                {"unresolved": sorted(c.citation_id for c in unresolved)},
            )
        ]
    return []


REGISTRY: dict[str, Callable[[Package], list[Finding]]] = {
    "UNSOURCED_INPUT": control_unsourced_input,
    "CITATION_MISMATCH": control_citation_mismatch,
    "DATE_MISREAD": control_date_misread,
    "ORPHANED_DEPENDANT": control_orphaned_dependant,
    "QUESTION_COUNT_MISMATCH": control_question_count,
    "ATTACHMENT_DRIFT": control_attachment_drift,
    "RESIDUAL_PLUGGED": control_residual_plugged,
    "PRESENTATION_DRIFT": control_presentation_drift,
    "EVIDENCE_OVERCLAIM": control_evidence_overclaim,
}


def verdict_for(findings: Iterable[Finding]) -> str:
    """Worst severity present, or :data:`PASS`."""
    worst = PASS
    for f in findings:
        if _SEVERITY_RANK[f.severity] > _SEVERITY_RANK[worst]:
            worst = f.severity
    return worst


def analyze_package(pkg: Package) -> dict[str, Any]:
    """Run every control over one package and return a structured result."""
    findings: list[Finding] = []
    for name in sorted(REGISTRY):
        findings.extend(REGISTRY[name](pkg))
    findings.sort(key=lambda f: f.sort_key)
    return {
        "package_id": pkg.package_id,
        "entity": pkg.entity,
        "period_label": pkg.period_label,
        "verdict": verdict_for(findings),
        "findings": [f.as_dict() for f in findings],
        "counts": {
            "cells": len(pkg.cells),
            "citations": len(pkg.citations),
            "questions": len(pkg.questions),
            "findings": len(findings),
        },
    }


def analyze_document(raw: dict[str, Any]) -> dict[str, Any]:
    """Parse and analyze one decoded package object."""
    return analyze_package(parse_package(raw))


def analyze_folder(folder: str) -> dict[str, Any]:
    """Analyze every ``.json`` package in ``folder``. Read-only."""
    import json

    names = sorted(n for n in os.listdir(folder) if n.endswith(".json"))
    results = []
    for n in names:
        with open(os.path.join(folder, n), "r", encoding="utf-8") as fh:
            results.append(analyze_document(json.load(fh)))
    overall = PASS
    for r in results:
        if _SEVERITY_RANK[r["verdict"]] > _SEVERITY_RANK[overall]:
            overall = r["verdict"]
    return {"folder": os.path.basename(os.path.abspath(folder)),
            "packages": results, "verdict": overall}
