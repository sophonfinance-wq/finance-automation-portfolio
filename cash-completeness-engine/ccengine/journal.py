"""Journal-entry discipline: draft only what the evidence supports.

The most dangerous moment of a reconciliation is the last one, when
exceptions turn into journal entries. A misclassified exception costs a
re-review; a journal entry with an *invented* offset moves real balances
between the wrong accounts and survives until someone repeats the whole
investigation. This module therefore refuses to guess:

* A draft is ``ready`` only when BOTH the amount and the offset are fully
  documented by the underlying evidence. For a stale close-out that means
  the traced sweep destinations must exist and re-add to the stale TB
  figure to the cent -- the destinations *are* the documented offset.
* When anything is missing, the draft is ``needs_judgment`` and carries the
  precise question a reviewer must answer. It never carries guessed lines.
* Timing differences get ``no_entry``: post-cutoff activity clears itself
  next period, and booking against it would double-count.
* Phantom TB rows (no register has ever matched the line) get ``no_entry``
  with the instruction to retire the line -- there is no cash to book.

Every draft that carries lines is asserted to balance to the cent before it
leaves this module; an unbalanced draft is a bug, not a review item.

Like :mod:`ccengine.report`, this module is representation-tolerant: it
accepts the ``ExceptionItem`` / ``TBRow`` objects from ``models.py`` or
their plain-dict serializations (e.g. exceptions read back from a saved
report). The kind and status strings below mirror the controlled
vocabularies in ``models.py``.

All entities, banks, accounts, and figures in this package are fictional
(Juniper 42 Development LLC, First Legacy Bank, Union National Bank, and
friends); see the repository README.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, Iterable, List, Optional

__all__ = ["JEDraft", "draft_entries", "STATUS_READY", "STATUS_NEEDS_JUDGMENT",
           "STATUS_NO_ENTRY", "JE_STATUSES"]

# --------------------------------------------------------------------------
# Controlled vocabulary (mirrors models.py -- kept in sync by tests)
# --------------------------------------------------------------------------

#: Amount and offset fully documented; safe to book as drafted.
STATUS_READY = "ready"
#: Something is undocumented; the draft carries the reviewer's question
#: instead of guessed lines.
STATUS_NEEDS_JUDGMENT = "needs_judgment"
#: No entry is the correct answer (timing, phantom lines).
STATUS_NO_ENTRY = "no_entry"

JE_STATUSES: tuple = (STATUS_READY, STATUS_NEEDS_JUDGMENT, STATUS_NO_ENTRY)

_KIND_UNMAPPED = "A_UNMAPPED_SUCCESSOR"
_KIND_STALE = "B_STALE_CLOSEOUT"
_KIND_TIMING = "C_TIMING"
_KIND_UNEXPLAINED = "D_UNEXPLAINED"

#: One half-cent: two amounts within this are "equal to the cent".
_CENT = 0.005


# --------------------------------------------------------------------------
# The draft record
# --------------------------------------------------------------------------


@dataclass
class JEDraft:
    """One drafted journal entry (or the documented decision not to book one).

    Attributes
    ----------
    ref:
        Stable reference (``JE-001``, ``JE-002``, ...) used in the CSV and
        the executive summary.
    entity:
        Owning entity, when known. Phantom TB rows have no register side
        and therefore may not have one.
    lines:
        Zero or more dicts with keys ``account``, ``debit``, ``credit``
        (floats, zero on the unused side). Non-empty only for ``ready``
        drafts: an undocumented entry gets a question, never guessed lines.
    status:
        One of :data:`JE_STATUSES`.
    question:
        For ``needs_judgment``: the precise question the reviewer must
        answer before anything is booked. For ``no_entry``: the rationale /
        instruction (e.g. "retire the line"). Blank only when ``ready``.
    """

    ref: str
    entity: str
    lines: List[Dict[str, Any]] = dc_field(default_factory=list)
    status: str = STATUS_NEEDS_JUDGMENT
    question: str = ""

    def __post_init__(self) -> None:
        if self.status not in JE_STATUSES:
            raise ValueError(
                f"status must be one of {JE_STATUSES}, got {self.status!r}"
            )

    @property
    def total_debits(self) -> float:
        """Sum of the debit column, rounded to the cent."""
        return round(sum(float(l.get("debit") or 0.0) for l in self.lines), 2)

    @property
    def total_credits(self) -> float:
        """Sum of the credit column, rounded to the cent."""
        return round(sum(float(l.get("credit") or 0.0) for l in self.lines), 2)


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _get(obj: Any, name: str, default: Any = None) -> Any:
    """Read ``name`` from a dataclass attribute or a mapping key."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _num(value: Any) -> Optional[float]:
    """Coerce to float, returning ``None`` for missing / non-numeric values."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _money(x: Optional[float]) -> str:
    """Format dollars for question text; ``None`` stays visibly missing."""
    if x is None:
        return "n/a"
    x = float(x)
    return f"({abs(x):,.2f})" if x < 0 else f"{x:,.2f}"


def _line(account: str, debit: float = 0.0, credit: float = 0.0) -> Dict[str, Any]:
    """Build one JE line dict with cent-rounded amounts."""
    return {
        "account": account,
        "debit": round(float(debit), 2),
        "credit": round(float(credit), 2),
    }


def _assert_balanced(draft: JEDraft) -> None:
    """Every line-bearing draft must balance to the cent. Non-negotiable."""
    if not draft.lines:
        return
    assert abs(draft.total_debits - draft.total_credits) <= _CENT, (
        f"{draft.ref}: drafted lines do not balance "
        f"(debits {draft.total_debits:,.2f}, credits {draft.total_credits:,.2f})"
    )


# --------------------------------------------------------------------------
# Per-class drafting rules
# --------------------------------------------------------------------------


def _draft_unmapped_successor(ref: str, exc: Any) -> JEDraft:
    """Class A: live register account with no TB row.

    The amount is documented (the bank register), but the offset is not:
    nobody has yet said which GL line should carry this cash or which
    documented movement funded it. Inventing that offset is exactly the
    mistake this module exists to prevent, so the draft asks instead.
    """
    gl = str(_get(exc, "gl_norm") or "")
    entity = str(_get(exc, "entity") or "")
    reg = _num(_get(exc, "register_balance"))
    return JEDraft(
        ref=ref,
        entity=entity,
        lines=[],
        status=STATUS_NEEDS_JUDGMENT,
        question=(
            f"Live account {gl} holds {_money(reg)} at the bank but has no "
            f"trial-balance row. Which GL line should carry this cash, and "
            f"what documented movement funded it (often the debit side of a "
            f"Class B close-out sweep)? Map the account first; book nothing "
            f"until the offset is documented."
        ),
    )


def _draft_stale_closeout(ref: str, exc: Any) -> JEDraft:
    """Class B: TB still carries a balance for a closed, swept account.

    ``ready`` only when the evidence is complete: the stale TB figure is
    known, the register is truly swept to ~0, and the traced sweep
    destinations re-add to the stale figure to the cent. The destinations
    are then the documented offset -- one debit line per traced sweep,
    one credit clearing the stale GL. Any gap downgrades the draft to
    ``needs_judgment`` with the exact shortfall named.
    """
    gl = str(_get(exc, "gl_norm") or "")
    entity = str(_get(exc, "entity") or "")
    tb = _num(_get(exc, "tb_balance"))
    reg = _num(_get(exc, "register_balance"))
    destinations = list(_get(exc, "destinations") or [])

    def _needs(question: str) -> JEDraft:
        return JEDraft(ref=ref, entity=entity, lines=[],
                       status=STATUS_NEEDS_JUDGMENT, question=question)

    if tb is None:
        return _needs(
            f"Closed account {gl}: the TB balance is missing, so the amount "
            f"to clear is undocumented. Confirm the stale TB figure before "
            f"booking."
        )
    if reg is None:
        # A missing register balance is *unknown*, not confirmed zero. A
        # close-out entry assumes the account was swept to ~0, so an absent
        # figure must be resolved before booking -- never coerced to 0.0.
        return _needs(
            f"Closed account {gl}: the register balance is missing, so the "
            f"account cannot be confirmed swept to zero. Supply the register "
            f"balance before booking a close-out entry."
        )
    if abs(reg) > _CENT:
        return _needs(
            f"Account {gl} is marked closed but the register still shows "
            f"{_money(reg)}. A close-out entry assumes a swept-to-zero "
            f"account; confirm the register before booking."
        )
    if not destinations:
        return _needs(
            f"Closed account {gl} still carries {_money(tb)} on the TB, but "
            f"no sweep destinations could be traced from the register. "
            f"Document where the closing balance went before booking; do "
            f"not book against an untraced offset."
        )

    amounts = [_num(_get(d, "amount")) for d in destinations]
    if any(a is None for a in amounts):
        return _needs(
            f"Closed account {gl}: one or more traced sweep destinations "
            f"has no parseable amount. Complete the trace before booking."
        )
    traced = [abs(a) for a in amounts]  # magnitudes of money that left
    traced_total = round(sum(traced), 2)
    if abs(traced_total - abs(tb)) > _CENT:
        gap = round(abs(tb) - traced_total, 2)
        return _needs(
            f"Closed account {gl}: traced sweeps total {_money(traced_total)} "
            f"but the stale TB figure is {_money(abs(tb))}; document the "
            f"remaining {_money(gap)} before booking. Partial offsets are "
            f"not booked."
        )

    # Fully documented: clear the stale GL against the traced destinations.
    # Direction follows the TB balance being removed; the per-destination
    # side re-adds exactly, so the entry balances by construction.
    lines: List[Dict[str, Any]] = []
    for d, magnitude in zip(destinations, traced):
        counterparty = str(_get(d, "counterparty") or "").strip()
        date = str(_get(d, "date") or "").strip()
        label = counterparty or "(unnamed sweep destination)"
        account = f"Cash - {label}" + (f" (swept {date})" if date else "")
        if tb >= 0:
            lines.append(_line(account, debit=magnitude))
        else:
            lines.append(_line(account, credit=magnitude))
    if tb >= 0:
        lines.append(_line(f"Cash - {gl} (stale close-out)", credit=traced_total))
    else:
        lines.append(_line(f"Cash - {gl} (stale close-out)", debit=traced_total))

    return JEDraft(ref=ref, entity=entity, lines=lines, status=STATUS_READY,
                   question="")


def _draft_timing(ref: str, exc: Any) -> JEDraft:
    """Class C: difference fully explained by post-cutoff / DIT activity."""
    gl = str(_get(exc, "gl_norm") or "")
    entity = str(_get(exc, "entity") or "")
    reg = _num(_get(exc, "register_balance"))
    tb = _num(_get(exc, "tb_balance"))
    return JEDraft(
        ref=ref,
        entity=entity,
        lines=[],
        status=STATUS_NO_ENTRY,
        question=(
            f"No entry: register {_money(reg)} vs TB {_money(tb)} on {gl} is "
            f"explained by timing (in-transit / post-cutoff) activity and "
            f"clears next period. Re-check at the next close."
        ),
    )


def _draft_unexplained(ref: str, exc: Any) -> JEDraft:
    """Class D: nothing explains the difference. Never book against it."""
    gl = str(_get(exc, "gl_norm") or "")
    entity = str(_get(exc, "entity") or "")
    reg = _num(_get(exc, "register_balance"))
    tb = _num(_get(exc, "tb_balance"))
    diff = None
    if reg is not None or tb is not None:
        diff = round((reg or 0.0) - (tb or 0.0), 2)
    return JEDraft(
        ref=ref,
        entity=entity,
        lines=[],
        status=STATUS_NEEDS_JUDGMENT,
        question=(
            f"Unexplained difference of {_money(diff)} on {gl} (register "
            f"{_money(reg)}, TB {_money(tb)}). What transaction population "
            f"explains it? Investigate before close; an entry against an "
            f"unexplained difference is a plug, not a fix."
        ),
    )


def _draft_unknown_kind(ref: str, exc: Any, kind: str) -> JEDraft:
    """Anything with an unrecognized kind: surface it, never drop it."""
    gl = str(_get(exc, "gl_norm") or "")
    entity = str(_get(exc, "entity") or "")
    return JEDraft(
        ref=ref,
        entity=entity,
        lines=[],
        status=STATUS_NEEDS_JUDGMENT,
        question=(
            f"Exception on {gl} carries unrecognized kind {kind!r}; classify "
            f"it before any entry is considered."
        ),
    )


def _draft_phantom(ref: str, row: Any) -> JEDraft:
    """Phantom / no-register TB row: retire the line, book nothing.

    These are the typo-line lesson: a TB row whose GL key never matched a
    register account. There is no cash behind the line, so a cash entry
    would manufacture money; the fix is editorial, not monetary.
    """
    gl = str(_get(row, "gl_norm") or _get(row, "gl_raw") or "")
    title = str(_get(row, "title") or "").strip()
    sheet = str(_get(row, "sheet") or "").strip()
    balance = _num(_get(row, "balance"))
    where = f" on sheet '{sheet}'" if sheet else ""
    label = f" ('{title}')" if title else ""
    return JEDraft(
        ref=ref,
        entity=str(_get(row, "entity") or ""),
        lines=[],
        status=STATUS_NO_ENTRY,
        question=(
            f"Retire the line: TB row {gl}{label}{where} carries "
            f"{_money(balance)} but no register account has ever matched it. "
            f"Correct or remove the TB line; no cash entry exists because no "
            f"cash exists."
        ),
    )


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

_DISPATCH = {
    _KIND_UNMAPPED: _draft_unmapped_successor,
    _KIND_STALE: _draft_stale_closeout,
    _KIND_TIMING: _draft_timing,
    _KIND_UNEXPLAINED: _draft_unexplained,
}


def draft_entries(
    exceptions: Iterable[Any],
    phantom_rows: Optional[Iterable[Any]] = None,
) -> List[JEDraft]:
    """Draft one journal-entry decision per exception (and phantom TB row).

    Parameters
    ----------
    exceptions:
        Classified ``ExceptionItem`` objects (or their dict serializations)
        from ``reconcile``. Every item yields exactly one draft; nothing is
        dropped.
    phantom_rows:
        Optional TB rows flagged ``phantom_or_no_register`` -- lines with no
        register match ever. Each yields a ``no_entry`` draft instructing
        the reviewer to retire the line.

    Returns
    -------
    list[JEDraft]
        One draft per input, in input order, with sequential ``JE-NNN``
        references. Only fully documented drafts are ``ready``; every
        line-bearing draft is asserted to balance to the cent.
    """
    drafts: List[JEDraft] = []
    seq = 0

    for exc in exceptions:
        seq += 1
        ref = f"JE-{seq:03d}"
        kind = str(_get(exc, "kind") or "")
        maker = _DISPATCH.get(kind)
        draft = maker(ref, exc) if maker else _draft_unknown_kind(ref, exc, kind)
        _assert_balanced(draft)
        drafts.append(draft)

    for row in phantom_rows or []:
        seq += 1
        draft = _draft_phantom(f"JE-{seq:03d}", row)
        _assert_balanced(draft)
        drafts.append(draft)

    return drafts
