"""
waterfall_engine
================

A deterministic, **read-only** control engine for a real-estate joint-venture
distribution waterfall: the preferred-return accrual, the capital-account
roll-forward, the tier sequencing and pari-passu splits, the hurdle boundary, the
promote/carry split, the capital-call dilution, and the realized-returns summary
all re-derived -- number by number -- from the executed operating agreement's
mechanics and the contribution history, and compared to the figures the workpaper
states.

A JV waterfall is a chain of dependent computations, and a wrong number early
travels silently to the bottom line: a mis-compounded month of preferred return,
a tier paid out of order, a pari-passu split struck off the wrong weights, a
promote tier entered as though the hurdle were already cleared, a realized-returns
table that nobody recomputed from the waterfall underneath it. The engine rebuilds
each figure through the shared kernel in :mod:`waterfall_engine.waterfall` and
compares with exact integer-cent equality. It never pays, never files and never
writes to a source artifact. Every accrual and covenant window is measured against
an ``as_of_period`` month index carried in the file, never the system clock.

All data shipped with this package is **fictional**. No real entity, person,
project or path appears anywhere.

Public API
----------
- :func:`waterfall_engine.engine.analyze_document`
- :func:`waterfall_engine.engine.analyze_folder`
- :data:`waterfall_engine.engine.REGISTRY`
- :func:`waterfall_engine.generate.generate_corpus`
- :func:`waterfall_engine.report.build_markdown_report`
- :func:`waterfall_engine.report.build_json_report`
- :func:`waterfall_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
