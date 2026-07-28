"""
rollforward_engine
==================

A deterministic, **read-only** control engine for the annual trial-balance
roll-forward: the state-filing workpaper a group rebuilds every fiscal year --
last year's column structure carried forward, final-year entities retired,
renamed entities carried once, first-year entities admitted with their
registration dates, and every column repopulated from the year-end trial-balance
extract, tied to an embedded backup tab, cell by cell.

Nothing here prepares a filing. Which return an entity owes is a calendar
question, and a separate engine owns it. This engine is the workpaper underneath
that filing, and it is more treacherous than it looks, because the failure modes
all produce a workpaper that *balances*. A column populated from the activity
column instead of the balance column still sums to zero, because monthly
movement foots the same way balances do. A retained-earnings balance parked on
an equivalent chart code vanishes without unbalancing anything when the
equivalence is dropped. An eliminations range written over last year's columns
silently excludes the two columns added this year. A backup tab that quotes the
source's category column instead of its title column reads plausibly forever.

So the controls here re-derive rather than trust: every cell from the declared
balance column of its book, every dual-code row as the sum of its codes through
the chart-equivalence map, every column to zero, every eliminations range over
every column, every backup row against the source's own title column, and both
rendered twins against each other. Exact ``==``, integer cents, no tolerance.
It never writes to a source artifact, and every date is tested against the
fiscal year carried in the file, never the system clock.

All data shipped with this package is **fictional**. No real entity, project,
place, account balance or path appears anywhere.

Public API
----------
- :func:`rollforward_engine.engine.analyze_document`
- :func:`rollforward_engine.engine.analyze_folder`
- :data:`rollforward_engine.engine.REGISTRY`
- :func:`rollforward_engine.generate.generate_corpus`
- :func:`rollforward_engine.report.build_markdown_report`
- :func:`rollforward_engine.report.build_json_report`
- :func:`rollforward_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
