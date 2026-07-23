"""Bank-first reconciliation: match the register population to the TB and
classify every difference.

The population of record is the set of bank registers, never the trial
balance. A TB-first reconciliation walks the TB's cash lines and asks "does
each line tie to a bank statement?" -- which can never surface an account
the TB is missing. This module walks the *register* population and asks the
opposite question of every account: "where is this account in the books?"

Classification ladder
---------------------
Every register account lands in exactly one of five places:

* **tied** -- register and TB agree to the cent (no exception; the scope
  statement's ``tb_matched_ties`` bucket).
* ``A_UNMAPPED_SUCCESSOR`` -- a live account with no TB row at all,
  typically a successor-bank account opened mid-year that was never mapped
  into the GL. The signature blind spot of TB-first work.
* ``B_STALE_CLOSEOUT`` -- the TB still carries a balance for an account
  that was closed and swept to ~0. :func:`trace_sweeps` reads the closing
  transactions out of the register and names every destination; the class
  is only awarded when the stale TB figure equals the traced pre-sweep
  balance, so a Class B item is fully documented by construction.
* ``C_TIMING`` -- a live account whose register/TB difference is fully
  explained by post-cutoff or deposit-in-transit activity. Clears itself
  next period; no entry.
* ``D_UNEXPLAINED`` -- everything else. Nothing is ever netted away or
  silently dropped: if the evidence does not fully explain a difference,
  the difference ships as Class D and blocks sign-off.

TB rows whose GL key never matches any register account are returned
separately as ``phantom_or_no_register`` rows (the mis-keyed "typo line"
lesson) -- they have no bank-side dollar to classify, only a book line to
retire or remap.

All entities, banks, account numbers and figures used with this module are
fictional and exist only for a portfolio demonstration.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .models import (
    CENT_TOLERANCE,
    EXCEPTION_KINDS,
    KIND_STALE_CLOSEOUT,
    KIND_TIMING,
    KIND_UNEXPLAINED,
    KIND_UNMAPPED_SUCCESSOR,
    STATUS_LIVE,
    ExceptionItem,
    RegisterAccount,
    TBRow,
    Transaction,
)
from .normalize import is_placeholder_gl

__all__ = [
    "PopulationMatch",
    "match_population",
    "trace_sweeps",
    "pre_sweep_balance",
    "classify_exceptions",
    "flag_placeholder_gls",
]


# ---------------------------------------------------------------------------
# Population matching
# ---------------------------------------------------------------------------


@dataclass
class PopulationMatch:
    """Result of matching the register population against the TB.

    Attributes
    ----------
    matched:
        ``(account, tb_rows)`` pairs -- one entry per register account that
        found at least one TB row on its ``gl_norm``. Multiple TB rows on
        the same key are all carried (a typo-duplicated line is one of the
        failure modes this engine teaches); classifiers sum them.
    register_only:
        Register accounts with no TB row on their ``gl_norm``. These are
        the accounts a TB-first reconciliation can never see.
    tb_only:
        TB rows whose ``gl_norm`` matches no register account ever. These
        become the ``phantom_or_no_register`` review population.
    """

    matched: List[Tuple[RegisterAccount, List[TBRow]]] = field(
        default_factory=list
    )
    register_only: List[RegisterAccount] = field(default_factory=list)
    tb_only: List[TBRow] = field(default_factory=list)


def match_population(
    registers: List[RegisterAccount], tb_rows: List[TBRow]
) -> PopulationMatch:
    """Match every register account to its TB rows by canonical GL key.

    Matching is done exclusively on ``gl_norm`` (see
    :func:`ccengine.normalize.normalize_gl`); the raw keys are kept on the
    records for evidence but never compared.

    Parameters
    ----------
    registers:
        The full bank-side population, straight from ingest.
    tb_rows:
        The trial balance's cash rows.

    Returns
    -------
    PopulationMatch
        Every register account in exactly one of ``matched`` /
        ``register_only``; every TB row either attached to a match or in
        ``tb_only``. Nothing is dropped.
    """
    tb_by_gl: Dict[str, List[TBRow]] = {}
    for row in tb_rows:
        tb_by_gl.setdefault(row.gl_norm, []).append(row)

    result = PopulationMatch()
    for acct in registers:
        rows = tb_by_gl.get(acct.gl_norm)
        if rows:
            result.matched.append((acct, list(rows)))
        else:
            result.register_only.append(acct)

    register_gls = {acct.gl_norm for acct in registers}
    result.tb_only = [r for r in tb_rows if r.gl_norm not in register_gls]
    return result


# ---------------------------------------------------------------------------
# Sweep tracing (Class B evidence)
# ---------------------------------------------------------------------------

#: Description patterns that mark a closing sweep. The first two capture a
#: named destination; the last two are generic close-out phrasings whose
#: destination, if any, comes from the transaction's counterparty field.
_SWEEP_PATTERNS: Tuple["re.Pattern[str]", ...] = (
    re.compile(r"\btransfer\s+to\s+(?P<name>.+)", re.IGNORECASE),
    re.compile(r"\bwire\s+to\s+(?P<name>.+)", re.IGNORECASE),
    re.compile(r"\bto\s+close\s+account\b", re.IGNORECASE),
    re.compile(r"\bclose\s+account\b", re.IGNORECASE),
)

#: Trailing "... to close account" clause sometimes appended after the
#: destination name (e.g. "Transfer to Union National Bank - to close
#: account"); stripped so the destination stays clean.
_CLOSE_TAIL = re.compile(
    r"[\s,;:\-(]*\b(?:to\s+)?close\s+account\b.*$", re.IGNORECASE
)


def _sweep_lines(
    account: RegisterAccount,
) -> List[Tuple[Transaction, str]]:
    """Return ``(transaction, destination)`` for every closing-sweep outflow.

    A line qualifies when it moves money out (negative amount) and its
    description matches one of the recognised close-out patterns. The
    destination is the name captured from the description, cleaned of any
    trailing close-account clause, falling back to the register's
    counterparty column when the description names none.
    """
    out: List[Tuple[Transaction, str]] = []
    for txn in account.transactions:
        if txn.amount >= -CENT_TOLERANCE:
            continue  # sweeps move money out of the account
        name: Optional[str] = None
        for pattern in _SWEEP_PATTERNS:
            m = pattern.search(txn.description or "")
            if m is None:
                continue
            captured = m.groupdict().get("name") or ""
            name = _CLOSE_TAIL.sub("", captured).strip(" .,;:-")
            break
        if name is None:
            continue  # no pattern matched; an ordinary outflow
        if not name:
            name = (txn.counterparty or "").strip()
        out.append((txn, name))
    return out


def trace_sweeps(account: RegisterAccount) -> List[Dict[str, object]]:
    """Trace an account's closing sweeps to their named destinations.

    Reads the register's own transactions and recognises close-out lines by
    description pattern (``"Transfer to <name>"``, ``"Wire to <name>"``,
    ``"To close account"``, ``"Close account"``).

    Parameters
    ----------
    account:
        The register account to trace (typically ``status == "closed"``).

    Returns
    -------
    list[dict]
        One dict per sweep line, in register order, with keys ``date``,
        ``counterparty`` and ``amount``. Amounts are positive dollars moved
        *out* to that destination, so the list answers "where did the money
        go?" directly and sums to the total swept away.
    """
    return [
        {
            "date": txn.date,
            "counterparty": name,
            "amount": round(-txn.amount, 2),
        }
        for txn, name in _sweep_lines(account)
    ]


def pre_sweep_balance(account: RegisterAccount) -> Optional[float]:
    """Balance the account held immediately before its first closing sweep.

    This is the figure a stale TB line should still be carrying: the last
    balance the books ever saw before the account was emptied.

    Returns
    -------
    float or None
        The reconstructed pre-sweep balance, or ``None`` when the register
        contains no recognisable sweep line.
    """
    lines = _sweep_lines(account)
    if not lines:
        return None
    first = lines[0][0]
    return round(first.running_balance - first.amount, 2)


# ---------------------------------------------------------------------------
# Timing analysis (Class C evidence)
# ---------------------------------------------------------------------------


def _timing_explanation(
    account: RegisterAccount, tb_balance: float, cutoff: Optional[str]
) -> Optional[List[Transaction]]:
    """Find the trailing transactions that fully explain a live difference.

    With an explicit ``cutoff`` (ISO date), the candidate set is every
    transaction dated strictly after it; the explanation stands only if
    those amounts sum exactly to ``register - TB``.

    Without a cutoff, the register's own running balances are used: walk
    backwards to the latest line whose running balance lands exactly on the
    TB figure -- everything after that point is in-transit activity, and it
    must still sum to the difference (guarding against registers whose
    running balances do not internally foot).

    Returns the explaining transactions, or ``None`` when the difference is
    not a clean timing story (in which case the caller must classify the
    account ``D_UNEXPLAINED`` -- never invent an explanation).
    """
    txns = account.transactions
    if not txns:
        return None
    diff = account.balance - tb_balance

    if cutoff:
        trailing = [t for t in txns if t.date > cutoff]
        if trailing and abs(sum(t.amount for t in trailing) - diff) <= CENT_TOLERANCE:
            return trailing
        return None

    for i in range(len(txns) - 1, -1, -1):
        if abs(txns[i].running_balance - tb_balance) <= CENT_TOLERANCE:
            trailing = txns[i + 1:]
            if trailing and abs(sum(t.amount for t in trailing) - diff) <= CENT_TOLERANCE:
                return trailing
            return None

    # The TB may equal the opening balance, with every listed transaction
    # in transit.
    opening = txns[0].running_balance - txns[0].amount
    if (
        abs(opening - tb_balance) <= CENT_TOLERANCE
        and abs(sum(t.amount for t in txns) - diff) <= CENT_TOLERANCE
    ):
        return list(txns)
    return None


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify_exceptions(
    registers: List[RegisterAccount],
    tb_rows: List[TBRow],
    cutoff: Optional[str] = None,
) -> Tuple[List[ExceptionItem], List[TBRow]]:
    """Classify every register-vs-TB difference; drop nothing.

    Emits at most one :class:`~ccengine.models.ExceptionItem` per register
    account. Accounts that tie to the cent produce no exception and belong
    in the scope statement's ``tb_matched_ties`` bucket (see
    :func:`ccengine.scope.build_scope_reconciliation`).

    Parameters
    ----------
    registers:
        The full bank-side population, straight from ingest.
    tb_rows:
        The trial balance's cash rows.
    cutoff:
        Optional ISO reporting date. When given, Class C timing evidence is
        restricted to transactions dated strictly after it; when omitted,
        timing is derived from the register's own running balances.

    Returns
    -------
    tuple[list[ExceptionItem], list[TBRow]]
        ``(exceptions, phantom_rows)``. Exceptions are sorted by class then
        entity then GL for deterministic output. ``phantom_rows`` are the
        TB rows with no register match ever -- the
        ``phantom_or_no_register`` review population, returned separately
        because they carry no bank-side dollar to classify.
    """
    match = match_population(registers, tb_rows)
    exceptions: List[ExceptionItem] = []

    # --- Register accounts the TB cannot see at all -----------------------
    for acct in match.register_only:
        if acct.status == STATUS_LIVE:
            exceptions.append(
                ExceptionItem(
                    kind=KIND_UNMAPPED_SUCCESSOR,
                    gl_norm=acct.gl_norm,
                    entity=acct.entity,
                    register_balance=acct.balance,
                    tb_balance=None,
                    note=(
                        f"live {acct.bank} account with no trial-balance "
                        "row; map it into the GL. A TB-first reconciliation "
                        "would never see this account."
                    ),
                )
            )
        elif abs(acct.balance) > CENT_TOLERANCE:
            exceptions.append(
                ExceptionItem(
                    kind=KIND_UNEXPLAINED,
                    gl_norm=acct.gl_norm,
                    entity=acct.entity,
                    register_balance=acct.balance,
                    tb_balance=None,
                    note=(
                        f"closed account absent from the TB still holds "
                        f"{acct.balance:,.2f} at the bank; investigate "
                        "before close."
                    ),
                )
            )
        # else: closed, swept to ~0, absent from the TB -- fully resolved,
        # nothing left to book; ties by absence.

    # --- Register accounts with TB rows ------------------------------------
    for acct, rows in match.matched:
        tb_balance = round(sum(r.balance for r in rows), 2)
        diff = round(acct.balance - tb_balance, 2)
        if abs(diff) <= CENT_TOLERANCE:
            continue  # ties to the cent

        if acct.status == STATUS_LIVE:
            trailing = _timing_explanation(acct, tb_balance, cutoff)
            if trailing is not None:
                total = round(sum(t.amount for t in trailing), 2)
                # Be honest about the evidence path. With an explicit cutoff
                # these are transactions dated strictly after it ("post-cutoff");
                # without one they are the trailing in-transit items the
                # register's own running balances isolate. Claiming
                # "post-cutoff" with no cutoff configured would overstate what
                # was tested.
                if cutoff:
                    basis = (
                        f"{len(trailing)} transaction(s) dated after the "
                        f"{cutoff} cutoff"
                    )
                else:
                    basis = (
                        f"{len(trailing)} trailing in-transit transaction(s) "
                        "(no cutoff configured; isolated from the register's "
                        "running balances)"
                    )
                exceptions.append(
                    ExceptionItem(
                        kind=KIND_TIMING,
                        gl_norm=acct.gl_norm,
                        entity=acct.entity,
                        register_balance=acct.balance,
                        tb_balance=tb_balance,
                        note=(
                            f"{basis} ({trailing[0].date} to "
                            f"{trailing[-1].date}) totalling {total:,.2f} "
                            "fully explain the difference; no entry, clears "
                            "next period."
                        ),
                    )
                )
            else:
                exceptions.append(
                    ExceptionItem(
                        kind=KIND_UNEXPLAINED,
                        gl_norm=acct.gl_norm,
                        entity=acct.entity,
                        register_balance=acct.balance,
                        tb_balance=tb_balance,
                        note=(
                            f"register {acct.balance:,.2f} vs TB "
                            f"{tb_balance:,.2f} (difference {diff:,.2f}); "
                            "no timing explanation found in the register; "
                            "investigate before close."
                        ),
                    )
                )
            continue

        # Closed account whose TB row does not tie: the stale-closeout
        # story must be *fully* corroborated by the register or it is not
        # awarded -- traced destinations, account swept to ~0, and the
        # stale TB figure equal to the pre-sweep balance.
        destinations = trace_sweeps(acct)
        pre_sweep = pre_sweep_balance(acct)
        swept_to_zero = abs(acct.balance) <= CENT_TOLERANCE
        stale_figure_ties = (
            pre_sweep is not None
            and abs(pre_sweep - tb_balance) <= CENT_TOLERANCE
        )
        if destinations and swept_to_zero and stale_figure_ties:
            total_out = round(sum(d["amount"] for d in destinations), 2)
            exceptions.append(
                ExceptionItem(
                    kind=KIND_STALE_CLOSEOUT,
                    gl_norm=acct.gl_norm,
                    entity=acct.entity,
                    register_balance=acct.balance,
                    tb_balance=tb_balance,
                    destinations=destinations,
                    note=(
                        f"TB still carries the traced pre-sweep balance "
                        f"{tb_balance:,.2f}; account closed and swept to "
                        f"{len(destinations)} named destination(s) "
                        f"totalling {total_out:,.2f}. Book the close-out "
                        "entry."
                    ),
                )
            )
        else:
            reasons: List[str] = []
            if not destinations:
                reasons.append(
                    "no closing sweep could be traced in the register"
                )
            if not swept_to_zero:
                reasons.append(
                    f"the register still holds {acct.balance:,.2f}"
                )
            if destinations and not stale_figure_ties:
                reasons.append(
                    f"the stale TB figure {tb_balance:,.2f} does not equal "
                    f"the traced pre-sweep balance {pre_sweep:,.2f}"
                )
            exceptions.append(
                ExceptionItem(
                    kind=KIND_UNEXPLAINED,
                    gl_norm=acct.gl_norm,
                    entity=acct.entity,
                    register_balance=acct.balance,
                    tb_balance=tb_balance,
                    note=(
                        f"closed account carried on the TB at "
                        f"{tb_balance:,.2f} but " + "; ".join(reasons)
                        + ". Investigate before close."
                    ),
                )
            )

    kind_order = {kind: i for i, kind in enumerate(EXCEPTION_KINDS)}
    exceptions.sort(key=lambda e: (kind_order[e.kind], e.entity, e.gl_norm))
    return exceptions, match.tb_only


# ---------------------------------------------------------------------------
# Placeholder / mis-keyed GL review flag
# ---------------------------------------------------------------------------


def flag_placeholder_gls(
    registers: List[RegisterAccount],
) -> List[RegisterAccount]:
    """Return register accounts whose GL key looks mis-keyed, not real.

    A register account can tie to the TB to the cent and still be booked
    against a *placeholder* GL key -- e.g. the ``001-001-...`` BAL-row
    pattern (see :func:`ccengine.normalize.is_placeholder_gl`). Such an
    account foots perfectly and would otherwise sit silently in the
    ``tb_matched_ties`` bucket, so its suspicious key never reaches a
    reviewer. This flag is deliberately *orthogonal* to the A/B/C/D
    classification: it does not move the account out of its scope bucket
    (that would break the completeness foot), it travels alongside as a
    review list so the key gets a human look.

    Parameters
    ----------
    registers:
        The full bank-side population, straight from ingest.

    Returns
    -------
    list[RegisterAccount]
        The accounts whose ``gl_norm`` (falling back to ``gl_raw``) trips
        :func:`is_placeholder_gl`, sorted by entity then GL for
        deterministic output. Empty when every key looks like a real
        account.
    """
    flagged = [
        acct
        for acct in registers
        if is_placeholder_gl(acct.gl_norm or acct.gl_raw)
    ]
    flagged.sort(key=lambda a: (a.entity, a.gl_norm))
    return flagged
