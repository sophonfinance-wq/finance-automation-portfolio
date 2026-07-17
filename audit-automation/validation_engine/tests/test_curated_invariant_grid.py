"""Curated invariant grid for the validation engine (1,500 cases).

A bounded, CI-gating slice of the SWEEP-gated ``test_bulk_invariant_grid.py``.
Every case exercises the real ``validation_engine`` types and asserts exact
invariants:

* ``Finding`` is a frozen dataclass whose fields round-trip through construction
  and through ``to_dict`` (status serialises to its ``.value``);
* ``_is_formula`` is deterministic and true exactly when the string starts "=".
"""

import itertools

import pytest

from validation_engine.engine import (
    Finding,
    Status,
    _is_formula,
)

_STATUSES = [Status.PASS, Status.FAIL, Status.FLAG]

# 30 x 50 = 1,500.
_GRID = list(itertools.product(range(0, 30), range(0, 50)))


@pytest.mark.parametrize("a,b", _GRID)
def test_finding_roundtrip_and_is_formula(a: int, b: int) -> None:
    status = _STATUSES[(a + b) % 3]
    rule = f"rule_{a}_{b}"
    location = f"Sheet{a}!B{b}"
    message = f"msg-{a}-{b}"

    f = Finding(rule=rule, status=status, location=location, message=message)

    # Frozen-dataclass field round-trip.
    assert f.rule == rule
    assert f.status is status
    assert f.location == location
    assert f.message == message

    # to_dict round-trip: status serialises to its .value, others verbatim.
    assert f.to_dict() == {
        "rule": rule,
        "status": status.value,
        "location": location,
        "message": message,
    }

    # Frozen: mutation must raise.
    with pytest.raises(Exception):
        f.rule = "mutated"

    # _is_formula: leading '=' => True, otherwise False; deterministic.
    body = f"A{a}+B{b}"
    assert _is_formula("=" + body) is True
    assert _is_formula(body) is False
    assert _is_formula("=" + body) is _is_formula("=" + body)
    # Non-strings are never formulas.
    assert _is_formula(a) is False
    assert _is_formula(None) is False
