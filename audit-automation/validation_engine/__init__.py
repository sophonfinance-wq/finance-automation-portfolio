"""
validation_engine
=================

A deterministic, **read-only** rules-based validation engine for finished
financial workbooks (``.xlsx``) and their JSON exports.

The engine runs a *registry* of independent checks over each workbook and emits
a structured report (markdown + JSON) with a per-finding ``PASS`` / ``FAIL`` /
``FLAG`` status, a cell/location reference, and an overall verdict.

All data shipped with this package is **fictional** (e.g. "Demo Holdings LLC",
"Maple Fund LP"). The engine never writes to an audited file.

Public API
----------
- :func:`validation_engine.engine.validate_workbook`
- :func:`validation_engine.engine.validate_folder`
- :data:`validation_engine.engine.REGISTRY`
- :func:`validation_engine.generate.generate_corpus`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
