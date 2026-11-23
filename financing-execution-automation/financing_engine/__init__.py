"""
financing_engine
================

A deterministic, **read-only** control engine for a developer's monthly
capital-markets "Upcoming Financings" report: every financing workstream proved,
milestone by milestone, to have a variance that re-derives from its dates, a
``Prior`` column that ties last month's ``Current``, a frozen ``Original``
baseline, the standard milestone playbook for its financing type, and no overdue
milestone left unflagged.

This is the schedule-and-execution half of the capital-markets story. Whether a
wire cleared, a note accrued or cash settled is another engine's job -- this
engine never touches money in motion. It asks the narrower, entirely evidentiary
question: does the pipeline report the deal team circulated reconcile to itself
and to the month before it?

An "Upcoming Financings" report is a snapshot of a pipeline that moves every
month, and it drifts in ways nobody watches: the ``Variance`` column falls behind
a hand-edited date; this month's ``Prior`` no longer equals last month's
``Current`` or the ``Original`` baseline is quietly overwritten; a workstream is
missing a playbook milestone or a portfolio project has no workstream; the rollup
count or Gantt bar summarises the schedule on a figure nobody recomputed from it.

The engine recomputes every variance, overdue flag, Gantt month and rollup count
from the base schedule facts, and compares. It never books, never files and never
writes to a source artifact. Every overdue and period-end test is made against a
``report_date`` carried in the file, never the system clock.

All data shipped with this package is **fictional**. No real entity, person,
bank, city, state, project or path appears anywhere.

Public API
----------
- :func:`financing_engine.engine.analyze_document`
- :func:`financing_engine.engine.analyze_folder`
- :data:`financing_engine.engine.REGISTRY`
- :func:`financing_engine.generate.generate_corpus`
- :func:`financing_engine.report.build_markdown_report`
- :func:`financing_engine.report.build_json_report`
- :func:`financing_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
