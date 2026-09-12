"""
Money primitives for the workpaper review & handback engine.
============================================================

Every monetary amount inside the engine is an **integer number of cents**, so a
figure quoted in a citation can be compared to the figure the citation resolves
to with exact ``==``. Floating-point dollars are never used for accumulation or
comparison; they appear only at the formatting edge. Dataclass fields and JSON
keys carry a ``_cents`` suffix.

There is **no tolerance band**, and the reason is the whole point of this engine.
The defects it exists to catch are citations that resolve to a *plausible* number
rather than the right one, and the plausible-wrong number is frequently within a
rounding-sized distance of the right one. A tolerance band is precisely the
mechanism that makes those invisible: a pair of figures a dollar apart is exactly
the pair a reviewer waves through. Here, a dollar apart is a finding.

A materiality threshold does exist, but only to grade a *confirmed* difference
for review routing. It never decides whether a difference exists.

Helpers covering the operations that can lose pennies:

* :func:`split_evenly` distributes an amount across N parts so the parts sum back
  to the whole; the rounding remainder lands on the final part.
* :func:`allocate_by_ratio` splits an amount by integer basis-point weights using
  the largest-remainder method, guaranteeing the parts sum to the whole. A
  flow-through leg derived as receipts times a profit percentage is built with it.
* :func:`apply_rate` applies an integer basis-point rate with truncating division,
  so a derived figure can be compared to a reported figure with exact ``==``.

A value that should be integer cents but is not raises :class:`AmountInvalidError`
with code :data:`AMOUNT_INVALID`. The engine reports that code rather than
coercing: silently rounding a source figure would make the engine the author of
the number it is meant to audit.
"""

from __future__ import annotations

__all__ = [
    "AMOUNT_INVALID",
    "AmountInvalidError",
    "ensure_cents",
    "format_cents",
    "split_evenly",
    "allocate_by_ratio",
    "apply_rate",
]

AMOUNT_INVALID = "AMOUNT_INVALID"

BPS_DENOMINATOR = 10_000


class AmountInvalidError(ValueError):
    """A value that must be integer cents is not.

    Carries :data:`AMOUNT_INVALID` as ``code`` so a caller can report the
    condition without re-deriving why the amount was rejected.
    """

    code = AMOUNT_INVALID

    def __init__(self, value: object, field: str = "amount_cents") -> None:
        self.value = value
        self.field = field
        super().__init__(
            "%s must be an integer number of cents, got %r (%s)"
            % (field, value, type(value).__name__)
        )


def ensure_cents(value: object, field: str = "amount_cents") -> int:
    """Return ``value`` as integer cents, or raise :class:`AmountInvalidError`.

    ``bool`` is rejected even though it is an ``int`` subclass: a flag that has
    leaked into a money field is a defect, not a zero or a one.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise AmountInvalidError(value, field)
    return value


def format_cents(amount_cents: int) -> str:
    """Format integer cents for a report, negatives in parentheses.

    Accounting presentation, matching how the figures appear in the workpapers
    the engine reads. Formatting is the only place dollars appear.
    """
    amount_cents = ensure_cents(amount_cents)
    whole, frac = divmod(abs(amount_cents), 100)
    body = "{:,}.{:02d}".format(whole, frac)
    return "(" + body + ")" if amount_cents < 0 else body


def split_evenly(amount_cents: int, parts: int) -> list[int]:
    """Split ``amount_cents`` into ``parts`` pieces that sum back to the whole."""
    amount_cents = ensure_cents(amount_cents)
    if not isinstance(parts, int) or isinstance(parts, bool) or parts < 1:
        raise ValueError("parts must be a positive integer, got %r" % (parts,))
    base, remainder = divmod(amount_cents, parts)
    out = [base] * parts
    out[-1] += remainder
    assert sum(out) == amount_cents
    return out


def allocate_by_ratio(amount_cents: int, weights_bps: list[int]) -> list[int]:
    """Allocate by integer basis-point weights using largest remainder.

    The parts are guaranteed to sum to ``amount_cents``. Weights must be
    non-negative integers and must not all be zero.
    """
    amount_cents = ensure_cents(amount_cents)
    if not weights_bps:
        raise ValueError("weights_bps must not be empty")
    for w in weights_bps:
        if isinstance(w, bool) or not isinstance(w, int) or w < 0:
            raise ValueError("weights_bps must be non-negative integers, got %r" % (w,))
    total_weight = sum(weights_bps)
    if total_weight == 0:
        raise ValueError("weights_bps must not sum to zero")

    scaled = [amount_cents * w for w in weights_bps]
    floors = [s // total_weight for s in scaled]
    shortfall = amount_cents - sum(floors)
    remainders = sorted(
        range(len(weights_bps)),
        key=lambda i: (-(scaled[i] - floors[i] * total_weight), i),
    )
    out = list(floors)
    step = 1 if shortfall >= 0 else -1
    for k in range(abs(shortfall)):
        out[remainders[k % len(out)]] += step
    assert sum(out) == amount_cents
    return out


def apply_rate(base_cents: int, rate_bps: int) -> int:
    """Apply an integer basis-point rate with truncating division.

    Truncation, not rounding, so a figure derived here and a figure derived the
    same way elsewhere agree exactly rather than nearly.
    """
    base_cents = ensure_cents(base_cents, "base_cents")
    if isinstance(rate_bps, bool) or not isinstance(rate_bps, int):
        raise AmountInvalidError(rate_bps, "rate_bps")
    product = base_cents * rate_bps
    if product < 0:
        return -((-product) // BPS_DENOMINATOR)
    return product // BPS_DENOMINATOR
