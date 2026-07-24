"""
wire_engine
===========

A deterministic, **read-only** control engine for an operating entity's outbound
wire and transfer release: every wire, ACH and book transfer proved -- packet by
packet -- to have two distinct signers, a complete secondary authorization, an
approved beneficiary (or a called-back new one), a valid routing number resolved
to the right bank, a funding account that covers it, no already-posted duplicate,
and an in-order path through the three-stage workflow.

This is the gate in front of the wire room. Where a transfer finally lands in the
general ledger is a *booking* question owned by a separate engine -- and that
engine assumes the money was allowed to leave. This engine is that check. A wire
is irreversible the moment it posts, and it goes wrong in ways nobody watches:
one person moves the money end to end; the beneficiary is off template or the
bank detail changed with no callback; the routing number fails its checksum or
names the wrong bank; the funding account cannot cover it; a payment is sent
twice; the daily released-wire log calls a packet releasable on a determination
nobody recomputed from the signatures and templates underneath it.

The engine recomputes every packet's releasable determination from the signers,
the beneficiary templates and the funding accounts, and compares. It never pays,
never posts and never writes to a source artifact. Every date test is made
against the dates carried in the file, never the system clock.

All data shipped with this package is **fictional**. No real entity, person,
bank, project or path appears anywhere.

Public API
----------
- :func:`wire_engine.engine.analyze_document`
- :func:`wire_engine.engine.analyze_folder`
- :data:`wire_engine.engine.REGISTRY`
- :func:`wire_engine.generate.generate_corpus`
- :func:`wire_engine.report.build_markdown_report`
- :func:`wire_engine.report.build_json_report`
- :func:`wire_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
