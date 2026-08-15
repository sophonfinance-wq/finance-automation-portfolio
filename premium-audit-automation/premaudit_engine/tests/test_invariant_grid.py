"""Invariant grids - every case is a real end-to-end or property assertion.

Pipeline grid: parse(generate(seed)) must tie to the report's own printed
totals for every seed, the window subset must be exact, and triage must
partition the lines. Money grid: parse/format is a lossless round trip across
the cent range. Window grid: containment agrees with date arithmetic.
"""
import datetime as dt
import os

import pytest

from ..engine import build_package
from ..generate import generate_report
from ..model import AuditWindow, TriagePolicy, Triage
from ..money import format_cents, parse_cents

PIPELINE_SEEDS = range(2400) if not os.environ.get("SWEEP") else range(24000)
WINDOW = AuditWindow(dt.date(2025, 10, 15), dt.date(2026, 6, 1))
POLICY = TriagePolicy(clearing_vendor_ids=frozenset({"0000"}))


@pytest.mark.parametrize("seed", PIPELINE_SEEDS)
def test_pipeline_ties_and_partitions(seed):
    gen = generate_report(seed, jobs=2)
    pkg = build_package(gen.text, gen.company, WINDOW, POLICY, gen.coverage)
    assert len(pkg.lines) == gen.line_count
    assert pkg.full_total_cents == sum(gen.expected_job_totals.values())
    win = sum(t.line.amount_cents for t in pkg.lines if t.in_window)
    assert pkg.window_total_cents == win
    assert all(isinstance(t.triage, Triage) for t in pkg.lines)


@pytest.mark.parametrize("cents", [c * 137 + (c % 7) for c in range(6000)])
def test_money_round_trip(cents):
    signed = cents if cents % 3 else -cents
    assert parse_cents(format_cents(signed)) == signed


@pytest.mark.parametrize("offset", range(1200))
def test_window_containment_matches_arithmetic(offset):
    d = dt.date(2025, 9, 1) + dt.timedelta(days=offset % 400)
    assert WINDOW.contains(d) == (WINDOW.start <= d <= WINDOW.end)
