"""
closing_engine
==============

A deterministic, **read-only** tie-out engine for a residential developer's
home-sale closings: every unit that reaches close of escrow proved -- unit by
unit -- to have a balanced closing journal entry that foots, a settlement
statement that recomputes, rate-derived fees struck at the proforma rates,
revenue recognized in the close month, and a loan release that ties to the
lender's loan statement.

This is a tie-out check, not an underwriting one. What a home should have sold
for, whether the proforma was right, whether the loan should have been made --
those are questions a different engine owns. A close-of-escrow package is a stack
of spreadsheets assembled under deadline, and it goes wrong in ways nobody
watches: the entry that does not foot; the settlement total keyed rather than
summed; the fee struck at the wrong rate; revenue recognized in the wrong month;
the loan release that does not tie; the rollup that states a count or a total
nobody recomputed from the units underneath it.

The engine recomputes every unit's tie-out determination from the settlement, the
entry, the revenue line, the loan release and the cost-of-sale schedule, and
compares. It never posts, never files and never writes to a source artifact.

All data shipped with this package is **fictional**. No real entity, person,
project, lender or path appears anywhere.

Public API
----------
- :func:`closing_engine.engine.analyze_document`
- :func:`closing_engine.engine.analyze_folder`
- :data:`closing_engine.engine.REGISTRY`
- :func:`closing_engine.generate.generate_corpus`
- :func:`closing_engine.report.build_markdown_report`
- :func:`closing_engine.report.build_json_report`
- :func:`closing_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
