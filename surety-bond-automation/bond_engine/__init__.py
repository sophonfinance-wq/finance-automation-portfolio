"""
bond_engine
===========

A deterministic, **read-only** control engine for a residential developer's
surety bond programme.

A developer cannot pull a permit, record a plat or turn a street over to a city
without posting surety, so the bonds accumulate: a statutory licence bond per
operating entity, a performance bond per set of subdivision improvements, a
maintenance bond running through the warranty period after the city accepts the
work, a street-use bond for the right of way. Each carries its own obligee, term
and premium, and some are collateralised with the developer's own cash.

The failure mode is quiet. A bond does its job, the city accepts the work, the
obligation ends, the register is marked released -- and nobody writes to the
surety. The collateral stays where it is. It raises no payable, ages on no
report, and sits in restricted cash looking exactly like cash until someone ties
the register to the ledger. The mirror image is just as expensive: a bond nobody
released keeps renewing its premium and keeps consuming the aggregate limit of
the indemnity agreement, so the next project's bond is declined for capacity the
programme is not actually using.

The controls here are lifecycle controls. A bond has a beginning, a term, an
obligation it secures and an end; the collateral, the premium and the exposure
each have to follow that lifecycle, and each is tested against it.

It never posts, never releases and never writes to a source artifact. It is a
sensor: the deterministic ground truth other systems and reviewers consume. Every
date test is made against an ``as_of`` carried in the file, never the system
clock, so the verdict is a property of the data rather than of the day it ran.

All data shipped with this package is **fictional**. No real entity, person,
surety, municipality, project or path appears anywhere.

Public API
----------
- :func:`bond_engine.engine.analyze_document`
- :func:`bond_engine.engine.analyze_folder`
- :data:`bond_engine.engine.REGISTRY`
- :func:`bond_engine.generate.generate_corpus`
- :func:`bond_engine.report.build_markdown_report`
- :func:`bond_engine.report.build_json_report`
- :func:`bond_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
