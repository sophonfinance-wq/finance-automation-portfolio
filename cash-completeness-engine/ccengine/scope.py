"""Scope reconciliation: every register account in exactly one bucket.

The scope statement is the report's completeness claim, written down in a
form that can be cross-footed. It places each account of the bank-side
population -- the registers, never the trial balance -- into exactly one of
five buckets:

    tb_matched_ties   register and TB agree to the cent (including closed
                      accounts that were fully resolved, with nothing left
                      to book)
    exceptions_A      A_UNMAPPED_SUCCESSOR -- live account with no TB row
    exceptions_B      B_STALE_CLOSEOUT -- TB still carries a swept balance
    exceptions_C      C_TIMING -- difference explained by post-cutoff items
    exceptions_D      D_UNEXPLAINED -- everything else; blocks sign-off

All five buckets are always present, even when empty, so a reader can see
at a glance that no class was quietly omitted. Bucket totals are the summed
*register* balances of the member accounts, which is what lets
:meth:`~ccengine.models.ScopeReconciliation.foot` (and, independently,
:func:`ccengine.verify.independent_verify`) re-add them from raw balances.

Phantom TB rows (``phantom_or_no_register``) are deliberately NOT scope
members: the scope statement covers the register population, and a TB line
with no register behind it has no bank-side dollar to place. Those rows
travel separately through the report and the resolution schedule.

A scope statement that does not foot is worse than no scope statement at
all -- it is the overclaim this engine exists to catch -- so
:func:`foot_scope` returns the *exact* orphaned, double-counted, or unknown
accounts rather than a boolean.

All entities, banks, account numbers and figures used with this module are
fictional and exist only for a portfolio demonstration.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

from .models import (
    KIND_STALE_CLOSEOUT,
    KIND_TIMING,
    KIND_UNEXPLAINED,
    KIND_UNMAPPED_SUCCESSOR,
    ExceptionItem,
    RegisterAccount,
    ScopeReconciliation,
)

__all__ = [
    "BUCKET_MATCHED",
    "BUCKET_A",
    "BUCKET_B",
    "BUCKET_C",
    "BUCKET_D",
    "BUCKET_ORDER",
    "KIND_TO_BUCKET",
    "build_scope_reconciliation",
    "foot_scope",
]

#: Accounts whose register balance ties to the TB to the cent.
BUCKET_MATCHED = "tb_matched_ties"
#: One bucket per exception class, in report order.
BUCKET_A = "exceptions_A"
BUCKET_B = "exceptions_B"
BUCKET_C = "exceptions_C"
BUCKET_D = "exceptions_D"

#: Every bucket a register account can land in, in presentation order.
BUCKET_ORDER: Tuple[str, ...] = (
    BUCKET_MATCHED,
    BUCKET_A,
    BUCKET_B,
    BUCKET_C,
    BUCKET_D,
)

#: Exception kind -> scope bucket.
KIND_TO_BUCKET: Dict[str, str] = {
    KIND_UNMAPPED_SUCCESSOR: BUCKET_A,
    KIND_STALE_CLOSEOUT: BUCKET_B,
    KIND_TIMING: BUCKET_C,
    KIND_UNEXPLAINED: BUCKET_D,
}

#: Conflict rank when (defensively) one GL key carries exceptions of more
#: than one class: the most conservative placement wins, and unexplained
#: always wins -- a dollar must never look more resolved than it is.
_CONFLICT_RANK: Dict[str, int] = {
    BUCKET_C: 0,
    BUCKET_B: 1,
    BUCKET_A: 2,
    BUCKET_D: 3,
}


def build_scope_reconciliation(
    registers: Iterable[RegisterAccount],
    exceptions: Iterable[ExceptionItem],
) -> ScopeReconciliation:
    """Place every register account in exactly one scope bucket.

    Placement is driven by the classified exceptions: an account with an
    exception goes to that exception's bucket; an account with none ties
    and goes to ``tb_matched_ties``. Because the loop runs over the
    *register population* (not over the exceptions), an account cannot be
    skipped -- completeness is structural, not a matter of the classifier
    remembering everyone.

    Parameters
    ----------
    registers:
        The full bank-side population, straight from ingest.
    exceptions:
        Classified items from
        :func:`ccengine.reconcile.classify_exceptions`. Exceptions keyed to
        a GL that is not in the register population (there should be none;
        phantom TB rows are not exceptions) are ignored here and will be
        surfaced by the verifier if a report ever claims them.

    Returns
    -------
    ScopeReconciliation
        All five buckets present (possibly empty), members sorted for
        deterministic output, and ``totals`` holding the summed register
        balances per bucket. Duplicate ``gl_norm`` keys in the population
        are placed once per account so that :meth:`foot` reports them
        loudly instead of hiding them.

    Raises
    ------
    ValueError
        If an exception carries a kind outside the shared vocabulary.
    """
    placement: Dict[str, str] = {}
    for item in exceptions:
        bucket = KIND_TO_BUCKET.get(item.kind)
        if bucket is None:
            raise ValueError(
                f"exception for {item.gl_norm!r} has unknown kind "
                f"{item.kind!r}; expected one of {sorted(KIND_TO_BUCKET)}"
            )
        current = placement.get(item.gl_norm)
        if current is None or _CONFLICT_RANK[bucket] > _CONFLICT_RANK[current]:
            placement[item.gl_norm] = bucket

    buckets: Dict[str, List[str]] = {name: [] for name in BUCKET_ORDER}
    totals: Dict[str, float] = {name: 0.0 for name in BUCKET_ORDER}
    for acct in registers:
        bucket = placement.get(acct.gl_norm, BUCKET_MATCHED)
        buckets[bucket].append(acct.gl_norm)
        totals[bucket] += acct.balance

    for name in buckets:
        buckets[name].sort()
    for name in totals:
        totals[name] = round(totals[name], 2)
    return ScopeReconciliation(buckets=buckets, totals=totals)


def foot_scope(
    scope: ScopeReconciliation,
    registers: Iterable[RegisterAccount],
) -> List[str]:
    """Cross-foot a scope statement against the register population.

    Thin wiring over :meth:`ccengine.models.ScopeReconciliation.foot`, kept
    here so callers holding a scope statement and a population do not need
    to know which side owns the check.

    Parameters
    ----------
    scope:
        The scope statement to test (typically from
        :func:`build_scope_reconciliation`, but any
        :class:`~ccengine.models.ScopeReconciliation` -- including one
        rebuilt from a saved report -- foots the same way).
    registers:
        The full register population, straight from ingest.

    Returns
    -------
    list[str]
        Human-readable problems naming the exact orphaned accounts (in the
        population but in no bucket), double-counted accounts (in more than
        one bucket), unknown accounts (in a bucket but not the population),
        and any bucket total that does not re-add from its members'
        register balances. An empty list means the scope statement is
        clean.
    """
    return scope.foot(list(registers))
