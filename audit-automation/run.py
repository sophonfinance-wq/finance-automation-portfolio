"""
Convenience entrypoint for the validation engine.
=================================================

Equivalent to ``python -m validation_engine`` but runnable as a plain script
from the folder root. With no arguments it regenerates the fictional sample
corpus into ``./samples`` and validates it, writing both report formats.

Examples
--------
::

    python run.py                       # generate + validate ./samples, write reports
    python run.py ./samples             # just validate an existing folder
    python run.py ./samples --json r.json --md r.md
"""

from __future__ import annotations

import sys
from pathlib import Path

from validation_engine.cli import main

if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Zero-arg quickstart: generate the corpus and write both reports.
        here = Path(__file__).resolve().parent
        samples = here / "samples"
        argv = [
            str(samples),
            "--generate",
            "--json",
            str(here / "validation_report.json"),
            "--md",
            str(here / "validation_report.md"),
        ]
        raise SystemExit(main(argv))
    raise SystemExit(main())
