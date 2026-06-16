#!/usr/bin/env python3
"""Convenience entrypoint: ``python run.py [args]``.

Equivalent to ``python -m triangulate``. Lets the project run without any
install step from the folder root.
"""

import sys

from triangulate.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
