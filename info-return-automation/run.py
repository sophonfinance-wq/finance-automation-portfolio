#!/usr/bin/env python3
"""
One-command demo of the information-return issuance engine.
==========================================================

::

    python run.py

Regenerates the fictional corpus into ``samples/``, runs every control over it,
writes ``inforeturn_report.json`` and ``inforeturn_report.md``, and exits with
the verdict code (0 PASS / 1 REVIEW / 2 FAIL / 3 usage). The corpus deliberately
contains planted defects, so a non-zero exit here is the engine working.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from inforeturn_engine.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(
        main([
            str(HERE / "samples"),
            "--generate",
            "--json", str(HERE / "inforeturn_report.json"),
            "--md", str(HERE / "inforeturn_report.md"),
        ])
    )
