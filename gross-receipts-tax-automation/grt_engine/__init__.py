"""
grt_engine
==========

A deterministic, **read-only** control engine for a developer's gross-receipts &
excise tax filings -- every worksheet's tax re-derived, jurisdiction by
jurisdiction, from the general-ledger revenue pull and the classification rate
that was actually in force for the period, tied to the number the worksheet
filed, with the filing calendar proved complete, timely and approved.

A developer that manages projects across several taxing jurisdictions owes a
gross-receipts or excise tax in each one -- a state Business & Occupation tax, a
city excise, a territorial general-excise tax -- each with its own rate, cadence,
deductions, thresholds and due dates, and each rate can change mid-year. The tax
on a worksheet is a *derived* figure, and it goes wrong in ways that look right:
a base that does not tie the ledger, a rate that was right last quarter, a
deduction taken twice, a below-threshold rule claimed above the threshold, a
filing that is missing or late or unapproved.

The engine re-derives every worksheet's tax from the receipts and the rate table
and compares; it enumerates every expected filing from the calendar and proves it
present, timely and approved. It never pays, never files and never writes to a
source artifact. Every due-date and renewal test is made against an ``as_of``
carried in the file, never the system clock.

All data shipped with this package is **fictional**. No real entity, person,
jurisdiction, city, project or path appears anywhere.

Public API
----------
- :func:`grt_engine.engine.analyze_document`
- :func:`grt_engine.engine.analyze_folder`
- :data:`grt_engine.engine.REGISTRY`
- :func:`grt_engine.generate.generate_corpus`
- :func:`grt_engine.report.build_markdown_report`
- :func:`grt_engine.report.build_json_report`
- :func:`grt_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
