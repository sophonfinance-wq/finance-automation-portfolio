import datetime as dt

from ..engine import build_package
from ..generate import generate_report
from ..model import AuditWindow, TriagePolicy
from ..report import package_json, package_markdown


def test_same_seed_same_bytes():
    a = generate_report(123)
    b = generate_report(123)
    assert a.text == b.text
    assert a.expected_job_totals == b.expected_job_totals


def test_different_seeds_differ():
    assert generate_report(1).text != generate_report(2).text


def test_package_json_is_byte_stable(window=None):
    window = AuditWindow(dt.date(2025, 10, 15), dt.date(2026, 6, 1))
    gen = generate_report(55)
    p1 = build_package(gen.text, gen.company, window, TriagePolicy(), gen.coverage)
    p2 = build_package(gen.text, gen.company, window, TriagePolicy(), gen.coverage)
    assert package_json(p1) == package_json(p2)
    assert package_markdown(p1) == package_markdown(p2)


def test_parse_does_not_mutate_input_text():
    gen = generate_report(9)
    before = gen.text
    from ..parse import parse_report
    parse_report(gen.text, gen.company)
    assert gen.text == before
