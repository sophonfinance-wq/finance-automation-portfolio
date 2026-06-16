"""Money helpers for the 1065 automation demo."""

from __future__ import annotations


def to_cents(amount: float | int) -> int:
    """Convert dollars to integer cents."""
    return int(round(float(amount) * 100))


def fmt(cents: int) -> str:
    """Format cents as accounting-style dollars."""
    if cents < 0:
        return f"({abs(cents) / 100:,.2f})"
    return f"{cents / 100:,.2f}"


def allocate_by_bps(total_cents: int, bps: list[int]) -> list[int]:
    """Allocate cents by basis points, preserving the exact total.

    Uses largest-remainder allocation so partner K-1 amounts sum exactly to the
    Schedule K total even when percentages create pennies.
    """
    sign = -1 if total_cents < 0 else 1
    total_abs = abs(total_cents)
    raw = [total_abs * bp for bp in bps]
    base = [value // 10_000 for value in raw]
    remainder = total_abs - sum(base)
    order = sorted(range(len(bps)), key=lambda i: raw[i] % 10_000, reverse=True)
    for i in order[:remainder]:
        base[i] += 1
    return [sign * value for value in base]
