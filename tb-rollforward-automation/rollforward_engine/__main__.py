"""Module entrypoint: ``python -m rollforward_engine <folder>``."""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
