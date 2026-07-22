"""
draw_engine
===========

A deterministic, **read-only** control engine for the construction loan draw
cycle in real-estate development.

A draw request is the moment a developer asks a lender for money, and it is
almost entirely arithmetic. The package has to prove three things at once: that
cumulative draws equal cumulative costs, that the form the lender receives
agrees with the working papers behind it, and that the money being requested was
actually incurred inside the period being billed.

The engine consumes the fixed-format artifacts a draw cycle emits -- the
job-cost-to-draw reconciliation, the lender's draw request form, the
current-period cost detail, the funding ledger, the supporting-documentation
index and the cycle calendar -- and runs an ordered registry of controls
answering the questions a lender, an auditor and a controller each ask of the
same document:

1. Do cumulative draws equal cumulative costs?
2. Does the form the lender receives agree with the working paper behind it?
3. Was contingency drawn only as fast as the work was earned?
4. Were the costs actually incurred inside the period being billed?
5. Is the package supportable: signed, backed up, distributed?

It never bills, never funds and never writes to a source artifact. It is a
sensor: the deterministic ground truth other systems and reviewers consume.

All data shipped with this package is **fictional** (e.g. "Alderpoint Terraces",
"Meridian Sandbox Bank, N.A."). No real project, lender, vendor, person,
document number or path appears anywhere.

Public API
----------
- :func:`draw_engine.engine.analyze_document`
- :func:`draw_engine.engine.analyze_folder`
- :data:`draw_engine.engine.REGISTRY`
- :func:`draw_engine.generate.generate_corpus`
- :func:`draw_engine.report.build_markdown_report`
- :func:`draw_engine.report.build_json_report`
- :func:`draw_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
