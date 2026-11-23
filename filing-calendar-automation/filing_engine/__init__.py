"""
filing_engine
=============

A deterministic, **read-only** control engine for a fiscal-year filing-obligation
calendar: every entity, in every jurisdiction, proved -- obligation by obligation
-- to have filed or validly extended each return and payment before its statutory
due date, paid each fixed-amount voucher in the exact statutory amount, and to
have a status register that ties to the filed evidence with nothing missing and
nothing orphaned.

This engine does not prepare a return or compute a tax. It takes the finished
calendar and asks the narrower, entirely evidentiary question: was every deadline
met or validly deferred, and does the register tie to the paper underneath it? A
filing calendar is a matrix of dates that was correct the day someone typed it,
and it goes wrong in ways nobody watches: the due date keyed to the wrong form;
the obligation that slid past its deadline unfiled; the row marked filed that no
voucher backs; the fixed annual tax cut for anything but the statutory constant.

The engine recomputes every due date from the form and the year-end against the
statutory table, rebuilds every obligation's status from its dates, checks each
fixed payment against the exact statutory amount, and ties every filed row to
evidence and every piece of evidence back to a row. It never files, never pays
and never writes to a source artifact. Every due-date and overdue test is made
against an ``as_of`` carried in the file, never the system clock.

All data shipped with this package is **fictional**. No real entity, person,
agency, jurisdiction or path appears anywhere.

Public API
----------
- :func:`filing_engine.engine.analyze_document`
- :func:`filing_engine.engine.analyze_folder`
- :data:`filing_engine.engine.REGISTRY`
- :func:`filing_engine.generate.generate_corpus`
- :func:`filing_engine.report.build_markdown_report`
- :func:`filing_engine.report.build_json_report`
- :func:`filing_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
