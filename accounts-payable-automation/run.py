"""
Convenience entrypoint for the accounts payable engine.
=======================================================

Equivalent to ``python -m ap_engine`` but runnable as a plain script from the
folder root. With no arguments it regenerates the fictional sample corpus into
``./samples``, analyzes it, and writes both committed report artifacts.

Examples
--------
::

    python run.py                        # generate + analyze ./samples, write reports
    python run.py ./samples              # just analyze an existing folder
    python run.py ./samples --json r.json --md r.md

Exit codes
----------
``0`` PASS - ``1`` REVIEW - ``2`` FAIL - ``3`` usage / IO error.
"""

from __future__ import annotations

import sys
from pathlib import Path

from ap_engine.cli import main

if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Zero-arg quickstart: generate the corpus and write both artifacts.
        here = Path(__file__).resolve().parent
        samples = here / "samples"
        argv = [
            str(samples),
            "--generate",
            "--json",
            str(here / "ap_report.json"),
            "--md",
            str(here / "ap_report.md"),
        ]
        raise SystemExit(main(argv))
    raise SystemExit(main())
