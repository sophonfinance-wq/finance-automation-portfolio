"""Line-level certificate triage under a deterministic policy.

Order matters and is fixed: cost-code professional exemptions first (a Legal
cost code is professional regardless of vendor costume), then journal entries
(no vendor exists), then clearing accounts, then wrap enrollment, then
category exemptions, then live coverage, then chase. Every line lands in
exactly one bucket.
"""
from __future__ import annotations

import datetime as dt

from .model import (AuditWindow, CostLine, CoverageRecord, Triage,
                    TriagePolicy, TranType)

PROFESSIONAL_CODE_WORDS = ("legal", "attorney", "professional", "audit fee")
MATERIALS_CODE_WORDS = ("materials", "supplies", "tools")


def _code_says(line: CostLine, words: tuple[str, ...]) -> bool:
    blob = f"{line.cost_code} {line.cost_code_desc}".lower()
    return any(w in blob for w in words)


def coverage_current(records: list[CoverageRecord], vendor_name: str,
                     required: str, as_of: dt.date) -> bool:
    best: dt.date | None = None
    vn = vendor_name.upper()
    for r in records:
        if r.vendor_name.upper() != vn or not r.received:
            continue
        if r.coverage == required or best is None:
            if r.coverage == required:
                if best is None or r.expiration > best:
                    best = r.expiration
    return best is not None and best >= as_of


def triage_line(line: CostLine, policy: TriagePolicy,
                coverage: list[CoverageRecord], window: AuditWindow) -> Triage:
    if _code_says(line, PROFESSIONAL_CODE_WORDS):
        return Triage.PROFESSIONAL
    if line.tran_type is not TranType.AP or not line.vendor_name:
        return Triage.JOURNAL_ENTRY
    if line.vendor_id in policy.clearing_vendor_ids \
            or line.vendor_name.upper() == "SUMMARY VENDOR":
        return Triage.CLEARING_ACCOUNT
    vn = line.vendor_name.upper()
    if vn in policy.wrap_enrolled_vendors:
        return Triage.OCIP_ENROLLED
    if vn in policy.materials_only_vendors:
        return Triage.MATERIALS_ONLY
    if vn in policy.professional_vendors:
        return Triage.PROFESSIONAL
    if coverage_current(coverage, vn, policy.required_coverage, window.end):
        return Triage.COVERED_CURRENT
    return Triage.CHASE
