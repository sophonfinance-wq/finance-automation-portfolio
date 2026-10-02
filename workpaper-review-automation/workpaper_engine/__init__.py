"""
workpaper_engine
================

A deterministic, **read-only** control engine for the handback problem: a tax
workpaper package whose numbers are agreed but which a reviewer cannot verify
without redoing the preparer's work.

Nothing here checks whether taxable income foots. That is a within-document
question and other engines own it. This engine starts after the numbers are
settled, because every failure mode it exists for *survives* a footing check.

Six ways a correct package is still not reviewable. **A figure is correct and
untraceable** -- a current-year amount typed onto a consolidation foots
perfectly and says nothing about where it came from. **A citation resolves to a
plausible wrong number** -- the reference is valid, the cell exists, a believable
figure comes back, and it is the wrong cell; the closer the wrong figure sits to
the right one the longer it survives, so a rounding-sized gap is treated as
seriously as a large one. **A sweep repairs what was never broken** -- dates are
stored as integers, so every amount in a date-shaped band looks like a date, and
reformatting a genuine amount corrupts a tab without changing any total.
**A dependant is orphaned** -- a block is moved after confirming no other
document references it, but same-document references carry no document name and
the check missed them. **The cover note and the workbook disagree** -- the note
says three open questions, the file carries fifteen, and both are internally
consistent. **A residual is silenced rather than disclosed** -- a known,
accepted, immaterial difference is plugged to zero and the package now looks
cleaner than it is.

The controls are therefore traceability controls. Every current-year input must
name a source record. Every citation is verified by the amount it returns, never
by whether it resolves. Every reclassification to a date must carry corroborating
context from the cell's own presentation. Every dependant of a moved block is
proven re-pointed. The note's counts are reconciled against the question block
inside the file rather than against any tracker. Disclosed residuals are proven
still disclosed. Exact ``==``, integer cents, no tolerance band -- because a
tolerance band is exactly the mechanism that hides the defects this engine
exists to find.

The engine refuses rather than fudges: it reports a bad amount rather than
coercing it, and it never writes to the package it reads.

All data shipped with this package is **fictional**. No real entity, person,
place, figure, document or path appears anywhere.

Public API
----------
- :func:`workpaper_engine.engine.analyze_document`
- :func:`workpaper_engine.engine.analyze_folder`
- :data:`workpaper_engine.engine.REGISTRY`
- :func:`workpaper_engine.generate.generate_corpus`
- :func:`workpaper_engine.report.build_markdown_report`
- :func:`workpaper_engine.report.build_json_report`
- :func:`workpaper_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
