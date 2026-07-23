"""Shared data contracts for the cash-completeness engine.

Every module in :mod:`ccengine` codes against the dataclasses in this file.
They describe a *bank-first* cash reconciliation: the population of record is
the set of bank registers (one per account), and the trial balance is tested
against that population -- never the other way around. A TB-first
reconciliation cannot see accounts that are missing from the TB; a
register-first reconciliation cannot miss them.

Conventions
-----------
* All monetary amounts are plain ``float`` dollars. Inflows are positive,
  outflows negative.
* Dates are ISO ``YYYY-MM-DD`` strings; the engine never does date math that
  needs a richer type.
* GL account numbers appear twice on every record: ``gl_raw`` exactly as it
  was keyed in the source file, and ``gl_norm`` in the canonical
  ``XXX-XXX-XXXX`` form produced by :func:`ccengine.normalize.normalize_gl`.
  All matching is done on ``gl_norm``; ``gl_raw`` is kept for evidence.
* Nothing is ever silently dropped. Anything the classifier cannot explain
  becomes a ``D_UNEXPLAINED`` exception, and TB lines with no register match
  are flagged ``phantom_or_no_register``.

All entities, banks, account numbers and figures used with these contracts
are fictional and exist only for a portfolio demonstration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Controlled vocabularies
# ---------------------------------------------------------------------------

#: Live register account with no TB row at all (e.g. a successor-bank account
#: opened mid-year that was never mapped into the GL).
KIND_UNMAPPED_SUCCESSOR = "A_UNMAPPED_SUCCESSOR"

#: TB row still carrying a balance for a register account that was closed and
#: swept to ~0; the stale figure should equal the pre-sweep balance.
KIND_STALE_CLOSEOUT = "B_STALE_CLOSEOUT"

#: Live account where the register/TB difference is fully explained by
#: post-cutoff or deposit-in-transit activity.
KIND_TIMING = "C_TIMING"

#: Anything the classifier cannot explain. Never silently dropped.
KIND_UNEXPLAINED = "D_UNEXPLAINED"

#: All valid :class:`ExceptionItem.kind` values, in severity/report order.
EXCEPTION_KINDS: tuple = (
    KIND_UNMAPPED_SUCCESSOR,
    KIND_STALE_CLOSEOUT,
    KIND_TIMING,
    KIND_UNEXPLAINED,
)

#: Review flag applied to TB rows that never match any register account
#: (the mis-keyed "typo line" lesson). Not an :class:`ExceptionItem` kind --
#: these rows have no register population entry to attach to.
PHANTOM_FLAG = "phantom_or_no_register"

#: Register account status values.
STATUS_LIVE = "live"
STATUS_CLOSED = "closed"
ACCOUNT_STATUSES: tuple = (STATUS_LIVE, STATUS_CLOSED)

#: Independent-verification verdict statuses.
VERDICT_GO = "GO"
VERDICT_GO_WITH_FIXES = "GO_WITH_FIXES"
VERDICT_NO_GO = "NO_GO"
VERDICT_STATUSES: tuple = (VERDICT_GO, VERDICT_GO_WITH_FIXES, VERDICT_NO_GO)

#: Cent-level tolerance used when footing dollar totals.
CENT_TOLERANCE = 0.005


# ---------------------------------------------------------------------------
# Core records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Transaction:
    """One line of a bank register.

    Attributes
    ----------
    date:
        ISO ``YYYY-MM-DD`` posting date.
    description:
        Verbatim bank description (used by the sweep tracer to recognise
        closing transfers, e.g. ``"Transfer to Union National Bank"``).
    amount:
        Signed dollars: positive inflow, negative outflow.
    running_balance:
        Balance of the account immediately after this transaction.
    counterparty:
        Named counterparty if the register provides one, else ``None``.
    """

    date: str
    description: str
    amount: float
    running_balance: float
    counterparty: Optional[str] = None


@dataclass
class RegisterAccount:
    """One bank account, as evidenced by its register file.

    The list of :class:`RegisterAccount` objects loaded from the register
    directory *is* the reconciliation population. Every downstream scope
    statement must account for each of these exactly once.

    Attributes
    ----------
    source_file:
        Basename of the register file this account was loaded from.
    entity:
        Legal entity that owns the account (fictional).
    bank:
        Bank name (fictional).
    bank_account_no:
        Bank's own account number, kept as a string to preserve leading
        zeros.
    gl_raw:
        GL account exactly as keyed in the source file.
    gl_norm:
        Canonical GL key from :func:`ccengine.normalize.normalize_gl`; all
        matching uses this.
    balance:
        Register (bank-side) balance as of ``as_of``.
    as_of:
        ISO date the ``balance`` speaks to.
    status:
        ``"live"`` or ``"closed"``.
    transactions:
        Register lines in source order (banks list chronologically; the
        order is preserved for sweep tracing).
    """

    source_file: str
    entity: str
    bank: str
    bank_account_no: str
    gl_raw: str
    gl_norm: str
    balance: float
    as_of: str
    status: str
    transactions: List[Transaction] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status not in ACCOUNT_STATUSES:
            raise ValueError(
                f"status for {self.gl_norm or self.gl_raw!r} must be one of "
                f"{ACCOUNT_STATUSES}, got {self.status!r}"
            )


@dataclass(frozen=True)
class TBRow:
    """One cash line of the trial balance.

    Attributes
    ----------
    source_file:
        Basename of the TB file.
    sheet:
        Sheet / tab name the row came from.
    gl_raw:
        GL account exactly as keyed (this is where typo lines live).
    gl_norm:
        Canonical GL key; ``""`` when the raw cell was blank.
    title:
        Account title per the TB.
    balance:
        TB balance in dollars.
    """

    source_file: str
    sheet: str
    gl_raw: str
    gl_norm: str
    title: str
    balance: float


@dataclass
class ExceptionItem:
    """One classified register-vs-TB exception.

    Attributes
    ----------
    kind:
        One of :data:`EXCEPTION_KINDS`.
    gl_norm:
        Canonical GL key of the register account (or the TB key when no
        register side exists).
    entity:
        Owning entity.
    register_balance:
        Bank-side balance, or ``None`` when there is no register side.
    tb_balance:
        TB-side balance, or ``None`` when there is no TB row.
    destinations:
        For ``B_STALE_CLOSEOUT``: traced sweep destinations, each a dict
        with keys ``date``, ``counterparty``, ``amount``. Empty otherwise.
    note:
        Human-readable explanation carried into the resolution schedule.
    """

    kind: str
    gl_norm: str
    entity: str
    register_balance: Optional[float] = None
    tb_balance: Optional[float] = None
    destinations: List[Dict] = field(default_factory=list)
    note: str = ""

    def __post_init__(self) -> None:
        if self.kind not in EXCEPTION_KINDS:
            raise ValueError(
                f"kind must be one of {EXCEPTION_KINDS}, got {self.kind!r}"
            )


@dataclass
class ScopeReconciliation:
    """The report's statement of scope: which bucket each account landed in.

    ``buckets`` maps a bucket name (e.g. ``"matched_clean"``,
    ``"A_UNMAPPED_SUCCESSOR"``) to the list of register ``gl_norm`` keys
    placed in it. ``totals`` maps the same bucket names to the summed
    *register* balances of those accounts.

    :meth:`foot` is the completeness test: every register account must sit
    in exactly one bucket, no bucket may claim an account that does not
    exist, and every total must re-add from the member balances.
    """

    buckets: Dict[str, List[str]] = field(default_factory=dict)
    totals: Dict[str, float] = field(default_factory=dict)

    def foot(self, all_register_accounts: List[RegisterAccount]) -> List[str]:
        """Cross-foot this scope statement against the register population.

        Parameters
        ----------
        all_register_accounts:
            The full register population, straight from ingest.

        Returns
        -------
        list[str]
            Human-readable problems. An empty list means the scope statement
            is clean: every register account appears in exactly one bucket,
            no bucket references an unknown account, bucket and total keys
            agree, and every total re-adds to the cent.
        """
        problems: List[str] = []

        # Where does each gl_norm claim to sit?
        placements: Dict[str, List[str]] = {}
        for bucket_name, members in self.buckets.items():
            for gl in members:
                placements.setdefault(gl, []).append(bucket_name)

        balances: Dict[str, float] = {}
        seen: set = set()
        for acct in all_register_accounts:
            gl = acct.gl_norm
            balances[gl] = balances.get(gl, 0.0) + acct.balance
            if gl in seen:
                problems.append(
                    f"register population contains duplicate gl_norm {gl} "
                    f"({acct.entity}, {acct.source_file}); scope cannot be "
                    "footed on a non-unique key"
                )
                continue
            seen.add(gl)
            spots = placements.get(gl, [])
            if len(spots) == 0:
                problems.append(
                    f"register account {gl} ({acct.entity}) is missing from "
                    "every scope bucket"
                )
            elif len(spots) > 1:
                problems.append(
                    f"register account {gl} ({acct.entity}) appears in "
                    f"{len(spots)} buckets: {sorted(spots)}"
                )

        for gl in sorted(placements):
            if gl not in balances:
                names = sorted(set(placements[gl]))
                problems.append(
                    f"bucket(s) {names} list {gl}, which is not in the "
                    "register population"
                )

        for name in self.buckets:
            if name not in self.totals:
                problems.append(f"bucket '{name}' has no entry in totals")
        for name in self.totals:
            if name not in self.buckets:
                problems.append(
                    f"totals has entry '{name}' with no matching bucket"
                )

        for name, members in self.buckets.items():
            if name not in self.totals:
                continue
            summed = sum(balances.get(gl, 0.0) for gl in members)
            if abs(summed - self.totals[name]) > CENT_TOLERANCE:
                problems.append(
                    f"bucket '{name}' total {self.totals[name]:.2f} does not "
                    f"re-add from member register balances ({summed:.2f})"
                )

        return problems


@dataclass
class Verdict:
    """Outcome of the independent verification pass.

    Attributes
    ----------
    status:
        ``"GO"`` (report is safe to ship), ``"GO_WITH_FIXES"`` (ship after
        the listed fixes), or ``"NO_GO"`` (the report overclaims; do not
        ship).
    findings:
        One dict per finding with keys ``severity``, ``finding``, ``fix``.
    """

    status: str
    findings: List[Dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status not in VERDICT_STATUSES:
            raise ValueError(
                f"status must be one of {VERDICT_STATUSES}, got {self.status!r}"
            )
