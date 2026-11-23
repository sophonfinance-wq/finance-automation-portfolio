"""
proforma_engine
===============

A deterministic, **read-only** control engine for a real-estate developer's
quarterly project-proforma reporting (QPR): every active development project's
proforma re-derived, figure by figure, and held to the tie-out registry the
workbook is built around -- source-and-use balance, cost-budget equalities,
interest-reserve adequacy, the profit -> waterfall -> distribution chain,
margin and per-NSF re-derivation, current-vs-prior variance, and the
reporting-calendar completeness and due-date gate.

A quarterly proforma is a workbook that was internally consistent the day it was
saved, and it drifts in ways nobody watches: a source-and-use total that stopped
balancing, a net profit that no longer equals revenue minus cost, a waterfall
whose distributed profit stopped tying to the budgeted profit, a margin quoted
off a stale cost, a variance column that was typed rather than subtracted, a
project whose QPR never made the cycle or landed after its region's due date.

The engine recomputes every stated figure from the proforma's own base ledger
through the same kernel that produced the data, and compares. It never books,
never files and never writes to a source artifact. Every date gate is measured
against an ``as_of`` carried in the file, never the system clock.

All data shipped with this package is **fictional**. No real entity, person,
project, region or path appears anywhere.

Public API
----------
- :func:`proforma_engine.engine.analyze_document`
- :func:`proforma_engine.engine.analyze_folder`
- :data:`proforma_engine.engine.REGISTRY`
- :func:`proforma_engine.generate.generate_corpus`
- :func:`proforma_engine.report.build_markdown_report`
- :func:`proforma_engine.report.build_json_report`
- :func:`proforma_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
