"""
upgrade_engine
==============

A deterministic, **read-only** control engine for a homebuilder's buyer-upgrade
programme.

A buyer pays for an upgrade months before the home closes. That money is not
revenue when it arrives -- it is a liability, and it stays one until the unit
actually closes. Between those two dates the same figure has to appear
consistently in four places maintained by different people on different cadences:
the closings schedule, the general ledger, the cost-to-complete report and the
proforma.

So the failure mode is almost never a wrong number. It is the *same* number
failing to move everywhere at once: a unit closes and the deferred balance is
released in the schedule but not the ledger; an upgrade is repriced and the
proforma keeps the old figure; a change order is executed and the committed cost
never lands. Every one of those is a tie-out with a right answer.

The engine runs an ordered registry of controls answering:

1. Does every upgrade belong to a real unit, exactly once?
2. Is deferred revenue released when the unit closes, and only then?
3. Does the closing entry balance, and is cost coded where it belongs?
4. Is sales tax carried as a liability rather than as revenue?
5. Do the four schedules agree with each other?

It never bills, never posts and never writes to a source artifact. It is a
sensor: the deterministic ground truth other systems and reviewers consume.

All data shipped with this package is **fictional**. No real buyer, project,
unit, document number or path appears anywhere.

Public API
----------
- :func:`upgrade_engine.engine.analyze_document`
- :func:`upgrade_engine.engine.analyze_folder`
- :data:`upgrade_engine.engine.REGISTRY`
- :func:`upgrade_engine.generate.generate_corpus`
- :func:`upgrade_engine.report.build_markdown_report`
- :func:`upgrade_engine.report.build_json_report`
- :func:`upgrade_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
