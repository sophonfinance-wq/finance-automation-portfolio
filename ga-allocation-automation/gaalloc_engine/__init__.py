"""
gaalloc_engine
==============

A deterministic, **read-only** control engine for a management or holding
entity's recurring G&A expense allocation: shared overhead, corporate G&A and
metered postage pushed out every month to the operating entities and projects
that consumed them, on a driver, with every share, every allocated amount and
the generated journal entry re-derived and compared.

The workbook this engine watches is the classic recurring one -- one tab per
month, a driver tab and a lookup tab behind it, a stamped accounting date per
period, a formula column that turns a driver share into a dollar figure. It is
copied forward every month, which is exactly why it drifts: the share column
that quietly sums to 99.97% and leaves cost behind in the holding entity; the
allocated column rounded recipient by recipient until it no longer ties the pool
it divided; the entry that still balances but no longer matches the schedule it
was posted from; the month that was never rolled, or was rolled and stamped to
the date of the month it was copied from.

The engine rebuilds every share from the driver counts, every amount from the
share and the pool -- both by largest remainder, so the residual cent lands on
exactly one recipient -- and the entry from both, then compares. It reconciles
the postage component to the meter delta the workbook already carries. It never
posts, never files, never pays, and never writes to a source artifact. Every
accounting-date test is made against the period stamped in the file, never the
system clock.

All data shipped with this package is **fictional**. No real entity, person,
project, account or path appears anywhere.

Public API
----------
- :func:`gaalloc_engine.engine.analyze_document`
- :func:`gaalloc_engine.engine.analyze_folder`
- :data:`gaalloc_engine.engine.REGISTRY`
- :func:`gaalloc_engine.generate.generate_corpus`
- :func:`gaalloc_engine.report.build_markdown_report`
- :func:`gaalloc_engine.report.build_json_report`
- :func:`gaalloc_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
