"""
insurance_engine
================

A deterministic, **read-only** control engine for a residential developer's
insurance cost allocation: one master-programme premium apportioned across many
projects' job cost, the builder's risk written over what is under construction,
and the carrier audit true-up that lands months after the term.

A developer does not buy insurance per project. It buys a programme -- a general
liability tower, a builder's risk policy, an excess layer -- and one premium then
has to become a number on each project's job cost, correctly, reproducibly, and
summing back to what was actually paid. Three things go wrong and none of them
look wrong: the residual cent that is dropped or double-counted, the basis value
that never arrived and silently redistributes every other project's share, and the
audit credited to whoever is open today rather than to the projects that bore the
deposit.

The engine re-derives every share from its declared basis by the same
largest-remainder method that should have produced it, and compares to the cent.
It never pays, never files and never writes to a source artifact. Every expiry and
ageing test is made against an ``as_of`` carried in the file, never the system
clock.

All data shipped with this package is **fictional**. No real entity, person,
carrier, project or path appears anywhere.

Public API
----------
- :func:`insurance_engine.engine.analyze_document`
- :func:`insurance_engine.engine.analyze_folder`
- :data:`insurance_engine.engine.REGISTRY`
- :func:`insurance_engine.generate.generate_corpus`
- :func:`insurance_engine.report.build_markdown_report`
- :func:`insurance_engine.report.build_json_report`
- :func:`insurance_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
