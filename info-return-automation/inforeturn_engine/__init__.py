"""
inforeturn_engine
=================

A deterministic, **read-only** control engine for the annual information-return
issuance run: the payee population a group reassembles entity by entity, the box
threshold applied to it, the form issued off the back of that, and every box
footed back to the payment lines it came from.

Nothing here decides whether a payment should have been made. Approving and
releasing a disbursement is a separate engine's job, and that engine explicitly
declines to ask whether what it released was reportable. This engine is that
question, asked once a year over the whole population, and it is narrower than it
looks: a threshold, a taxpayer number, a box total and a transmittal, restated by
hand for every payee, every year. The payee who clears a threshold in one entity
and is never cut a form. The payee with no taxpayer number on file and nothing
withheld against it. The box amount re-keyed from a summary rather than footed
from the entity's own payment lines. The transmittal whose count or total is
maintained beside the register rather than struck from it.

The engine recomputes every box from the payment lines beneath it and compares
with exact ``==``, rebuilds each issuance decision from the threshold that
defines it, recomputes backup withholding at the statutory rate, and foots the
transmittals and the annual rollup back to the forms. Controls and the generator
share one issuance kernel, so a form cannot disagree with the data that produced
it. It never posts, never files and never writes to a source artifact. Every
payment line is tested against the reporting year carried in the file, never the
system clock.

All data shipped with this package is **fictional**. No real entity, person,
payee, taxpayer number or path appears anywhere.

Public API
----------
- :func:`inforeturn_engine.engine.analyze_document`
- :func:`inforeturn_engine.engine.analyze_folder`
- :data:`inforeturn_engine.engine.REGISTRY`
- :func:`inforeturn_engine.generate.generate_corpus`
- :func:`inforeturn_engine.report.build_markdown_report`
- :func:`inforeturn_engine.report.build_json_report`
- :func:`inforeturn_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
