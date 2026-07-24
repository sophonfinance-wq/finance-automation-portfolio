"""
spending_engine
===============

A deterministic, **read-only** control engine for a developer's capital
Spending Request phase gates: before capital is committed to a development
project, the correct dollar trigger proved to have fired *after* the Initial
Commitment approval, the five Investment Committee phase gates entered in
sequence with every prior phase's deliverables complete, and the underwriting
standards -- contingency floors, the standard growth default, the prescribed
fee formulas, the phase-indexed estimate basis, the comparison-basis switch and
the template calendar -- re-derived and tied, with every deviation flagged as
an exception.

The engine deliberately checks only the deterministic standards-compliance
layer. Whether the underlying investment is worth making is genuine business
judgment and no control here opines on it. Everything the package states as a
determination -- the fees, the total, the per-phase gate summary, the
plan-comparison variances -- is recomputed from the package's own base facts
through a single shared standards kernel, and compared. The engine never
approves, never spends and never writes to a source artifact. Every calendar
test is made against an ``as_of`` carried in the file, never the system clock.

All data shipped with this package is **fictional**. No real entity, person,
place, vendor, project or path appears anywhere.

Public API
----------
- :func:`spending_engine.engine.analyze_document`
- :func:`spending_engine.engine.analyze_folder`
- :data:`spending_engine.engine.REGISTRY`
- :func:`spending_engine.generate.generate_corpus`
- :func:`spending_engine.report.build_markdown_report`
- :func:`spending_engine.report.build_json_report`
- :func:`spending_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
