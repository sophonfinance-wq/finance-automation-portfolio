"""
franchise_engine
================

A deterministic, **read-only** control engine for a combined-group franchise
(margin) tax return: a group of affiliated development companies filing one
combined return each fiscal year in the fictional State of Marran, with the
affiliate roster rebuilt from the prior year, the group margin apportioned to
Marran by a single receipts factor, and the tax re-derived from the workpapers.

The engine rebuilds the combined roster from last year's members plus this year's
additions less its removals and compares; ties consolidated group revenue to the
consolidated tax trial-balance workpaper; recomputes the single receipts
apportionment factor -- in-state receipts over everywhere receipts, bounded to
``[0, 1]``; and re-derives the whole margin tax -- revenue less the elected
deduction, apportioned by the factor, struck at the rate -- tying every figure to
the return. It never pays, never files and never writes to a source artifact.
Every registration-renewal test is made against an ``as_of`` carried in the file,
never the system clock.

All data shipped with this package is **fictional**. No real entity, person,
state, city, registration or path appears anywhere.

Public API
----------
- :func:`franchise_engine.engine.analyze_document`
- :func:`franchise_engine.engine.analyze_folder`
- :data:`franchise_engine.engine.REGISTRY`
- :func:`franchise_engine.generate.generate_corpus`
- :func:`franchise_engine.report.build_markdown_report`
- :func:`franchise_engine.report.build_json_report`
- :func:`franchise_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
