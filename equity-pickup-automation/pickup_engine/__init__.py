"""
pickup_engine
=============

A deterministic, **read-only** control engine for equity-method pickup &
consolidation eliminations: every parent's investment-in-sub carrying value
re-footed as a begin + contributions + pickup - distributions roll-forward,
every equity pickup re-derived as ownership x sub net income, and every
Investment account proved paired to its sub's Equity-Parent account and
extinguished for exactly the carrying value -- so consolidation nets to zero
entity block by entity block.

Around that spine sit the feeding schedules, held to the same standard: the
preferred-return accrual re-derived as capital x rate x days/basis on a
contiguous, chained capital balance; the member allocation footed and tied to
the income it splits; and the trial balance's investment, pickup, should-be
and adjustment columns tied out in exact integer cents.

The engine deliberately does **not** opine on impairment or fair value --
those are judgment calls owned by a valuation workpaper. Everything here is a
hard equality, a threshold, a date gate, a membership test or a re-derivation.
It never posts, never consolidates and never writes to a source artifact.

All data shipped with this package is **fictional**. No real entity, person,
project or path appears anywhere.

Public API
----------
- :func:`pickup_engine.engine.analyze_document`
- :func:`pickup_engine.engine.analyze_folder`
- :data:`pickup_engine.engine.REGISTRY`
- :func:`pickup_engine.generate.generate_corpus`
- :func:`pickup_engine.report.build_markdown_report`
- :func:`pickup_engine.report.build_json_report`
- :func:`pickup_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
