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


# --- report counts conservation grid (+2,000 cases) ------------------------
# WorkbookReport.counts() must tally exactly and conserve the total, and
# Finding.to_dict must serialise the status to its .value string.
from validation_engine.engine import Verdict, WorkbookReport  # noqa: E402

_GRID_REPORT = list(itertools.product(range(0, 40), range(0, 50)))  # 40*50


@pytest.mark.parametrize("p,q", _GRID_REPORT)
def test_counts_conservation_and_verdict(p: int, q: int) -> None:
    n_pass = p % 5
    n_fail = q % 4
    n_flag = (p + q) % 3
    findings = (
        [Finding(f"r{p}", Status.PASS, "-", f"pass {i}") for i in range(n_pass)]
        + [Finding(f"r{p}", Status.FAIL, "-", f"fail {i}") for i in range(n_fail)]
        + [Finding(f"r{p}", Status.FLAG, "-", f"flag {i}") for i in range(n_flag)]
    )
    report = WorkbookReport(workbook=f"wb_{p}_{q}.xlsx", findings=findings)

    counts = report.counts()
    assert counts["PASS"] == n_pass
    assert counts["FAIL"] == n_fail
    assert counts["FLAG"] == n_flag
    # Conservation: the tally sums to the number of findings.
    assert counts["PASS"] + counts["FAIL"] + counts["FLAG"] == len(findings)

    # Verdict precedence: FAIL dominates, then FLAG, else PASS.
    if n_fail > 0:
        assert report.verdict is Verdict.FAIL
    elif n_flag > 0:
        assert report.verdict is Verdict.REVIEW
    else:
        assert report.verdict is Verdict.PASS

    # to_dict serialises status to its .value string.
    if findings:
        d = findings[0].to_dict()
        assert d["status"] == findings[0].status.value
