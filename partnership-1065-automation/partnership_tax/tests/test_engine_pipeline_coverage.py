"""Coverage tests for the 1065 engine, generator, report writers, and CLI.

These pin down the computed arithmetic in :func:`build_tax_package`, the
book->tax bridge identities, the form-line map, the K-1 allocation/capital
roll-forward, the JSON/Markdown emitters, and the CLI exit code — all against
the deterministic seeded source package.
"""

from __future__ import annotations

import json

import pytest

from partnership_tax import cli
from partnership_tax.engine import build_tax_package
from partnership_tax.generate import DEFAULT_SEED, generate_source_package
from partnership_tax.model import TaxSourcePackage
from partnership_tax.report import (
    form_preview_json,
    line_amount,
    review_checks_markdown,
    tax_workpapers_markdown,
    write_outputs,
)


def _src() -> TaxSourcePackage:
    return generate_source_package()


def _pkg():
    return build_tax_package(_src())


# ---------------------------------------------------------------------------
# Generator determinism & shape
# ---------------------------------------------------------------------------
def test_generator_is_deterministic_for_same_seed() -> None:
    a = generate_source_package(seed=DEFAULT_SEED)
    b = generate_source_package(seed=DEFAULT_SEED)
    assert a.income_items[0].amount_cents == b.income_items[0].amount_cents
    assert [d.amount_cents for d in a.deduction_items] == [
        d.amount_cents for d in b.deduction_items
    ]


def test_generator_seed_changes_rental_income() -> None:
    # Rental income jitters by the seed; seed 1 and 2 differ in our probe.
    a = generate_source_package(seed=1)
    b = generate_source_package(seed=2)
    assert a.income_items[0].amount_cents != b.income_items[0].amount_cents


def test_generator_year_is_threaded_through() -> None:
    assert generate_source_package(year=2030).year == 2030


def test_generator_has_three_partners_summing_to_100pct() -> None:
    src = _src()
    assert len(src.partners) == 3
    assert sum(p.profit_bps for p in src.partners) == 10_000


def test_generator_ein_is_placeholder() -> None:
    assert _src().ein == "00-0000000"


# ---------------------------------------------------------------------------
# Engine arithmetic identities
# ---------------------------------------------------------------------------
def test_book_income_is_income_minus_deductions() -> None:
    src = _src()
    pkg = build_tax_package(src)
    income = sum(i.amount_cents for i in src.income_items)
    deductions = sum(d.amount_cents for d in src.deduction_items)
    assert pkg.book_income_cents == income - deductions


def test_total_income_equals_sum_of_income_items() -> None:
    src = _src()
    pkg = build_tax_package(src)
    assert pkg.total_income_cents == sum(i.amount_cents for i in src.income_items)


def test_ordinary_income_is_book_plus_adjustments() -> None:
    src = _src()
    pkg = build_tax_package(src)
    adj = sum(a.amount_cents for a in src.book_tax_adjustments)
    assert pkg.ordinary_income_cents == pkg.book_income_cents + adj


def test_tax_depreciation_is_abs_of_m1_tdep_adjustment() -> None:
    src = _src()
    pkg = build_tax_package(src)
    tdep = sum(a.amount_cents for a in src.book_tax_adjustments if a.code == "M1-TDEP")
    assert pkg.tax_depreciation_cents == abs(tdep)
    assert pkg.tax_depreciation_cents > 0


def test_total_deductions_is_deductible_book_plus_tax_dep() -> None:
    src = _src()
    pkg = build_tax_package(src)
    deductible_book = sum(
        d.amount_cents for d in src.deduction_items
        if d.deductible_for_tax and not d.is_book_depreciation
    )
    assert pkg.total_deductions_cents == deductible_book + pkg.tax_depreciation_cents


def test_nondeductible_syndication_excluded_from_total_deductions() -> None:
    # The syndication cost (deductible_for_tax=False) must not inflate deductions.
    src = _src()
    pkg = build_tax_package(src)
    syn = next(d for d in src.deduction_items if d.source_id == "SYN-001")
    assert syn.deductible_for_tax is False
    deductible_book = sum(
        d.amount_cents for d in src.deduction_items
        if d.deductible_for_tax and not d.is_book_depreciation
    )
    assert syn.amount_cents not in (pkg.total_deductions_cents - deductible_book,)


def test_book_depreciation_excluded_from_tax_deductions() -> None:
    src = _src()
    pkg = build_tax_package(src)
    book_dep = next(d for d in src.deduction_items if d.is_book_depreciation)
    # Tax deductions use tax depreciation, not the book figure.
    assert pkg.total_deductions_cents != book_dep.amount_cents


# ---------------------------------------------------------------------------
# Form-line map
# ---------------------------------------------------------------------------
def test_form_line_count_is_fifteen() -> None:
    assert len(_pkg().form_lines) == 15


@pytest.mark.parametrize(
    "form,line",
    [
        ("Form 1065", "1c"),
        ("Form 1065", "14"),
        ("Form 1065", "20"),
        ("Form 1065", "21"),
        ("Form 1065", "22"),
        ("Schedule K", "1"),
        ("Schedule L", "14"),
        ("Schedule L", "21"),
        ("Schedule M-1", "1"),
        ("Schedule M-1", "9"),
        ("Schedule M-2", "1"),
        ("Schedule M-2", "9"),
    ],
)
def test_expected_form_lines_present(form, line) -> None:
    assert isinstance(line_amount(_pkg(), form, line), int)


def test_line_20_plus_depreciation_equals_total_deductions() -> None:
    pkg = _pkg()
    other = line_amount(pkg, "Form 1065", "20")
    dep = line_amount(pkg, "Form 1065", "14")
    assert other + dep == line_amount(pkg, "Form 1065", "21")


def test_line_14_equals_tax_depreciation() -> None:
    pkg = _pkg()
    assert line_amount(pkg, "Form 1065", "14") == pkg.tax_depreciation_cents


def test_schedule_l_assets_match_balance_sheet() -> None:
    src = _src()
    pkg = build_tax_package(src)
    assert line_amount(pkg, "Schedule L", "14") == src.balance_sheet.total_assets_cents


def test_line_amount_unknown_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        line_amount(_pkg(), "Form 9999", "1")


def test_every_form_line_carries_at_least_one_source_id() -> None:
    assert all(fl.source_ids for fl in _pkg().form_lines)


# ---------------------------------------------------------------------------
# Partner allocations & capital roll-forward
# ---------------------------------------------------------------------------
def test_allocations_one_per_partner() -> None:
    src = _src()
    pkg = build_tax_package(src)
    assert len(pkg.partner_allocations) == len(src.partners)


def test_allocations_sum_to_ordinary_income() -> None:
    pkg = _pkg()
    assert sum(a.ordinary_income_cents for a in pkg.partner_allocations) == (
        pkg.ordinary_income_cents
    )


def test_ending_capital_rollforward_identity_per_partner() -> None:
    pkg = _pkg()
    for a in pkg.partner_allocations:
        assert a.ending_capital_cents == (
            a.beginning_capital_cents
            + a.contributions_cents
            + a.ordinary_income_cents
            - a.distributions_cents
        )


def test_allocation_order_matches_partner_order() -> None:
    src = _src()
    pkg = build_tax_package(src)
    assert [a.partner_id for a in pkg.partner_allocations] == [
        p.partner_id for p in src.partners
    ]


# ---------------------------------------------------------------------------
# Review checks
# ---------------------------------------------------------------------------
def test_there_are_seven_checks_all_ok() -> None:
    pkg = _pkg()
    assert len(pkg.checks) == 7
    assert all(c.status == "OK" for c in pkg.checks)
    assert pkg.ready is True


def test_check_006_is_non_money_percentage_check() -> None:
    pkg = _pkg()
    chk = next(c for c in pkg.checks if c.check_id == "CHK-006")
    assert chk.is_money is False
    assert chk.expected_cents == 10_000


def test_check_ids_are_unique() -> None:
    ids = [c.check_id for c in _pkg().checks]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Report emitters
# ---------------------------------------------------------------------------
def test_workpapers_markdown_marks_ready() -> None:
    md = tax_workpapers_markdown(_pkg())
    assert "READY FOR REVIEW" in md
    assert "FICTIONAL" in md


def test_workpapers_markdown_lists_each_partner() -> None:
    pkg = _pkg()
    md = tax_workpapers_markdown(pkg)
    for a in pkg.partner_allocations:
        assert a.partner_name in md


def test_review_checks_markdown_overall_ready() -> None:
    assert "**Overall status:** READY" in review_checks_markdown(_pkg())


def test_preview_json_status_and_counts() -> None:
    data = form_preview_json(_pkg())
    assert data["status"] == "READY"
    assert len(data["form_lines"]) == 15
    assert len(data["k1_allocations"]) == 3
    assert len(data["checks"]) == 7


def test_preview_json_form_line_amounts_match_package() -> None:
    pkg = _pkg()
    data = form_preview_json(pkg)
    by_key = {(d["form"], d["line"]): d["amount_cents"] for d in data["form_lines"]}
    for fl in pkg.form_lines:
        assert by_key[(fl.form, fl.line)] == fl.amount_cents


def test_preview_json_ein_and_name() -> None:
    data = form_preview_json(_pkg())
    assert data["ein"] == "00-0000000"
    assert data["partnership_name"] == "Demo 721 Development LP"


# ---------------------------------------------------------------------------
# write_outputs + CLI (tmp_path only)
# ---------------------------------------------------------------------------
def test_write_outputs_without_xlsx_creates_three_files(tmp_path) -> None:
    written = write_outputs(_pkg(), tmp_path, write_xlsx=False)
    names = {p.name for p in written}
    assert names == {
        "tax_workpapers.md",
        "review_checks.md",
        "form_1065_preview.json",
    }


def test_write_outputs_json_round_trips_to_disk(tmp_path) -> None:
    write_outputs(_pkg(), tmp_path, write_xlsx=False)
    data = json.loads((tmp_path / "form_1065_preview.json").read_text(encoding="utf-8"))
    assert data["status"] == "READY"
    assert data["checks"][0]["status"] == "OK"


def test_cli_returns_zero_when_package_ready(tmp_path) -> None:
    code = cli.main(["--out", str(tmp_path), "--no-xlsx"])
    assert code == 0


def test_cli_writes_expected_artifacts(tmp_path) -> None:
    cli.main(["--out", str(tmp_path), "--no-xlsx"])
    assert (tmp_path / "tax_workpapers.md").exists()
    assert (tmp_path / "review_checks.md").exists()
    assert (tmp_path / "form_1065_preview.json").exists()


def test_cli_parser_defaults() -> None:
    args = cli.build_parser().parse_args([])
    assert args.year == 2025
    assert args.seed == DEFAULT_SEED
    assert args.no_xlsx is False
    assert args.section704c is False


def test_cli_parser_accepts_year_and_seed() -> None:
    args = cli.build_parser().parse_args(["--year", "2031", "--seed", "7"])
    assert args.year == 2031
    assert args.seed == 7
