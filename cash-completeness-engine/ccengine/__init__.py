"""ccengine -- a bank-first cash-completeness reconciliation engine.

The engine productizes one month-end lesson: a trial-balance-first
reconciliation cannot see cash accounts that are missing from the trial
balance. Completeness has to be asserted from the bank side instead --
load the full register population, reconcile every account, classify every
exception, and independently verify the report before it ships.

Package layout
--------------
* :mod:`ccengine.models` -- shared dataclass contracts every module codes
  against (Transaction, RegisterAccount, TBRow, ExceptionItem,
  ScopeReconciliation, Verdict) plus the controlled vocabularies.
* :mod:`ccengine.normalize` -- canonical GL-key normalization and the
  mis-keyed-placeholder detector.
* :mod:`ccengine.ingest` -- CSV loaders for registers and the trial balance
  (stdlib-only), with optional ``openpyxl``-backed xlsx variants.
* :mod:`ccengine.reconcile` -- bank-first population matching and exception
  classification (A/B/C/D kinds; nothing silently dropped).
* :mod:`ccengine.verify` -- the independent verification pass: re-derives
  the population from raw inputs and cross-foots the report (GO /
  GO_WITH_FIXES / NO_GO).
* :mod:`ccengine.journal` -- journal-entry drafting discipline (never
  invents an offset).
* :mod:`ccengine.report` / :mod:`ccengine.evidence` -- markdown/CSV outputs
  and per-exception evidence cards.

All data shipped with this package is fictional; the engine demonstrates a
methodology, not any real company's books.
"""

from __future__ import annotations

from .ingest import (
    load_registers,
    load_trial_balance,
    load_xlsx_registers,
    load_xlsx_trial_balance,
)
from .models import (
    ACCOUNT_STATUSES,
    EXCEPTION_KINDS,
    KIND_STALE_CLOSEOUT,
    KIND_TIMING,
    KIND_UNEXPLAINED,
    KIND_UNMAPPED_SUCCESSOR,
    PHANTOM_FLAG,
    STATUS_CLOSED,
    STATUS_LIVE,
    VERDICT_GO,
    VERDICT_GO_WITH_FIXES,
    VERDICT_NO_GO,
    VERDICT_STATUSES,
    ExceptionItem,
    RegisterAccount,
    ScopeReconciliation,
    TBRow,
    Transaction,
    Verdict,
)
from .normalize import is_placeholder_gl, normalize_gl

__version__ = "1.0.0"

__all__ = [
    "__version__",
    # models
    "Transaction",
    "RegisterAccount",
    "TBRow",
    "ExceptionItem",
    "ScopeReconciliation",
    "Verdict",
    "EXCEPTION_KINDS",
    "KIND_UNMAPPED_SUCCESSOR",
    "KIND_STALE_CLOSEOUT",
    "KIND_TIMING",
    "KIND_UNEXPLAINED",
    "PHANTOM_FLAG",
    "ACCOUNT_STATUSES",
    "STATUS_LIVE",
    "STATUS_CLOSED",
    "VERDICT_STATUSES",
    "VERDICT_GO",
    "VERDICT_GO_WITH_FIXES",
    "VERDICT_NO_GO",
    # normalize
    "normalize_gl",
    "is_placeholder_gl",
    # ingest
    "load_registers",
    "load_trial_balance",
    "load_xlsx_registers",
    "load_xlsx_trial_balance",
]
