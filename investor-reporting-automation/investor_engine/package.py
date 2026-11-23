"""
The package arithmetic, defined once.
=====================================

Re-deriving a figure the investor package states -- a net balance, a capital
ending, a Total column, the section a balance belongs in, the gap between a job
cost report and the ledger behind it, whether a caption fits its schedule, and
whether the package may leave the building -- is the single operation this whole
engine is built around, so it lives here alone and both the generator and the
controls import it.

That is deliberate. If the engine recomputed a member's ending capital or the
side of the balance sheet an intercompany balance belongs on by *different* logic
than the logic that produced the data, the two would disagree on the edge cases
-- a member's capital ending exactly at zero, an intercompany account sitting
exactly flat, a bridge whose reconciling items exactly close the gap, a caption
that carries both markers at once -- and the tie-out controls would be measuring
the disagreement between two implementations rather than the correctness of the
package.

Everything here works on already-extracted primitives -- integer cents, integer
basis points and plain strings -- so the caller owns reading (and, in the
engine's case, integer-validating) the raw fields. That keeps the kernel free of
JSON-shape and money-coercion concerns and makes the boundary rules -- a flat
balance presented as an asset, a bridge closed *exactly* by its disclosures, a
package held the moment one exception is open -- state exactly once.
"""

from __future__ import annotations

from collections.abc import Iterable

from .model import (
    CAPTION_FORBIDDEN,
    CAPTION_REQUIRED,
    RELEASE_HELD,
    RELEASE_RELEASED,
    SECTION_ASSETS,
    SECTION_LIABILITIES,
)


def net_balance(debit_cents: int, credit_cents: int) -> int:
    """The signed balance of an account: debits less credits.

    One number instead of two, so a balance can be compared to the figure the
    package states for it without either side having to guess which column the
    preparer used. A positive result is a net debit, a negative result a net
    credit, and zero is an account that cycled and closed -- which is not the
    same thing as an account with no activity, and ``tb_completeness`` cares
    about the difference.
    """
    return debit_cents - credit_cents


def has_activity(debit_cents: int, credit_cents: int) -> bool:
    """Whether an account moved in the period at all.

    Activity is *either* column being non-zero, never the net. A clearing
    account that took in 45,000 and released 45,000 has a net balance of zero
    and is emphatically not an account with nothing in it: dropping it from the
    package trial balance hides the whole of what it did.
    """
    return debit_cents != 0 or credit_cents != 0


def presentation_section(net_cents: int) -> str:
    """The balance sheet section a signed balance has to be presented in.

    A net credit is a liability whatever the chart of accounts numbered it. This
    is the rule behind ``interco_classified``: an intercompany account that has
    gone into credit is money the project entity owes, and netting it against
    assets understates both sides of the statement by the same amount, which is
    exactly why the balance sheet still balances afterwards and nobody notices.

    A flat balance is presented as an asset: there is nothing owed, so there is
    nothing to reclassify, and a zero row on the asset side is the harmless
    presentation of the two.
    """
    return SECTION_LIABILITIES if net_cents < 0 else SECTION_ASSETS


def capital_ending(
    beginning_cents: int,
    contributions_cents: int,
    net_income_cents: int,
    distributions_cents: int,
) -> int:
    """A member's capital at the end of the period.

    The whole of the capital rollforward: what the member had, plus what the
    member put in, plus the member's share of the result, less what came back
    out. Distributions are subtracted rather than carried as a negative
    contribution, so a return of capital is always visible as its own row
    instead of quietly shrinking the contribution column.
    """
    return beginning_cents + contributions_cents + net_income_cents - distributions_cents


def cross_foot(column_values: Iterable[int]) -> int:
    """The Total column figure a row of member columns produces.

    Trivial arithmetic, named and shared on purpose. The defect this exists to
    catch is a Total cell that links somewhere else -- to the ledger, to a
    funding notice, to last period's total -- instead of summing the row it sits
    on. Naming the sum makes "the Total column is the sum of the member columns"
    a statement the code makes once rather than an assumption spread across
    controls.
    """
    return sum(column_values)


def variance(stated_cents: int, derived_cents: int) -> int:
    """Stated less derived: the figure an exception has to quantify.

    Reported in this direction so the sign reads the way a reviewer thinks about
    it -- positive means the package says more than its source supports.
    """
    return stated_cents - derived_cents


def bridge_gap(ledger_cents: int, report_cents: int, reconciled_cents: int) -> int:
    """What is left of a job cost bridge once its disclosures are applied.

    The report plus everything itemized against it must reach the ledger. A
    non-zero result is a difference that was neither itemized nor disclosed --
    the difference that gets absorbed into a rounding line and never reaches the
    partner. Zero means the bridge closes **exactly**; there is no tolerance
    band, because a bridge that nearly closes is a bridge with an unexplained
    figure in it.
    """
    return ledger_cents - (report_cents + reconciled_cents)


def caption_matches(schedule_type: str, caption: str) -> tuple[bool, tuple[str, ...]]:
    """Whether a schedule's caption says what the schedule actually measures.

    A cost-to-date schedule captioned as period activity is read as a month of
    spend when it is really every month since the ground broke. The comparison
    is case-insensitive on purpose -- a caption's case is a house-style question
    and not a control -- and a caption has to carry a marker of its own type
    *and* carry none of the other type's, so it cannot straddle both.

    Args:
        schedule_type: One of :data:`~investor_engine.model.SCHEDULE_TYPES`.
        caption: The caption as printed.

    Returns:
        ``(ok, offending_markers)``. When ``ok`` is ``False`` the tuple holds the
        markers of the *other* type that the caption carries, or is empty when
        the caption simply carries no marker of its own type at all.
    """
    required = CAPTION_REQUIRED.get(schedule_type, ())
    forbidden = CAPTION_FORBIDDEN.get(schedule_type, ())
    lowered = caption.lower()
    offending = tuple(m for m in forbidden if m in lowered)
    if offending:
        return (False, offending)
    if not any(m in lowered for m in required):
        return (False, ())
    return (True, ())


def release_decision_required(blocking_count: int) -> str:
    """The decision the package's own exception position forces.

    One open exception is enough to hold the package. There is no materiality
    gate here and there should not be: materiality is a judgement about a figure
    the partner has not seen yet, and the engine's job is to make sure whoever
    makes that judgement is looking at the exception rather than at a package
    already in the partner's inbox.
    """
    return RELEASE_HELD if blocking_count > 0 else RELEASE_RELEASED
