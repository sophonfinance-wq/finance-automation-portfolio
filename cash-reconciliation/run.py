"""Convenience entry point: ``python run.py`` runs the reconciliation CLI.

Equivalent to ``python -m recon_engine``. Accepts the same arguments.
"""

from __future__ import annotations

from recon_engine.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
