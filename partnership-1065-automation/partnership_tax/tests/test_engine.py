"""Unit tests for the 1065 workpaper engine."""

from __future__ import annotations

from partnership_tax.engine import build_tax_package
from partnership_tax.generate import generate_source_package
from partnership_tax.report import line_amount


def _package():
    return build_tax_package(generate_source_package())


def test_package_is_ready() -> None:
    package = _package()
    assert package.ready is True
    assert all(check.status == "OK" for check in package.checks)


def test_form_1065_line_22_ties_to_schedule_k_line_1() -> None:
    package = _package()
    assert line_amount(package, "Form 1065", "22") == line_amount(package, "Schedule K", "1")


def test_k1_allocations_sum_to_schedule_k() -> None:
    package = _package()
    total = sum(alloc.ordinary_income_cents for alloc in package.partner_allocations)
    assert total == line_amount(package, "Schedule K", "1")


def test_schedule_l_balances() -> None:
    package = _package()
    assets = line_amount(package, "Schedule L", "14")
    liabilities = line_amount(package, "Schedule L", "21")
    ending_capital = sum(alloc.ending_capital_cents for alloc in package.partner_allocations)
    assert assets == liabilities + ending_capital


def test_m1_reconciles_book_to_tax_income() -> None:
    source = generate_source_package()
    package = build_tax_package(source)
    expected = package.book_income_cents + sum(adj.amount_cents for adj in source.book_tax_adjustments)
    assert expected == package.ordinary_income_cents


def test_m2_ending_capital_ties_to_partner_rollforward() -> None:
    package = _package()
    assert line_amount(package, "Schedule M-2", "9") == sum(
        alloc.ending_capital_cents for alloc in package.partner_allocations
    )


def test_every_form_line_has_source_support() -> None:
    package = _package()
    assert package.form_lines
    assert all(line.source_ids for line in package.form_lines)


def test_demo_uses_only_placeholder_identifiers() -> None:
    # The public demo must expose only fictional / placeholder identifiers — never a
    # real EIN or engagement code. We assert the placeholders are present and that no
    # EIN-shaped token other than the placeholder appears; we deliberately do NOT embed
    # any real identifier here, since asserting one absent would itself publish it.
    import re

    package = _package()
    assert package.source.ein == "00-0000000"
    assert "Demo" in package.source.partnership_name
    blob = " ".join(
        [package.source.partnership_name, package.source.ein]
        + [alloc.partner_name for alloc in package.partner_allocations]
    )
    eins = set(re.findall(r"\b\d{2}-\d{7}\b", blob))
    assert eins <= {"00-0000000"}
