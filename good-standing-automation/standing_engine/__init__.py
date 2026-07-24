"""
standing_engine
===============

A deterministic, **read-only** control engine for a closely-held real-estate
family's entity good-standing: every legal entity proved -- state by state -- to
have its annual/biennial report filed on time, its franchise tax paid in the
exact statutory amount by its due date, its registered agent of record the one
under contract, and its Secretary-of-State status ACTIVE, with every wound-down
entity cancelled in every state it ever belonged to.

A good-standing record is a snapshot that was true the day the state produced it,
and it goes stale in ways nobody watches: the filing slips past its due date while
the register still shows the entity Active; the franchise tax is paid a dollar
short of the flat statutory amount; the agent named on the state's record is not
the agent under contract; the monthly rollup calls an entity in good standing on
a determination nobody recomputed from the records underneath it.

The engine re-derives every statutory due date and flat fee, recomputes every
entity's good-standing determination from the jurisdiction matrix and the state
records, and compares. It never pays, never files and never writes to a source
artifact. Every currency and renewal test is made against an ``as_of`` carried in
the file, never the system clock.

All data shipped with this package is **fictional**. No real entity, person,
agent, jurisdiction or path appears anywhere.

Public API
----------
- :func:`standing_engine.engine.analyze_document`
- :func:`standing_engine.engine.analyze_folder`
- :data:`standing_engine.engine.REGISTRY`
- :func:`standing_engine.generate.generate_corpus`
- :func:`standing_engine.report.build_markdown_report`
- :func:`standing_engine.report.build_json_report`
- :func:`standing_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
