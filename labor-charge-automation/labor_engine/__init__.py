"""
labor_engine
============

A deterministic, **read-only** control engine for charging employee labor cost to
projects: the advance authorization a project manager gives before an employee is
charged, the monthly charge that must match it, the invoice those charges foot into,
the project labor budget they must stay inside, and the general-ledger tie-out.

An employee's time is not free to a project just because the company already pays
the salary. The cost has to be charged over -- salary plus payroll taxes plus
benefits -- and only where a project manager authorized it in advance, only from the
month the authorization takes effect, at the fixed amount or percentage that was
authorized, and only up to the labor budget the project carries. Four things go
wrong and none of them look wrong: the charge that outruns its authorization, the
charge that predates the authorized start, the charge on a project or cost code
nobody named, and the budget quietly overrun.

The engine re-derives every percentage charge from the employee's fully-burdened
cost by the same truncating rate that should have produced it, re-foots every
invoice from the charges beneath it, and measures the cumulative charge against the
budget. It never pays, never files and never writes to a source artifact. Every date
test is made against an ``as_of`` carried in the file, never the system clock.

All data shipped with this package is **fictional**. No real entity, person, project
or path appears anywhere.

Public API
----------
- :func:`labor_engine.engine.analyze_document`
- :func:`labor_engine.engine.analyze_folder`
- :data:`labor_engine.engine.REGISTRY`
- :func:`labor_engine.generate.generate_corpus`
- :func:`labor_engine.report.build_markdown_report`
- :func:`labor_engine.report.build_json_report`
- :func:`labor_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
