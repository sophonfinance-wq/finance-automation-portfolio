"""
investor_engine
===============

A deterministic, **read-only** control engine for the monthly financial reporting
package a developer issues to the joint-venture equity partner of a single
project entity: the trial balance, the balance sheet, the statement of
operations, the statement of members' capital, the development cost schedule, the
job cost bridge and the notes, re-derived from the sources that are supposed to
produce them and compared with exact ``==``.

Nothing here decides anything. Whether a cost the ledger calls a lender's charge
and the draw schedule calls investor diligence is one or the other is a
classification judgement, and no engine can make it -- the engine reports that
two sources disagree and stops. Whether a bank statement that has not arrived
supports the cash it is supposed to support is a question about a document that
does not exist yet, and no amount of recomputation conjures one. Whether and how
to tell the partner about an exception is a decision, not a computation.

What an engine can settle is narrower and entirely arithmetic, which is exactly
why it can be settled: the package is monthly, per project, per investor,
assembled by hand from five sources, and the failure mode is a wrong figure sent
to an outside equity partner. A difference gets dropped rather than disclosed. A
contribution column agrees to no executed draw. A cost-to-date schedule keeps a
caption saying the cost arose in the period. The cover asserts no exceptions over
notes that disclose one. A tie-out check row ships inside the print area.

The engine re-derives every figure the package states from the source that
produces it -- matched by account number and member id, never by row position --
foots and cross-foots every statement, rolls each member's capital forward,
bridges job cost to the ledger and insists any difference is itemized and
disclosed, then holds the package unless every control above it passes. It never
posts, never files and never writes to a source artifact. Every executed draw is
tested against the reporting period carried in the file, never the system clock.

All data shipped with this package is **fictional**. No real entity, person,
project, street, neighbourhood, jurisdiction or path appears anywhere.

Public API
----------
- :func:`investor_engine.engine.analyze_document`
- :func:`investor_engine.engine.analyze_folder`
- :data:`investor_engine.engine.REGISTRY`
- :func:`investor_engine.generate.generate_corpus`
- :func:`investor_engine.report.build_markdown_report`
- :func:`investor_engine.report.build_json_report`
- :func:`investor_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
