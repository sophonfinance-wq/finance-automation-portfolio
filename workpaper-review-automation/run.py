"""Generate the fictional corpus, analyze it, and write both reports.

    python run.py

Writes ``samples/`` (the seeded corpus), ``workpaper_report.json`` and
``workpaper_report.md``. Exit code is the verdict, as everywhere in this repo.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from workpaper_engine.cli import main  # noqa: E402

if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    sys.exit(
        main(
            [
                os.path.join(here, "samples"),
                "--generate",
                "--json", os.path.join(here, "workpaper_report.json"),
                "--md", os.path.join(here, "workpaper_report.md"),
                "--quiet",
            ]
        )
    )
