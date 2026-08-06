"""What the builder constructs, and what each control actually means.

Two halves. The first proves the **construction pipeline**: the harvest and its
entity-block scope, the classification, the rolled captions, the frozen layers
and appended rows, the member capital blocks, the earnings-and-profits roll, the
evidence tab, the build register and the manifest digests -- asserted against
hand-derived figures rather than against the builder's own output.

The second proves the **controls**, one at a time, by taking a cleanly built file
and breaking exactly one thing in it. A control that only ever runs over a clean
corpus and a single planted defect has been demonstrated once; these cases show
what it accepts as well as what it rejects, and where its boundary sits.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from workpaper_engine.build import (
    advance_year_text,
    build_package,
    capture_prebuild_image,
    classification_map,
    digest_payload,
    ep_accumulated,
    equity_presented,
    flatten_cells,
    flow_amount,
    member_closing,
    net_income,
    prebuild_digest_payload,
    prior_balances,
    register_cell_ids,
    rendered_strings,
    retained_earnings_beginning,
    row_form,
    source_by_account,
    source_rows,
    tax_basis,
    total_liabilities,
    year_tokens,
)
from workpaper_engine.engine import REGISTRY, analyze_document
from workpaper_engine.generate import (
    CURRENT_BALANCES,
    ENTITY_BLOCK,
    FISCAL_YEAR,
    MEMBER_CALDERWOOD,
    MEMBER_WESTMERE,
    OUT_OF_SCOPE_BLOCK,
    PORTFOLIOS,
    PRIOR_BALANCES,
    PRIOR_FISCAL_YEAR,
    PRIOR_NET_INCOME_CENTS,
    baseline,
    prior_package,
)
from workpaper_engine.model import (
    DOC_ALLOCATION_REGISTER,
    DOC_BUILD_REGISTER,
    DOC_BUILT_PACKAGE,
    DOC_COUNTERPART_STUB,
    DOC_EXCEPTION_REGISTER,
    DOC_LOCKED_SOURCE,
    DOC_MANIFEST,
    DOC_PREBUILD_IMAGE,
    DOC_PRIOR_PACKAGE,
    FORM_CUMULATIVE_RESIDUAL,
    FORM_YEAR_DELTA,
    SECTION_EQUITY,
    SECTION_PROFIT_LOSS,
    DocumentReport,
    Status,
)

# The figures the corpus is built to produce, derived by hand from the seeded
# balances and asserted against the pipeline rather than read back out of it.
NET_INCOME_CENTS = 52_488_889
TAXABLE_CENTS = 48_288_889
PRIOR_EQUITY_TOTAL_CENTS = 493_500_000
EQUITY_TOTAL_CENTS = 645_288_889
LIABILITIES_CENTS = 262_200_000
INCOME_SHARES = {MEMBER_CALDERWOOD: 18_371_111, MEMBER_WESTMERE: 34_117_778}
TAXABLE_SHARES = {MEMBER_CALDERWOOD: 16_901_111, MEMBER_WESTMERE: 31_387_778}
LIABILITY_SHARES = {MEMBER_CALDERWOOD: 91_770_000, MEMBER_WESTMERE: 170_430_000}
CLOSING_BOOK = {MEMBER_CALDERWOOD: 222_596_111, MEMBER_WESTMERE: 422_692_778}
CLOSING_TAX = {MEMBER_CALDERWOOD: 211_901_111, MEMBER_WESTMERE: 403_687_778}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _run(tmp_path: Path, payload: dict[str, Any]) -> DocumentReport:
    """Write a build file and run the whole registry over it."""
    path = tmp_path / "case.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return analyze_document(path)


def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any]:
    return next(d for d in payload["documents"] if d.get("doc_type") == doc_type)


def _pkg(payload: dict[str, Any]) -> dict[str, Any]:
    return _doc(payload, DOC_BUILT_PACKAGE)


def _row(rows: list[dict[str, Any]], key: str, value: str) -> dict[str, Any]:
    return next(r for r in rows if r.get(key) == value)


@pytest.fixture
def payload() -> dict[str, Any]:
    """A fresh, cleanly built file the test is free to break."""
    return baseline(PORTFOLIOS[0])


# =========================================================================== #
# PART ONE -- the construction pipeline
# =========================================================================== #

# --------------------------------------------------------------------------- #
# Harvest and scope
# --------------------------------------------------------------------------- #
def test_harvest_is_scoped_to_the_entity_block(inputs: dict[str, Any]) -> None:
    """Only rows carrying the scoped block are harvested."""
    rows = source_rows(inputs["sources"], ENTITY_BLOCK)
    assert rows
    assert {r["entity_block"] for r in rows} == {ENTITY_BLOCK}


def test_the_extract_really_does_carry_a_second_block(inputs: dict[str, Any]) -> None:
    """Scoping is only a control because the neighbour is genuinely in the file."""
    blocks = {r["entity_block"] for r in inputs["sources"]["rows"]}
    assert blocks == {ENTITY_BLOCK, OUT_OF_SCOPE_BLOCK}


def test_harvest_is_in_account_order(inputs: dict[str, Any]) -> None:
    rows = source_rows(inputs["sources"], ENTITY_BLOCK)
    assert [r["account"] for r in rows] == sorted(r["account"] for r in rows)


def test_harvest_of_an_unknown_block_is_empty(inputs: dict[str, Any]) -> None:
    assert source_rows(inputs["sources"], "NOT-A-BLOCK") == []


def test_source_by_account_is_keyed_exactly(inputs: dict[str, Any]) -> None:
    by_account = source_by_account(inputs["sources"], ENTITY_BLOCK)
    assert set(by_account) == set(CURRENT_BALANCES)
    for account, balance in CURRENT_BALANCES.items():
        assert by_account[account]["balance_cents"] == balance


# --------------------------------------------------------------------------- #
# Trial balance and classification
# --------------------------------------------------------------------------- #
def test_trial_balance_carries_every_funded_account(built) -> None:
    accounts = {r["account"] for r in built.trial_balance["rows"]}
    assert accounts == {a for a, v in CURRENT_BALANCES.items() if v != 0}


def test_trial_balance_leaves_flat_accounts_off(built) -> None:
    """An account with no balance carries no figure onto the workpaper."""
    accounts = {r["account"] for r in built.trial_balance["rows"]}
    assert "1600" not in accounts
    assert CURRENT_BALANCES["1600"] == 0


def test_flat_accounts_still_appear_on_the_evidence_tab(built) -> None:
    """Which is what makes completeness provable rather than assumed."""
    accounts = {r["account"] for r in built.evidence["rows"]}
    assert "1600" in accounts


@pytest.mark.parametrize("account", sorted(a for a, v in CURRENT_BALANCES.items() if v))
def test_every_trial_balance_row_holds_the_source_balance(built, account: str) -> None:
    row = _row(built.trial_balance["rows"], "account", account)
    assert row["balance_cents"] == CURRENT_BALANCES[account]


def test_trial_balance_foots_to_zero(built) -> None:
    assert sum(r["balance_cents"] for r in built.trial_balance["rows"]) == 0


def test_classification_comes_from_the_prior_year_map(built, inputs) -> None:
    """A new year does not get to invent where an account belongs."""
    chart = classification_map(inputs["prior_year"])
    for row in built.trial_balance["rows"]:
        assert row["section"] == chart[row["account"]]["section"]


def test_balance_sheet_foots_to_zero(built) -> None:
    assert built.balance_sheet["total_cents"] == 0


def test_profit_loss_reports_the_result(built) -> None:
    assert built.profit_loss["net_income_cents"] == NET_INCOME_CENTS


def test_profit_loss_carries_only_operations_rows(built, inputs) -> None:
    chart = classification_map(inputs["prior_year"])
    for row in built.profit_loss["rows"]:
        assert chart[row["row_id"]]["section"] == SECTION_PROFIT_LOSS


def test_balance_sheet_total_equity_is_the_equity_section(built) -> None:
    assert built.balance_sheet["total_equity_cents"] == EQUITY_TOTAL_CENTS


def test_balance_sheet_carries_a_result_row(built) -> None:
    """The year's result is equity on a balance sheet even before it is closed."""
    row = _row(built.balance_sheet["rows"], "row_id", "NET_INCOME")
    assert row["amount_cents"] == -NET_INCOME_CENTS
    assert row["section"] == SECTION_EQUITY


# --------------------------------------------------------------------------- #
# Captions
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "caption_id,expected",
    [
        ("package_title", "Tax workpaper package - fiscal year ended June 30, 2029"),
        ("trial_balance_title", "Trial balance - fiscal year ended June 30, 2029"),
        ("balance_sheet_title", "Balance sheet - June 30, 2029"),
        (
            "profit_loss_title",
            "Statement of operations - fiscal year ended June 30, 2029",
        ),
        (
            "equity_title",
            "Statement of members' equity - fiscal year ended June 30, 2029",
        ),
        ("equity_closing", "Balance at June 30, 2029"),
        ("member_block_current", "Fiscal year ended June 30, 2029"),
        (
            "ep_block_current",
            "Accumulated earnings and profits at June 30, 2029",
        ),
        (
            "evidence_title",
            "Support - general ledger harvest - fiscal year ended June 30, 2029",
        ),
    ],
)
def test_rolled_caption_reads_exactly(built, caption_id: str, expected: str) -> None:
    assert built.captions[caption_id] == expected


def test_no_rolled_caption_still_names_the_prior_year(built) -> None:
    for text in built.captions.values():
        assert str(PRIOR_FISCAL_YEAR) not in text


@pytest.mark.parametrize(
    "text,step,expected",
    [
        ("Balance at June 30, 2028", 1, "Balance at June 30, 2029"),
        ("fiscal 2028 and 2027", 1, "fiscal 2029 and 2028"),
        ("no year here", 1, "no year here"),
        ("June 30, 2028", 2, "June 30, 2030"),
        ("Account 20281 stays", 1, "Account 20281 stays"),
    ],
)
def test_advance_year_text(text: str, step: int, expected: str) -> None:
    """Only whole four-digit years move; an account number that looks like one does not."""
    assert advance_year_text(text, step) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Balance at June 30, 2029", [2029]),
        ("fiscal 2028 and 2029", [2028, 2029]),
        ("nothing", []),
        ("1899 and 2100 are out of range", []),
    ],
)
def test_year_tokens(text: str, expected: list[int]) -> None:
    assert year_tokens(text) == expected


# --------------------------------------------------------------------------- #
# Equity schedule
# --------------------------------------------------------------------------- #
def test_frozen_layers_are_carried_verbatim(built, inputs) -> None:
    prior_rows = inputs["prior_year"]["equity"]["rows"]
    assert built.equity["rows"][: len(prior_rows)] == prior_rows


def test_appended_rows_all_carry_the_year_being_built(built) -> None:
    prior_count = len(prior_package()["equity"]["rows"])
    for row in built.equity["rows"][prior_count:]:
        assert row["year"] == FISCAL_YEAR


@pytest.mark.parametrize(
    "account,expected",
    [
        ("3000", 40_000_000),
        ("3010", 60_000_000),
        ("3020", 25_000_000),
        ("3100", -9_000_000),
        ("3110", -16_700_000),
    ],
)
def test_current_year_flow_is_the_movement(built, account: str, expected: int) -> None:
    row = _row(built.equity["rows"], "row_id", f"EQ-{FISCAL_YEAR}-{account}")
    assert row["amount_cents"] == expected


def test_retained_earnings_never_gets_a_flow_row(built) -> None:
    """Its movement is last year's result, not this year's capital activity."""
    ids = {r["row_id"] for r in built.equity["rows"]}
    assert f"EQ-{FISCAL_YEAR}-3900" not in ids


@pytest.mark.parametrize(
    "member,expected", sorted(INCOME_SHARES.items())
)
def test_income_row_is_the_allocated_result(built, member: str, expected: int) -> None:
    row = _row(built.equity["rows"], "row_id", f"EQ-{FISCAL_YEAR}-INC-{member}")
    assert row["amount_cents"] == expected


def test_income_rows_sum_back_to_the_result(built) -> None:
    rows = [r for r in built.equity["rows"] if r.get("role") == "income"
            and r.get("year") == FISCAL_YEAR]
    assert sum(r["amount_cents"] for r in rows) == NET_INCOME_CENTS


def test_equity_closes_at_the_derived_total(built) -> None:
    assert built.equity["total_cents"] == EQUITY_TOTAL_CENTS
    closing = _row(built.equity["rows"], "row_id", f"EQ-{FISCAL_YEAR}-BAL")
    assert closing["amount_cents"] == EQUITY_TOTAL_CENTS


def test_equity_total_is_prior_plus_flows_plus_result(built) -> None:
    flows = 40_000_000 + 60_000_000 + 25_000_000 - 9_000_000 - 16_700_000
    assert (
        PRIOR_EQUITY_TOTAL_CENTS + flows + NET_INCOME_CENTS == EQUITY_TOTAL_CENTS
    )
    assert built.equity["prior_total_cents"] == PRIOR_EQUITY_TOTAL_CENTS


@pytest.mark.parametrize(
    "account,expected",
    [
        ("3000", FORM_YEAR_DELTA),
        ("3010", FORM_YEAR_DELTA),
        ("3020", FORM_CUMULATIVE_RESIDUAL),
        ("3100", FORM_YEAR_DELTA),
        ("3110", FORM_YEAR_DELTA),
    ],
)
def test_row_form_follows_the_prior_balance(built, account: str, expected: str) -> None:
    row = _row(built.equity["rows"], "row_id", f"EQ-{FISCAL_YEAR}-{account}")
    assert row["row_form"] == expected


def test_the_cumulative_residual_row_is_the_unfunded_account(built) -> None:
    """3020 was flat last year, so its balance and its movement are one figure."""
    assert "3020" not in PRIOR_BALANCES
    assert CURRENT_BALANCES["3020"] != 0


# --------------------------------------------------------------------------- #
# Member capital
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("member", sorted(CLOSING_BOOK))
def test_new_block_opens_where_the_prior_block_closed(built, member: str) -> None:
    prior = _row(
        prior_package()["member_capital"]["blocks"], "member_id", member
    )
    block = _row(
        built.member_capital["blocks"], "block_id", f"MC-{FISCAL_YEAR}-{member}"
    )
    assert block["opening_book_cents"] == prior["closing_book_cents"]
    assert block["opening_tax_cents"] == prior["closing_tax_cents"]


@pytest.mark.parametrize("member,expected", sorted(CLOSING_BOOK.items()))
def test_new_block_closes_at_the_derived_book_capital(
    built, member: str, expected: int
) -> None:
    block = _row(
        built.member_capital["blocks"], "block_id", f"MC-{FISCAL_YEAR}-{member}"
    )
    assert block["closing_book_cents"] == expected


@pytest.mark.parametrize("member,expected", sorted(CLOSING_TAX.items()))
def test_new_block_closes_at_the_derived_tax_capital(
    built, member: str, expected: int
) -> None:
    block = _row(
        built.member_capital["blocks"], "block_id", f"MC-{FISCAL_YEAR}-{member}"
    )
    assert block["closing_tax_cents"] == expected


@pytest.mark.parametrize("member,expected", sorted(LIABILITY_SHARES.items()))
def test_liability_share_is_allocated_on_the_carried_split(
    built, member: str, expected: int
) -> None:
    block = _row(
        built.member_capital["blocks"], "block_id", f"MC-{FISCAL_YEAR}-{member}"
    )
    assert block["liability_share_cents"] == expected


@pytest.mark.parametrize("member", sorted(CLOSING_TAX))
def test_tax_basis_is_capital_plus_liability_share(built, member: str) -> None:
    block = _row(
        built.member_capital["blocks"], "block_id", f"MC-{FISCAL_YEAR}-{member}"
    )
    assert block["tax_basis_cents"] == (
        CLOSING_TAX[member] + LIABILITY_SHARES[member]
    )


def test_member_closings_sum_to_the_equity_schedule(built) -> None:
    blocks = [
        b for b in built.member_capital["blocks"] if b["year"] == FISCAL_YEAR
    ]
    assert sum(b["closing_book_cents"] for b in blocks) == EQUITY_TOTAL_CENTS


def test_liability_shares_sum_to_the_liabilities(built) -> None:
    blocks = [
        b for b in built.member_capital["blocks"] if b["year"] == FISCAL_YEAR
    ]
    assert sum(b["liability_share_cents"] for b in blocks) == LIABILITIES_CENTS


def test_westmere_contributions_gather_both_of_its_accounts(built) -> None:
    """A member funded through two equity accounts is credited with both."""
    block = _row(
        built.member_capital["blocks"], "block_id", f"MC-{FISCAL_YEAR}-{MEMBER_WESTMERE}"
    )
    assert block["contributions_book_cents"] == 60_000_000 + 25_000_000


def test_member_block_caption_names_the_member(built) -> None:
    """Two members sharing one caption is how a dropped label hides."""
    captions = {
        b["caption"] for b in built.member_capital["blocks"]
        if b["year"] == FISCAL_YEAR
    }
    assert len(captions) == 2


# --------------------------------------------------------------------------- #
# Earnings and profits
# --------------------------------------------------------------------------- #
def test_ep_block_opens_at_the_prior_accumulated(built) -> None:
    block = built.earnings_and_profits["blocks"][-1]
    assert block["prior_accumulated_cents"] == 61_000_000


def test_ep_block_carries_the_taxable_result(built) -> None:
    block = built.earnings_and_profits["blocks"][-1]
    assert block["current_taxable_cents"] == TAXABLE_CENTS


def test_ep_block_accumulates(built) -> None:
    block = built.earnings_and_profits["blocks"][-1]
    assert block["accumulated_end_cents"] == 61_000_000 + TAXABLE_CENTS


def test_prior_ep_blocks_are_carried_untouched(built) -> None:
    prior = prior_package()["earnings_and_profits"]["blocks"]
    assert built.earnings_and_profits["blocks"][: len(prior)] == prior


# --------------------------------------------------------------------------- #
# Evidence
# --------------------------------------------------------------------------- #
def test_evidence_carries_every_harvested_row(built) -> None:
    assert {r["account"] for r in built.evidence["rows"]} == set(CURRENT_BALANCES)


def test_evidence_subtotal_foots_to_zero(built) -> None:
    assert built.evidence["subtotal_cents"] == 0
    assert sum(r["balance_cents"] for r in built.evidence["rows"]) == 0


@pytest.mark.parametrize(
    "field,expected",
    [
        ("source_file", "gl_extract_fy2029.xlsx"),
        ("tab", "TB by entity block"),
        ("balance_column", "Ending balance"),
        ("harvest_date", "2029-08-03"),
    ],
)
def test_citation_names_the_source(built, field: str, expected: str) -> None:
    assert built.evidence["citation"][field] == expected


def test_citation_carries_no_path(built) -> None:
    """A delivered workpaper cites a file, not somebody's drive."""
    assert "\\" not in built.evidence["citation"]["source_file"]
    assert "/" not in built.evidence["citation"]["source_file"]


# --------------------------------------------------------------------------- #
# Register, manifest and cells
# --------------------------------------------------------------------------- #
def test_every_register_entry_carries_a_derivation(built) -> None:
    for entry in built.build_register:
        assert entry.derivation.strip()
        assert len(entry.derivation) > 10


def test_register_cell_ids_are_unique(built) -> None:
    ids = [e.cell_id for e in built.build_register]
    assert len(ids) == len(set(ids))


def test_register_covers_every_cell_the_build_changed(built, inputs) -> None:
    """The register is complete by construction, which control 19 then polices."""
    pre = inputs["registers"]["prebuild_image"]["cells"]
    cells = built.cells()
    touched = {k for k in cells if k not in pre or cells[k] != pre[k]}
    assert touched <= {e.cell_id for e in built.build_register}


def test_register_names_no_cell_the_package_does_not_hold(built) -> None:
    cells = built.cells()
    unknown = [
        e.cell_id for e in built.build_register if e.cell_id not in cells
    ]
    assert not unknown, unknown


def test_frozen_regions_are_absent_from_the_register(built) -> None:
    """A frozen layer is not constructed, so it must not appear as constructed."""
    ids = {e.cell_id for e in built.build_register}
    for row in prior_package()["equity"]["rows"]:
        assert f"equity/{row['row_id']}/amount_cents" not in ids
    for note in prior_package()["notes"]["rows"]:
        assert f"notes/{note['note_id']}/text" not in ids


def test_manifest_digests_are_distinct_and_well_formed(built) -> None:
    manifest = built.manifest_doc()
    digests = {
        manifest["locked_source_digest"],
        manifest["prebuild_image_digest"],
        manifest["built_package_digest"],
    }
    assert len(digests) == 3
    for value in digests:
        assert len(value) == 64
        assert set(value) <= set("0123456789abcdef")


def test_manifest_source_digest_covers_the_extract(built, inputs) -> None:
    assert built.manifest_doc()["locked_source_digest"] == digest_payload(
        inputs["sources"]
    )


def test_manifest_prebuild_digest_covers_the_image(built, inputs) -> None:
    assert built.manifest_doc()["prebuild_image_digest"] == digest_payload(
        prebuild_digest_payload(inputs["registers"]["prebuild_image"])
    )


def test_prebuild_image_holds_the_prior_year_values(inputs) -> None:
    cells = inputs["registers"]["prebuild_image"]["cells"]
    assert cells["equity/TOTAL/amount_cents"] == PRIOR_EQUITY_TOTAL_CENTS
    assert cells["trial_balance/1000/balance_cents"] == PRIOR_BALANCES["1000"]


def test_flatten_is_keyed_by_row_identity_not_position(built) -> None:
    """Which is why a re-sorted schedule reads as zero edits and not a thousand."""
    before = flatten_cells(built.package_doc())
    doc = built.package_doc()
    doc["equity"]["rows"] = list(reversed(doc["equity"]["rows"]))
    assert flatten_cells(doc) == before


def test_flatten_of_nothing_is_empty() -> None:
    assert flatten_cells(None) == {}
    assert flatten_cells({}) == {}


def test_rendered_strings_walks_the_whole_package(built) -> None:
    texts = [t for _p, t in rendered_strings(built.package_doc())]
    assert built.captions["package_title"] in texts
    assert any("Suspense" in t for t in texts)


def test_rendered_package_is_clean(built) -> None:
    for _path, text in rendered_strings(built.package_doc()):
        assert "#REF!" not in text
        assert "http" not in text
        assert "C:\\" not in text


# --------------------------------------------------------------------------- #
# The shared kernel
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "current,prior,expected",
    [
        (-215_000_000, -175_000_000, 40_000_000),
        (-25_000_000, 0, 25_000_000),
        (30_000_000, 21_000_000, -9_000_000),
        (0, 0, 0),
        (-100, -100, 0),
    ],
)
def test_flow_amount(current: int, prior: int, expected: int) -> None:
    assert flow_amount(current, prior) == expected


@pytest.mark.parametrize("balance,expected", [(-100, 100), (100, -100), (0, 0)])
def test_equity_presented(balance: int, expected: int) -> None:
    assert equity_presented(balance) == expected


@pytest.mark.parametrize(
    "prior,expected",
    [(0, FORM_CUMULATIVE_RESIDUAL), (-1, FORM_YEAR_DELTA), (1, FORM_YEAR_DELTA)],
)
def test_row_form(prior: int, expected: str) -> None:
    assert row_form(prior) == expected


def test_net_income_flips_the_operations_section(inputs) -> None:
    chart = classification_map(inputs["prior_year"])
    assert net_income(CURRENT_BALANCES, chart) == NET_INCOME_CENTS


def test_prior_net_income_is_what_the_prior_package_reported(inputs) -> None:
    chart = classification_map(inputs["prior_year"])
    assert net_income(PRIOR_BALANCES, chart) == PRIOR_NET_INCOME_CENTS


def test_total_liabilities_presents_positive(inputs) -> None:
    chart = classification_map(inputs["prior_year"])
    assert total_liabilities(CURRENT_BALANCES, chart) == LIABILITIES_CENTS


@pytest.mark.parametrize(
    "opening,contrib,income,distrib,expected",
    [
        (100, 10, 5, 3, 112),
        (0, 0, 0, 0, 0),
        (100, 0, -20, 0, 80),
        (0, 0, 0, 50, -50),
    ],
)
def test_member_closing(
    opening: int, contrib: int, income: int, distrib: int, expected: int
) -> None:
    assert member_closing(opening, contrib, income, distrib) == expected


@pytest.mark.parametrize(
    "capital,share,expected", [(100, 50, 150), (0, 0, 0), (-100, 50, -50)]
)
def test_tax_basis(capital: int, share: int, expected: int) -> None:
    assert tax_basis(capital, share) == expected


@pytest.mark.parametrize(
    "prior,taxable,expected", [(61_000_000, 48_288_889, 109_288_889), (0, -5, -5)]
)
def test_ep_accumulated(prior: int, taxable: int, expected: int) -> None:
    assert ep_accumulated(prior, taxable) == expected


def test_retained_earnings_beginning_adds_last_years_result() -> None:
    assert retained_earnings_beginning(30_000_000, 23_500_000) == 53_500_000
    assert equity_presented(CURRENT_BALANCES["3900"]) == 53_500_000


def test_prior_balances_reads_absent_accounts_as_zero(inputs) -> None:
    priors = prior_balances(inputs["prior_year"])
    assert "3020" not in priors
    assert priors.get("3020", 0) == 0


def test_digest_payload_is_order_independent() -> None:
    assert digest_payload({"a": 1, "b": 2}) == digest_payload({"b": 2, "a": 1})


def test_digest_payload_changes_with_content() -> None:
    assert digest_payload({"a": 1}) != digest_payload({"a": 2})


def test_register_cell_ids_of_nothing_is_empty() -> None:
    assert register_cell_ids(None) == set()
    assert register_cell_ids({"entries": []}) == set()


# =========================================================================== #
# PART TWO -- what each control accepts and rejects
# =========================================================================== #
def _fired(report: DocumentReport) -> list[str]:
    return report.rules_fired()


def test_1_a_frozen_amount_that_moves_is_caught(tmp_path, payload) -> None:
    _pkg(payload)["equity"]["rows"][1]["amount_cents"] += 1
    assert "frozen_layers_byte_equal" in _fired(_run(tmp_path, payload))


def test_1_a_dropped_frozen_layer_is_caught(tmp_path, payload) -> None:
    rows = _pkg(payload)["equity"]["rows"]
    _pkg(payload)["equity"]["rows"] = [
        r for r in rows if r["row_id"] != f"EQ-{PRIOR_FISCAL_YEAR}-3010"
    ]
    assert "frozen_layers_byte_equal" in _fired(_run(tmp_path, payload))


def test_2_a_caption_advanced_two_years_is_caught(tmp_path, payload) -> None:
    """The control asserts the step, not merely that the year changed."""
    _pkg(payload)["captions"]["equity_closing"] = "Balance at June 30, 2030"
    assert "captions_advance_one_year" in _fired(_run(tmp_path, payload))


def test_2_a_roll_that_does_not_advance_is_caught(tmp_path, payload) -> None:
    _pkg(payload)["fiscal_year"] = PRIOR_FISCAL_YEAR
    assert "captions_advance_one_year" in _fired(_run(tmp_path, payload))


def test_3_a_balance_where_a_delta_belongs_is_caught(tmp_path, payload) -> None:
    """The defect this control exists for: the row carries the whole account."""
    row = _row(_pkg(payload)["equity"]["rows"], "row_id", f"EQ-{FISCAL_YEAR}-3000")
    row["amount_cents"] = -CURRENT_BALANCES["3000"]
    assert "capital_flow_equals_delta" in _fired(_run(tmp_path, payload))


def test_3_a_missing_flow_row_is_caught(tmp_path, payload) -> None:
    rows = _pkg(payload)["equity"]["rows"]
    _pkg(payload)["equity"]["rows"] = [
        r for r in rows if r["row_id"] != f"EQ-{FISCAL_YEAR}-3110"
    ]
    assert "capital_flow_equals_delta" in _fired(_run(tmp_path, payload))


def test_4_a_short_split_is_caught(tmp_path, payload) -> None:
    _doc(payload, DOC_ALLOCATION_REGISTER)["splits"]["ordinary_income"][
        MEMBER_WESTMERE
    ] = 6400
    assert "split_pairs_sum_to_one" in _fired(_run(tmp_path, payload))


def test_4_an_omitted_member_is_caught(tmp_path, payload) -> None:
    del _doc(payload, DOC_ALLOCATION_REGISTER)["splits"]["liability_share"][
        MEMBER_CALDERWOOD
    ]
    assert "split_pairs_sum_to_one" in _fired(_run(tmp_path, payload))


def test_5_stands_down_when_the_split_is_not_a_pair(tmp_path, payload) -> None:
    """The split control owns that finding; this one refuses to guess a ratio."""
    _doc(payload, DOC_ALLOCATION_REGISTER)["splits"]["ordinary_income"][
        MEMBER_WESTMERE
    ] = 6400
    report = _run(tmp_path, payload)
    assert "income_split_rows_exact" not in _fired(report)
    assert not [f for f in report.findings if f.rule == "income_split_rows_exact"]


def test_5_a_missing_income_row_is_caught(tmp_path, payload) -> None:
    rows = _pkg(payload)["equity"]["rows"]
    _pkg(payload)["equity"]["rows"] = [
        r for r in rows if r["row_id"] != f"EQ-{FISCAL_YEAR}-INC-{MEMBER_WESTMERE}"
    ]
    assert "income_split_rows_exact" in _fired(_run(tmp_path, payload))


def test_5_rounding_the_two_shares_independently_is_caught(tmp_path, payload) -> None:
    """Two independently rounded shares no longer sum to the result."""
    rows = _pkg(payload)["equity"]["rows"]
    _row(rows, "row_id", f"EQ-{FISCAL_YEAR}-INC-{MEMBER_WESTMERE}")[
        "amount_cents"
    ] = 34_117_777
    assert "income_split_rows_exact" in _fired(_run(tmp_path, payload))


def test_6_measures_against_the_inputs_not_the_rows(tmp_path, payload) -> None:
    """Footing the total from the rows would let a wrong row make a right total."""
    pkg = _pkg(payload)
    pkg["equity"]["total_cents"] += 700
    _row(pkg["equity"]["rows"], "row_id", f"EQ-{FISCAL_YEAR}-BAL")[
        "amount_cents"
    ] += 700
    assert "equity_total_rolls" in _fired(_run(tmp_path, payload))


def test_7_a_disclosure_for_a_different_amount_does_not_excuse_it(
    tmp_path, payload
) -> None:
    _row(_pkg(payload)["balance_sheet"]["rows"], "row_id", "3000")[
        "amount_cents"
    ] += 50_000
    _pkg(payload)["balance_sheet"]["total_equity_cents"] -= 50_000
    _doc(payload, DOC_EXCEPTION_REGISTER)["tie_out_disclosures"].append(
        {"schedule": "equity_vs_balance_sheet", "variance_cents": 999, "note": "x"}
    )
    report = _run(tmp_path, payload)
    assert "equity_ties_balance_sheet" in _fired(report)
    statuses = {
        f.status for f in report.findings if f.rule == "equity_ties_balance_sheet"
    }
    assert Status.FAIL in statuses


def test_7_a_stated_total_that_is_not_the_rows_is_caught(tmp_path, payload) -> None:
    _pkg(payload)["balance_sheet"]["total_equity_cents"] += 1
    assert "equity_ties_balance_sheet" in _fired(_run(tmp_path, payload))


def test_8_the_tax_column_is_chained_too(tmp_path, payload) -> None:
    """Book and tax are separate chains; breaking either has to be caught."""
    _row(
        _pkg(payload)["member_capital"]["blocks"],
        "block_id",
        f"MC-{FISCAL_YEAR}-{MEMBER_WESTMERE}",
    )["income_tax_cents"] += 5
    assert "member_capital_chain" in _fired(_run(tmp_path, payload))


def test_8_a_gap_between_two_year_blocks_is_caught(tmp_path, payload) -> None:
    block = _row(
        _pkg(payload)["member_capital"]["blocks"],
        "block_id",
        f"MC-{FISCAL_YEAR}-{MEMBER_CALDERWOOD}",
    )
    block["opening_book_cents"] += 100
    block["closing_book_cents"] += 100
    assert "member_capital_chain" in _fired(_run(tmp_path, payload))


def test_9_a_missing_current_year_block_is_caught(tmp_path, payload) -> None:
    blocks = _pkg(payload)["member_capital"]["blocks"]
    _pkg(payload)["member_capital"]["blocks"] = [
        b for b in blocks if b["year"] != FISCAL_YEAR
    ]
    assert "member_closing_ties_equity" in _fired(_run(tmp_path, payload))


def test_10_a_prior_year_basis_is_checked_as_well(tmp_path, payload) -> None:
    """Every block, not only the one the build just appended."""
    _row(
        _pkg(payload)["member_capital"]["blocks"],
        "block_id",
        f"MC-{PRIOR_FISCAL_YEAR}-{MEMBER_WESTMERE}",
    )["tax_basis_cents"] += 1
    assert "tax_basis_is_capital_plus_liability" in _fired(_run(tmp_path, payload))


def test_11_a_broken_link_between_ep_blocks_is_caught(tmp_path, payload) -> None:
    block = _row(
        _pkg(payload)["earnings_and_profits"]["blocks"], "block_id", f"EP-{FISCAL_YEAR}"
    )
    block["prior_accumulated_cents"] += 1
    block["accumulated_end_cents"] += 1
    assert "ep_chain_rolls" in _fired(_run(tmp_path, payload))


def test_12_a_beginning_balance_that_overshoots_is_caught(tmp_path, payload) -> None:
    _row(_pkg(payload)["trial_balance"]["rows"], "account", "3900")[
        "balance_cents"
    ] -= 100
    assert "retained_earnings_beginning_rolls" in _fired(_run(tmp_path, payload))


def test_13_a_delta_row_mislabelled_cumulative_is_caught(tmp_path, payload) -> None:
    """The control works in both directions, not only for the unfunded account."""
    _row(_pkg(payload)["equity"]["rows"], "row_id", f"EQ-{FISCAL_YEAR}-3000")[
        "row_form"
    ] = FORM_CUMULATIVE_RESIDUAL
    assert "row_form_classified_from_balances" in _fired(_run(tmp_path, payload))


def test_13_a_live_formula_alone_is_not_a_finding(tmp_path, payload) -> None:
    """A formula is not the defect; classifying from it is."""
    _row(_pkg(payload)["equity"]["rows"], "row_id", f"EQ-{FISCAL_YEAR}-3000")[
        "formula_present"
    ] = True
    assert "row_form_classified_from_balances" not in _fired(_run(tmp_path, payload))


def test_14_an_evidence_balance_off_the_source_is_caught(tmp_path, payload) -> None:
    _row(_pkg(payload)["evidence"]["rows"], "account", "1200")["balance_cents"] += 1
    assert "evidence_ties_locked_source" in _fired(_run(tmp_path, payload))


def test_14_a_dropped_evidence_row_is_caught(tmp_path, payload) -> None:
    rows = _pkg(payload)["evidence"]["rows"]
    _pkg(payload)["evidence"]["rows"] = [r for r in rows if r["account"] != "1600"]
    assert "evidence_ties_locked_source" in _fired(_run(tmp_path, payload))


def test_14_an_out_of_scope_row_on_the_evidence_tab_is_caught(
    tmp_path, payload
) -> None:
    """Support harvested from the neighbouring entity ties to nothing here."""
    _pkg(payload)["evidence"]["rows"].append(
        {"account": "8100", "title": "Neighbouring block", "balance_cents": 0,
         "display": "0.00"}
    )
    assert "evidence_ties_locked_source" in _fired(_run(tmp_path, payload))


def test_15_a_subtotal_that_foots_but_is_not_zero_is_caught(
    tmp_path, payload
) -> None:
    """Both halves of the control matter: it foots the rows *and* expects zero."""
    pkg = _pkg(payload)
    pkg["evidence"]["rows"].append(
        {"account": "1000", "title": "duplicate", "balance_cents": 500,
         "display": "5.00"}
    )
    pkg["evidence"]["subtotal_cents"] = 500
    assert "evidence_subtotal_foots" in _fired(_run(tmp_path, payload))


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_file", "gl_extract_fy2028.xlsx"),
        ("tab", "Summary"),
        ("balance_column", "Monthly activity"),
        ("harvest_date", "2029-09-01"),
    ],
)
def test_16_every_citation_field_is_checked(
    tmp_path, payload, field: str, value: str
) -> None:
    _pkg(payload)["evidence"]["citation"][field] = value
    assert "citation_block_correct" in _fired(_run(tmp_path, payload))


def test_17_any_change_to_the_extract_invalidates_the_build(
    tmp_path, payload
) -> None:
    _doc(payload, DOC_LOCKED_SOURCE)["tab"] = "TB by entity block "
    assert "locked_source_digest_matches" in _fired(_run(tmp_path, payload))


def test_18_a_changed_backup_cell_breaks_custody(tmp_path, payload) -> None:
    _doc(payload, DOC_PREBUILD_IMAGE)["cells"]["equity/TOTAL/amount_cents"] = 1
    assert "prebuild_image_digest_matches" in _fired(_run(tmp_path, payload))


def test_19_an_edited_frozen_cell_is_out_of_scope(tmp_path, payload) -> None:
    """The scope control is broader than the frozen-layer control, on purpose."""
    _pkg(payload)["equity"]["rows"][1]["amount_cents"] += 1
    assert "edit_scope_matches_register" in _fired(_run(tmp_path, payload))


def test_19_a_deleted_register_entry_makes_a_cell_undeclared(
    tmp_path, payload
) -> None:
    register = _doc(payload, DOC_BUILD_REGISTER)
    register["entries"] = [
        e for e in register["entries"]
        if e["cell_id"] != "trial_balance/1000/balance_cents"
    ]
    assert "edit_scope_matches_register" in _fired(_run(tmp_path, payload))


def test_20_an_intercompany_row_off_the_balance_sheet_is_caught(
    tmp_path, payload
) -> None:
    _row(_pkg(payload)["balance_sheet"]["rows"], "row_id", "2200")[
        "amount_cents"
    ] += 1
    assert "cross_schedule_reciprocity" in _fired(_run(tmp_path, payload))


def test_20_a_stub_for_the_wrong_account_is_caught(tmp_path, payload) -> None:
    _doc(payload, DOC_COUNTERPART_STUB)["account"] = "1310"
    assert "cross_schedule_reciprocity" in _fired(_run(tmp_path, payload))


def test_21_a_flat_account_may_be_left_off(tmp_path, payload) -> None:
    """The permission the completeness control is built around."""
    assert "source_completeness" not in _fired(_run(tmp_path, payload))
    accounts = {r["account"] for r in _pkg(payload)["trial_balance"]["rows"]}
    assert "1600" not in accounts


def test_21_a_funded_account_may_not(tmp_path, payload) -> None:
    rows = _pkg(payload)["trial_balance"]["rows"]
    _pkg(payload)["trial_balance"]["rows"] = [
        r for r in rows if r["account"] != "1200"
    ]
    assert "source_completeness" in _fired(_run(tmp_path, payload))


def test_22_a_deregistered_mislabel_is_caught(tmp_path, payload) -> None:
    exceptions = _doc(payload, DOC_EXCEPTION_REGISTER)
    exceptions["account_exceptions"] = [
        e for e in exceptions["account_exceptions"] if e["account"] != "2100"
    ]
    assert "exception_register_honored" in _fired(_run(tmp_path, payload))


def test_22_the_wrong_kind_of_registration_does_not_count(tmp_path, payload) -> None:
    for entry in _doc(payload, DOC_EXCEPTION_REGISTER)["account_exceptions"]:
        if entry["account"] == "9990":
            entry["kind"] = "mislabeled"
    assert "exception_register_honored" in _fired(_run(tmp_path, payload))


@pytest.mark.parametrize(
    "text",
    ["#REF!", "#VALUE!", "#DIV/0!", "#N/A", "https://example.invalid/book",
     "C:\\workpapers\\fy2029.xlsx", "[fy2028.xlsx]Equity"],
)
def test_23_every_hygiene_marker_is_caught(tmp_path, payload, text: str) -> None:
    _row(_pkg(payload)["trial_balance"]["rows"], "account", "1000")["display"] = text
    assert "render_hygiene" in _fired(_run(tmp_path, payload))


def test_23_a_plain_filename_in_the_citation_is_not_a_finding(
    tmp_path, payload
) -> None:
    """A citation has to name a file; naming one is not a hygiene failure."""
    assert "render_hygiene" not in _fired(_run(tmp_path, payload))


def test_24_a_lost_equity_layer_caption_is_caught(tmp_path, payload) -> None:
    row = _row(
        _pkg(payload)["equity"]["rows"], "row_id", f"EQ-{PRIOR_FISCAL_YEAR - 1}-BAL"
    )
    row["caption"] = "Opening balance"
    report = _run(tmp_path, payload)
    assert "history_labels_survive" in _fired(report)


def test_24_a_lost_ep_caption_is_caught(tmp_path, payload) -> None:
    _row(
        _pkg(payload)["earnings_and_profits"]["blocks"],
        "block_id",
        f"EP-{PRIOR_FISCAL_YEAR}",
    ).pop("caption")
    assert "history_labels_survive" in _fired(_run(tmp_path, payload))


# --------------------------------------------------------------------------- #
# Evidence absence
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "doc_type",
    [
        DOC_LOCKED_SOURCE,
        DOC_PRIOR_PACKAGE,
        DOC_ALLOCATION_REGISTER,
        DOC_EXCEPTION_REGISTER,
        DOC_COUNTERPART_STUB,
        DOC_PREBUILD_IMAGE,
        DOC_BUILT_PACKAGE,
        DOC_BUILD_REGISTER,
        DOC_MANIFEST,
    ],
)
def test_removing_any_artifact_produces_a_failure_not_a_pass(
    tmp_path, payload, doc_type: str
) -> None:
    """Every control that needed the artifact reports; none of them passes on it."""
    payload["documents"] = [
        d for d in payload["documents"] if d.get("doc_type") != doc_type
    ]
    report = _run(tmp_path, payload)
    assert report.rules_fired()
    for finding in report.findings:
        if finding.location.startswith(f"{doc_type}:-"):
            assert finding.status is Status.FAIL


def test_the_registry_is_ordered_carry_derive_schedules_evidence_custody() -> None:
    """Report order follows the build, which is what makes the report readable."""
    ids = [rule_id for rule_id, _fn in REGISTRY]
    assert ids[0] == "frozen_layers_byte_equal"
    assert ids.index("capital_flow_equals_delta") < ids.index("member_capital_chain")
    assert ids.index("member_capital_chain") < ids.index("evidence_ties_locked_source")
    assert ids.index("evidence_ties_locked_source") < ids.index(
        "locked_source_digest_matches"
    )
    assert ids[-1] == "history_labels_survive"


def test_rebuilding_from_the_files_own_inputs_reproduces_the_package(payload) -> None:
    """The stored package is the pipeline's output, not a hand-written fixture."""
    package = build_package(
        _doc(payload, DOC_LOCKED_SOURCE),
        _doc(payload, DOC_PRIOR_PACKAGE),
        {
            "allocation": _doc(payload, DOC_ALLOCATION_REGISTER),
            "exception": _doc(payload, DOC_EXCEPTION_REGISTER),
            "counterpart_stub": _doc(payload, DOC_COUNTERPART_STUB),
            "prebuild_image": _doc(payload, DOC_PREBUILD_IMAGE),
        },
    )
    assert package.package_doc() == _pkg(payload)


def test_capture_prebuild_image_is_a_view_of_the_prior_package() -> None:
    prior = prior_package()
    image = capture_prebuild_image(prior, captured_at="2029-08-03", document_id="P")
    prior["equity"]["total_cents"] = 1
    assert image["cells"]["equity/TOTAL/amount_cents"] == PRIOR_EQUITY_TOTAL_CENTS


def test_building_a_two_year_step_advances_captions_twice(inputs) -> None:
    """Nothing in the pipeline assumes the step is one; the control asserts it."""
    sources = copy.deepcopy(inputs["sources"])
    sources["fiscal_year"] = PRIOR_FISCAL_YEAR + 2
    package = build_package(sources, inputs["prior_year"], inputs["registers"])
    assert package.captions["equity_closing"] == "Balance at June 30, 2030"
