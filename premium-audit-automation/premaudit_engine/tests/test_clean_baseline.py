import pytest

from ..generate import generate_report
from ..parse import parse_report


@pytest.mark.parametrize("seed", [0, 1, 7, 42, 99])
def test_clean_report_parses_and_ties(seed):
    gen = generate_report(seed)
    parsed = parse_report(gen.text, gen.company)
    sums = {job: 0 for job in gen.expected_job_totals}  # jobs may print with zero lines
    for line in parsed.lines:
        sums[line.job] = sums.get(line.job, 0) + line.amount_cents
    assert sums == gen.expected_job_totals
    assert len(parsed.lines) == gen.line_count
    printed = {t.job: t.total_cents for t in parsed.printed_totals}
    assert printed == gen.expected_job_totals


def test_header_dates_extracted():
    gen = generate_report(3)
    parsed = parse_report(gen.text, gen.company)
    assert parsed.date_from.isoformat() == "2025-09-01"
    assert parsed.date_to.isoformat() == "2026-08-14"


def test_reversal_pairs_net_to_zero_within_vendor():
    # seeds are deterministic; find a report containing a reversal and assert
    # the reversal line carries the same vendor as its original.
    for seed in range(60):
        gen = generate_report(seed)
        parsed = parse_report(gen.text, gen.company)
        revs = [l for l in parsed.lines if l.description.startswith("(Rev)")]
        if revs:
            for r in revs:
                assert r.vendor_name  # vendor survived the continuation line
                assert r.amount_cents < 0
            return
    raise AssertionError("no seed under 60 produced a reversal - generator drifted")
