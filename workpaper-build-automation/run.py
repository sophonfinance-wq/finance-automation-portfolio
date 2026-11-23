#!/usr/bin/env python3
"""
One-command demo of the tax workpaper build engine.
===================================================

::

    python run.py

Regenerates the fictional corpus into ``samples/``, **builds** a workpaper
package and its build register for every file into ``out/`` (a generated
directory the repository does not track), runs all twenty-four controls over the
built artifacts, writes ``workpaper_report.json`` and ``workpaper_report.md``,
and exits with the verdict code (0 PASS / 1 REVIEW / 2 FAIL / 3 usage). The
corpus deliberately contains planted defects, so a non-zero exit here is the
engine working.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from workpaper_engine.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(
        main([
            str(HERE / "samples"),
            "--generate",
            "--build", str(HERE / "out"),
            "--json", str(HERE / "workpaper_report.json"),
            "--md", str(HERE / "workpaper_report.md"),
        ])
    )
