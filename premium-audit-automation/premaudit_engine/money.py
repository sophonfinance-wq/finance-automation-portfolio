"""Integer-cent money helpers. No floats cross a boundary in this engine."""
from __future__ import annotations


class MoneyError(ValueError):
    """Raised when an amount string cannot be represented exactly in cents."""


def parse_cents(text: str) -> int:
    """Parse a printed amount like '1,324.20' or '-2,580.00' into integer cents.

    The print format always carries exactly two decimals; anything else refuses.
    """
    s = text.strip().replace(",", "")
    if not s:
        raise MoneyError("empty amount")
    neg = s.startswith("-")
    if neg:
        s = s[1:]
    if "." not in s:
        raise MoneyError(f"amount without decimals: {text!r}")
    whole, _, frac = s.partition(".")
    if len(frac) != 2 or not frac.isdigit() or not (whole.isdigit() or whole == ""):
        raise MoneyError(f"malformed amount: {text!r}")
    cents = int(whole or "0") * 100 + int(frac)
    return -cents if neg else cents


def format_cents(cents: int) -> str:
    """Format integer cents as a printed amount with thousands separators."""
    neg = cents < 0
    c = -cents if neg else cents
    whole, frac = divmod(c, 100)
    return f"{'-' if neg else ''}{whole:,}.{frac:02d}"
