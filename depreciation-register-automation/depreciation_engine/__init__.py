"""
depreciation_engine
===================

A deterministic, **read-only** control engine for an entity's fixed-asset
depreciation register and prepaid amortization schedule: every straight-line
charge re-derived from cost, life and convention; every prepaid waterfall
figure re-derived from its stated amortization window (first-period catch-up
included); the accumulated-depreciation and prepaid balances rolled forward;
and the register totals tied back to the GL control accounts and the posted
monthly recurring journal entry.

The engine owns the subledgers, not their neighbours. The JE-posting cadence of
the close, debt and loan amortization, and the prepaid-insurance entity
allocation each belong to a separate engine; the question here is narrower and
entirely arithmetical. A depreciation register is a spreadsheet of tiny derived
numbers, and it drifts in ways nobody watches: a life keyed off the class
table, a monthly charge overtyped, an asset depreciating past its end date or
before it enters service, a roll-forward that stops closing, a register total
that quietly stops tying the GL and the recurring JE.

The engine recomputes every derived figure through one shared schedule kernel
and compares. It never posts, never disposes and never writes to a source
artifact. Every derivation and date gate is measured against a ``close_month``
carried in the file, never the system clock.

All data shipped with this package is **fictional**. No real entity, person,
vendor, project or path appears anywhere.

Public API
----------
- :func:`depreciation_engine.engine.analyze_document`
- :func:`depreciation_engine.engine.analyze_folder`
- :data:`depreciation_engine.engine.REGISTRY`
- :func:`depreciation_engine.generate.generate_corpus`
- :func:`depreciation_engine.report.build_markdown_report`
- :func:`depreciation_engine.report.build_json_report`
- :func:`depreciation_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
