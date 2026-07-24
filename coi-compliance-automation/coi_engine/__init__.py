"""
coi_engine
==========

A deterministic, **read-only** control engine for a residential developer's
certificate-of-insurance (COI) compliance: every consultant, general contractor
and subcontractor the developer hires proved -- party by party -- to have its
certificate on file, unexpired, and meeting the contract-required limits and
endorsements for its type.

This is the other half of the insurance story. Where a master premium lands on
each project's job cost is an *allocation* question owned by a separate engine --
and that engine explicitly declines to check whether a certificate is on file.
This engine is that check. A COI is a one-page snapshot of coverage that was true
the day the broker issued it, and it goes stale in ways nobody watches: the
policy lapses and the renewal never arrives; the limits sit below what the
contract required; the additional-insured or waiver-of-subrogation endorsement
was never added; the monthly rollup calls a party compliant on a determination
nobody recomputed from the certificates underneath it.

The engine recomputes every party's compliant determination from the requirement
matrix and the governing certificates, and compares. It never pays, never files
and never writes to a source artifact. Every expiry and renewal test is made
against an ``as_of`` carried in the file, never the system clock.

All data shipped with this package is **fictional**. No real entity, person,
carrier, project or path appears anywhere.

Public API
----------
- :func:`coi_engine.engine.analyze_document`
- :func:`coi_engine.engine.analyze_folder`
- :data:`coi_engine.engine.REGISTRY`
- :func:`coi_engine.generate.generate_corpus`
- :func:`coi_engine.report.build_markdown_report`
- :func:`coi_engine.report.build_json_report`
- :func:`coi_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
