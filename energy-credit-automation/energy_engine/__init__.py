"""
energy_engine
=============

A deterministic, **read-only** control engine for the IRC §45L energy-efficient
home credit: every claimed dwelling unit re-derived -- unit by unit -- from its
close-of-escrow date, its RESNET/HERS certification and the dated statutory
per-unit amount, then rolled up per project, per region and per fiscal year, with
net-benefit and partner-allocation derivation and a full cross-artifact tie-out.

The §45L credit is a per-unit credit: a builder earns a fixed statutory amount for
each newly built dwelling it sells, but only for a unit that closed inside the
fiscal-year window being filed and holds an energy certificate from a certified
rater. The gross credit is the count of qualifying units times the dated rate, and
every figure above it -- profit addback, tax effect, net benefit, partner split --
is arithmetic on that product. It goes wrong in ways nobody watches: a unit claimed
that closed out of period or past the sunset or was never certified; a unit counted
twice across successive period filings; a rollup, tie-out or allocation stated on a
number nobody recomputed from the units underneath it.

The engine rebuilds every credit figure from the unit register and the dated
statutory rate, and compares. It never files, never pays and never writes to a
source artifact. Every close-of-escrow and sunset test is made against the period
and sunset dates carried in the file, never the system clock.

All data shipped with this package is **fictional**. No real entity, person,
project, place or path appears anywhere.

Public API
----------
- :func:`energy_engine.engine.analyze_document`
- :func:`energy_engine.engine.analyze_folder`
- :data:`energy_engine.engine.REGISTRY`
- :func:`energy_engine.generate.generate_corpus`
- :func:`energy_engine.report.build_markdown_report`
- :func:`energy_engine.report.build_json_report`
- :func:`energy_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
