"""Tax Surplus / ACB Model — a working Canadian foreign-affiliate surplus-pool engine.

This package implements the PUBLIC Canadian foreign-affiliate surplus regime
(Income Tax Regulations Reg. 5907 series) generically, over **fully fictional**
data. It models a multi-tier ownership chain and, per entity per fiscal year:

    standalone taxable income
        -> Reg. 5907(2)-style book-tax adjustments
        -> allocable surplus (by ownership %)
        -> distribution waterfall (exempt -> taxable -> pre-acq capital)
           with an exempt-distribution cap
        -> roll-forward of cumulative pool balances

Surplus elevates up a tier only on an *actual distribution* (Reg. 5907(1)(d)
style), at the owner's %. ACB moves ONLY on capital events (contributions,
returns of capital, pre-acquisition dividends) — never on operating income.

All entity names, figures, FX rates and paths in this package are invented for a
portfolio demonstration. Nothing here reproduces any real entity, person, or
methodology.
"""

from __future__ import annotations

__version__ = "1.1.0"

__all__ = ["__version__"]
