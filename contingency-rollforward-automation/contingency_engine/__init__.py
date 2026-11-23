"""
contingency_engine
==================

A deterministic, **read-only** control engine for the contingency status block a
developer restates in every periodic project report: construction contingency and
project contingency rolled forward, project by project, from the prior period's
balance through the draws allocated against them to the balance remaining, and
assessed adequate only when what is left covers the projected potential use.

Nothing here forecasts. Whether the projected potential use is a sound estimate is
a judgement no engine can make. The question here is narrower and entirely
arithmetic, which is exactly why it can be settled: six numbers and a word,
restated by hand, every period, for every active project, then added up into a
portfolio rollup. The current balance gets typed rather than derived. The
allocated-this-period total is maintained beside the draw detail rather than from
it, so a draw never reaches the total -- or a single draw is written for more than
the balance it draws against. The adequacy word is carried forward from a period
in which it was true, while the projected potential use climbs past the balance
behind it.

The engine recomputes every derived figure in the block from the base facts and
compares with exact ``==``, rebuilds each adequacy call from the two amounts that
define it, reconciles both buckets to the contingency lines carried in the project
budget, and foots the portfolio rollup back to the blocks. It never posts, never
files and never writes to a source artifact. Every draw is tested against the
reporting period carried in the file, never the system clock.

All data shipped with this package is **fictional**. No real entity, person,
project, jurisdiction or path appears anywhere.

Public API
----------
- :func:`contingency_engine.engine.analyze_document`
- :func:`contingency_engine.engine.analyze_folder`
- :data:`contingency_engine.engine.REGISTRY`
- :func:`contingency_engine.generate.generate_corpus`
- :func:`contingency_engine.report.build_markdown_report`
- :func:`contingency_engine.report.build_json_report`
- :func:`contingency_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
