"""
sov_engine
==========

A deterministic, **read-only** control engine for a residential developer's
subcontract commitment billing: every schedule of values (SOV) proved to foot
to its original contract, every revised commitment re-derived as original plus
net *approved* change orders, every pay-application line recomputed -- completed
= previously billed + this period, billed within its scheduled value, retention
and sales tax at the contract rates, payment due as request minus retention
plus tax -- every month's opening tied to the prior month's close, and every
conditional lien release tied to the certified payment.

The neighbouring questions stay with their engines. Which lender draw funds a
pay app is a funding question owned by the draw engine; whether a lien waiver's
statutory form is right is a document-compliance question owned by the waiver
engine. This engine owns the arithmetic chain those two stand on: whether every
figure on the SOV / change-order / pay-app page re-derives from the figures
beneath it.

The engine recomputes every derived figure through the same billing kernel that
generated the corpus, and compares -- exactly, in integer cents, with no
tolerance. It never pays, never files and never writes to a source artifact.

All data shipped with this package is **fictional**. No real entity, person,
vendor, project, jurisdiction or path appears anywhere.

Public API
----------
- :func:`sov_engine.engine.analyze_document`
- :func:`sov_engine.engine.analyze_folder`
- :data:`sov_engine.engine.REGISTRY`
- :func:`sov_engine.generate.generate_corpus`
- :func:`sov_engine.report.build_markdown_report`
- :func:`sov_engine.report.build_json_report`
- :func:`sov_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
