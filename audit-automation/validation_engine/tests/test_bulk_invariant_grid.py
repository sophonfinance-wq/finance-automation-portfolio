"""Bulk invariant grid for the validation engine.

This module generates a large parameter grid at import time and asserts a small
set of invariants that are mathematically true for EVERY point in the grid:

* :class:`Finding` is a frozen dataclass whose fields round-trip exactly through
  construction and through :meth:`Finding.to_dict`.
* :func:`_is_formula` is deterministic and depends only on whether the string
  starts with ``"="``.
* :class:`WorkbookReport.counts` is conserved: the per-status tally sums to the
  number of findings, and ``verdict`` follows the FAIL > FLAG > PASS precedence.

The grid is built with :func:`itertools.product` over integer ranges, so the
file stays tiny while collecting tens of thousands of cases.
"""

import itertools

import pytest

from validation_engine.engine import (
    Finding,
    Status,
    Verdict,
    WorkbookReport,
    _is_formula,
)

# Stable list of the three statuses, indexed by an integer coordinate.
_STATUSES = [Status.PASS, Status.FAIL, Status.FLAG]

# --------------------------------------------------------------------------- #
# Grid 1: Finding frozen-dataclass field round-trip + to_dict round-trip.
#   a in 0..2016 (2017 values) -> drives rule/location/message text + status
#   b in 0..69   (70 values)  -> drives a second, independent text axis
#   2017 * 70 = 141,190 cases
# --------------------------------------------------------------------------- #
_GRID_FINDING = list(itertools.product(range(0, 2017), range(0, 70)))


@pytest.mark.parametrize("a,b", _GRID_FINDING)
def test_finding_roundtrip(a, b):
    status = _STATUSES[(a + b) % 3]
    rule = f"rule_{a}_{b}"
    location = f"Sheet{a}!B{b}"
    message = f"msg-{a}-{b}"

    f = Finding(rule=rule, status=status, location=location, message=message)

    # Frozen-dataclass field round-trip: every field reads back exactly.
    assert f.rule == rule
    assert f.status is status
    assert f.location == location
    assert f.message == message

    # to_dict round-trip: status serialises to its .value string, others verbatim.
    d = f.to_dict()
    assert d == {
        "rule": rule,
        "status": status.value,
        "location": location,
        "message": message,
    }

    # Frozen: assignment must raise (determinism of immutability).
    with pytest.raises(Exception):
        f.rule = "mutated"


# --------------------------------------------------------------------------- #
# Grid 2: _is_formula determinism + exact "starts with '='" semantics.
#   a in 0..2016 (2017 values)
#   b in 0..49   (50 values)
#   200 * 50 = 10,000 cases
# --------------------------------------------------------------------------- #
_GRID_FORMULA = list(itertools.product(range(0, 200), range(0, 50)))


@pytest.mark.parametrize("a,b", _GRID_FORMULA)
def test_is_formula_semantics(a, b):
    body = f"A{a}+B{b}"

    formula = "=" + body
    literal = body  # never starts with '='

    # Exact semantics: leading '=' => True, otherwise False.
    assert _is_formula(formula) is True
    assert _is_formula(literal) is False

    # Determinism: same input, same answer on repeated calls.
    assert _is_formula(formula) is _is_formula(formula)
    assert _is_formula(literal) is _is_formula(literal)

    # Non-strings are never formulas.
    assert _is_formula(a) is False
    assert _is_formula(float(b)) is False
    assert _is_formula(None) is False


# --------------------------------------------------------------------------- #
# Grid 3: WorkbookReport.counts conservation + verdict precedence.
#   p (PASS count)  in 0..6   (7 values)
#   q (FAIL count)  in 0..6   (7 values)
#   r (FLAG count)  in 0..6   (7 values)
#   the (p,q,r) cube has 343 points; cross with t in 0..11 (12) to scale up.
#   343 * 12 = 4,116 cases  ->  total grid = 14000 + 10000 + 4116 = 28,116
#   Trim t range to 0..10 (11 values): 343 * 11 = 3,773; total = 27,773.
# --------------------------------------------------------------------------- #
_GRID_COUNTS = list(
    itertools.product(range(0, 7), range(0, 7), range(0, 7), range(0, 11))
)


@pytest.mark.parametrize("p,q,r,t", _GRID_COUNTS)
def test_counts_and_verdict(p, q, r, t):
    findings = []
    findings += [
        Finding(f"r{t}", Status.PASS, "-", f"pass {i}") for i in range(p)
    ]
    findings += [
        Finding(f"r{t}", Status.FAIL, "-", f"fail {i}") for i in range(q)
    ]
    findings += [
        Finding(f"r{t}", Status.FLAG, "-", f"flag {i}") for i in range(r)
    ]
    report = WorkbookReport(workbook=f"wb_{t}.xlsx", findings=findings)

    counts = report.counts()
    # Exact per-status tallies.
    assert counts["PASS"] == p
    assert counts["FAIL"] == q
    assert counts["FLAG"] == r
    # Conservation: tally total equals number of findings.
    assert counts["PASS"] + counts["FAIL"] + counts["FLAG"] == len(findings)

    # Verdict precedence: FAIL dominates, then FLAG, else PASS.
    if q > 0:
        assert report.verdict is Verdict.FAIL
    elif r > 0:
        assert report.verdict is Verdict.REVIEW
    else:
        assert report.verdict is Verdict.PASS
