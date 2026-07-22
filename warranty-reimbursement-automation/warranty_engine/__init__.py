"""
warranty_engine
===============

A deterministic, **read-only** control engine for a homebuilder's warranty
reimbursement programme.

A builder buys a warranty policy at the start of a project, then spends the next
several years claiming against it a few thousand dollars at a time: a leaking
sink in unit 4, a failed circuit in unit 11. Each claim is trivially small. The
policy behind them is not, and it is finite.

So the failure mode is **accumulation**, and the boundaries at the edges of each
period. Any one claim is obviously fine; the running total is what goes wrong,
and nobody reviewing a single claim can see it. Two things have to hold at once:
the pool is bounded by a coverage limit derived from a premium derived from
construction cost -- three numbers typed once at inception and trusted forever --
and every claim has to be inside its policy period, inside its own quarterly
window, and after the unit it relates to actually closed, because coverage begins
at close of escrow and not before.

It never files, never pays and never writes to a source artifact. It is a sensor:
the deterministic ground truth other systems and reviewers consume.

All data shipped with this package is **fictional**. No real policy, insurer,
buyer, unit, invoice or path appears anywhere.

Public API
----------
- :func:`warranty_engine.engine.analyze_document`
- :func:`warranty_engine.engine.analyze_folder`
- :data:`warranty_engine.engine.REGISTRY`
- :func:`warranty_engine.generate.generate_corpus`
- :func:`warranty_engine.report.build_markdown_report`
- :func:`warranty_engine.report.build_json_report`
- :func:`warranty_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
