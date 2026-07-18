"""Module entry point so the package runs as ``python -m cash_engine``."""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
