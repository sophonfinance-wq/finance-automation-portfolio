"""Reconcile parsed print lines against a ledger export, and measure the
distance between two period bases.

A print report is authoritative about amounts and blind about transaction
dates. A ledger export carries both dates but arrives as an undifferentiated
dump. Matching them on a composite line key gives every print line its true
transaction date - and the count of lines that did NOT match is the honest
measure of how much of the answer is still assumed.

The alternative to this - inferring a transaction date from some adjacent
system's document date - is a proxy, and `proxy_error` exists to quantify how
wrong a proxy was once the real data arrives. In the engagement this module
generalizes, a document-date proxy overshot the true figure while the raw
accounting basis undershot it: the proxy was not merely imprecise, it was wrong
in the opposite direction from the error it was introduced to correct.
"""
from __future__ import annotations

import collections
import dataclasses
import datetime as dt

from .model import (AuditWindow, BasisDivergence, CostLine, LedgerRow,
                    PeriodBasis, Reconciliation)


def reconcile(lines: tuple[CostLine, ...] | list[CostLine],
              ledger: tuple[LedgerRow, ...] | list[LedgerRow]) -> Reconciliation:
    """Attach transaction dates to print lines by exact line-key match.

    Duplicate keys are resolved positionally (first print line takes the first
    ledger row with that key), never merged - two identical-looking costs are
    two costs, and collapsing them would silently halve a total.
    """
    pool: dict[tuple, list[LedgerRow]] = collections.defaultdict(list)
    for row in ledger:
        pool[row.line_key].append(row)
    for bucket in pool.values():
        bucket.sort(key=lambda r: (r.txn_date, r.tran_type.value))

    out: list[CostLine] = []
    matched = unmatched = 0
    for line in lines:
        bucket = pool.get(line.line_key)
        if bucket:
            row = bucket.pop(0)
            out.append(dataclasses.replace(line, txn_date=row.txn_date))
            matched += 1
        else:
            out.append(line)          # txn_date stays None: unknown, not assumed
            unmatched += 1
    leftover = sum(len(b) for b in pool.values())
    return Reconciliation(tuple(out), matched, unmatched, leftover)


def window_total_cents(lines, window: AuditWindow, basis: PeriodBasis,
                       *, fallback: bool = True) -> int:
    """Total the lines that fall in the window on the given basis.

    With ``fallback`` a line whose basis date is unknown is judged on its
    accounting date, which is what a preparer does in practice; without it,
    unknown-date lines are excluded, which is what a purist would do. The
    difference between the two runs is itself a useful disclosure.
    """
    total = 0
    for line in lines:
        d = line.date_on(basis)
        if d is None:
            if not fallback:
                continue
            d = line.acctg_date
        if window.contains(d):
            total += line.amount_cents
    return total


def divergence(lines, window: AuditWindow) -> BasisDivergence:
    """Compare the accounting-basis and transaction-basis cuts line by line."""
    acct = window_total_cents(lines, window, PeriodBasis.ACCOUNTING)
    txn = window_total_cents(lines, window, PeriodBasis.TRANSACTION)
    moved_in: list[CostLine] = []
    moved_out: list[CostLine] = []
    for line in lines:
        in_a = window.contains(line.acctg_date)
        td = line.txn_date if line.txn_date is not None else line.acctg_date
        in_t = window.contains(td)
        if in_a and not in_t:
            moved_out.append(line)
        elif in_t and not in_a:
            moved_in.append(line)
    return BasisDivergence(acct, txn, tuple(moved_in), tuple(moved_out))


def proxy_error(lines, window: AuditWindow,
                proxy_dates: dict[tuple, dt.date]) -> int:
    """Signed cents by which a proxy basis misses the true transaction basis.

    ``proxy_dates`` maps line keys to whatever stand-in date was used before
    the real transaction dates were available. Positive means the proxy
    overstated the period; negative means it understated it.
    """
    truth = window_total_cents(lines, window, PeriodBasis.TRANSACTION)
    proxy = 0
    for line in lines:
        d = proxy_dates.get(line.line_key, line.acctg_date)
        if window.contains(d):
            proxy += line.amount_cents
    return proxy - truth
