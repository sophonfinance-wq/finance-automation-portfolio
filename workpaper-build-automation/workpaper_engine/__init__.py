"""
workpaper_engine
================

A deterministic engine that **builds** the annual tax workpaper package for a
new fiscal year, and then proves what it built.

The product is a constructed package: a trial balance harvested from a locked
general-ledger extract by exact account number and scoped to one entity block; a
balance sheet and statement of operations classified from the prior year's map
and footing to zero; a members' equity schedule that freezes every prior-year
layer as a constant, advances each rolling caption by exactly one year, derives
each current-year contribution and distribution as the movement in its account
and allocates the result on the carried split; member capital accounts with a
new year block per member, book and tax, carrying liability shares and outside
basis; an earnings-and-profits roll-forward; an evidence tab with its citation
and a subtotal that foots to zero; and a build register naming every constructed
cell beside the derivation that produced it, with content digests for chain of
custody.

Rolling a workpaper is not copying one. The failure modes are the ones that
survive a footing check -- a prior-year layer that moves, a caption left at last
year's date, a contribution row carrying a balance where a delta belongs, a row
form read off a live formula rather than off the balances at both year-ends, a
rebuild that touched a cell nobody declared. So twenty-four controls run over
the emitted artifact and re-derive each of them from the inputs, with exact
``==``, integer cents and no tolerance band.

All data shipped with this package is **fictional**. No real entity, project,
place, account balance or path appears anywhere.

Public API
----------
- :func:`workpaper_engine.build.build_package`
- :class:`workpaper_engine.build.WorkpaperPackage`
- :func:`workpaper_engine.build.capture_prebuild_image`
- :func:`workpaper_engine.engine.analyze_document`
- :func:`workpaper_engine.engine.analyze_folder`
- :data:`workpaper_engine.engine.REGISTRY`
- :func:`workpaper_engine.generate.generate_corpus`
- :func:`workpaper_engine.report.build_register_markdown`
- :func:`workpaper_engine.report.build_markdown_report`
- :func:`workpaper_engine.report.build_json_report`
- :func:`workpaper_engine.cli.main`
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
