"""
sales_engine
============

A deterministic, **read-only** control engine for a residential for-sale
project's unit sales administration and brokerage commissions: every unit on the
Matrix proved -- row by row -- to carry a revenue per square foot, a net proceeds
and a total commission that re-derive from the prices beside them, a commission
split that sums to the total it divides, and a closing that reconciles to the
Sold/Close tab.

One workbook template is instantiated on every for-sale project, so the same
three failures recur in every instantiation. A derived column stops deriving when
somebody types over one cell of it, and from then on revenue per square foot or
net proceeds no longer follows from the price above it. The Commission Log stops
adding up, paying named agents an amount the Matrix never authorised. And the
tabs stop reconciling -- a unit marked Sold with no closing row, a sale date
logged before the offer date, a rollup the Matrix does not support.

The engine recomputes every derived figure from the base prices that produced it,
and compares. It never posts, never releases a commission and never writes to a
source artifact. Every closing test is made against an ``as_of`` carried in the
file, never the system clock.

All data shipped with this package is **fictional**. No real entity, person,
project, address or path appears anywhere.

Public API
----------
- :func:`sales_engine.engine.analyze_document`
- :func:`sales_engine.engine.analyze_folder`
- :data:`sales_engine.engine.REGISTRY`
- :func:`sales_engine.generate.generate_corpus`
- :func:`sales_engine.report.build_markdown_report`
- :func:`sales_engine.report.build_json_report`
- :func:`sales_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
