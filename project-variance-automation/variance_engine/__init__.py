"""
variance_engine
===============

A deterministic, **read-only** control engine for the periodic project report a
developer re-issues off every development proforma: the current period restated
against the prior period and against the approved Business Plan baseline, each
cost line broken into Total Budget / Cost to Date / Cost to Complete, and each
milestone date reported Current vs Prior vs Variance against a frozen schedule.

Nothing here underwrites a development. Whether the proforma behind the report is
a good proforma is a judgement no engine can make. The question here is narrower
and entirely arithmetic, which is exactly why it can be settled: six metrics, three
budget columns and a handful of dates, restated by hand, every period, for every
active project, then footed into a portfolio rollup. The variance column carried
forward rather than derived, so it no longer equals the difference of the two
columns it sits between. The Cost to Complete maintained beside the budget rather
than struck as Total Budget less Cost to Date, so an overrun rides in a column
nobody re-footed. The Business Plan column quietly re-based to a revision nobody
approved, which makes every plan variance smaller at once.

The engine recomputes every derived figure in the report from the base facts and
compares with exact ``==``, re-foots each variance column from the two columns
that define it, strikes Cost to Complete as the remainder, re-derives each
milestone variance with the correct sign convention, checks the plan column
against the frozen approved baseline, and foots the rollup back across all
projects. Controls and the generator share one restatement kernel, so a variance
cannot disagree with the data that produced it. It never posts, never files and
never writes to a source artifact. Every milestone is tested against the reporting
period carried in the file, never the system clock.

All data shipped with this package is **fictional**. No real entity, person,
project, jurisdiction or path appears anywhere.

Public API
----------
- :func:`variance_engine.engine.analyze_document`
- :func:`variance_engine.engine.analyze_folder`
- :data:`variance_engine.engine.REGISTRY`
- :func:`variance_engine.generate.generate_corpus`
- :func:`variance_engine.report.build_markdown_report`
- :func:`variance_engine.report.build_json_report`
- :func:`variance_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
