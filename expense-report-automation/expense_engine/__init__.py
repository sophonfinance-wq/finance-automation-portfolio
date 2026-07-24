"""
expense_engine
==============

A deterministic, **read-only** control engine for employee expense reports and
company purchasing-card (P-Card) spending: every charge on a bank statement
reconciled to a receipted, coded, approved line on an expense report.

A company does not reimburse a card statement on trust. It issues a card, the
bank issues a statement, and the cardholder owes a matching expense report -- one
line per charge, each with a receipt on file, a business purpose, a valid GL code
and a real project, filed inside the submission window, under the per-charge
limit, approved by somebody other than the cardholder.

Three failures hide inside that, and none of them look wrong in a page of small
numbers: the charge that never gets a report line (a company expense nobody coded
and nobody has a receipt for), the residual cent between the report and the bank,
and the charge that should never have been on the card at all.

The engine reconciles every charge to the cent, checks every line for its receipt
and its coding, and holds each report to the policy. It never pays, never files
and never writes to a source artifact. Every window and ageing test is made
against an ``as_of`` carried in the file, never the system clock.

All data shipped with this package is **fictional**. No real entity, person,
merchant, project or path appears anywhere.

Public API
----------
- :func:`expense_engine.engine.analyze_document`
- :func:`expense_engine.engine.analyze_folder`
- :data:`expense_engine.engine.REGISTRY`
- :func:`expense_engine.generate.generate_corpus`
- :func:`expense_engine.report.build_markdown_report`
- :func:`expense_engine.report.build_json_report`
- :func:`expense_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
