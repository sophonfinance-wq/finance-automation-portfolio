import datetime as dt

from ..engine import build_package
from ..generate import generate_report
from ..model import AuditWindow, CoverageRecord, CostLine, Triage, TranType
from ..triage import triage_line


def _ap_line(vendor_id="ACME01", vendor_name="ACME CONCRETE CUTTING INC",
             date=dt.date(2026, 1, 15)) -> CostLine:
    return CostLine(job="7100-99", job_name="Fictional Warranty", cost_code="86-104",
                    cost_code_desc="Warranty - Third Party Repairs",
                    tran_type=TranType.AP, acctg_date=date, vendor_id=vendor_id,
                    vendor_name=vendor_name, invoice="INV1", description="X",
                    amount_cents=1000)


def test_window_is_inclusive_both_ends(window):
    assert window.contains(dt.date(2025, 10, 15))
    assert window.contains(dt.date(2026, 6, 1))
    assert not window.contains(dt.date(2025, 10, 14))
    assert not window.contains(dt.date(2026, 6, 2))


def test_journal_entries_never_need_certificates(window, policy):
    jc = CostLine(job="7100-99", job_name="F", cost_code="99-202",
                  cost_code_desc="Admin", tran_type=TranType.JC,
                  acctg_date=dt.date(2026, 1, 1), vendor_id="", vendor_name="",
                  invoice="", description="cc", amount_cents=500)
    assert triage_line(jc, policy, [], window) is Triage.JOURNAL_ENTRY


def test_clearing_account_by_id_and_by_name(window, policy):
    assert triage_line(_ap_line("0000", "summary vendor"), policy, [], window) \
        is Triage.CLEARING_ACCOUNT
    assert triage_line(_ap_line("CLR002", "SUMMARY VENDOR"), policy, [], window) \
        is Triage.CLEARING_ACCOUNT


def test_policy_precedence_wrap_beats_coverage(window, policy):
    cov = [CoverageRecord("FENWICK ELECTRIC LLP", "General",
                          dt.date(2025, 6, 1), dt.date(2027, 6, 1),
                          100_000_000, True)]
    line = _ap_line("FEN006", "FENWICK ELECTRIC LLP")
    assert triage_line(line, policy, cov, window) is Triage.OCIP_ENROLLED


def test_materials_and_professional_exemptions(window, policy):
    assert triage_line(_ap_line("DOV004", "DOVETAIL PAINT SUPPLY CO"),
                       policy, [], window) is Triage.MATERIALS_ONLY
    assert triage_line(_ap_line("ELM005", "ELMGATE LAW GROUP PLLC"),
                       policy, [], window) is Triage.PROFESSIONAL


def test_expired_coverage_means_chase(window, policy):
    cov = [CoverageRecord("ACME CONCRETE CUTTING INC", "General",
                          dt.date(2024, 6, 1), dt.date(2025, 6, 1),
                          100_000_000, True)]
    assert triage_line(_ap_line(), policy, cov, window) is Triage.CHASE


def test_current_coverage_is_on_file(window, policy):
    cov = [CoverageRecord("ACME CONCRETE CUTTING INC", "General",
                          dt.date(2025, 7, 1), dt.date(2026, 7, 1),
                          100_000_000, True)]
    assert triage_line(_ap_line(), policy, cov, window) is Triage.COVERED_CURRENT


def test_unreceived_certificate_does_not_count(window, policy):
    cov = [CoverageRecord("ACME CONCRETE CUTTING INC", "General",
                          dt.date(2025, 7, 1), dt.date(2026, 7, 1),
                          100_000_000, False)]
    assert triage_line(_ap_line(), policy, cov, window) is Triage.CHASE


def test_package_partitions_every_line_exactly_once(window, policy):
    gen = generate_report(7)
    pkg = build_package(gen.text, gen.company, window, policy, gen.coverage)
    assert len(pkg.lines) == gen.line_count
    assert pkg.full_total_cents == sum(gen.expected_job_totals.values())
    assert pkg.window_total_cents == sum(
        t.line.amount_cents for t in pkg.lines if t.in_window)
    assert all(t.triage in Triage for t in pkg.lines)
