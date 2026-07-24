"""
withholding_engine
==================

A deterministic, **read-only** control engine for a US withholding agent's
non-resident (Chapter 3/4 FDAP) withholding and Form 1042 / 1042-S reconciliation:
every cross-border interest, dividend, royalty and rent payment proved -- payment
by payment -- to be rated from the payee's Chapter 3/4 status and the treaty
table, every reduced rate supported by a valid Form W-8, the deposits tied to the
liability, and the annual Form 1042 tied to the 1042-S slips it transmits.

A withholding determination is a snapshot of a payee's status on the day a payment
went out, and it goes stale -- or was wrong to begin with -- in ways nobody
watches: the treaty rate applied behind a missing or expired W-8; the US payee
withheld or the accrued coupon treated as paid; the non-participating FFI given
treaty relief it is barred from; the deposits that do not equal the liability; the
Form 1042 that does not tie to the slips underneath it.

The engine recomputes every payment's applicable rate from the payee's status and
the treaty table, gates every reduced rate on a valid W-8, and rebuilds the 1042
totals from the slips and deposits, and compares. It never pays, never files and
never writes to a source artifact. Every expiry and renewal test is made against
an ``as_of`` carried in the file, never the system clock.

All data shipped with this package is **fictional**. No real entity, person,
jurisdiction, bank or path appears anywhere.

Public API
----------
- :func:`withholding_engine.engine.analyze_document`
- :func:`withholding_engine.engine.analyze_folder`
- :data:`withholding_engine.engine.REGISTRY`
- :func:`withholding_engine.generate.generate_corpus`
- :func:`withholding_engine.report.build_markdown_report`
- :func:`withholding_engine.report.build_json_report`
- :func:`withholding_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
