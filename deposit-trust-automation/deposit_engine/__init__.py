"""
deposit_engine
==============

A deterministic, **read-only** control engine for a residential developer's
pre-close earnest-money deposit trust: the internal deposit ledger, the escrow
agent's record and the construction-loan paydown register proved -- unit by
unit -- to describe the same money, to the cent, with every cancellation split
into fee, refund and reversal and every rollup figure recomputed from the
deposits underneath it.

Before a for-sale unit closes, its buyer's earnest money is receipted into
escrow, split from any upgrade deposit, and swept to the construction loan as
a principal paydown; if the buyer cancels, the deposit decomposes into a
retained termination fee, a refund, and a reversal of the earlier paydown.
Three failures hide inside that and none look wrong on any single page: the
agent's record and the books disagree on a unit; the sweep drifts from the
ledger's own status column; and the reconciliation summary carries variances,
bucket totals and trust balances nobody recomputed. The fully-closed unit's
settlement tie-out belongs to the close-of-escrow engine, and the upgrade
deposit's selection/pricing story to the buyer-upgrades engine -- here the
upgrade column is only the segregation counterpart that must sum with earnest
money to the cash that moved.

The engine recomputes every stated determination through the shared
reconciliation kernel and compares. It never pays, never posts and never
writes to a source artifact.

All data shipped with this package is **fictional**. No real entity, person,
bank, escrow agent, project or path appears anywhere.

Public API
----------
- :func:`deposit_engine.engine.analyze_document`
- :func:`deposit_engine.engine.analyze_folder`
- :data:`deposit_engine.engine.REGISTRY`
- :func:`deposit_engine.generate.generate_corpus`
- :func:`deposit_engine.report.build_markdown_report`
- :func:`deposit_engine.report.build_json_report`
- :func:`deposit_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
