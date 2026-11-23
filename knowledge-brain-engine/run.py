#!/usr/bin/env python
"""Convenience entrypoint: ``python run.py [args...]``.

Equivalent to ``python -m brain_engine``. Lets the package run without
installation from the folder root.
"""

from __future__ import annotations

import sys

from brain_engine.cli import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
