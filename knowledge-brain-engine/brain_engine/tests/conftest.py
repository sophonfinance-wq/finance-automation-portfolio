"""Test path setup for running from this package directory."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# --- Optional exhaustive property/invariant sweep --------------------------
# `test_bulk_invariant_grid.py` generates a very large parametrized sweep
# (hundreds of thousands of cases). It is excluded from the default suite for
# speed and runs on demand:  SWEEP=1 pytest
def pytest_ignore_collect(collection_path, config):
    import os
    if os.environ.get("SWEEP") != "1" and collection_path.name == "test_bulk_invariant_grid.py":
        return True
