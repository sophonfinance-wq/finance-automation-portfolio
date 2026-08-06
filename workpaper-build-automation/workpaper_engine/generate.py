"""
Fictional corpus generator for the tax workpaper build engine.
==============================================================

Builds one clean file plus one file per planted defect. The clean file is
constructed **through the builder itself** (:func:`~workpaper_engine.build.build_package`),
so the corpus can never drift from the thing the controls audit: the trial
balance, the classified statements, the equity schedule, the member capital
accounts, the earnings-and-profits roll, the evidence tab, the build register
and the manifest digests are all produced by the pipeline rather than typed
here.

Each defect file starts from a fresh build and applies exactly one mutation
**after** the build has run -- which is what makes it a defect rather than a
differently-shaped truth. One mutation, one control: a corpus where a single
break trips three controls cannot demonstrate that any of the three is
independently violable.

Every name, account number, date and balance here is invented. No real entity,
project, place, ledger or path appears anywhere in this package.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .build import build_package, capture_prebuild_image
from .model import (
    DOC_ALLOCATION_REGISTER,
    DOC_BUILT_PACKAGE,
    DOC_COUNTERPART_STUB,
    DOC_EXCEPTION_REGISTER,
    DOC_LOCKED_SOURCE,
    DOC_PREBUILD_IMAGE,
    DOC_PRIOR_PACKAGE,
    EQUITY_CONTRIBUTION,
    EQUITY_DISTRIBUTION,
    EQUITY_RETAINED_EARNINGS,
    EXC_MISLABELED,
    EXC_PLACEHOLDER,
    FORM_YEAR_DELTA,
    ROLE_CLOSING,
    ROLE_CONTRIBUTION,
    ROLE_DISTRIBUTION,
    ROLE_INCOME,
    ROLE_OPENING,
    SECTION_BALANCE_SHEET,
    SECTION_EQUITY,
    SECTION_PROFIT_LOSS,
    SPLIT_LIABILITY_SHARE,
    SPLIT_ORDINARY_INCOME,
)

#: Fictional groups whose workpaper builds the corpus carries.
PORTFOLIOS: tuple[str, ...] = (
    "Rivermont Holdings",
    "Ashfield Holdings",
    "Copperfield Yards Group",
    "Alderpoint Terraces Partners",
)

#: The entity block the build is scoped to, and one it deliberately is not.
ENTITY_BLOCK = "RIVERMONT-01"
OUT_OF_SCOPE_BLOCK = "ASHFIELD-04"

#: Fictional-future fiscal years. Every date in the corpus comes from here, so
#: nothing in the engine ever reads a clock.
FISCAL_YEAR = 2029
PRIOR_FISCAL_YEAR = 2028
AS_OF = "2029-08-05"
HARVEST_DATE = "2029-08-03"
PREBUILD_CAPTURED_AT = "2029-08-03T09:15:00"

#: Members, in the order every schedule lists them.
MEMBER_CALDERWOOD = "M-CALDERWOOD"
MEMBER_WESTMERE = "M-WESTMERE"
MEMBERS: tuple[tuple[str, str], ...] = (
    (MEMBER_CALDERWOOD, "Calderwood Group"),
    (MEMBER_WESTMERE, "Westmere Partners"),
)

#: The book-to-tax adjustment declared on the current-year extract.
TAX_ADJUSTMENT_CENTS = -4_200_000


# --------------------------------------------------------------------------- #
# The chart of accounts -- the prior year's classification map
# --------------------------------------------------------------------------- #
CHART: dict[str, dict[str, Any]] = {
    "1000": {"section": SECTION_BALANCE_SHEET, "title": "Cash - operating"},
    "1010": {"section": SECTION_BALANCE_SHEET, "title": "Cash - reserve"},
    "1200": {
        "section": SECTION_BALANCE_SHEET,
        "title": "Due from affiliate",
        "intercompany": True,
    },
    "1300": {
        "section": SECTION_BALANCE_SHEET,
        "title": "Investment in Brightwater Commons JV",
        "investment": True,
    },
    "1500": {"section": SECTION_BALANCE_SHEET, "title": "Real estate under development"},
    "1600": {"section": SECTION_BALANCE_SHEET, "title": "Deferred costs"},
    "2000": {
        "section": SECTION_BALANCE_SHEET,
        "title": "Accounts payable",
        "is_liability": True,
    },
    "2100": {
        "section": SECTION_BALANCE_SHEET,
        "title": "Accrued liabilities",
        "is_liability": True,
    },
    "2200": {
        "section": SECTION_BALANCE_SHEET,
        "title": "Due to affiliate",
        "is_liability": True,
        "intercompany": True,
    },
    "2500": {
        "section": SECTION_BALANCE_SHEET,
        "title": "Note payable - member",
        "is_liability": True,
    },
    "3000": {
        "section": SECTION_EQUITY,
        "title": "Member contributions - Calderwood Group",
        "member_id": MEMBER_CALDERWOOD,
        "equity_kind": EQUITY_CONTRIBUTION,
    },
    "3010": {
        "section": SECTION_EQUITY,
        "title": "Member contributions - Westmere Partners",
        "member_id": MEMBER_WESTMERE,
        "equity_kind": EQUITY_CONTRIBUTION,
    },
    "3020": {
        "section": SECTION_EQUITY,
        "title": "Member contributions - Westmere Partners - second tranche",
        "member_id": MEMBER_WESTMERE,
        "equity_kind": EQUITY_CONTRIBUTION,
    },
    "3100": {
        "section": SECTION_EQUITY,
        "title": "Member distributions - Calderwood Group",
        "member_id": MEMBER_CALDERWOOD,
        "equity_kind": EQUITY_DISTRIBUTION,
    },
    "3110": {
        "section": SECTION_EQUITY,
        "title": "Member distributions - Westmere Partners",
        "member_id": MEMBER_WESTMERE,
        "equity_kind": EQUITY_DISTRIBUTION,
    },
    "3900": {
        "section": SECTION_EQUITY,
        "title": "Retained earnings - beginning of year",
        "equity_kind": EQUITY_RETAINED_EARNINGS,
    },
    "4000": {"section": SECTION_PROFIT_LOSS, "title": "Rental revenue"},
    "4100": {"section": SECTION_PROFIT_LOSS, "title": "Other income"},
    "5000": {"section": SECTION_PROFIT_LOSS, "title": "Operating expenses"},
    "5100": {"section": SECTION_PROFIT_LOSS, "title": "Depreciation"},
    "5200": {"section": SECTION_PROFIT_LOSS, "title": "Interest expense"},
    "5300": {"section": SECTION_PROFIT_LOSS, "title": "Management fee - affiliate"},
    "9990": {"section": SECTION_BALANCE_SHEET, "title": "Suspense - unmapped"},
}

#: How the current-year extract titles each account. Account 2100 is abbreviated
#: by the source system; the difference is registered, which is the only reason
#: the build is allowed to carry it.
SOURCE_TITLES: dict[str, str] = {
    **{account: info["title"] for account, info in CHART.items()},
    "2100": "Accrued liabilities - other",
}

#: Current-year balances, in integer cents, debits positive. The whole column
#: sums to zero, because a ledger does.
CURRENT_BALANCES: dict[str, int] = {
    "1000": 92_000_000,
    "1010": 14_000_000,
    "1200": 7_500_000,
    "1300": 46_500_000,
    "1500": 747_363_889,
    "1600": 0,
    "2000": -35_200_000,
    "2100": -10_200_000,
    "2200": -16_800_000,
    "2500": -200_000_000,
    "3000": -215_000_000,
    "3010": -385_000_000,
    "3020": -25_000_000,
    "3100": 30_000_000,
    "3110": 55_700_000,
    "3900": -53_500_000,
    "4000": -240_000_000,
    "4100": -6_000_000,
    "5000": 105_000_000,
    "5100": 56_000_000,
    "5200": 19_500_000,
    "5300": 13_011_111,
    "9990": 125_000,
}

#: Prior-year balances, as the signed prior package carried them. Account 3020
#: is absent: the second tranche was not funded until the current year, which is
#: what makes its current-year row a cumulative residual rather than a delta.
PRIOR_BALANCES: dict[str, int] = {
    "1000": 85_000_000,
    "1010": 12_500_000,
    "1200": 6_000_000,
    "1300": 40_000_000,
    "1500": 605_000_000,
    "2000": -31_000_000,
    "2100": -9_500_000,
    "2200": -14_500_000,
    "2500": -200_000_000,
    "3000": -175_000_000,
    "3010": -325_000_000,
    "3100": 21_000_000,
    "3110": 39_000_000,
    "3900": -30_000_000,
    "4000": -190_000_000,
    "4100": -4_500_000,
    "5000": 90_000_000,
    "5100": 52_000_000,
    "5200": 18_000_000,
    "5300": 11_000_000,
}

#: The neighbouring entity block sitting in the same extract. The build never
#: harvests it; that it is there at all is what makes scoping a control.
OUT_OF_SCOPE_BALANCES: dict[str, int] = {
    "1000": 41_000_000,
    "2000": -12_000_000,
    "3000": -60_000_000,
    "4000": -29_000_000,
    "5000": 60_000_000,
}

#: Last year's result, as the prior package reported it.
PRIOR_NET_INCOME_CENTS = 23_500_000


# --------------------------------------------------------------------------- #
# Input artifacts
# --------------------------------------------------------------------------- #
def locked_source() -> dict[str, Any]:
    """The locked current-year general-ledger extract."""
    rows: list[dict[str, Any]] = []
    for account in sorted(CURRENT_BALANCES):
        rows.append({
            "account": account,
            "title": SOURCE_TITLES[account],
            "entity_block": ENTITY_BLOCK,
            "balance_cents": CURRENT_BALANCES[account],
        })
    for account in sorted(OUT_OF_SCOPE_BALANCES):
        rows.append({
            "account": account,
            "title": CHART[account]["title"],
            "entity_block": OUT_OF_SCOPE_BLOCK,
            "balance_cents": OUT_OF_SCOPE_BALANCES[account],
        })
    return {
        "doc_type": DOC_LOCKED_SOURCE,
        "document_id": f"GL-FY{FISCAL_YEAR}-{ENTITY_BLOCK}",
        "entity_block": ENTITY_BLOCK,
        "fiscal_year": FISCAL_YEAR,
        "source_file": "gl_extract_fy2029.xlsx",
        "tab": "TB by entity block",
        "balance_column": "Ending balance",
        "harvest_date": HARVEST_DATE,
        "tax_adjustment_cents": TAX_ADJUSTMENT_CENTS,
        "rows": rows,
    }


def _prior_equity_rows() -> list[dict[str, Any]]:
    """Last year's members' equity schedule, exactly as it was signed."""
    return [
        {
            "row_id": f"EQ-{PRIOR_FISCAL_YEAR - 1}-BAL",
            "caption": f"Balance at June 30, {PRIOR_FISCAL_YEAR - 1}",
            "year": PRIOR_FISCAL_YEAR - 1,
            "role": ROLE_OPENING,
            "amount_cents": 360_000_000,
        },
        {
            "row_id": f"EQ-{PRIOR_FISCAL_YEAR}-3000",
            "caption": f"{CHART['3000']['title']} - fiscal year {PRIOR_FISCAL_YEAR}",
            "year": PRIOR_FISCAL_YEAR,
            "role": ROLE_CONTRIBUTION,
            "account": "3000",
            "member_id": MEMBER_CALDERWOOD,
            "row_form": FORM_YEAR_DELTA,
            "formula_present": False,
            "amount_cents": 45_000_000,
        },
        {
            "row_id": f"EQ-{PRIOR_FISCAL_YEAR}-3010",
            "caption": f"{CHART['3010']['title']} - fiscal year {PRIOR_FISCAL_YEAR}",
            "year": PRIOR_FISCAL_YEAR,
            "role": ROLE_CONTRIBUTION,
            "account": "3010",
            "member_id": MEMBER_WESTMERE,
            "row_form": FORM_YEAR_DELTA,
            "formula_present": False,
            "amount_cents": 80_000_000,
        },
        {
            "row_id": f"EQ-{PRIOR_FISCAL_YEAR}-3100",
            "caption": f"{CHART['3100']['title']} - fiscal year {PRIOR_FISCAL_YEAR}",
            "year": PRIOR_FISCAL_YEAR,
            "role": ROLE_DISTRIBUTION,
            "account": "3100",
            "member_id": MEMBER_CALDERWOOD,
            "row_form": FORM_YEAR_DELTA,
            "formula_present": False,
            "amount_cents": -6_000_000,
        },
        {
            "row_id": f"EQ-{PRIOR_FISCAL_YEAR}-3110",
            "caption": f"{CHART['3110']['title']} - fiscal year {PRIOR_FISCAL_YEAR}",
            "year": PRIOR_FISCAL_YEAR,
            "role": ROLE_DISTRIBUTION,
            "account": "3110",
            "member_id": MEMBER_WESTMERE,
            "row_form": FORM_YEAR_DELTA,
            "formula_present": False,
            "amount_cents": -9_000_000,
        },
        {
            "row_id": f"EQ-{PRIOR_FISCAL_YEAR}-INC-{MEMBER_CALDERWOOD}",
            "caption": (
                f"Net income allocated - Calderwood Group - fiscal year "
                f"{PRIOR_FISCAL_YEAR}"
            ),
            "year": PRIOR_FISCAL_YEAR,
            "role": ROLE_INCOME,
            "member_id": MEMBER_CALDERWOOD,
            "amount_cents": 8_225_000,
        },
        {
            "row_id": f"EQ-{PRIOR_FISCAL_YEAR}-INC-{MEMBER_WESTMERE}",
            "caption": (
                f"Net income allocated - Westmere Partners - fiscal year "
                f"{PRIOR_FISCAL_YEAR}"
            ),
            "year": PRIOR_FISCAL_YEAR,
            "role": ROLE_INCOME,
            "member_id": MEMBER_WESTMERE,
            "amount_cents": 15_275_000,
        },
        {
            "row_id": f"EQ-{PRIOR_FISCAL_YEAR}-BAL",
            "caption": f"Balance at June 30, {PRIOR_FISCAL_YEAR}",
            "year": PRIOR_FISCAL_YEAR,
            "role": ROLE_CLOSING,
            "amount_cents": 493_500_000,
        },
    ]


def _prior_member_blocks() -> list[dict[str, Any]]:
    """Last year's member capital accounts, book and tax."""
    return [
        {
            "block_id": f"MC-{PRIOR_FISCAL_YEAR}-{MEMBER_CALDERWOOD}",
            "member_id": MEMBER_CALDERWOOD,
            "member_name": "Calderwood Group",
            "year": PRIOR_FISCAL_YEAR,
            "caption": (
                f"Calderwood Group - Fiscal year ended June 30, {PRIOR_FISCAL_YEAR}"
            ),
            "opening_book_cents": 126_000_000,
            "contributions_book_cents": 45_000_000,
            "income_book_cents": 8_225_000,
            "distributions_book_cents": 6_000_000,
            "closing_book_cents": 173_225_000,
            "opening_tax_cents": 118_000_000,
            "contributions_tax_cents": 45_000_000,
            "income_tax_cents": 7_000_000,
            "distributions_tax_cents": 6_000_000,
            "closing_tax_cents": 164_000_000,
            "liability_share_cents": 89_250_000,
            "tax_basis_cents": 253_250_000,
        },
        {
            "block_id": f"MC-{PRIOR_FISCAL_YEAR}-{MEMBER_WESTMERE}",
            "member_id": MEMBER_WESTMERE,
            "member_name": "Westmere Partners",
            "year": PRIOR_FISCAL_YEAR,
            "caption": (
                f"Westmere Partners - Fiscal year ended June 30, {PRIOR_FISCAL_YEAR}"
            ),
            "opening_book_cents": 234_000_000,
            "contributions_book_cents": 80_000_000,
            "income_book_cents": 15_275_000,
            "distributions_book_cents": 9_000_000,
            "closing_book_cents": 320_275_000,
            "opening_tax_cents": 220_000_000,
            "contributions_tax_cents": 80_000_000,
            "income_tax_cents": 13_000_000,
            "distributions_tax_cents": 9_000_000,
            "closing_tax_cents": 304_000_000,
            "liability_share_cents": 165_750_000,
            "tax_basis_cents": 469_750_000,
        },
    ]


def prior_package() -> dict[str, Any]:
    """Last year's signed workpaper package: the thing being rolled."""
    return {
        "doc_type": DOC_PRIOR_PACKAGE,
        "document_id": f"WP-{ENTITY_BLOCK}-FY{PRIOR_FISCAL_YEAR}",
        "entity_block": ENTITY_BLOCK,
        "fiscal_year": PRIOR_FISCAL_YEAR,
        "net_income_cents": PRIOR_NET_INCOME_CENTS,
        "captions": {
            "package_title": (
                f"Tax workpaper package - fiscal year ended June 30, "
                f"{PRIOR_FISCAL_YEAR}"
            ),
            "trial_balance_title": (
                f"Trial balance - fiscal year ended June 30, {PRIOR_FISCAL_YEAR}"
            ),
            "balance_sheet_title": f"Balance sheet - June 30, {PRIOR_FISCAL_YEAR}",
            "profit_loss_title": (
                f"Statement of operations - fiscal year ended June 30, "
                f"{PRIOR_FISCAL_YEAR}"
            ),
            "equity_title": (
                f"Statement of members' equity - fiscal year ended June 30, "
                f"{PRIOR_FISCAL_YEAR}"
            ),
            "equity_closing": f"Balance at June 30, {PRIOR_FISCAL_YEAR}",
            "member_block_current": (
                f"Fiscal year ended June 30, {PRIOR_FISCAL_YEAR}"
            ),
            "ep_block_current": (
                f"Accumulated earnings and profits at June 30, {PRIOR_FISCAL_YEAR}"
            ),
            "evidence_title": (
                f"Support - general ledger harvest - fiscal year ended June 30, "
                f"{PRIOR_FISCAL_YEAR}"
            ),
        },
        "classification": copy.deepcopy(CHART),
        "trial_balance": {
            "rows": [
                {
                    "account": account,
                    "title": CHART[account]["title"],
                    "balance_cents": PRIOR_BALANCES[account],
                }
                for account in sorted(PRIOR_BALANCES)
            ]
        },
        "equity": {
            "rows": _prior_equity_rows(),
            "total_cents": 493_500_000,
        },
        "member_capital": {
            "members": [
                {"member_id": mid, "member_name": name} for mid, name in MEMBERS
            ],
            "blocks": _prior_member_blocks(),
        },
        "earnings_and_profits": {
            "blocks": [
                {
                    "block_id": f"EP-{PRIOR_FISCAL_YEAR - 1}",
                    "year": PRIOR_FISCAL_YEAR - 1,
                    "caption": (
                        f"Accumulated earnings and profits at June 30, "
                        f"{PRIOR_FISCAL_YEAR - 1}"
                    ),
                    "prior_accumulated_cents": 25_000_000,
                    "current_taxable_cents": 16_000_000,
                    "accumulated_end_cents": 41_000_000,
                },
                {
                    "block_id": f"EP-{PRIOR_FISCAL_YEAR}",
                    "year": PRIOR_FISCAL_YEAR,
                    "caption": (
                        f"Accumulated earnings and profits at June 30, "
                        f"{PRIOR_FISCAL_YEAR}"
                    ),
                    "prior_accumulated_cents": 41_000_000,
                    "current_taxable_cents": 20_000_000,
                    "accumulated_end_cents": 61_000_000,
                },
            ]
        },
        "notes": {
            "rows": [
                {
                    "note_id": "N-01",
                    "text": (
                        "Members' interests are allocated in accordance with the "
                        "operating agreement in effect for the fiscal year."
                    ),
                },
                {
                    "note_id": "N-02",
                    "text": (
                        "The note payable to a member is unsecured and bears "
                        "interest at a fixed annual rate."
                    ),
                },
                {
                    "note_id": "N-03",
                    "text": (
                        "Deferred costs are carried at cost and amortized over the "
                        "term of the related agreement."
                    ),
                },
            ]
        },
    }


def allocation_register() -> dict[str, Any]:
    """Member split percentages, in integer basis points, carried forward."""
    return {
        "doc_type": DOC_ALLOCATION_REGISTER,
        "document_id": f"AR-{ENTITY_BLOCK}-FY{FISCAL_YEAR}",
        "members": [{"member_id": mid, "member_name": name} for mid, name in MEMBERS],
        "splits": {
            SPLIT_ORDINARY_INCOME: {MEMBER_CALDERWOOD: 3500, MEMBER_WESTMERE: 6500},
            SPLIT_LIABILITY_SHARE: {MEMBER_CALDERWOOD: 3500, MEMBER_WESTMERE: 6500},
        },
    }


def exception_register() -> dict[str, Any]:
    """The account exceptions and tie-out differences already accepted."""
    return {
        "doc_type": DOC_EXCEPTION_REGISTER,
        "document_id": f"ER-{ENTITY_BLOCK}-FY{FISCAL_YEAR}",
        "account_exceptions": [
            {
                "account": "9990",
                "kind": EXC_PLACEHOLDER,
                "note": (
                    "Suspense code the ledger has not retired; the balance was "
                    "reviewed and accepted for this year."
                ),
            },
            {
                "account": "2100",
                "kind": EXC_MISLABELED,
                "note": (
                    "The extract abbreviates the chart title; the account number "
                    "is confirmed against the chart."
                ),
            },
        ],
        "tie_out_disclosures": [],
    }


def counterpart_stub() -> dict[str, Any]:
    """The counterpart entity's stub for the investment held in this block."""
    return {
        "doc_type": DOC_COUNTERPART_STUB,
        "document_id": f"CS-{ENTITY_BLOCK}-FY{FISCAL_YEAR}",
        "account": "1300",
        "counterpart_entity": "Brightwater Commons JV",
        "stub_period": f"FY{FISCAL_YEAR}",
        "value_cents": CURRENT_BALANCES["1300"],
    }


# --------------------------------------------------------------------------- #
# Assembling a build file
# --------------------------------------------------------------------------- #
def _assemble(
    source: dict[str, Any],
    prior: dict[str, Any],
    allocation: dict[str, Any],
    exceptions: dict[str, Any],
    stub: dict[str, Any],
    image: dict[str, Any],
) -> list[dict[str, Any]]:
    registers = {
        "allocation": allocation,
        "exception": exceptions,
        "counterpart_stub": stub,
        "prebuild_image": image,
    }
    package = build_package(source, prior, registers)
    return [
        source,
        prior,
        allocation,
        exceptions,
        stub,
        image,
        package.package_doc(),
        package.register_doc(),
        package.manifest_doc(),
    ]


def baseline(portfolio: str) -> dict[str, Any]:
    """A complete, clean build file: four inputs, a backup, and the product."""
    source = locked_source()
    prior = prior_package()
    allocation = allocation_register()
    exceptions = exception_register()
    stub = counterpart_stub()
    image = capture_prebuild_image(
        prior,
        captured_at=PREBUILD_CAPTURED_AT,
        document_id=f"PRE-{ENTITY_BLOCK}-FY{FISCAL_YEAR}",
    )
    return {
        "file_id": "baseline",
        "portfolio": portfolio,
        "entity_block": ENTITY_BLOCK,
        "fiscal_year": FISCAL_YEAR,
        "prior_fiscal_year": PRIOR_FISCAL_YEAR,
        "as_of": AS_OF,
        "documents": _assemble(source, prior, allocation, exceptions, stub, image),
    }


def rederive(payload: dict[str, Any]) -> None:
    """Re-run the build over the file's own inputs, in place.

    Used when a scenario legitimately changes an input and the package that
    follows from it should change too. Applying a mutation *without* calling this
    is what makes a defect a defect.
    """
    source = _require(payload, DOC_LOCKED_SOURCE)
    prior = _require(payload, DOC_PRIOR_PACKAGE)
    allocation = _require(payload, DOC_ALLOCATION_REGISTER)
    exceptions = _require(payload, DOC_EXCEPTION_REGISTER)
    stub = _require(payload, DOC_COUNTERPART_STUB)
    image = _require(payload, DOC_PREBUILD_IMAGE)
    payload["documents"] = _assemble(
        source, prior, allocation, exceptions, stub, image
    )


# --------------------------------------------------------------------------- #
# Accessors used by the mutations
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _require(payload: dict[str, Any], doc_type: str) -> dict[str, Any]:
    doc = _doc(payload, doc_type)
    if doc is None:
        raise KeyError(f"corpus file carries no {doc_type!r} document")
    return doc


def _built(payload: dict[str, Any]) -> dict[str, Any]:
    return _require(payload, DOC_BUILT_PACKAGE)


def _equity_row(payload: dict[str, Any], row_id: str) -> dict[str, Any]:
    for row in _built(payload)["equity"]["rows"]:
        if row.get("row_id") == row_id:
            return row
    raise KeyError(f"no equity row {row_id!r}")


def _member_block(payload: dict[str, Any], block_id: str) -> dict[str, Any]:
    for block in _built(payload)["member_capital"]["blocks"]:
        if block.get("block_id") == block_id:
            return block
    raise KeyError(f"no member capital block {block_id!r}")


def _ep_block(payload: dict[str, Any], block_id: str) -> dict[str, Any]:
    for block in _built(payload)["earnings_and_profits"]["blocks"]:
        if block.get("block_id") == block_id:
            return block
    raise KeyError(f"no earnings-and-profits block {block_id!r}")


def _tb_row(payload: dict[str, Any], account: str) -> dict[str, Any]:
    for row in _built(payload)["trial_balance"]["rows"]:
        if row.get("account") == account:
            return row
    raise KeyError(f"no trial balance row {account!r}")


def _bs_row(payload: dict[str, Any], row_id: str) -> dict[str, Any]:
    for row in _built(payload)["balance_sheet"]["rows"]:
        if row.get("row_id") == row_id:
            return row
    raise KeyError(f"no balance sheet row {row_id!r}")


# --------------------------------------------------------------------------- #
# The planted defects -- one per control
# --------------------------------------------------------------------------- #
def _frozen_layer_reordered(payload: dict[str, Any]) -> None:
    """Sort the equity schedule and two years of history swap places."""
    rows = _built(payload)["equity"]["rows"]
    rows[1], rows[2] = rows[2], rows[1]


def _stale_prior_year_caption(payload: dict[str, Any]) -> None:
    """The figures rolled; one caption did not."""
    _built(payload)["captions"]["equity_title"] = (
        f"Statement of members' equity - fiscal year ended June 30, "
        f"{PRIOR_FISCAL_YEAR}"
    )


def _flow_off_source_delta(payload: dict[str, Any]) -> None:
    """A contribution row nudged off the movement it is supposed to be."""
    _equity_row(payload, f"EQ-{FISCAL_YEAR}-3000")["amount_cents"] += 25_000


def _liability_split_does_not_sum(payload: dict[str, Any]) -> None:
    """A carried split pair that adds to 101.00%."""
    _require(payload, DOC_ALLOCATION_REGISTER)["splits"][SPLIT_LIABILITY_SHARE][
        MEMBER_WESTMERE
    ] = 6600


def _income_split_off_ratio(payload: dict[str, Any]) -> None:
    """One income row allocated on a ratio the register does not carry."""
    _equity_row(payload, f"EQ-{FISCAL_YEAR}-INC-{MEMBER_CALDERWOOD}")[
        "amount_cents"
    ] = 26_244_444


def _equity_total_typed_over(payload: dict[str, Any]) -> None:
    """The schedule total typed rather than rolled."""
    _built(payload)["equity"]["total_cents"] += 50_000


def _equity_vs_bs_undisclosed(payload: dict[str, Any]) -> None:
    """The balance sheet and the equity schedule stop agreeing, silently."""
    _bs_row(payload, "3000")["amount_cents"] += 50_000
    built = _built(payload)
    built["balance_sheet"]["total_equity_cents"] -= 50_000


def _equity_vs_bs_disclosed(payload: dict[str, Any]) -> None:
    """The same difference, written down in the exception register."""
    _equity_vs_bs_undisclosed(payload)
    _require(payload, DOC_EXCEPTION_REGISTER)["tie_out_disclosures"].append({
        "schedule": "equity_vs_balance_sheet",
        "variance_cents": 50_000,
        "note": (
            "Contribution received after the extract was locked; presented on the "
            "balance sheet and carried to the equity schedule next year."
        ),
    })


def _member_contribution_column_typed(payload: dict[str, Any]) -> None:
    """A member's contribution column overstated, closing balance untouched."""
    _member_block(payload, f"MC-{FISCAL_YEAR}-{MEMBER_CALDERWOOD}")[
        "contributions_book_cents"
    ] += 40_000


def _member_closing_off_equity(payload: dict[str, Any]) -> None:
    """A block that still chains internally but no longer sums to the schedule."""
    block = _member_block(payload, f"MC-{FISCAL_YEAR}-{MEMBER_WESTMERE}")
    block["income_book_cents"] += 60_000
    block["closing_book_cents"] += 60_000


def _tax_basis_omits_liability(payload: dict[str, Any]) -> None:
    """Basis reported at capital, with the liability share left out."""
    block = _member_block(payload, f"MC-{FISCAL_YEAR}-{MEMBER_CALDERWOOD}")
    block["tax_basis_cents"] = block["closing_tax_cents"]


def _ep_accumulated_typed_over(payload: dict[str, Any]) -> None:
    """The accumulated figure hand-maintained and drifting."""
    _ep_block(payload, f"EP-{FISCAL_YEAR}")["accumulated_end_cents"] += 100_000


def _retained_earnings_not_rolled(payload: dict[str, Any]) -> None:
    """The beginning balance kept from the copied file."""
    _tb_row(payload, "3900")["balance_cents"] = PRIOR_BALANCES["3900"]


def _row_form_read_from_formula(payload: dict[str, Any]) -> None:
    """A cumulative-residual row classified from the formula it inherited."""
    row = _equity_row(payload, f"EQ-{FISCAL_YEAR}-3020")
    row["row_form"] = FORM_YEAR_DELTA
    row["formula_present"] = True


def _evidence_title_off_source(payload: dict[str, Any]) -> None:
    """An evidence row re-titled so it no longer ties the source it cites."""
    for row in _built(payload)["evidence"]["rows"]:
        if row.get("account") == "1010":
            row["title"] = "Cash - reserve account"


def _evidence_subtotal_typed_over(payload: dict[str, Any]) -> None:
    """The support subtotal typed over the formula that footed it."""
    _built(payload)["evidence"]["subtotal_cents"] = 12_000


def _citation_names_wrong_tab(payload: dict[str, Any]) -> None:
    """A citation that sends the reviewer to the activity tab."""
    _built(payload)["evidence"]["citation"]["tab"] = "Monthly activity"


def _source_moved_after_build(payload: dict[str, Any]) -> None:
    """The extract re-exported after the build, in a block nobody harvested."""
    for row in _require(payload, DOC_LOCKED_SOURCE)["rows"]:
        if row["entity_block"] == OUT_OF_SCOPE_BLOCK and row["account"] == "1000":
            row["balance_cents"] += 100_000


def _prebuild_image_retaken(payload: dict[str, Any]) -> None:
    """The custody backup re-taken, so it no longer predates the build."""
    _require(payload, DOC_PREBUILD_IMAGE)["captured_at"] = "2029-08-05T18:40:00"


def _cell_edited_outside_register(payload: dict[str, Any]) -> None:
    """A carried-forward note edited without appearing in the build register."""
    for row in _built(payload)["notes"]["rows"]:
        if row.get("note_id") == "N-02":
            row["text"] = (
                "The note payable to a member is unsecured and bears interest at "
                "a fixed annual rate, payable at maturity."
            )


def _investment_stub_drifts(payload: dict[str, Any]) -> None:
    """The counterpart's stub and this package's investment part company."""
    _require(payload, DOC_COUNTERPART_STUB)["value_cents"] -= 150_000


def _funded_account_left_off(payload: dict[str, Any]) -> None:
    """A funded account dropped from the workpaper, which still foots."""
    built = _built(payload)
    built["trial_balance"]["rows"] = [
        r for r in built["trial_balance"]["rows"] if r.get("account") != "1010"
    ]


def _placeholder_deregistered(payload: dict[str, Any]) -> None:
    """The suspense account is still in the package; its acceptance is not."""
    exceptions = _require(payload, DOC_EXCEPTION_REGISTER)
    exceptions["account_exceptions"] = [
        e for e in exceptions["account_exceptions"] if e.get("account") != "9990"
    ]


def _formula_error_rendered(payload: dict[str, Any]) -> None:
    """An error marker delivered where a figure belongs."""
    _tb_row(payload, "1500")["display"] = "#REF!"


def _history_label_dropped(payload: dict[str, Any]) -> None:
    """A prior year's block caption lost in the roll, figures intact."""
    _member_block(payload, f"MC-{PRIOR_FISCAL_YEAR}-{MEMBER_CALDERWOOD}").pop(
        "caption", None
    )


def _amount_not_integer(payload: dict[str, Any]) -> None:
    """A flow row carrying a fractional cent."""
    row = _equity_row(payload, f"EQ-{FISCAL_YEAR}-3010")
    row["amount_cents"] = float(row["amount_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "frozen_layer_reordered": ("frozen_layers_byte_equal", _frozen_layer_reordered),
    "stale_prior_year_caption": (
        "captions_advance_one_year",
        _stale_prior_year_caption,
    ),
    "flow_off_source_delta": ("capital_flow_equals_delta", _flow_off_source_delta),
    "liability_split_does_not_sum": (
        "split_pairs_sum_to_one",
        _liability_split_does_not_sum,
    ),
    "income_split_off_ratio": ("income_split_rows_exact", _income_split_off_ratio),
    "equity_total_typed_over": ("equity_total_rolls", _equity_total_typed_over),
    "equity_vs_bs_undisclosed": (
        "equity_ties_balance_sheet",
        _equity_vs_bs_undisclosed,
    ),
    "equity_vs_bs_disclosed": ("equity_ties_balance_sheet", _equity_vs_bs_disclosed),
    "member_contribution_column_typed": (
        "member_capital_chain",
        _member_contribution_column_typed,
    ),
    "member_closing_off_equity": (
        "member_closing_ties_equity",
        _member_closing_off_equity,
    ),
    "tax_basis_omits_liability": (
        "tax_basis_is_capital_plus_liability",
        _tax_basis_omits_liability,
    ),
    "ep_accumulated_typed_over": ("ep_chain_rolls", _ep_accumulated_typed_over),
    "retained_earnings_not_rolled": (
        "retained_earnings_beginning_rolls",
        _retained_earnings_not_rolled,
    ),
    "row_form_read_from_formula": (
        "row_form_classified_from_balances",
        _row_form_read_from_formula,
    ),
    "evidence_title_off_source": (
        "evidence_ties_locked_source",
        _evidence_title_off_source,
    ),
    "evidence_subtotal_typed_over": (
        "evidence_subtotal_foots",
        _evidence_subtotal_typed_over,
    ),
    "citation_names_wrong_tab": ("citation_block_correct", _citation_names_wrong_tab),
    "source_moved_after_build": (
        "locked_source_digest_matches",
        _source_moved_after_build,
    ),
    "prebuild_image_retaken": (
        "prebuild_image_digest_matches",
        _prebuild_image_retaken,
    ),
    "cell_edited_outside_register": (
        "edit_scope_matches_register",
        _cell_edited_outside_register,
    ),
    "investment_stub_drifts": ("cross_schedule_reciprocity", _investment_stub_drifts),
    "funded_account_left_off": ("source_completeness", _funded_account_left_off),
    "placeholder_deregistered": (
        "exception_register_honored",
        _placeholder_deregistered,
    ),
    "formula_error_rendered": ("render_hygiene", _formula_error_rendered),
    "history_label_dropped": ("history_labels_survive", _history_label_dropped),
    "amount_not_integer": ("capital_flow_equals_delta", _amount_not_integer),
}


# --------------------------------------------------------------------------- #
# Corpus writer
# --------------------------------------------------------------------------- #
def generate_corpus(folder: Path) -> list[Path]:
    """Write the fictional corpus into ``folder`` and return the paths written."""
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    files: list[dict[str, Any]] = []
    clean = baseline(PORTFOLIOS[0])
    clean["file_id"] = f"clean__{PORTFOLIOS[0].replace(' ', '_')}"
    files.append(clean)

    for i, name in enumerate(sorted(DEFECTS)):
        _rule, mutate = DEFECTS[name]
        portfolio = PORTFOLIOS[(i + 1) % len(PORTFOLIOS)]
        payload = baseline(portfolio)
        payload["file_id"] = f"{name}__{portfolio.replace(' ', '_')}"
        payload["planted_defect"] = name
        mutate(payload)
        files.append(payload)

    for payload in files:
        path = folder / f"{payload['file_id']}.json"
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return sorted(written)
