"""Close Sentinel: an independent post-close control layer.

Runs ten controls (C1-C10) over a finished close: independent re-balancing,
intercompany mirroring, a completeness calendar, asset-life guards, driver
provenance, crossfooting, step-change review, rounding policy, a shadow
recomputation gate, and a period lock. Every finding is a typed
:class:`~close_engine.sentinel.findings.Finding`; the close is clean only if
no control raises a CRITICAL finding.

All data audited here is FICTIONAL and seeded, like the rest of the package.
"""

from __future__ import annotations

from .controls import ALL_CONTROLS, lock_register
from .findings import Finding, SentinelReport, Severity
from .sentinel import run_sentinel

__all__ = [
    "ALL_CONTROLS",
    "Finding",
    "SentinelReport",
    "Severity",
    "lock_register",
    "run_sentinel",
]
