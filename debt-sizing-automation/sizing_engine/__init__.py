"""
sizing_engine
=============

A deterministic, **read-only** control engine for a borrower's debt term-sheet
sizing: every active deal proved -- deal by deal -- to be sized within its
advance rate, to carry an all-in rate and fees that re-derive from their own
inputs, to reconcile its term and extensions to the stated maturity, and to foot
into a portfolio rollup that ties across the deals.

This is the sizing half of the debt story. Whether a draw is actually advanced
against a budget line is a *funding* question owned by a separate engine -- and
that engine explicitly declines to re-foot a term sheet. This engine is that
tie-out. A term sheet is a one-page summary re-keyed from a longer credit memo,
and it drifts in ways nobody re-foots: the loan sized a cent over max
loan-to-cost times the cost basis; the all-in rate typed as index-plus-spread
where the floor governs; a fee struck on the wrong base; the portfolio total
maintained beside the deals rather than footed from them.

The engine recomputes every all-in rate, every fee amount and every portfolio
total from the base terms, and compares. It never funds, never files and never
writes to a source artifact. Every term-sheet expiry test is made against an
``as_of`` pricing date carried in the file, never the system clock.

All data shipped with this package is **fictional**. No real entity, person,
lender, benchmark, project or path appears anywhere.

Public API
----------
- :func:`sizing_engine.engine.analyze_document`
- :func:`sizing_engine.engine.analyze_folder`
- :data:`sizing_engine.engine.REGISTRY`
- :func:`sizing_engine.generate.generate_corpus`
- :func:`sizing_engine.report.build_markdown_report`
- :func:`sizing_engine.report.build_json_report`
- :func:`sizing_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
