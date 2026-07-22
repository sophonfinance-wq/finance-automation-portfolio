"""
Money primitives for the accounts payable engine.
=================================================

Every monetary amount inside the engine is an **integer number of cents**, so
arithmetic is exact and tie-outs are deterministic. Floating-point dollars are
never used for accumulation or comparison; they appear only at the formatting
edge. Dataclass fields and JSON keys carry a ``_cents`` suffix.

Comparisons are exact ``==`` -- there is **no tolerance band**. A control that
tolerates a penny cannot prove a post balanced.

A handful of helpers handle the two operations that can lose pennies:

* :func:`split_evenly` distributes an amount across N periods so the parts sum
  back to the whole (the rounding remainder lands on the final period).
* :func:`allocate_by_ratio` splits an amount by integer basis-point weights
  using the largest-remainder method, guaranteeing the parts sum to the whole.

No control in the current registry needs to divide an amount, so those two
helpers have no caller inside the engine. They are retained deliberately as
platform-standard primitives: every engine on the platform exposes the same
penny-safe split and allocate contract, so a schedule- or allocation-shaped rule
added later inherits a tested implementation instead of hand-rolling one.

A value that should be integer cents but is not raises
:class:`AmountInvalidError`, whose code is :data:`AMOUNT_INVALID`. The engine
reports that code rather than coercing the amount: silently rounding a source
figure would make the engine the author of the number it is meant to audit.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from decimal import ROUND_HALF_UP, Decimal

# A cent is the atomic unit. 100 cents == 1 currency unit (USD, fictional).
CENTS_PER_UNIT = 100

#: Finding code emitted when a value that must be integer cents is not.
AMOUNT_INVALID = "AMOUNT_INVALID"


class AmountInvalidError(ValueError):
    """Raised when a value that must be integer cents is not an ``int``.

    Attributes
    ----------
    code:
        Always :data:`AMOUNT_INVALID`; surfaced verbatim in the finding message.
    field:
        Dotted path of the offending field, e.g. ``"POST-2026-0001/gl_recap"``.
    value:
        The rejected value, reproduced for the reviewer.
    """

    code = AMOUNT_INVALID

    def __init__(self, field: str, value: object, unit: str = "integer cents") -> None:
        self.field = field
        self.value = value
        self.unit = unit
        super().__init__(f"{AMOUNT_INVALID}: {field} must be {unit}, got {value!r}")


def require_cents(field: str, value: object, *, unit: str = "integer cents") -> int:
    """Return ``value`` as an integer, or raise :class:`AmountInvalidError`.

    ``bool`` is rejected explicitly: it is an ``int`` subclass in Python, and a
    boolean masquerading as an amount is exactly the kind of schema drift this
    guard exists to catch.

    Args:
        field: Dotted path of the field being read (used in the message).
        value: The candidate amount.
        unit: What the field is expected to hold, quoted in the message. The
            same guard protects amounts, whole counts and basis-point rates.

    Returns:
        The value, unchanged, as an ``int``.

    Raises:
        AmountInvalidError: If ``value`` is not a non-boolean ``int``.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise AmountInvalidError(field, value, unit)
    return value


def to_cents(amount: float | int | str) -> int:
    """Convert a dollar amount to integer cents, rounding half-up.

    Half-up means half **away from zero**, so ``0.005`` becomes 1 cent and
    ``-0.005`` becomes -1 cent.

    Args:
        amount: A dollar figure (e.g. ``1200.00`` or ``"1200.00"``).

    Returns:
        The amount expressed as an integer number of cents.
    """
    # The value is routed through Decimal via its string form and quantized
    # before any scaling. Multiplying by 100 in binary floating point first
    # would land values such as 1.005 just below the half-cent boundary and
    # round them down, which is the drift this conversion exists to prevent.
    quantized = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(quantized * CENTS_PER_UNIT)


def fmt(cents: int) -> str:
    """Format integer cents as a fixed two-decimal dollar string.

    No float ever touches the value: the split is done with :func:`divmod`.

    Args:
        cents: Amount in integer cents (may be negative).

    Returns:
        A string like ``"1,200.00"`` or ``"-50.00"`` (no currency symbol).
    """
    sign = "-" if cents < 0 else ""
    whole, frac = divmod(abs(cents), CENTS_PER_UNIT)
    return f"{sign}{whole:,}.{frac:02d}"


def split_evenly(total_cents: int, periods: int) -> list[int]:
    """Split a total into ``periods`` equal integer-cent parts.

    The parts sum exactly to ``total_cents``; any rounding remainder is added to
    the **final** part so straight-line schedules never drift.

    Args:
        total_cents: Amount to split, in cents.
        periods: Number of periods (must be >= 1).

    Returns:
        A list of ``periods`` integer-cent amounts summing to ``total_cents``.

    Raises:
        ValueError: If ``periods`` < 1.
    """
    if periods < 1:
        raise ValueError("periods must be >= 1")
    base = total_cents // periods
    parts = [base] * periods
    remainder = total_cents - base * periods
    parts[-1] += remainder
    return parts


def allocate_by_ratio(total_cents: int, weights_bps: Sequence[int]) -> list[int]:
    """Allocate a total across weights given in basis points (sum == 10000).

    Uses the largest-remainder (Hamilton) method so the allocated parts sum
    exactly to ``total_cents`` with no penny lost or created.

    Args:
        total_cents: Amount to allocate, in cents.
        weights_bps: Integer basis-point weights; must sum to 10000 (100.00%).

    Returns:
        A list of integer-cent allocations, one per weight, summing to
        ``total_cents``.

    Raises:
        ValueError: If the weights do not sum to exactly 10000 basis points.
    """
    if sum(weights_bps) != 10000:
        raise ValueError(
            f"allocation weights must sum to 10000 bps (100.00%); "
            f"got {sum(weights_bps)}"
        )
    floors: list[int] = []
    remainders: list[tuple[int, int]] = []  # (fractional_remainder, index)
    for idx, w in enumerate(weights_bps):
        exact = total_cents * w
        floor = exact // 10000
        floors.append(floor)
        remainders.append((exact - floor * 10000, idx))
    leftover = total_cents - sum(floors)
    # Hand out the leftover cents to the largest fractional remainders first.
    remainders.sort(key=lambda t: (-t[0], t[1]))
    for i in range(leftover):
        floors[remainders[i][1]] += 1
    return floors


def apply_rate(base_cents: int, rate_bps: int) -> int:
    """Apply an integer basis-point rate to an integer-cent base.

    Truncating division is the contract: a retention or tax line computed by a
    subcontractor progress-billing platform is derived the same way, so the
    engine can compare the reported line to the derived one with exact ``==``.

    Args:
        base_cents: Base amount in cents.
        rate_bps: Rate in basis points (1000 == 10.00%).

    Returns:
        The rated amount in integer cents.
    """
    return base_cents * rate_bps // 10000


def total(amounts: Iterable[int]) -> int:
    """Sum an iterable of integer-cent amounts."""
    return sum(amounts)
