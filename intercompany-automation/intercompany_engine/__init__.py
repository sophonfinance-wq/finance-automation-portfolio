"""
intercompany_engine
====================

A deterministic, **read-only** control engine for a development group's
intercompany reciprocity and cash-flow funding protocol.

A development group is a tree of entities, not one company: a holding parent over
a services arm that carries the payroll and a capital arm that guarantees the
construction loans, plus a predevelopment entity that carries land while it is
entitled. Cash moves between them constantly -- advances down the chain, repayments
back up, equity into projects -- and every movement lands two entries on two sets
of books kept by two people.

So the failure mode is that the two sides drift. Each entity's own books foot; the
break lives *between* two entities and surfaces only at consolidation, when the
intercompany balances are meant to eliminate to zero and instead leave a residual
nobody can source. The controls here are reciprocity controls: a due-from must
equal the due-to that faces it, a closing balance must roll forward from the
transactions that moved it, and cash must flow along the ownership chain from the
protocol-correct source -- not merely balance on each entity alone.

It never funds, never sweeps and never writes to a source artifact. It is a
sensor: the deterministic ground truth other systems and reviewers consume.

All data shipped with this package is **fictional**. No real entity, person, bank,
project or path appears anywhere.

Public API
----------
- :func:`intercompany_engine.engine.analyze_document`
- :func:`intercompany_engine.engine.analyze_folder`
- :data:`intercompany_engine.engine.REGISTRY`
- :func:`intercompany_engine.generate.generate_corpus`
- :func:`intercompany_engine.report.build_markdown_report`
- :func:`intercompany_engine.report.build_json_report`
- :func:`intercompany_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
