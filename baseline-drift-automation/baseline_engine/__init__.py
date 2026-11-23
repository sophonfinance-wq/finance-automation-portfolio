"""
baseline_engine
===============

A deterministic, **read-only** control engine for baseline and version drift:
the problem of one project budget existing in four authoritative copies at once
-- the contractual exhibit a deal was signed against, the sponsor's working
model, the billing instrument a draw is requested on, and the summary memo
circulated to a lender -- each of which can be internally perfect while
disagreeing with the other three.

Nothing here checks whether a single budget foots. That is a within-document
question and a separate engine owns it. This engine starts where that one stops,
because every failure mode it exists for *survives* a within-document check.

Four copies, four ways to be quietly wrong. A copy is internally consistent and
materially wrong -- sources equal uses in all four, they simply carry different
totals. A reclassification reads as a change, because two lines moved by equal
and opposite amounts and grading that as a budget revision buries the genuine
ones. A category exists in one copy and not another, so a comparison that pairs
on names walks straight past the line that was renamed or split. A copy is stale
rather than wrong: it was right when it was prepared, its cost-through date is
months behind the period being reported, and every figure read off it since is
quoted with confidence. And a derived schedule loses its inputs -- blank the
milestone a fee amortisation spans and the schedule does not error, it silently
keeps the last amortisation it was handed.

So the controls here are agreement controls. Category sets are reconciled before
any value is compared, and a category present in one copy and absent from another
is a finding in its own right rather than an absence to skip. Totals are summed
from the lines and then compared to the stated figure, because a stated total
that disagrees with its own lines was typed. Offsetting movements with an
unchanged total are graded as reclassification. Every change on the billing
instrument is re-derived from its own approved-plus-changes columns and traced to
an approved amendment for its exact amount. Every date is tested against the
reporting period carried in the file, never the system clock. Exact ``==``,
integer cents. The materiality threshold grades a difference that has already
been found; it never decides whether one exists.

All data shipped with this package is **fictional**. No real project, entity,
place, budget figure or path appears anywhere.

Public API
----------
- :func:`baseline_engine.engine.analyze_document`
- :func:`baseline_engine.engine.analyze_folder`
- :data:`baseline_engine.engine.REGISTRY`
- :func:`baseline_engine.generate.generate_corpus`
- :func:`baseline_engine.report.build_markdown_report`
- :func:`baseline_engine.report.build_json_report`
- :func:`baseline_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
