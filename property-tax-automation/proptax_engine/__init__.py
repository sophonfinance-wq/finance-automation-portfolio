"""
proptax_engine
==============

A deterministic, **read-only** control engine for a residential developer's
property tax cycle.

A homebuilder's property tax problem is not the arithmetic on one bill. It is that
the unit of taxation and the unit of ownership come apart, continuously, in a
direction nobody is watching.

A project starts as one parent parcel. It is platted, and becomes forty. The
assessor picks the split up on its own schedule, which is not the developer's.
Then the units close -- one at a time, over eighteen months -- and each closing
moves exactly one parcel off the developer's books while the tax roll keeps
billing the account it always has. The bill still arrives. It still looks right.
It is simply, increasingly, for somebody else's houses.

Nothing in the payables cycle catches this. The invoice is genuine, the payee is
genuinely the county, the amount genuinely matches the notice. The only thing
wrong is *whose parcel it is*, and that fact lives in a closing file the person
approving the payment has never seen.

The second problem is the calendar. A developer operating across state lines is
subject to regimes that share no dates, no instalment count and no penalty
arithmetic, so applying one jurisdiction's habits to another's parcel is how a
delinquency is discovered after the penalty has already attached. Every regime
here is **data**: its fiscal year, its instalments, its due dates and its penalty
rates are rows in a table, and no control hard-codes any of them.

It never pays, never files and never writes to a source artifact. It is a sensor:
the deterministic ground truth other systems and reviewers consume. Every
delinquency test is made against an ``as_of`` carried in the file, never the
system clock.

All data shipped with this package is **fictional**. No real entity, person,
county, parcel, project or path appears anywhere.

Public API
----------
- :func:`proptax_engine.engine.analyze_document`
- :func:`proptax_engine.engine.analyze_folder`
- :data:`proptax_engine.engine.REGISTRY`
- :func:`proptax_engine.generate.generate_corpus`
- :func:`proptax_engine.report.build_markdown_report`
- :func:`proptax_engine.report.build_json_report`
- :func:`proptax_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
