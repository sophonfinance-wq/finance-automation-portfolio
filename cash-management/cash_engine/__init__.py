"""Cash Management — five validation-only cash-manager controls (fictional data).

A cash manager's monthly control set, each read-only, integer-cent, and
deterministic, and each ending at READY FOR HUMAN REVIEW (never a sign-off):

* :mod:`cash_engine.bank_rec`            — bank -> GL reconciliation bridge
* :mod:`cash_engine.outstanding_checks`  — outstanding / void / stale check register
* :mod:`cash_engine.wire_approval`       — wire dual-approval / segregation of duties
* :mod:`cash_engine.bank_register`       — running-balance continuity
* :mod:`cash_engine.cash_concentration`  — concentration sweep tie-out

Every control validates; none of them post, draft a journal entry, or mutate a
source system. All examples run on invented data.
"""

from __future__ import annotations

__all__ = [
    "bank_rec",
    "outstanding_checks",
    "wire_approval",
    "bank_register",
    "cash_concentration",
]
