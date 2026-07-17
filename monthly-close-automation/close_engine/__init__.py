"""Month-End Close Engine.

A deterministic, tie-checked month-end close engine for a small multi-entity
group. Computes recurring journal entries (prepaid amortization, fixed-asset
depreciation, deferred rent + CAM straight-lining, management-fee accruals,
fixed-fee accruals, note interest accruals, G&A cost allocation, insurance,
and exact-route postage allocation), enforces
debits == credits on every entry, ties each schedule back to the general
ledger, and produces a JE register, an updated trial balance, and a markdown
close report.

All data in this package is FICTIONAL and generated with a seeded ``random``
stream for full reproducibility. Nothing here reproduces any real entity,
person, figure, or procedure.
"""

from __future__ import annotations

__version__ = "1.0.0"

__all__ = ["__version__"]
