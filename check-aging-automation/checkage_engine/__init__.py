"""
checkage_engine
===============

A deterministic, **read-only** control engine for outstanding-check aging and
escheatment: every check an entity has issued and the bank has not yet been asked
to keep, re-derived from the register, aged to a stated as-of date, tied to the
bank reconciliation, and tested against the stale-dating and dormancy thresholds.

This is the back half of the disbursement story. Whether a payment was approved,
coded and released is somebody else's control. This engine starts after the check
has left the building and asks a narrower question: of everything issued, what has
never cleared, how old is it, and what has to happen to it now?

Three failures hide in an outstanding-check register and none of them look wrong.
The outstanding schedule is maintained beside the register instead of derived from
it, so it drifts and the bank reconciliation ties to the drift. A voided,
zero-dollar or stop-payment check keeps living -- still counted as outstanding, or
with a void that never nets the amount to zero. And the clock runs: six months out
the item is stale-dated and the bank may refuse it; a dormancy period out it is
unclaimed property owed to a state, and the register looks identical the day
before and the day after.

The engine rebuilds the outstanding set, every aging band, the follow-up marker
and the escheatment schedule from the check register and compares. It never voids,
never re-issues, never escheats, never pays and never writes to a source artifact.
Every age is measured against an ``as_of`` carried in the file, never the system
clock.

All data shipped with this package is **fictional**. No real entity, person, bank,
account number, project or path appears anywhere.

Public API
----------
- :func:`checkage_engine.engine.analyze_document`
- :func:`checkage_engine.engine.analyze_folder`
- :data:`checkage_engine.engine.REGISTRY`
- :func:`checkage_engine.generate.generate_corpus`
- :func:`checkage_engine.report.build_markdown_report`
- :func:`checkage_engine.report.build_json_report`
- :func:`checkage_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
