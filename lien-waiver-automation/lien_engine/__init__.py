"""
lien_engine
===========

A deterministic, **read-only** control engine for a residential developer's
mechanics-lien waiver coverage: every progress payment down the subcontractor
tier chain matched to a lien waiver -- of the right kind, through the right date,
for the right amount -- so that no lien survives to attach to the developer's
title.

A developer pays a general contractor, who pays subcontractors, who pay their own
lower-tier subs and suppliers. Every one of those parties can file a mechanics
lien, and a lien waiver is the release that gives it up. Three things go wrong and
none of them look wrong while a waiver is on file: the *conditional* waiver signed
at payment that was never upgraded to the *unconditional* owed once the cheque
cleared; the waiver whose through-date stops short of the money it was meant to
cover; and the lower-tier supplier, funded from the same payment, that never
released at all.

The engine re-derives the unwaived exposure from the payments and the releases,
and matches every cleared payment to an unconditional waiver that runs at least as
far as the money did. It never pays, never files and never writes to a source
artifact. Every coverage and ageing test is made against an ``as_of`` carried in
the file, never the system clock.

All data shipped with this package is **fictional**. No real entity, person,
project or path appears anywhere.

Public API
----------
- :func:`lien_engine.engine.analyze_document`
- :func:`lien_engine.engine.analyze_folder`
- :data:`lien_engine.engine.REGISTRY`
- :func:`lien_engine.generate.generate_corpus`
- :func:`lien_engine.report.build_markdown_report`
- :func:`lien_engine.report.build_json_report`
- :func:`lien_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
