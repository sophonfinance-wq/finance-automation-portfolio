#!/usr/bin/env python3
"""Convenience entrypoint: ``python run.py --period 2026-03``.

Thin wrapper around :func:`close_engine.cli.main` so the package can be run
without the ``-m`` flag.
"""

from __future__ import annotations

import sys

from close_engine.cli import main

if __name__ == "__main__":
    sys.exit(main())
