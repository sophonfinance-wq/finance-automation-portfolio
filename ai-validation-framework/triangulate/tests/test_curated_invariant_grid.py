"""Curated invariant grid for the Triangulate formula evaluator (1,500 cases).

A bounded, CI-gating slice of the SWEEP-gated ``test_bulk_invariant_grid.py``.
The evaluator is a pure, eval-free shunting-yard arithmetic engine, so over
integer inputs the basic identities are exact:

* ``=B2+B3`` -> ``a + b``; ``=B2-B3`` -> ``a - b``; ``=B2*B3`` -> ``a * b``;
* the evaluator is deterministic (same inputs -> identical result).
"""

import itertools

import pytest

from triangulate.formula import evaluate

# 30 x 50 = 1,500 operand pairs (B2 spans negatives/zero/positives, B3 positive).
_GRID = list(itertools.product(range(-15, 15), range(1, 51)))


@pytest.mark.parametrize("a,b", _GRID)
def test_integer_arithmetic_identities(a: int, b: int) -> None:
    cells = {"B2": a, "B3": b}

    assert evaluate("=B2+B3", cells) == a + b
    assert evaluate("=B2-B3", cells) == a - b
    assert evaluate("=B2*B3", cells) == a * b

    # Pure-function determinism.
    assert evaluate("=B2+B3", cells) == evaluate("=B2+B3", cells)
