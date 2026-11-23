"""
capitalize_engine
=================

A deterministic, **read-only** control engine for a real-estate developer's
Section 263A avoided-cost interest-capitalization schedule: every active
development project proved -- quarter by quarter -- to capitalize the interest
the method requires into project basis, foot to its annual totals, and tie the
year-over-year comparison.

A developer that builds designated property with borrowed money may not deduct
all of the interest it pays. Under the avoided-cost method of IRC section
263A(f), the interest that production could have avoided -- the period rate
applied to the accumulated production expenditures tied up in the project -- must
be capitalized into the property's basis rather than deducted in the year paid.
The annual schedule lays every active project across a grid of calendar
quarter-ends and computes that split; it is rebuilt every fiscal year, and it
goes stale in ways nobody watches: the row that stops footing to its annual
total; the split that leaks, where interest is neither capitalized nor deducted;
the project on the trial balance that never reaches the schedule; the capitalized
figure typed in rather than re-derived from the expenditures and the rate.

The engine recomputes every capitalized figure from the expenditures and the
period rate through one shared kernel, and compares. It never posts, never files
and never writes to a source artifact.

All data shipped with this package is **fictional**. No real entity, person,
project, index or path appears anywhere.

Public API
----------
- :func:`capitalize_engine.engine.analyze_document`
- :func:`capitalize_engine.engine.analyze_folder`
- :data:`capitalize_engine.engine.REGISTRY`
- :func:`capitalize_engine.generate.generate_corpus`
- :func:`capitalize_engine.report.build_markdown_report`
- :func:`capitalize_engine.report.build_json_report`
- :func:`capitalize_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
