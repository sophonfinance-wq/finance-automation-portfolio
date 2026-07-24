"""
interest_engine
===============

A deterministic, **read-only** control engine for a lender's interest accrual and
loan amortization: every promissory note proved -- note by note -- to accrue the
interest its own terms produce, to roll its balance forward without a break, to
hold its maturity, default-rate, prepayment and subordination gates, and to tie
its reciprocal receivable/payable and interest journal out to the schedule
underneath them.

This is the arithmetic proof beneath the debt-service note. Where a financing
cost lands, or how a construction draw is funded, are *separate* engines' jobs.
This engine is the check that the interest a note reports is the interest its
rate, day-count and balance produce; that one period's ending balance is the
next period's beginning; that accrual stops at maturity and steps at default;
that a note is not prepaid before maturity or paid ahead of the senior it sits
behind; and that the lender's income equals the borrower's expense equals the
accrual the journal records.

The engine recomputes every accrual from the note's terms and every rollup
determination from the schedule, and compares. It never pays, never posts and
never writes to a source artifact. Every maturity and gate test is made against
an ``as_of`` carried in the file, never the system clock.

All data shipped with this package is **fictional**. No real entity, person,
bank, jurisdiction, project or path appears anywhere.

Public API
----------
- :func:`interest_engine.engine.analyze_document`
- :func:`interest_engine.engine.analyze_folder`
- :data:`interest_engine.engine.REGISTRY`
- :func:`interest_engine.generate.generate_corpus`
- :func:`interest_engine.report.build_markdown_report`
- :func:`interest_engine.report.build_json_report`
- :func:`interest_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
