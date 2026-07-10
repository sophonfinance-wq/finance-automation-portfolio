"""Partnership-Tax §704(c) Model — a working US partnership (Form 1065) engine.

This package implements the PUBLIC US partnership-tax framework — IRC §704(b)
book capital, §704(c) built-in gain/loss allocation under the **traditional
method**, and the **ceiling rule** — generically, over **fully fictional** data.
It models a partnership whose partners contribute cash or appreciated property
and, per fiscal year:

    contribution at FMV (book) and carryover tax basis
        -> straight-line book vs. tax depreciation on contributed property
        -> §704(c) traditional-method tax allocation (non-contributing partners
           first, to cure the book-tax disparity)
        -> ceiling-rule limitation surfaced when tax items run short
        -> §704(c) layer roll-forward (built-in gain amortised toward zero)
        -> on sale, remaining built-in gain taxed to the contributing partner
        -> Schedule K-1-style book + tax capital roll-forward per partner

LIMITATION (documented on purpose): only the §704(c) traditional method is
implemented. The remedial and curative methods of Reg. §1.704-3 are NOT modelled;
where the ceiling rule binds, the distortion is *surfaced*, not cured.

All partnership names, partner names, figures, and paths in this package are
invented for a portfolio demonstration. Nothing here reproduces any real entity,
person, or methodology.
"""

from __future__ import annotations

__version__ = "1.0.0"

__all__ = ["__version__"]
