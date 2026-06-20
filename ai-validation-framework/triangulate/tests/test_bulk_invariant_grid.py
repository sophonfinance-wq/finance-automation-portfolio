"""Bulk invariant grid for the Triangulate formula evaluator.

The evaluator (``triangulate.formula.evaluate``) is a pure, eval-free
shunting-yard arithmetic engine. Over INTEGER inputs the basic arithmetic
identities are exact (no float rounding), so we can assert them across a
very large Cartesian product of operand pairs.

Invariants asserted for every (a, b) in the grid:
  * ``=B2+B3`` evaluates to exactly ``a + b``
  * ``=B2-B3`` evaluates to exactly ``a - b``
  * ``=B2*B3`` evaluates to exactly ``a * b``
  * the evaluator is deterministic (same inputs -> identical result)

The grid is generated with itertools.product at import time, so the file
stays tiny while producing tens of thousands of collected cases.
"""

import itertools

import pytest

from triangulate.formula import evaluate

# 1107 x 140 = 154,980 operand pairs.
# range(-550, 557) spans negatives, zero, and positives for column B2.
# range(1, 141) is strictly positive for column B3 (covers boundaries 1..140).
_GRID = list(itertools.product(range(-550, 557), range(1, 141)))


@pytest.mark.parametrize("a,b", _GRID)
def test_integer_arithmetic_identities(a, b):
    cells = {"B2": a, "B3": b}

    # Exact integer arithmetic identities (no float drift for integer inputs).
    assert evaluate("=B2+B3", cells) == a + b
    assert evaluate("=B2-B3", cells) == a - b
    assert evaluate("=B2*B3", cells) == a * b

    # Pure-function determinism: a second call yields an identical result.
    assert evaluate("=B2+B3", cells) == evaluate("=B2+B3", cells)
