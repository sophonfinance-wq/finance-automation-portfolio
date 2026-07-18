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


# --- compound expression & commutativity grid (+5,500 cases) ---------------
# Operator precedence and commutativity are exact over integer inputs:
#   =B2*B3+B2  ->  a*b + a   (multiplication binds tighter than addition)
#   a+b == b+a and a*b == b*a (commutativity)
#   a-b == -(b-a)             (antisymmetry of subtraction)
_GRID_COMPOUND = list(itertools.product(range(-27, 28), range(1, 101)))  # 55*100


@pytest.mark.parametrize("a,b", _GRID_COMPOUND)
def test_compound_precedence_and_commutativity(a: int, b: int) -> None:
    cells = {"B2": a, "B3": b}

    # Precedence: multiplication before addition.
    assert evaluate("=B2*B3+B2", cells) == a * b + a

    # Commutativity of + and *.
    assert evaluate("=B2+B3", cells) == evaluate("=B3+B2", cells)
    assert evaluate("=B2*B3", cells) == evaluate("=B3*B2", cells)

    # Antisymmetry of subtraction.
    assert evaluate("=B2-B3", cells) == -evaluate("=B3-B2", cells)
