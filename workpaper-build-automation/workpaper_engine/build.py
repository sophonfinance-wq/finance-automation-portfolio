"""
The construction pipeline: how a tax workpaper package is built.
================================================================

This module is the product. :func:`build_package` takes a locked current-year
general-ledger extract, last year's signed workpaper package and the two
registers, and returns a :class:`WorkpaperPackage` -- a trial balance, a balance
sheet, a statement of operations, a members' equity schedule, member capital
accounts, an earnings-and-profits roll-forward, an evidence tab, a build
register naming every constructed cell with the derivation that produced it, and
a manifest of content digests.

Everything the controls in :mod:`.engine` later re-derive is derived **here,
once**. That is deliberate and it is the same reason the other engines in this
portfolio keep a shared kernel: if the build computed a member's closing capital
one way and the control that proves it computed the same figure another way, the
two would disagree at the edges -- an account that was flat at the prior
year-end, an allocation whose remainder falls on the second member, a year whose
taxable result is negative -- and the control suite would be measuring the
distance between two implementations instead of the correctness of the package.

The build is a pure function of its inputs. It reads dictionaries and returns a
new one; it never writes to the extract, the prior package or the registers, and
it takes no clock reading -- every date in the output comes from the inputs, so
the same inputs produce the same package bytes today and next year.

Order of construction
---------------------
1. **Harvest.** Every row of the locked extract whose entity block matches the
   scope, located by exact account number. Nothing is matched on title.
2. **Trial balance.** The harvested rows that carry a balance. An account that
   is flat is left off the workpaper and stays on the evidence tab, which is
   why completeness is a control rather than an assumption.
3. **Classification.** Balance sheet, equity or statement of operations, taken
   from the prior year's classification map. A new year does not get to invent
   where an account belongs.
4. **Captions.** Every rolling caption advanced by exactly the number of years
   between the two packages.
5. **Equity.** Prior layers frozen verbatim, current-year contribution and
   distribution rows derived as source-minus-prior per account, income rows
   allocated on the carried split, and a closing total.
6. **Member capital.** A new year block per member: opening from last year's
   closing, the year's flows, the allocated result, the closing, the liability
   share and the tax basis -- book and tax.
7. **Earnings and profits.** A new block: last year's accumulated plus this
   year's taxable.
8. **Evidence.** The harvested rows with their citation, and a subtotal that has
   to foot to zero.
9. **Register and manifest.** Every constructed cell, and the digests that make
   the build's custody checkable.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any

from .model import (
    CAPTION_IDS,
    EQUITY_CONTRIBUTION,
    EQUITY_DISTRIBUTION,
    FORM_CUMULATIVE_RESIDUAL,
    FORM_YEAR_DELTA,
    ROLE_CLOSING,
    ROLE_CONTRIBUTION,
    ROLE_DISTRIBUTION,
    ROLE_INCOME,
    SECTION_BALANCE_SHEET,
    SECTION_EQUITY,
    SECTION_PROFIT_LOSS,
    SPLIT_LIABILITY_SHARE,
    SPLIT_ORDINARY_INCOME,
)
from .money import BPS_FULL, allocate_by_ratio, fmt

# --------------------------------------------------------------------------- #
# Small shared primitives
# --------------------------------------------------------------------------- #
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")

#: The cell fields flattened out of each schedule. Anything not named here is
#: metadata rather than a cell, and the edit-scope control does not police it.
TB_CELL_FIELDS: tuple[str, ...] = ("title", "balance_cents", "display")
EVIDENCE_CELL_FIELDS: tuple[str, ...] = ("title", "balance_cents", "display")
MEMBER_CELL_FIELDS: tuple[str, ...] = (
    "caption",
    "opening_book_cents",
    "contributions_book_cents",
    "income_book_cents",
    "distributions_book_cents",
    "closing_book_cents",
    "opening_tax_cents",
    "contributions_tax_cents",
    "income_tax_cents",
    "distributions_tax_cents",
    "closing_tax_cents",
    "liability_share_cents",
    "tax_basis_cents",
)
EP_CELL_FIELDS: tuple[str, ...] = (
    "caption",
    "prior_accumulated_cents",
    "current_taxable_cents",
    "accumulated_end_cents",
)
CITATION_FIELDS: tuple[str, ...] = (
    "source_file",
    "tab",
    "balance_column",
    "harvest_date",
)


def year_tokens(text: str) -> list[int]:
    """Every four-digit year appearing in ``text``, in order of appearance."""
    return [int(m.group(0)) for m in _YEAR_RE.finditer(text)]


def advance_year_text(text: str, years: int = 1) -> str:
    """Advance every four-digit year in ``text`` by ``years``.

    A caption is rolled by moving the year it names, not by pasting a new
    caption over it: that keeps the house wording, the punctuation and the day
    of the fiscal year-end exactly as the prior package had them, so the only
    thing that changes is the thing that is supposed to change.
    """
    return _YEAR_RE.sub(lambda m: str(int(m.group(0)) + years), text)


def digest_payload(payload: Any) -> str:
    """SHA-256 of a JSON payload, serialised canonically.

    Sorted keys and tight separators mean the digest is a property of the
    *content*, not of how the file happened to be written, so a package
    re-serialised by a different writer still hashes the same.
    """
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Reading the inputs
# --------------------------------------------------------------------------- #
def source_rows(sources: dict[str, Any] | None, entity_block: str) -> list[dict[str, Any]]:
    """Rows of the locked extract belonging to ``entity_block``, in account order.

    Scope is an equality test on the block carried by each row. An extract holds
    more than one entity's ledger, and a harvest that filtered on anything softer
    -- a name prefix, a row range, a colour -- picks up a neighbouring entity the
    first time somebody inserts a row.
    """
    if not isinstance(sources, dict):
        return []
    rows = sources.get("rows")
    if not isinstance(rows, list):
        return []
    scoped = [
        r for r in rows
        if isinstance(r, dict) and r.get("entity_block") == entity_block
    ]
    return sorted(scoped, key=lambda r: str(r.get("account", "")))


def source_by_account(
    sources: dict[str, Any] | None, entity_block: str
) -> dict[str, dict[str, Any]]:
    """``{account: row}`` for the scoped extract, first occurrence winning."""
    out: dict[str, dict[str, Any]] = {}
    for row in source_rows(sources, entity_block):
        account = str(row.get("account", ""))
        if account and account not in out:
            out[account] = row
    return out


def classification_map(prior_year: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """The prior year's classification map: account -> section, title, kind."""
    if not isinstance(prior_year, dict):
        return {}
    raw = prior_year.get("classification")
    if not isinstance(raw, dict):
        return {}
    return {str(k): v for k, v in raw.items() if isinstance(v, dict)}


def prior_balances(prior_year: dict[str, Any] | None) -> dict[str, int]:
    """``{account: balance_cents}`` from the prior package's trial balance.

    An account absent from last year's trial balance reads as zero, which is the
    honest answer: it was not funded, and the current-year row that carries it is
    a cumulative residual rather than a delta.
    """
    out: dict[str, int] = {}
    if not isinstance(prior_year, dict):
        return out
    tb = prior_year.get("trial_balance")
    if not isinstance(tb, dict):
        return out
    for row in tb.get("rows", []) or []:
        if not isinstance(row, dict):
            continue
        account = str(row.get("account", ""))
        value = row.get("balance_cents")
        if account and isinstance(value, int) and not isinstance(value, bool):
            out.setdefault(account, value)
    return out


def prior_captions(prior_year: dict[str, Any] | None) -> dict[str, str]:
    """The prior package's rolling captions, by caption id."""
    if not isinstance(prior_year, dict):
        return {}
    raw = prior_year.get("captions")
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if isinstance(v, str)}


def split_pairs(registers: dict[str, Any] | None) -> dict[str, dict[str, int]]:
    """``{purpose: {member_id: bps}}`` from the allocation register."""
    allocation = (registers or {}).get("allocation")
    if not isinstance(allocation, dict):
        return {}
    raw = allocation.get("splits")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, int]] = {}
    for purpose, pair in raw.items():
        if not isinstance(pair, dict):
            continue
        out[str(purpose)] = {
            str(m): v for m, v in pair.items()
            if isinstance(v, int) and not isinstance(v, bool)
        }
    return out


def member_list(registers: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Members in allocation-register order, so every schedule lists them alike."""
    allocation = (registers or {}).get("allocation")
    if not isinstance(allocation, dict):
        return []
    members = allocation.get("members")
    if not isinstance(members, list):
        return []
    return [m for m in members if isinstance(m, dict)]


# --------------------------------------------------------------------------- #
# The arithmetic, stated once
# --------------------------------------------------------------------------- #
def equity_presented(balance_cents: int) -> int:
    """A ledger balance presented the way an equity schedule reads it.

    Equity is credit-natural, so the ledger carries it negative and the schedule
    prints it positive. Flipping the sign in one named place is what stops half
    the schedules in the package from disagreeing about which direction a
    contribution moves.
    """
    return -balance_cents


def flow_amount(current_balance_cents: int, prior_balance_cents: int) -> int:
    """The current year's movement in an equity account, as the schedule shows it.

    This is the single most valuable line in the module. A contribution row is
    the *change* in the contributions account between the two year-ends, not the
    account's balance: the balance is every contribution since inception, and
    dropping it onto a current-year row restates the whole history as if it
    happened this year -- while the schedule still foots, because the closing
    total was derived from the same wrong row.
    """
    return equity_presented(current_balance_cents) - equity_presented(prior_balance_cents)


def row_form(prior_balance_cents: int) -> str:
    """Whether a current-year row carries a year delta or a cumulative residual.

    Decided from the account's balance at the **prior** year-end, which together
    with the current balance is the whole of the evidence: an account that was
    flat last year has no history to net against, so its balance and its movement
    are the same figure and the row is a cumulative residual. An account that
    already carried a balance contributes only its movement.

    Nothing here looks at whether the cell holds a live formula. A formula
    survives a copy; a balance does not, and the row form has to follow the
    balances.
    """
    return FORM_CUMULATIVE_RESIDUAL if prior_balance_cents == 0 else FORM_YEAR_DELTA


def net_income(
    balances: dict[str, int], classification: dict[str, dict[str, Any]]
) -> int:
    """The result for the year: the statement of operations, sign-flipped.

    Revenue is credit-natural and expense debit-natural, so the section sums to
    a credit in a profitable year. Negating it once here means every schedule
    that reports a result -- the equity income rows, the member income column,
    the balance sheet's current-year line -- reports the same number.
    """
    return -sum(
        v for a, v in balances.items()
        if (classification.get(a) or {}).get("section") == SECTION_PROFIT_LOSS
    )


def total_liabilities(
    balances: dict[str, int], classification: dict[str, dict[str, Any]]
) -> int:
    """Liabilities presented positive, for the members' liability shares."""
    return -sum(
        v for a, v in balances.items()
        if (classification.get(a) or {}).get("is_liability") is True
    )


def derived_equity_total(
    prior_total_cents: int, flow_cents: Sequence[int], net_income_cents: int
) -> int:
    """Closing equity: what was there, plus the year's flows, plus the result."""
    return prior_total_cents + sum(flow_cents) + net_income_cents


def member_closing(
    opening_cents: int,
    contributions_cents: int,
    income_cents: int,
    distributions_cents: int,
) -> int:
    """A member's capital at the end of a year block.

    Distributions are subtracted as their own column rather than carried as a
    negative contribution, so a return of capital stays visible instead of
    quietly shrinking what the member is shown to have put in.
    """
    return opening_cents + contributions_cents + income_cents - distributions_cents


def tax_basis(capital_cents: int, liability_share_cents: int) -> int:
    """Outside basis: tax-basis capital plus the member's share of liabilities.

    The liability share is the half of basis that has no cell on the book
    statement, so it is the half that gets dropped -- and a member whose basis is
    understated by the liabilities is a member whose loss deduction is limited by
    a number nobody meant.
    """
    return capital_cents + liability_share_cents


def ep_accumulated(prior_accumulated_cents: int, current_taxable_cents: int) -> int:
    """Accumulated earnings and profits at the end of a year."""
    return prior_accumulated_cents + current_taxable_cents


def retained_earnings_beginning(
    prior_retained_earnings_cents: int, prior_net_income_cents: int
) -> int:
    """Retained earnings at the start of the year, presented positive.

    Last year's beginning balance plus last year's result. This is the roll that
    gets skipped when a package is built by copying the prior file: the account
    keeps last year's opening figure, the balance sheet still balances because
    the ledger was harvested for everything else, and the equity schedule is
    understated by exactly one year of earnings.
    """
    return prior_retained_earnings_cents + prior_net_income_cents


# --------------------------------------------------------------------------- #
# Cell flattening -- the vocabulary the edit-scope control speaks
# --------------------------------------------------------------------------- #
def _put(cells: dict[str, Any], cell_id: str, value: Any) -> None:
    if value is not None:
        cells[cell_id] = value


def flatten_cells(package: dict[str, Any] | None) -> dict[str, Any]:
    """Flatten a package into ``{cell_id: value}``.

    Cells are keyed by ``<schedule>/<row key>/<field>`` and never by position.
    That matters: a workpaper that has been re-sorted holds exactly the same
    cells, and an index-keyed comparison would report every row below the sort as
    edited while missing the one thing a sort actually breaks -- the order of a
    frozen history, which :mod:`.engine` polices separately.
    """
    cells: dict[str, Any] = {}
    if not isinstance(package, dict):
        return cells

    captions = package.get("captions")
    if isinstance(captions, dict):
        for key, value in captions.items():
            _put(cells, f"captions/{key}", value)

    tb = package.get("trial_balance")
    if isinstance(tb, dict):
        for row in tb.get("rows", []) or []:
            if not isinstance(row, dict):
                continue
            account = str(row.get("account", ""))
            for fld in TB_CELL_FIELDS:
                _put(cells, f"trial_balance/{account}/{fld}", row.get(fld))

    for name in ("balance_sheet", "profit_loss"):
        sched = package.get(name)
        if not isinstance(sched, dict):
            continue
        for row in sched.get("rows", []) or []:
            if not isinstance(row, dict):
                continue
            row_id = str(row.get("row_id", ""))
            _put(cells, f"{name}/{row_id}/caption", row.get("caption"))
            _put(cells, f"{name}/{row_id}/amount_cents", row.get("amount_cents"))
        _put(cells, f"{name}/TOTAL/amount_cents", sched.get("total_cents"))
        _put(cells, f"{name}/TOTAL_EQUITY/amount_cents", sched.get("total_equity_cents"))
        _put(cells, f"{name}/NET_INCOME/amount_cents", sched.get("net_income_cents"))

    equity = package.get("equity")
    if isinstance(equity, dict):
        for row in equity.get("rows", []) or []:
            if not isinstance(row, dict):
                continue
            row_id = str(row.get("row_id", ""))
            _put(cells, f"equity/{row_id}/caption", row.get("caption"))
            _put(cells, f"equity/{row_id}/amount_cents", row.get("amount_cents"))
        _put(cells, "equity/TOTAL/amount_cents", equity.get("total_cents"))

    member = package.get("member_capital")
    if isinstance(member, dict):
        for block in member.get("blocks", []) or []:
            if not isinstance(block, dict):
                continue
            block_id = str(block.get("block_id", ""))
            for fld in MEMBER_CELL_FIELDS:
                _put(cells, f"member_capital/{block_id}/{fld}", block.get(fld))

    ep = package.get("earnings_and_profits")
    if isinstance(ep, dict):
        for block in ep.get("blocks", []) or []:
            if not isinstance(block, dict):
                continue
            block_id = str(block.get("block_id", ""))
            for fld in EP_CELL_FIELDS:
                _put(cells, f"earnings_and_profits/{block_id}/{fld}", block.get(fld))

    evidence = package.get("evidence")
    if isinstance(evidence, dict):
        for row in evidence.get("rows", []) or []:
            if not isinstance(row, dict):
                continue
            account = str(row.get("account", ""))
            for fld in EVIDENCE_CELL_FIELDS:
                _put(cells, f"evidence/{account}/{fld}", row.get(fld))
        _put(cells, "evidence/SUBTOTAL/amount_cents", evidence.get("subtotal_cents"))
        citation = evidence.get("citation")
        if isinstance(citation, dict):
            for fld in CITATION_FIELDS:
                _put(cells, f"evidence/citation/{fld}", citation.get(fld))

    notes = package.get("notes")
    if isinstance(notes, dict):
        for row in notes.get("rows", []) or []:
            if not isinstance(row, dict):
                continue
            _put(cells, f"notes/{row.get('note_id', '')}/text", row.get("text"))

    return cells


def prior_as_package(prior_year: dict[str, Any] | None) -> dict[str, Any]:
    """View the prior package in the shape the built package uses.

    The pre-build image is the working file as it stood *before* the build ran --
    which is last year's package, sitting in this year's file. Rendering it
    through the same shape means the two are flattened by the same code, so a
    difference in the diff is a difference in the workpaper rather than a
    difference in how the two sides were read.
    """
    if not isinstance(prior_year, dict):
        return {}
    return {
        "captions": copy.deepcopy(prior_year.get("captions") or {}),
        "trial_balance": copy.deepcopy(prior_year.get("trial_balance") or {}),
        "equity": copy.deepcopy(prior_year.get("equity") or {}),
        "member_capital": copy.deepcopy(prior_year.get("member_capital") or {}),
        "earnings_and_profits": copy.deepcopy(
            prior_year.get("earnings_and_profits") or {}
        ),
        "notes": copy.deepcopy(prior_year.get("notes") or {}),
    }


def capture_prebuild_image(
    prior_year: dict[str, Any] | None, *, captured_at: str, document_id: str
) -> dict[str, Any]:
    """Take the backup image the build will later be diffed against.

    Custody, not cleanliness: the point of the image is that it was taken before
    anything moved, and the digest recorded in the manifest is what proves the
    image on disk is still the one that was taken.
    """
    return {
        "doc_type": "prebuild_image",
        "document_id": document_id,
        "captured_at": captured_at,
        "cells": flatten_cells(prior_as_package(prior_year)),
    }


def prebuild_digest_payload(image: dict[str, Any] | None) -> dict[str, Any]:
    """The part of a pre-build image the manifest digest covers."""
    if not isinstance(image, dict):
        return {}
    return {"captured_at": image.get("captured_at"), "cells": image.get("cells")}


def rendered_strings(payload: Any, path: str = "") -> Iterator[tuple[str, str]]:
    """Every string in a package, with the path it sits at.

    Rendering hygiene is a property of what a reviewer *reads*, so the sweep
    walks the whole package rather than a list of fields somebody remembered to
    add. A caption, a display value, a note and a citation are all text on the
    page.
    """
    if isinstance(payload, str):
        yield (path or "-", payload)
    elif isinstance(payload, dict):
        for key in sorted(payload, key=str):
            child = f"{path}/{key}" if path else str(key)
            yield from rendered_strings(payload[key], child)
    elif isinstance(payload, list):
        for i, item in enumerate(payload):
            yield from rendered_strings(item, f"{path}[{i}]")


# --------------------------------------------------------------------------- #
# The build register
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RegisterEntry:
    """One constructed cell and the derivation that produced it."""

    cell_id: str
    schedule: str
    row_id: str
    field: str
    derivation: str
    value: Any

    def to_dict(self) -> dict:
        """Return a JSON-serialisable representation of the entry."""
        return {
            "cell_id": self.cell_id,
            "schedule": self.schedule,
            "row_id": self.row_id,
            "field": self.field,
            "derivation": self.derivation,
            "value": self.value,
        }


class _Register:
    """Accumulates register entries as the build writes cells."""

    def __init__(self) -> None:
        self.entries: list[RegisterEntry] = []
        self._seen: set[str] = set()

    def add(
        self, schedule: str, row_id: str, fld: str, derivation: str, value: Any
    ) -> None:
        cell_id = f"{schedule}/{row_id}/{fld}" if row_id else f"{schedule}/{fld}"
        if cell_id in self._seen:
            return
        self._seen.add(cell_id)
        self.entries.append(
            RegisterEntry(cell_id, schedule, row_id, fld, derivation, value)
        )


def register_cell_ids(build_register: dict[str, Any] | None) -> set[str]:
    """The set of cell ids a build register claims to have constructed."""
    if not isinstance(build_register, dict):
        return set()
    out: set[str] = set()
    for entry in build_register.get("entries", []) or []:
        if isinstance(entry, dict) and isinstance(entry.get("cell_id"), str):
            out.add(entry["cell_id"])
    return out


# --------------------------------------------------------------------------- #
# The package
# --------------------------------------------------------------------------- #
@dataclass
class WorkpaperPackage:
    """The constructed package: schedules, register and manifest."""

    entity_block: str
    fiscal_year: int
    prior_fiscal_year: int
    captions: dict[str, str]
    trial_balance: dict[str, Any]
    balance_sheet: dict[str, Any]
    profit_loss: dict[str, Any]
    equity: dict[str, Any]
    member_capital: dict[str, Any]
    earnings_and_profits: dict[str, Any]
    evidence: dict[str, Any]
    notes: dict[str, Any]
    build_register: list[RegisterEntry] = field(default_factory=list)
    locked_source_digest: str = ""
    prebuild_image_digest: str = ""
    harvest_date: str = ""

    @property
    def document_id(self) -> str:
        """Stable identifier of the built package."""
        return f"WP-{self.entity_block}-FY{self.fiscal_year}"

    def package_doc(self) -> dict[str, Any]:
        """The built package as a typed document."""
        return {
            "doc_type": "built_package",
            "document_id": self.document_id,
            "entity_block": self.entity_block,
            "fiscal_year": self.fiscal_year,
            "prior_fiscal_year": self.prior_fiscal_year,
            "captions": self.captions,
            "trial_balance": self.trial_balance,
            "balance_sheet": self.balance_sheet,
            "profit_loss": self.profit_loss,
            "equity": self.equity,
            "member_capital": self.member_capital,
            "earnings_and_profits": self.earnings_and_profits,
            "evidence": self.evidence,
            "notes": self.notes,
        }

    def register_doc(self) -> dict[str, Any]:
        """The build register as a typed document."""
        return {
            "doc_type": "build_register",
            "document_id": f"BR-{self.entity_block}-FY{self.fiscal_year}",
            "entries": [e.to_dict() for e in self.build_register],
        }

    def manifest_doc(self) -> dict[str, Any]:
        """The chain-of-custody manifest as a typed document."""
        return {
            "doc_type": "manifest",
            "document_id": f"MF-{self.entity_block}-FY{self.fiscal_year}",
            "entity_block": self.entity_block,
            "fiscal_year": self.fiscal_year,
            "prior_fiscal_year": self.prior_fiscal_year,
            "harvest_date": self.harvest_date,
            "locked_source_digest": self.locked_source_digest,
            "prebuild_image_digest": self.prebuild_image_digest,
            "built_package_digest": digest_payload(self.package_doc()),
        }

    def cells(self) -> dict[str, Any]:
        """The built package flattened into ``{cell_id: value}``."""
        return flatten_cells(self.package_doc())

    def to_dict(self) -> dict[str, Any]:
        """Package, register and manifest together, ready to serialise."""
        return {
            "built_package": self.package_doc(),
            "build_register": self.register_doc(),
            "manifest": self.manifest_doc(),
        }


# --------------------------------------------------------------------------- #
# build_package -- the headline
# --------------------------------------------------------------------------- #
def build_package(
    sources: dict[str, Any],
    prior_year: dict[str, Any],
    registers: dict[str, Any],
) -> WorkpaperPackage:
    """Construct a tax workpaper package for a new fiscal year.

    Args:
        sources: The locked current-year general-ledger extract: ``entity_block``,
            ``fiscal_year``, ``rows`` (account, title, balance, entity block),
            the citation fields, and the year's book-to-tax adjustment.
        prior_year: Last year's signed workpaper package: captions,
            classification map, trial balance, equity schedule with its total,
            member capital blocks, earnings-and-profits blocks and notes.
        registers: ``{"allocation": ..., "exception": ..., "counterpart_stub":
            ..., "prebuild_image": ...}``. The allocation register carries the
            member split pairs in basis points; the pre-build image is the
            custody backup the build's edit scope is later diffed against.

    Returns:
        A :class:`WorkpaperPackage` carrying every schedule, the build register
        naming each constructed cell, and the manifest digests.
    """
    entity_block = str(sources.get("entity_block", ""))
    fiscal_year = int(sources.get("fiscal_year", 0))
    prior_fy = int(prior_year.get("fiscal_year", 0))
    step = fiscal_year - prior_fy

    reg = _Register()
    classification = classification_map(prior_year)
    priors = prior_balances(prior_year)
    harvested = source_rows(sources, entity_block)
    current = {
        str(r.get("account", "")): int(r.get("balance_cents", 0)) for r in harvested
    }

    # ---- 4. Captions ------------------------------------------------------- #
    prior_caps = prior_captions(prior_year)
    captions: dict[str, str] = {}
    for caption_id in CAPTION_IDS:
        text = prior_caps.get(caption_id, "")
        rolled = advance_year_text(text, step)
        captions[caption_id] = rolled
        reg.add(
            "captions", "", caption_id,
            f"prior-year caption advanced {step} year(s)", rolled,
        )

    # ---- 1/2/3. Harvest, trial balance, classification --------------------- #
    tb_rows: list[dict[str, Any]] = []
    for row in harvested:
        account = str(row.get("account", ""))
        balance = int(row.get("balance_cents", 0))
        if balance == 0:
            # A flat account carries no figure onto the workpaper. It stays on
            # the evidence tab, where completeness can still be proved against it.
            continue
        info = classification.get(account) or {}
        tb_row = {
            "account": account,
            "title": str(row.get("title", "")),
            "balance_cents": balance,
            "section": str(info.get("section", "")),
            "display": fmt(balance),
        }
        tb_rows.append(tb_row)
        reg.add(
            "trial_balance", account, "balance_cents",
            f"locked source balance column, account {account}, block {entity_block}",
            balance,
        )
        reg.add(
            "trial_balance", account, "title",
            f"locked source title column, account {account}", tb_row["title"],
        )
        reg.add(
            "trial_balance", account, "display",
            f"integer cents formatted, account {account}", tb_row["display"],
        )
    trial_balance = {"title": captions["trial_balance_title"], "rows": tb_rows}

    tb_balances = {r["account"]: int(r["balance_cents"]) for r in tb_rows}
    result_cents = net_income(tb_balances, classification)

    # ---- Statement of operations ------------------------------------------ #
    pl_rows: list[dict[str, Any]] = []
    for row in tb_rows:
        if row["section"] != SECTION_PROFIT_LOSS:
            continue
        pl_rows.append({
            "row_id": row["account"],
            "caption": row["title"],
            "amount_cents": row["balance_cents"],
        })
        reg.add(
            "profit_loss", row["account"], "amount_cents",
            "trial balance row classified profit_loss by the prior-year map",
            row["balance_cents"],
        )
        reg.add(
            "profit_loss", row["account"], "caption",
            "trial balance title", row["title"],
        )
    profit_loss = {
        "title": captions["profit_loss_title"],
        "rows": pl_rows,
        "total_cents": sum(r["amount_cents"] for r in pl_rows),
        "net_income_cents": result_cents,
    }
    reg.add(
        "profit_loss", "", "TOTAL/amount_cents",
        "sum of the classified profit_loss rows", profit_loss["total_cents"],
    )
    reg.add(
        "profit_loss", "", "NET_INCOME/amount_cents",
        "statement of operations total, sign-flipped to a result", result_cents,
    )

    # ---- Balance sheet ----------------------------------------------------- #
    bs_rows: list[dict[str, Any]] = []
    for row in tb_rows:
        if row["section"] not in (SECTION_BALANCE_SHEET, SECTION_EQUITY):
            continue
        bs_rows.append({
            "row_id": row["account"],
            "caption": row["title"],
            "amount_cents": row["balance_cents"],
            "section": row["section"],
        })
        reg.add(
            "balance_sheet", row["account"], "amount_cents",
            f"trial balance row classified {row['section']} by the prior-year map",
            row["balance_cents"],
        )
        reg.add(
            "balance_sheet", row["account"], "caption",
            "trial balance title", row["title"],
        )
    bs_rows.append({
        "row_id": "NET_INCOME",
        "caption": "Result for the year",
        "amount_cents": -result_cents,
        "section": SECTION_EQUITY,
    })
    reg.add(
        "balance_sheet", "NET_INCOME", "amount_cents",
        "the year's result, carried into equity as a credit", -result_cents,
    )
    reg.add(
        "balance_sheet", "NET_INCOME", "caption", "constructed caption",
        "Result for the year",
    )
    bs_total = sum(r["amount_cents"] for r in bs_rows)
    bs_total_equity = -sum(
        r["amount_cents"] for r in bs_rows if r["section"] == SECTION_EQUITY
    )
    balance_sheet = {
        "title": captions["balance_sheet_title"],
        "rows": bs_rows,
        "total_cents": bs_total,
        "total_equity_cents": bs_total_equity,
    }
    reg.add(
        "balance_sheet", "", "TOTAL/amount_cents",
        "sum of every balance sheet row; a classified statement foots to zero",
        bs_total,
    )
    reg.add(
        "balance_sheet", "", "TOTAL_EQUITY/amount_cents",
        "equity-section rows presented positive", bs_total_equity,
    )

    # ---- 5. Equity --------------------------------------------------------- #
    prior_equity = prior_year.get("equity") or {}
    prior_rows = copy.deepcopy(prior_equity.get("rows") or [])
    prior_total = int(prior_equity.get("total_cents", 0))

    # The prior layers are carried over untouched -- not re-derived, not
    # re-formatted, not re-sorted. History that can move is not history.
    equity_rows: list[dict[str, Any]] = list(prior_rows)

    flow_accounts = sorted(
        a for a, info in classification.items()
        if info.get("section") == SECTION_EQUITY
        and info.get("equity_kind") in (EQUITY_CONTRIBUTION, EQUITY_DISTRIBUTION)
        and (current.get(a, 0) != 0 or priors.get(a, 0) != 0)
    )
    flow_cents: list[int] = []
    for account in flow_accounts:
        info = classification[account]
        amount = flow_amount(current.get(account, 0), priors.get(account, 0))
        flow_cents.append(amount)
        row_id = f"EQ-{fiscal_year}-{account}"
        caption = f"{info.get('title', account)} - fiscal year {fiscal_year}"
        equity_rows.append({
            "row_id": row_id,
            "caption": caption,
            "year": fiscal_year,
            "role": (
                ROLE_CONTRIBUTION
                if info.get("equity_kind") == EQUITY_CONTRIBUTION
                else ROLE_DISTRIBUTION
            ),
            "account": account,
            "member_id": info.get("member_id"),
            "row_form": row_form(priors.get(account, 0)),
            "formula_present": False,
            "amount_cents": amount,
        })
        reg.add(
            "equity", row_id, "amount_cents",
            f"account {account}: current source balance less prior-year balance",
            amount,
        )
        reg.add("equity", row_id, "caption", "constructed current-year caption", caption)

    members = member_list(registers)
    income_split = split_pairs(registers).get(SPLIT_ORDINARY_INCOME, {})
    member_ids = [str(m.get("member_id", "")) for m in members]
    income_weights = [income_split.get(m, 0) for m in member_ids]
    income_shares = (
        allocate_by_ratio(result_cents, income_weights)
        if sum(income_weights) == BPS_FULL and member_ids
        else [0] * len(member_ids)
    )
    for member, share in zip(members, income_shares, strict=False):
        member_id = str(member.get("member_id", ""))
        row_id = f"EQ-{fiscal_year}-INC-{member_id}"
        caption = (
            f"Net income allocated - {member.get('member_name', member_id)} "
            f"- fiscal year {fiscal_year}"
        )
        equity_rows.append({
            "row_id": row_id,
            "caption": caption,
            "year": fiscal_year,
            "role": ROLE_INCOME,
            "member_id": member_id,
            "amount_cents": share,
        })
        reg.add(
            "equity", row_id, "amount_cents",
            f"result for the year allocated on the carried {SPLIT_ORDINARY_INCOME} split",
            share,
        )
        reg.add("equity", row_id, "caption", "constructed current-year caption", caption)

    equity_total = derived_equity_total(prior_total, flow_cents, result_cents)
    closing_id = f"EQ-{fiscal_year}-BAL"
    equity_rows.append({
        "row_id": closing_id,
        "caption": captions["equity_closing"],
        "year": fiscal_year,
        "role": ROLE_CLOSING,
        "amount_cents": equity_total,
    })
    reg.add(
        "equity", closing_id, "amount_cents",
        "prior-year total plus current-year flows plus the result", equity_total,
    )
    reg.add(
        "equity", closing_id, "caption", "rolled closing caption",
        captions["equity_closing"],
    )
    reg.add(
        "equity", "", "TOTAL/amount_cents", "the closing balance row", equity_total,
    )
    equity = {
        "title": captions["equity_title"],
        "rows": equity_rows,
        "total_cents": equity_total,
        "prior_total_cents": prior_total,
    }

    # ---- 6. Member capital accounts ---------------------------------------- #
    prior_member = prior_year.get("member_capital") or {}
    blocks: list[dict[str, Any]] = copy.deepcopy(prior_member.get("blocks") or [])

    tax_adjustment = int(sources.get("tax_adjustment_cents", 0))
    taxable_cents = result_cents + tax_adjustment
    taxable_shares = (
        allocate_by_ratio(taxable_cents, income_weights)
        if sum(income_weights) == BPS_FULL and member_ids
        else [0] * len(member_ids)
    )
    liability_split = split_pairs(registers).get(SPLIT_LIABILITY_SHARE, {})
    liability_weights = [liability_split.get(m, 0) for m in member_ids]
    liabilities_cents = total_liabilities(tb_balances, classification)
    liability_shares = (
        allocate_by_ratio(liabilities_cents, liability_weights)
        if sum(liability_weights) == BPS_FULL and member_ids
        else [0] * len(member_ids)
    )

    by_member_prior: dict[str, dict[str, Any]] = {}
    for block in blocks:
        member_id = str(block.get("member_id", ""))
        held = by_member_prior.get(member_id)
        if held is None or int(block.get("year", 0)) >= int(held.get("year", 0)):
            by_member_prior[member_id] = block

    for idx, member in enumerate(members):
        member_id = str(member.get("member_id", ""))
        last = by_member_prior.get(member_id) or {}
        contributions = sum(
            flow_cents[i] for i, a in enumerate(flow_accounts)
            if (classification[a].get("member_id") == member_id)
            and classification[a].get("equity_kind") == EQUITY_CONTRIBUTION
        )
        distributions = -sum(
            flow_cents[i] for i, a in enumerate(flow_accounts)
            if (classification[a].get("member_id") == member_id)
            and classification[a].get("equity_kind") == EQUITY_DISTRIBUTION
        )
        opening_book = int(last.get("closing_book_cents", 0))
        opening_tax = int(last.get("closing_tax_cents", 0))
        income_book = income_shares[idx] if idx < len(income_shares) else 0
        income_tax = taxable_shares[idx] if idx < len(taxable_shares) else 0
        closing_book = member_closing(
            opening_book, contributions, income_book, distributions
        )
        closing_tax = member_closing(
            opening_tax, contributions, income_tax, distributions
        )
        share = liability_shares[idx] if idx < len(liability_shares) else 0
        block_id = f"MC-{fiscal_year}-{member_id}"
        block = {
            "block_id": block_id,
            "member_id": member_id,
            "member_name": member.get("member_name", member_id),
            "year": fiscal_year,
            # The block caption names the member as well as the year. Two
            # members sharing one caption is how a dropped label hides: the
            # other member's copy is still on the page and the schedule reads
            # complete.
            "caption": f"{member.get('member_name', member_id)} - "
                       f"{captions['member_block_current']}",
            "opening_book_cents": opening_book,
            "contributions_book_cents": contributions,
            "income_book_cents": income_book,
            "distributions_book_cents": distributions,
            "closing_book_cents": closing_book,
            "opening_tax_cents": opening_tax,
            "contributions_tax_cents": contributions,
            "income_tax_cents": income_tax,
            "distributions_tax_cents": distributions,
            "closing_tax_cents": closing_tax,
            "liability_share_cents": share,
            "tax_basis_cents": tax_basis(closing_tax, share),
        }
        blocks.append(block)
        derivations = {
            "caption": "rolled current-year block caption",
            "opening_book_cents": "prior year block closing book capital",
            "contributions_book_cents": "current-year contribution flow rows for this member",
            "income_book_cents": f"result allocated on the carried {SPLIT_ORDINARY_INCOME} split",
            "distributions_book_cents": "current-year distribution flow rows for this member",
            "closing_book_cents": "opening plus contributions plus income less distributions",
            "opening_tax_cents": "prior year block closing tax capital",
            "contributions_tax_cents": "contributions, book and tax alike",
            "income_tax_cents": "taxable result allocated on the carried split",
            "distributions_tax_cents": "distributions, book and tax alike",
            "closing_tax_cents": "opening plus contributions plus income less distributions",
            "liability_share_cents": f"liabilities on the carried {SPLIT_LIABILITY_SHARE} split",
            "tax_basis_cents": "closing tax capital plus the member's liability share",
        }
        for fld, why in derivations.items():
            reg.add("member_capital", block_id, fld, why, block[fld])

    member_capital = {
        "title": captions["member_block_current"],
        "members": copy.deepcopy(members),
        "blocks": blocks,
    }

    # ---- 7. Earnings and profits ------------------------------------------- #
    prior_ep = prior_year.get("earnings_and_profits") or {}
    ep_blocks: list[dict[str, Any]] = copy.deepcopy(prior_ep.get("blocks") or [])
    last_ep = ep_blocks[-1] if ep_blocks else {}
    ep_prior_accumulated = int(last_ep.get("accumulated_end_cents", 0))
    ep_block_id = f"EP-{fiscal_year}"
    ep_block = {
        "block_id": ep_block_id,
        "year": fiscal_year,
        "caption": captions["ep_block_current"],
        "prior_accumulated_cents": ep_prior_accumulated,
        "current_taxable_cents": taxable_cents,
        "accumulated_end_cents": ep_accumulated(ep_prior_accumulated, taxable_cents),
    }
    ep_blocks.append(ep_block)
    for fld, why in {
        "caption": "rolled current-year block caption",
        "prior_accumulated_cents": "prior block accumulated at year end",
        "current_taxable_cents": "result for the year plus the book-to-tax adjustment",
        "accumulated_end_cents": "prior accumulated plus current taxable",
    }.items():
        reg.add("earnings_and_profits", ep_block_id, fld, why, ep_block[fld])
    earnings_and_profits = {"blocks": ep_blocks}

    # ---- 8. Evidence -------------------------------------------------------- #
    evidence_rows: list[dict[str, Any]] = []
    for row in harvested:
        account = str(row.get("account", ""))
        balance = int(row.get("balance_cents", 0))
        evidence_rows.append({
            "account": account,
            "title": str(row.get("title", "")),
            "balance_cents": balance,
            "display": fmt(balance),
        })
        for fld, why in {
            "balance_cents": f"harvested from the locked source, account {account}",
            "title": f"locked source title column, account {account}",
            "display": f"integer cents formatted, account {account}",
        }.items():
            reg.add("evidence", account, fld, why, evidence_rows[-1][fld])
    subtotal = sum(r["balance_cents"] for r in evidence_rows)
    citation = {
        "source_file": str(sources.get("source_file", "")),
        "tab": str(sources.get("tab", "")),
        "balance_column": str(sources.get("balance_column", "")),
        "harvest_date": str(sources.get("harvest_date", "")),
    }
    for fld in CITATION_FIELDS:
        reg.add(
            "evidence", "citation", fld,
            "declared by the locked source extract", citation[fld],
        )
    reg.add(
        "evidence", "", "SUBTOTAL/amount_cents",
        "sum of every harvested row; a complete ledger foots to zero", subtotal,
    )
    evidence = {
        "title": captions["evidence_title"],
        "rows": evidence_rows,
        "subtotal_cents": subtotal,
        "citation": citation,
    }

    notes = copy.deepcopy(prior_year.get("notes") or {"rows": []})

    prebuild = (registers or {}).get("prebuild_image")
    return WorkpaperPackage(
        entity_block=entity_block,
        fiscal_year=fiscal_year,
        prior_fiscal_year=prior_fy,
        captions=captions,
        trial_balance=trial_balance,
        balance_sheet=balance_sheet,
        profit_loss=profit_loss,
        equity=equity,
        member_capital=member_capital,
        earnings_and_profits=earnings_and_profits,
        evidence=evidence,
        notes=notes,
        build_register=reg.entries,
        locked_source_digest=digest_payload(sources),
        prebuild_image_digest=digest_payload(prebuild_digest_payload(prebuild)),
        harvest_date=str(sources.get("harvest_date", "")),
    )
