"""
ap_engine
=========

A deterministic, **read-only** control engine for the accounts-payable cycle in
construction and real-estate development.

The engine consumes the fixed-format posting artifacts an accounts-payable cycle
emits -- invoice posting reports, payment selection registers, approval-routing
matrices, information-reporting registers, commitment and change-order journals
-- and runs an ordered registry of controls that answer four questions a
controller actually asks:

1. Did the post actually happen, and did it balance?
2. Is this payment allowed to be released yet?
3. Is every job routed to a valid approver chain, with duties segregated?
4. Will year-end information reporting be complete and correct?

It never posts, never pays and never writes to a source artifact. It is a
sensor: the deterministic ground truth other systems and reviewers consume.

All data shipped with this package is **fictional** (e.g. "Demo Holdings LLC",
"Ironwood Sandbox Supply Co"). No real vendor, entity, person, bank, document
number or path appears anywhere.

Public API
----------
- :func:`ap_engine.engine.analyze_document`
- :func:`ap_engine.engine.analyze_folder`
- :data:`ap_engine.engine.REGISTRY`
- :func:`ap_engine.generate.generate_corpus`
- :func:`ap_engine.report.build_markdown_report`
- :func:`ap_engine.report.build_json_report`
- :func:`ap_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
