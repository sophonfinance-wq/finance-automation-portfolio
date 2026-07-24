"""
benefit_engine
==============

A deterministic, **read-only** control engine for one pay period's payroll
benefit reconciliation: every 401(k), HSA and FSA deduction on the payroll
register proved -- employee by employee, plan by plan -- to have reached each
provider, the general ledger and cash in the same amount, with the employer match
recomputed from its formula, every statutory limit respected, and every
participant deposit inside the DOL small-plan safe harbor.

Every pay period a payroll run fans one register out to several benefit
providers, to cash, and to the ledger, and the money has to arrive intact at each
one. A deferral withheld on the register has to reach both the recordkeeper and
the custodian; an HSA deduction has to reach the HSA administrator; the match has
to recompute from eligible compensation capped at 401(a)(17); nobody may breach
the 402(g), HSA-tier, FSA or 415(c) ceilings; participant money has to deposit
inside the seven-business-day safe harbor; and the ledger has to book a balanced
entry whose benefit payable clears to zero once remitted. The engine recomputes
each of those determinations from the evidence and compares. It never runs
payroll, never moves money and never writes to a source artifact. Every date-gate
is measured against dates carried in the file, never the system clock.

All data shipped with this package is **fictional**. No real entity, person,
provider, plan or path appears anywhere.

Public API
----------
- :func:`benefit_engine.engine.analyze_document`
- :func:`benefit_engine.engine.analyze_folder`
- :data:`benefit_engine.engine.REGISTRY`
- :func:`benefit_engine.generate.generate_corpus`
- :func:`benefit_engine.report.build_markdown_report`
- :func:`benefit_engine.report.build_json_report`
- :func:`benefit_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
