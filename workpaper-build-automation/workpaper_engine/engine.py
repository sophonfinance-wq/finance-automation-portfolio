"""
Controls that prove what the build produced.
============================================

Twenty-four controls, every one of them an assertion about the **built**
package rather than about the inputs. The engine's product is the package that
:mod:`.build` constructs; these controls are the evidence that the package is
what the inputs support, and they run over the artifact exactly as it was
emitted -- read-only, exact ``==``, integer cents, no tolerance band.

Registry order is report order and follows the build:

* **carry** -- the frozen history, the rolled captions, the labels that survive;
* **derive** -- the current-year flows, the carried split, the income rows, the
  equity total, the tie to the balance sheet;
* **schedules** -- member capital, tax basis, earnings and profits, retained
  earnings, row form;
* **evidence** -- the support tab, its subtotal and its citation;
* **custody** -- the source digest, the backup digest, the edit scope;
* **completeness and hygiene** -- reciprocity, missing accounts, registered
  exceptions, rendering, and the surviving history labels.

Every control re-derives from :mod:`.build`, which is the same kernel the
builder used. That is the point: a control that reimplemented the arithmetic
would be testing whether two authors agreed, not whether the package is right.
What the control does *not* share with the builder is the artifact -- it reads
the emitted package back and compares it to a figure derived from the inputs,
so a package edited after the build is exactly what these controls catch.

A control whose evidence is missing reports ``FAIL``. It never passes: a PASS
on an artifact that is not there is worse than no report at all.
"""

from __future__ import annotations

import contextlib
import functools
import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from .build import (
    CAPTION_IDS,
    CITATION_FIELDS,
    advance_year_text,
    classification_map,
    digest_payload,
    ep_accumulated,
    equity_presented,
    flatten_cells,
    flow_amount,
    member_closing,
    member_list,
    net_income,
    prebuild_digest_payload,
    prior_balances,
    prior_captions,
    register_cell_ids,
    rendered_strings,
    retained_earnings_beginning,
    row_form,
    source_by_account,
    split_pairs,
    tax_basis,
    year_tokens,
)
from .model import (
    DOC_ALLOCATION_REGISTER,
    DOC_BUILD_REGISTER,
    DOC_BUILT_PACKAGE,
    DOC_COUNTERPART_STUB,
    DOC_EXCEPTION_REGISTER,
    DOC_LOCKED_SOURCE,
    DOC_MANIFEST,
    DOC_PREBUILD_IMAGE,
    DOC_PRIOR_PACKAGE,
    EQUITY_CONTRIBUTION,
    EQUITY_DISTRIBUTION,
    EQUITY_RETAINED_EARNINGS,
    EXC_MISLABELED,
    EXC_PLACEHOLDER,
    EXTERNAL_MARKERS,
    FORMULA_ERROR_MARKERS,
    PLACEHOLDER_PREFIX,
    ROLE_CLOSING,
    ROLE_CONTRIBUTION,
    ROLE_DISTRIBUTION,
    ROLE_INCOME,
    SECTION_EQUITY,
    SPLIT_ORDINARY_INCOME,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import BPS_FULL, AmountInvalidError, allocate_by_ratio, fmt, require_cents

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: The severity each rule reports when it fails outright. One control --
#: ``equity_ties_balance_sheet`` -- downgrades a single finding to FLAG when the
#: difference it found is one the package itself discloses; the declared
#: severity here is the one that applies when nothing discloses it.
SEVERITY: dict[str, Status] = {}

#: An external-workbook link, as it survives into rendered text.
_EXTERNAL_LINK_RE = re.compile(r"\[[^\]]*\.xls[xmb]?\]", re.IGNORECASE)


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~workpaper_engine.money.AmountInvalidError` as a finding."""
    return Finding(
        rule_id,
        SEVERITY.get(rule_id, Status.FAIL),
        f"amount:{exc.field}",
        f"{exc} -- amounts are integer cents and are never coerced",
    )


@contextlib.contextmanager
def amount_guard(rule_id: str, out: list[Finding]) -> Iterator[None]:
    """Contain a malformed amount to the one cell being read."""
    try:
        yield
    except AmountInvalidError as exc:
        out.append(amount_invalid_finding(rule_id, exc))


def check(rule_id: str) -> Callable[[CheckFn], CheckFn]:
    """Register ``fn`` in :data:`REGISTRY` under ``rule_id``."""

    def wrapper(fn: CheckFn) -> CheckFn:
        @functools.wraps(fn)
        def guarded(ctx: Context) -> list[Finding]:
            try:
                return fn(ctx)
            except AmountInvalidError as exc:
                return [amount_invalid_finding(rule_id, exc)]

        REGISTRY.append((rule_id, guarded))
        return guarded

    return wrapper


def _sev(rule_id: str, status: Status) -> Status:
    SEVERITY[rule_id] = status
    return status


# --------------------------------------------------------------------------- #
# Shared readers
# --------------------------------------------------------------------------- #
def _need(
    ctx: Context, rule: str, *doc_types: str
) -> tuple[list[dict[str, Any]], list[Finding]]:
    """Fetch the artifacts a control needs, reporting any that are absent."""
    docs: list[dict[str, Any]] = []
    missing: list[Finding] = []
    for doc_type in doc_types:
        found = ctx.one(doc_type)
        if found is None:
            missing.append(
                Finding(
                    rule,
                    Status.FAIL,
                    f"{doc_type}:-",
                    f"required artifact {doc_type!r} is absent, so this control "
                    "cannot be evidenced -- it reports rather than passing, "
                    "because a PASS on evidence that is not there is worse than "
                    "no report at all",
                )
            )
            docs.append({})
        else:
            docs.append(found)
    return docs, missing


def _rows(doc: dict[str, Any], *path: str) -> list[dict[str, Any]]:
    """Walk ``path`` into ``doc`` and return the list of dict rows found there."""
    node: Any = doc
    for key in path:
        if not isinstance(node, dict):
            return []
        node = node.get(key)
    if not isinstance(node, list):
        return []
    return [r for r in node if isinstance(r, dict)]


def _sub(doc: dict[str, Any], key: str) -> dict[str, Any]:
    """A sub-document of the built package, or an empty dict."""
    value = doc.get(key) if isinstance(doc, dict) else None
    return value if isinstance(value, dict) else {}


def _tb_balances(built: dict[str, Any]) -> dict[str, int]:
    """``{account: balance_cents}`` from the built trial balance."""
    out: dict[str, int] = {}
    for row in _rows(built, "trial_balance", "rows"):
        account = str(row.get("account", ""))
        value = row.get("balance_cents")
        if account and isinstance(value, int) and not isinstance(value, bool):
            out.setdefault(account, value)
    return out


def _current_source_balances(
    source: dict[str, Any], entity_block: str
) -> dict[str, int]:
    """``{account: balance_cents}`` from the locked source, scoped to the block."""
    return {
        account: int(row.get("balance_cents", 0))
        for account, row in source_by_account(source, entity_block).items()
    }


def _flow_accounts(
    classification: dict[str, dict[str, Any]],
    current: dict[str, int],
    priors: dict[str, int],
) -> list[str]:
    """The equity accounts that earn a current-year flow row, in account order."""
    return sorted(
        a for a, info in classification.items()
        if info.get("section") == SECTION_EQUITY
        and info.get("equity_kind") in (EQUITY_CONTRIBUTION, EQUITY_DISTRIBUTION)
        and (current.get(a, 0) != 0 or priors.get(a, 0) != 0)
    )


def _derived_equity_total(ctx: Context) -> int | None:
    """Closing equity re-derived from the inputs, never from the built total.

    Three controls need this figure -- the total itself, the tie to the balance
    sheet, and the tie to the member capital accounts -- and every one of them
    has to measure the package against the *inputs*. Reading the built total and
    comparing the other two to it would make one typed cell agree with itself
    three times.
    """
    built = ctx.one(DOC_BUILT_PACKAGE)
    prior = ctx.one(DOC_PRIOR_PACKAGE)
    source = ctx.one(DOC_LOCKED_SOURCE)
    if built is None or prior is None or source is None:
        return None
    classification = classification_map(prior)
    priors = prior_balances(prior)
    current = _current_source_balances(source, ctx.entity_block)
    accounts = _flow_accounts(classification, current, priors)
    flows = [flow_amount(current.get(a, 0), priors.get(a, 0)) for a in accounts]
    prior_total = int(_sub(prior, "equity").get("total_cents", 0))
    return prior_total + sum(flows) + net_income(current, classification)


def _current_equity_rows(built: dict[str, Any]) -> list[dict[str, Any]]:
    """Equity rows appended by this build (their year is the year being built)."""
    year = built.get("fiscal_year")
    return [r for r in _rows(built, "equity", "rows") if r.get("year") == year]


# --------------------------------------------------------------------------- #
# 1. Carry: the frozen history
# --------------------------------------------------------------------------- #
_SEV_FROZEN = _sev("frozen_layers_byte_equal", Status.FAIL)


@check("frozen_layers_byte_equal")
def check_frozen_layers_byte_equal(ctx: Context) -> list[Finding]:
    """Every prior-year layer is carried byte-equal, in the order it was signed.

    History is a constant. The layers below the current year were reviewed,
    agreed and filed, and the only correct thing to do with them is nothing.
    Byte-equality includes **order**: a schedule that has been re-sorted holds
    exactly the same cells and still foots, but the years no longer read in the
    sequence they happened, and the next roll will freeze the new arrangement as
    if it were the record.
    """
    rule = "frozen_layers_byte_equal"
    (built, prior), missing = _need(ctx, rule, DOC_BUILT_PACKAGE, DOC_PRIOR_PACKAGE)
    if missing:
        return missing
    out: list[Finding] = []
    prior_rows = _rows(prior, "equity", "rows")
    prior_ids = [str(r.get("row_id", "")) for r in prior_rows]
    id_set = set(prior_ids)
    carried = [
        r for r in _rows(built, "equity", "rows")
        if str(r.get("row_id", "")) in id_set
    ]
    if len(carried) != len(prior_rows):
        missing_ids = sorted(id_set - {str(r.get("row_id", "")) for r in carried})
        out.append(
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(built, "equity/rows"),
                f"the build carried {len(carried)} of {len(prior_rows)} prior-year "
                f"layers; absent: {missing_ids or 'none (duplicated instead)'} -- a "
                "layer that leaves the schedule takes a signed figure with it",
            )
        )
    for idx, (got, want) in enumerate(zip(carried, prior_rows, strict=False)):
        if digest_payload(got) == digest_payload(want):
            continue
        out.append(
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(built, f"equity/rows[{idx}]"),
                f"frozen layer at position {idx} is not the prior-year row: the "
                f"package carries {got.get('row_id')!r} "
                f"({fmt(int(got.get('amount_cents', 0)))}) where the prior package "
                f"has {want.get('row_id')!r} "
                f"({fmt(int(want.get('amount_cents', 0)))}) -- a prior layer that "
                "moves is a signed figure being restated a year later",
            )
        )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-",
                f"all {len(prior_rows)} prior-year layers carried byte-equal and in order",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 2. Carry: the rolled captions
# --------------------------------------------------------------------------- #
_SEV_CAPTIONS = _sev("captions_advance_one_year", Status.FAIL)


@check("captions_advance_one_year")
def check_captions_advance_one_year(ctx: Context) -> list[Finding]:
    """Every rolling caption advanced by exactly the step between the two years.

    The figures roll whether the labels do or not. A caption left at last year's
    date is the cheapest possible defect to create and one of the most expensive
    to find: a reviewer reconciles a current-year column against a prior-year
    heading, cannot make it agree, and has no reason to suspect the heading.
    """
    rule = "captions_advance_one_year"
    (built, prior), missing = _need(ctx, rule, DOC_BUILT_PACKAGE, DOC_PRIOR_PACKAGE)
    if missing:
        return missing
    out: list[Finding] = []
    prior_fy = int(prior.get("fiscal_year", 0))
    fiscal_year = int(built.get("fiscal_year", 0))
    step = fiscal_year - prior_fy
    if step < 1:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(built, "fiscal_year"),
                f"the package claims fiscal year {fiscal_year} rolled from "
                f"{prior_fy}; a roll advances at least one year",
            )
        )
        return out
    built_caps = _sub(built, "captions")
    prior_caps = prior_captions(prior)
    for caption_id in CAPTION_IDS:
        want = advance_year_text(prior_caps.get(caption_id, ""), step)
        got = built_caps.get(caption_id)
        loc = ctx.loc(built, f"captions/{caption_id}")
        if got != want:
            out.append(
                Finding(
                    rule, Status.FAIL, loc,
                    f"caption {caption_id!r} reads {got!r}; rolling the prior-year "
                    f"caption forward {step} year(s) gives {want!r} -- the label has "
                    "to move with the figures underneath it",
                )
            )
        if isinstance(got, str) and prior_fy in year_tokens(got):
            out.append(
                Finding(
                    rule, Status.FAIL, loc,
                    f"caption {caption_id!r} still names {prior_fy} after the roll; "
                    "a stale year on a rolled row sends the reader to the wrong "
                    "column of the wrong package",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-",
                f"all {len(CAPTION_IDS)} rolling captions advanced {step} year(s), "
                f"none still naming {prior_fy}",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 3. Derive: current-year capital flows
# --------------------------------------------------------------------------- #
_SEV_FLOW = _sev("capital_flow_equals_delta", Status.FAIL)


@check("capital_flow_equals_delta")
def check_capital_flow_equals_delta(ctx: Context) -> list[Finding]:
    """Each current-year flow row is the account's movement, not its balance.

    A contributions account holds every contribution since the entity was
    formed. Dropping that balance onto a current-year row restates the whole
    history as this year's activity -- and the schedule still foots, because the
    closing total was footed from the same row. Only the delta between the two
    year-ends belongs on the row.
    """
    rule = "capital_flow_equals_delta"
    (built, prior, source), missing = _need(
        ctx, rule, DOC_BUILT_PACKAGE, DOC_PRIOR_PACKAGE, DOC_LOCKED_SOURCE
    )
    if missing:
        return missing
    out: list[Finding] = []
    classification = classification_map(prior)
    priors = prior_balances(prior)
    current = _current_source_balances(source, ctx.entity_block)
    expected_accounts = _flow_accounts(classification, current, priors)
    seen: set[str] = set()
    for row in _current_equity_rows(built):
        if row.get("role") not in (ROLE_CONTRIBUTION, ROLE_DISTRIBUTION):
            continue
        account = str(row.get("account", ""))
        seen.add(account)
        want = flow_amount(current.get(account, 0), priors.get(account, 0))
        loc = ctx.loc(built, f"equity/rows[{row.get('row_id')}]/amount_cents")
        with amount_guard(rule, out):
            got = require_cents(
                f"equity[{row.get('row_id')}]/amount_cents", row.get("amount_cents")
            )
            if got != want:
                out.append(
                    Finding(
                        rule, Status.FAIL, loc,
                        f"account {account} carries {fmt(got)} on the current-year "
                        f"row; the source balance less the prior-year balance is "
                        f"{fmt(want)} (source {fmt(current.get(account, 0))}, prior "
                        f"{fmt(priors.get(account, 0))}) -- a flow row is a movement, "
                        "never a balance",
                    )
                )
    for account in expected_accounts:
        if account in seen:
            continue
        out.append(
            Finding(
                rule, Status.FAIL, ctx.loc(built, "equity/rows"),
                f"equity account {account} moved by "
                f"{fmt(flow_amount(current.get(account, 0), priors.get(account, 0)))} "
                "and the build produced no current-year row for it",
            )
        )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-",
                f"all {len(expected_accounts)} current-year capital flows equal the "
                "source-less-prior delta for their account",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 4. Derive: the carried split
# --------------------------------------------------------------------------- #
_SEV_SPLIT = _sev("split_pairs_sum_to_one", Status.FAIL)


@check("split_pairs_sum_to_one")
def check_split_pairs_sum_to_one(ctx: Context) -> list[Finding]:
    """Every split pair carried into the new year sums to exactly 100.00%.

    A split that sums to 100.01% allocates a result the entity did not earn, and
    the overage lands wherever the largest remainder happens to fall. Because
    every schedule downstream is derived from the split, the error is not
    reported once -- it is reported in the equity income rows, in both members'
    capital accounts and in both liability shares, each in a different amount.
    """
    rule = "split_pairs_sum_to_one"
    (allocation,), missing = _need(ctx, rule, DOC_ALLOCATION_REGISTER)
    if missing:
        return missing
    out: list[Finding] = []
    registers = {"allocation": allocation}
    pairs = split_pairs(registers)
    members = [str(m.get("member_id", "")) for m in member_list(registers)]
    if not pairs:
        out.append(
            Finding(
                rule, Status.FAIL, ctx.loc(allocation, "splits"),
                "the allocation register carries no split pairs; the build has "
                "nothing to allocate the year's result on",
            )
        )
    for purpose in sorted(pairs):
        pair = pairs[purpose]
        loc = ctx.loc(allocation, f"splits/{purpose}")
        got = sum(pair.values())
        if got != BPS_FULL:
            out.append(
                Finding(
                    rule, Status.FAIL, loc,
                    f"the {purpose!r} split sums to {got} basis points, not "
                    f"{BPS_FULL}; a pair that is not exactly one allocates a whole "
                    "the entity never had",
                )
            )
        for member_id in members:
            if member_id not in pair:
                out.append(
                    Finding(
                        rule, Status.FAIL, loc,
                        f"member {member_id!r} carries no {purpose!r} split; an "
                        "omitted member is allocated nothing and nobody is told",
                    )
                )
        for member_id, bps in sorted(pair.items()):
            if bps < 0:
                out.append(
                    Finding(
                        rule, Status.FAIL, loc,
                        f"member {member_id!r} carries a negative {purpose!r} split "
                        f"of {bps} basis points",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-",
                f"all {len(pairs)} carried split pairs sum to exactly {BPS_FULL} "
                "basis points across every member",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 5. Derive: the income rows
# --------------------------------------------------------------------------- #
_SEV_INCOME = _sev("income_split_rows_exact", Status.FAIL)


@check("income_split_rows_exact")
def check_income_split_rows_exact(ctx: Context) -> list[Finding]:
    """Each income row is the result allocated on that member's carried split.

    Allocation is done by largest remainder so the member rows sum back to the
    result exactly. A row computed on last year's ratio, or rounded
    independently, breaks that: the two rows still look plausible and their sum
    is a cent or a thousand away from the statement of operations above them.

    When the split pair itself does not sum to one, ``split_pairs_sum_to_one``
    owns the finding and this control stands down rather than measuring the rows
    against a ratio the package does not have.
    """
    rule = "income_split_rows_exact"
    (built, allocation), missing = _need(
        ctx, rule, DOC_BUILT_PACKAGE, DOC_ALLOCATION_REGISTER
    )
    if missing:
        return missing
    out: list[Finding] = []
    registers = {"allocation": allocation}
    members = member_list(registers)
    member_ids = [str(m.get("member_id", "")) for m in members]
    pair = split_pairs(registers).get(SPLIT_ORDINARY_INCOME, {})
    weights = [pair.get(m, 0) for m in member_ids]
    if not member_ids or sum(weights) != BPS_FULL:
        return []
    result = int(_sub(built, "profit_loss").get("net_income_cents", 0))
    want = dict(zip(member_ids, allocate_by_ratio(result, weights), strict=False))
    got: dict[str, int] = {}
    for row in _current_equity_rows(built):
        if row.get("role") != ROLE_INCOME:
            continue
        member_id = str(row.get("member_id", ""))
        with amount_guard(rule, out):
            got[member_id] = require_cents(
                f"equity[{row.get('row_id')}]/amount_cents", row.get("amount_cents")
            )
    for member_id in member_ids:
        loc = ctx.loc(built, f"equity/rows[income/{member_id}]/amount_cents")
        if member_id not in got:
            out.append(
                Finding(
                    rule, Status.FAIL, loc,
                    f"no current-year income row for member {member_id!r}; a member "
                    "with no allocation row is a member whose capital account will "
                    "never agree with the equity schedule",
                )
            )
            continue
        if got[member_id] != want[member_id]:
            out.append(
                Finding(
                    rule, Status.FAIL, loc,
                    f"member {member_id!r} is allocated {fmt(got[member_id])}; "
                    f"{fmt(result)} at {pair.get(member_id, 0)} basis points is "
                    f"{fmt(want[member_id])} -- the income rows have to sum back to "
                    "the statement of operations to the cent",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-",
                f"the result of {fmt(result)} is allocated exactly across "
                f"{len(member_ids)} members on the carried split",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 6. Derive: the equity total
# --------------------------------------------------------------------------- #
_SEV_EQ_TOTAL = _sev("equity_total_rolls", Status.FAIL)


@check("equity_total_rolls")
def check_equity_total_rolls(ctx: Context) -> list[Finding]:
    """Closing equity is last year's total plus this year's flows and result.

    Stated against the *inputs*, not against the rows above it. A total footed
    from the rows agrees with the rows whatever the rows say; a total derived
    from the prior package's closing figure, the source deltas and the statement
    of operations is a second opinion, and a typed-over total has nowhere to
    hide from it.
    """
    rule = "equity_total_rolls"
    (built, prior, source), missing = _need(
        ctx, rule, DOC_BUILT_PACKAGE, DOC_PRIOR_PACKAGE, DOC_LOCKED_SOURCE
    )
    if missing:
        return missing
    out: list[Finding] = []
    want = _derived_equity_total(ctx)
    equity = _sub(built, "equity")
    prior_total = int(_sub(prior, "equity").get("total_cents", 0))
    with amount_guard(rule, out):
        got = require_cents("equity/total_cents", equity.get("total_cents"))
        if want is not None and got != want:
            out.append(
                Finding(
                    rule, Status.FAIL, ctx.loc(built, "equity/total_cents"),
                    f"the equity schedule closes at {fmt(got)}; the prior-year total "
                    f"of {fmt(prior_total)} plus the current-year flows and the "
                    f"result derives {fmt(want)}, a difference of {fmt(got - want)}",
                )
            )
    closing = [
        r for r in _current_equity_rows(built) if r.get("role") == ROLE_CLOSING
    ]
    for row in closing:
        with amount_guard(rule, out):
            amount = require_cents(
                f"equity[{row.get('row_id')}]/amount_cents", row.get("amount_cents")
            )
            if want is not None and amount != want:
                out.append(
                    Finding(
                        rule, Status.FAIL,
                        ctx.loc(built, f"equity/rows[{row.get('row_id')}]"),
                        f"the closing balance row reads {fmt(amount)} against a "
                        f"derived {fmt(want)}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-",
                f"closing equity of {fmt(want or 0)} equals the prior total plus "
                "flows plus the result",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 7. Derive: the tie to the balance sheet
# --------------------------------------------------------------------------- #
_SEV_EQ_BS = _sev("equity_ties_balance_sheet", Status.FAIL)


@check("equity_ties_balance_sheet")
def check_equity_ties_balance_sheet(ctx: Context) -> list[Finding]:
    """Total equity on the balance sheet equals the equity schedule.

    Two statements built from the same ledger have to agree about the same
    number, and when they do not, the package is telling a partner one figure
    and the return another. A difference the package itself discloses is a
    review signal rather than a failure -- the engine can confirm the disclosure
    exists and quantifies the exact difference, but it cannot confirm the
    disclosure is *right*, and that judgement belongs to a person.
    """
    rule = "equity_ties_balance_sheet"
    (built, prior, source, exceptions), missing = _need(
        ctx, rule, DOC_BUILT_PACKAGE, DOC_PRIOR_PACKAGE, DOC_LOCKED_SOURCE,
        DOC_EXCEPTION_REGISTER,
    )
    if missing:
        return missing
    out: list[Finding] = []
    want = _derived_equity_total(ctx)
    if want is None:
        return out
    bs_rows = _rows(built, "balance_sheet", "rows")
    equity_rows = [r for r in bs_rows if r.get("section") == SECTION_EQUITY]
    got = 0
    for row in equity_rows:
        with amount_guard(rule, out):
            got -= require_cents(
                f"balance_sheet[{row.get('row_id')}]/amount_cents",
                row.get("amount_cents"),
            )
    difference = want - got
    disclosures = [
        d for d in _rows(exceptions, "tie_out_disclosures")
        if d.get("schedule") == "equity_vs_balance_sheet"
    ]
    if difference != 0:
        matched = [
            d for d in disclosures if d.get("variance_cents") == difference
        ]
        loc = ctx.loc(built, "balance_sheet/rows[equity]")
        if matched:
            out.append(
                Finding(
                    rule, Status.FLAG, loc,
                    f"the balance sheet presents equity of {fmt(got)} against a "
                    f"derived {fmt(want)}; the difference of {fmt(difference)} is "
                    f"disclosed in the exception register "
                    f"({matched[0].get('note', 'no note')!r}) -- confirm the "
                    "disclosure still describes this year before the package is issued",
                )
            )
        else:
            out.append(
                Finding(
                    rule, Status.FAIL, loc,
                    f"the balance sheet presents equity of {fmt(got)} against a "
                    f"derived {fmt(want)}, a difference of {fmt(difference)} that no "
                    "entry in the disclosed-exception register accounts for",
                )
            )
    stated = _sub(built, "balance_sheet").get("total_equity_cents")
    if isinstance(stated, int) and not isinstance(stated, bool) and stated != got:
        out.append(
            Finding(
                rule, Status.FAIL,
                ctx.loc(built, "balance_sheet/total_equity_cents"),
                f"the balance sheet's stated total equity of {fmt(stated)} is not "
                f"the sum of its own equity rows ({fmt(got)})",
            )
        )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-",
                f"balance-sheet equity of {fmt(got)} ties the equity schedule exactly",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 8. Schedules: the member capital chain
# --------------------------------------------------------------------------- #
_SEV_MC_CHAIN = _sev("member_capital_chain", Status.FAIL)


@check("member_capital_chain")
def check_member_capital_chain(ctx: Context) -> list[Finding]:
    """Every member year block chains, book and tax, and links to the year before.

    Opening plus contributions plus the allocated result less distributions is
    the closing balance -- in both columns, in every block, not only the one the
    build just appended. And each block opens where the previous one closed: a
    capital account with a gap between two years is an account whose history has
    been edited, and the current year will still foot on its own.
    """
    rule = "member_capital_chain"
    (built,), missing = _need(ctx, rule, DOC_BUILT_PACKAGE)
    if missing:
        return missing
    out: list[Finding] = []
    blocks = _rows(built, "member_capital", "blocks")
    checked = 0
    for basis in ("book", "tax"):
        by_member: dict[str, list[dict[str, Any]]] = {}
        for block in blocks:
            by_member.setdefault(str(block.get("member_id", "")), []).append(block)
        for member_id in sorted(by_member):
            ordered = sorted(by_member[member_id], key=lambda b: int(b.get("year", 0)))
            previous: int | None = None
            for block in ordered:
                block_id = str(block.get("block_id", ""))
                loc = ctx.loc(built, f"member_capital/blocks[{block_id}]")
                with amount_guard(rule, out):
                    opening = require_cents(
                        f"member_capital[{block_id}]/opening_{basis}_cents",
                        block.get(f"opening_{basis}_cents"),
                    )
                    contributions = require_cents(
                        f"member_capital[{block_id}]/contributions_{basis}_cents",
                        block.get(f"contributions_{basis}_cents"),
                    )
                    income = require_cents(
                        f"member_capital[{block_id}]/income_{basis}_cents",
                        block.get(f"income_{basis}_cents"),
                    )
                    distributions = require_cents(
                        f"member_capital[{block_id}]/distributions_{basis}_cents",
                        block.get(f"distributions_{basis}_cents"),
                    )
                    closing = require_cents(
                        f"member_capital[{block_id}]/closing_{basis}_cents",
                        block.get(f"closing_{basis}_cents"),
                    )
                    checked += 1
                    want = member_closing(opening, contributions, income, distributions)
                    if closing != want:
                        out.append(
                            Finding(
                                rule, Status.FAIL, loc,
                                f"{basis} column of block {block_id!r} closes at "
                                f"{fmt(closing)}; {fmt(opening)} opening plus "
                                f"{fmt(contributions)} contributions plus "
                                f"{fmt(income)} allocated result less "
                                f"{fmt(distributions)} distributions is {fmt(want)}",
                            )
                        )
                    if previous is not None and opening != previous:
                        out.append(
                            Finding(
                                rule, Status.FAIL, loc,
                                f"{basis} column of block {block_id!r} opens at "
                                f"{fmt(opening)} but the prior block closed at "
                                f"{fmt(previous)} -- a capital account with a gap "
                                "between two years has had its history edited",
                            )
                        )
                    previous = closing
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-",
                f"{checked} member year-block columns chain and link across "
                f"{len(blocks)} blocks",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 9. Schedules: member capital ties equity
# --------------------------------------------------------------------------- #
_SEV_MC_TIE = _sev("member_closing_ties_equity", Status.FAIL)


@check("member_closing_ties_equity")
def check_member_closing_ties_equity(ctx: Context) -> list[Finding]:
    """The members' closing book capital sums to the equity schedule total.

    The equity schedule is the entity's story and the capital accounts are the
    members' story, and they are the same money. When they part company the
    partner's K-1 and the entity's balance sheet stop describing the same year,
    and each of them foots.
    """
    rule = "member_closing_ties_equity"
    (built, prior, source), missing = _need(
        ctx, rule, DOC_BUILT_PACKAGE, DOC_PRIOR_PACKAGE, DOC_LOCKED_SOURCE
    )
    if missing:
        return missing
    out: list[Finding] = []
    want = _derived_equity_total(ctx)
    year = built.get("fiscal_year")
    current_blocks = [
        b for b in _rows(built, "member_capital", "blocks") if b.get("year") == year
    ]
    got = 0
    for block in current_blocks:
        with amount_guard(rule, out):
            got += require_cents(
                f"member_capital[{block.get('block_id')}]/closing_book_cents",
                block.get("closing_book_cents"),
            )
    if not current_blocks:
        out.append(
            Finding(
                rule, Status.FAIL, ctx.loc(built, "member_capital/blocks"),
                f"the build appended no member capital block for {year}; the "
                "members' accounts stop a year before the entity's",
            )
        )
    elif want is not None and got != want:
        out.append(
            Finding(
                rule, Status.FAIL, ctx.loc(built, "member_capital/blocks"),
                f"the members' closing book capital sums to {fmt(got)} against an "
                f"equity schedule of {fmt(want)}, a difference of {fmt(got - want)} "
                f"across {len(current_blocks)} members",
            )
        )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-",
                f"{len(current_blocks)} members' closing book capital sums to "
                f"{fmt(got)} and ties the equity schedule",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 10. Schedules: tax basis
# --------------------------------------------------------------------------- #
_SEV_BASIS = _sev("tax_basis_is_capital_plus_liability", Status.FAIL)


@check("tax_basis_is_capital_plus_liability")
def check_tax_basis_is_capital_plus_liability(ctx: Context) -> list[Finding]:
    """Tax basis is tax-basis capital plus the member's share of liabilities.

    The liability share has no cell on the book statement, which is exactly why
    it is the half that gets left out. A basis reported at capital alone is
    understated by the member's share of every debt the entity carries, and the
    consequence -- a loss the member cannot actually take -- surfaces on a return
    rather than in the workpaper.
    """
    rule = "tax_basis_is_capital_plus_liability"
    (built,), missing = _need(ctx, rule, DOC_BUILT_PACKAGE)
    if missing:
        return missing
    out: list[Finding] = []
    blocks = _rows(built, "member_capital", "blocks")
    for block in blocks:
        block_id = str(block.get("block_id", ""))
        with amount_guard(rule, out):
            capital = require_cents(
                f"member_capital[{block_id}]/closing_tax_cents",
                block.get("closing_tax_cents"),
            )
            share = require_cents(
                f"member_capital[{block_id}]/liability_share_cents",
                block.get("liability_share_cents"),
            )
            stated = require_cents(
                f"member_capital[{block_id}]/tax_basis_cents",
                block.get("tax_basis_cents"),
            )
            want = tax_basis(capital, share)
            if stated != want:
                out.append(
                    Finding(
                        rule, Status.FAIL,
                        ctx.loc(built, f"member_capital/blocks[{block_id}]/tax_basis_cents"),
                        f"block {block_id!r} reports basis of {fmt(stated)}; "
                        f"{fmt(capital)} tax capital plus {fmt(share)} liability "
                        f"share is {fmt(want)}, a difference of {fmt(stated - want)}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-",
                f"tax basis equals capital plus liability share in all {len(blocks)} blocks",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 11. Schedules: earnings and profits
# --------------------------------------------------------------------------- #
_SEV_EP = _sev("ep_chain_rolls", Status.FAIL)


@check("ep_chain_rolls")
def check_ep_chain_rolls(ctx: Context) -> list[Finding]:
    """Accumulated earnings and profits roll: prior plus current equals end.

    The whole schedule is one addition repeated once a year, which is precisely
    why it is maintained by hand and why the hand-maintained figure is the one
    that drifts. Nothing else in the package re-states accumulated E&P, so a
    figure typed here is never contradicted by anything.
    """
    rule = "ep_chain_rolls"
    (built,), missing = _need(ctx, rule, DOC_BUILT_PACKAGE)
    if missing:
        return missing
    out: list[Finding] = []
    blocks = sorted(
        _rows(built, "earnings_and_profits", "blocks"),
        key=lambda b: int(b.get("year", 0)),
    )
    previous: int | None = None
    for block in blocks:
        block_id = str(block.get("block_id", ""))
        loc = ctx.loc(built, f"earnings_and_profits/blocks[{block_id}]")
        with amount_guard(rule, out):
            opening = require_cents(
                f"earnings_and_profits[{block_id}]/prior_accumulated_cents",
                block.get("prior_accumulated_cents"),
            )
            taxable = require_cents(
                f"earnings_and_profits[{block_id}]/current_taxable_cents",
                block.get("current_taxable_cents"),
            )
            end = require_cents(
                f"earnings_and_profits[{block_id}]/accumulated_end_cents",
                block.get("accumulated_end_cents"),
            )
            want = ep_accumulated(opening, taxable)
            if end != want:
                out.append(
                    Finding(
                        rule, Status.FAIL, loc,
                        f"block {block_id!r} ends at {fmt(end)}; {fmt(opening)} "
                        f"accumulated plus {fmt(taxable)} taxable is {fmt(want)}",
                    )
                )
            if previous is not None and opening != previous:
                out.append(
                    Finding(
                        rule, Status.FAIL, loc,
                        f"block {block_id!r} opens at {fmt(opening)} where the prior "
                        f"block ended at {fmt(previous)}",
                    )
                )
            previous = end
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-",
                f"the earnings-and-profits chain holds across {len(blocks)} year blocks",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 12. Schedules: retained earnings beginning
# --------------------------------------------------------------------------- #
_SEV_RE = _sev("retained_earnings_beginning_rolls", Status.FAIL)


@check("retained_earnings_beginning_rolls")
def check_retained_earnings_beginning_rolls(ctx: Context) -> list[Finding]:
    """Retained earnings at the start of the year include last year's result.

    This is the roll a copied file skips. Every other account is repopulated
    from the ledger, so the balance sheet still balances; only the beginning
    retained-earnings figure keeps last year's opening, and the equity schedule
    is understated by exactly one year of earnings with nothing pointing at it.
    """
    rule = "retained_earnings_beginning_rolls"
    (built, prior), missing = _need(ctx, rule, DOC_BUILT_PACKAGE, DOC_PRIOR_PACKAGE)
    if missing:
        return missing
    out: list[Finding] = []
    classification = classification_map(prior)
    accounts = sorted(
        a for a, info in classification.items()
        if info.get("equity_kind") == EQUITY_RETAINED_EARNINGS
    )
    if not accounts:
        out.append(
            Finding(
                rule, Status.FAIL, ctx.loc(prior, "classification"),
                "the prior-year classification map names no retained-earnings "
                "account, so the roll cannot be proved at all",
            )
        )
        return out
    priors = prior_balances(prior)
    built_balances = _tb_balances(built)
    prior_result = int(prior.get("net_income_cents", 0))
    for account in accounts:
        want = retained_earnings_beginning(
            equity_presented(priors.get(account, 0)), prior_result
        )
        got = equity_presented(built_balances.get(account, 0))
        if got != want:
            out.append(
                Finding(
                    rule, Status.FAIL,
                    ctx.loc(built, f"trial_balance/rows[{account}]/balance_cents"),
                    f"account {account} opens the year at {fmt(got)}; last year's "
                    f"opening of {fmt(equity_presented(priors.get(account, 0)))} plus "
                    f"last year's result of {fmt(prior_result)} is {fmt(want)}, a "
                    f"difference of {fmt(got - want)}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-",
                "beginning retained earnings equals the prior opening plus the "
                "prior year's result",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 13. Schedules: row form
# --------------------------------------------------------------------------- #
_SEV_FORM = _sev("row_form_classified_from_balances", Status.FAIL)


@check("row_form_classified_from_balances")
def check_row_form_classified_from_balances(ctx: Context) -> list[Finding]:
    """A row's form comes from the balances at both year-ends, not from a formula.

    An account that was flat at the prior year-end has no history to net
    against, so its current-year row carries the whole balance as a cumulative
    residual. An account already funded contributes only its movement. The
    distinction is visible in the two balances and nowhere else -- and reading it
    off whether the cell happens to hold a live formula gets it wrong every time
    a formula was copied down from the row above.
    """
    rule = "row_form_classified_from_balances"
    (built, prior, source), missing = _need(
        ctx, rule, DOC_BUILT_PACKAGE, DOC_PRIOR_PACKAGE, DOC_LOCKED_SOURCE
    )
    if missing:
        return missing
    out: list[Finding] = []
    priors = prior_balances(prior)
    current = _current_source_balances(source, ctx.entity_block)
    checked = 0
    for row in _current_equity_rows(built):
        if row.get("role") not in (ROLE_CONTRIBUTION, ROLE_DISTRIBUTION):
            continue
        account = str(row.get("account", ""))
        checked += 1
        want = row_form(priors.get(account, 0))
        got = row.get("row_form")
        if got == want:
            continue
        because = (
            " -- the row carries a live formula, which is what the form appears to "
            "have been read from"
            if row.get("formula_present") is True
            else ""
        )
        out.append(
            Finding(
                rule, Status.FAIL,
                ctx.loc(built, f"equity/rows[{row.get('row_id')}]/row_form"),
                f"account {account} is classified {got!r}; its balances "
                f"({fmt(priors.get(account, 0))} at the prior year-end, "
                f"{fmt(current.get(account, 0))} at this one) make it "
                f"{want!r}{because}",
            )
        )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-",
                f"all {checked} current-year rows are classified from the balances "
                "at both year-ends",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 14. Evidence: rows tie the locked source
# --------------------------------------------------------------------------- #
_SEV_EVID = _sev("evidence_ties_locked_source", Status.FAIL)


@check("evidence_ties_locked_source")
def check_evidence_ties_locked_source(ctx: Context) -> list[Finding]:
    """Every evidence row ties the locked source by exact account number.

    Support that does not tie is not support. The match is on the account
    number, never on the title: titles are edited, abbreviated and translated
    between systems, and a support tab matched on text reconciles to whichever
    row happened to read most like it.
    """
    rule = "evidence_ties_locked_source"
    (built, source), missing = _need(ctx, rule, DOC_BUILT_PACKAGE, DOC_LOCKED_SOURCE)
    if missing:
        return missing
    out: list[Finding] = []
    scoped = source_by_account(source, ctx.entity_block)
    seen: set[str] = set()
    for row in _rows(built, "evidence", "rows"):
        account = str(row.get("account", ""))
        seen.add(account)
        loc = ctx.loc(built, f"evidence/rows[{account}]")
        origin = scoped.get(account)
        if origin is None:
            out.append(
                Finding(
                    rule, Status.FAIL, loc,
                    f"evidence row {account!r} has no row in the locked source for "
                    f"block {ctx.entity_block!r} -- it cites a ledger line that does "
                    "not exist",
                )
            )
            continue
        with amount_guard(rule, out):
            got = require_cents(f"evidence[{account}]/balance_cents", row.get("balance_cents"))
            want = require_cents(f"locked_source[{account}]/balance_cents", origin.get("balance_cents"))
            if got != want:
                out.append(
                    Finding(
                        rule, Status.FAIL, loc,
                        f"evidence row {account!r} carries {fmt(got)}; the locked "
                        f"source carries {fmt(want)}",
                    )
                )
        if str(row.get("title", "")) != str(origin.get("title", "")):
            out.append(
                Finding(
                    rule, Status.FAIL, loc,
                    f"evidence row {account!r} is titled "
                    f"{str(row.get('title', ''))!r}; the locked source titles it "
                    f"{str(origin.get('title', ''))!r}",
                )
            )
    for account in sorted(set(scoped) - seen):
        out.append(
            Finding(
                rule, Status.FAIL, ctx.loc(built, "evidence/rows"),
                f"the locked source carries account {account!r} for block "
                f"{ctx.entity_block!r} and the evidence tab does not; the support "
                "is not the harvest",
            )
        )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-",
                f"all {len(seen)} evidence rows tie the locked source by exact "
                "account number",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 15. Evidence: the subtotal
# --------------------------------------------------------------------------- #
_SEV_SUB = _sev("evidence_subtotal_foots", Status.FAIL)


@check("evidence_subtotal_foots")
def check_evidence_subtotal_foots(ctx: Context) -> list[Finding]:
    """The evidence subtotal is the sum of its rows, and that sum is zero.

    A harvested ledger foots to zero because a ledger does. A subtotal typed
    over the formula that footed it is the classic repair: the number now says
    what the preparer expected instead of what the rows hold, and the tab looks
    finished from that moment on.
    """
    rule = "evidence_subtotal_foots"
    (built,), missing = _need(ctx, rule, DOC_BUILT_PACKAGE)
    if missing:
        return missing
    out: list[Finding] = []
    evidence = _sub(built, "evidence")
    rows = _rows(built, "evidence", "rows")
    footed = 0
    for row in rows:
        with amount_guard(rule, out):
            footed += require_cents(
                f"evidence[{row.get('account')}]/balance_cents",
                row.get("balance_cents"),
            )
    loc = ctx.loc(built, "evidence/subtotal_cents")
    with amount_guard(rule, out):
        stated = require_cents("evidence/subtotal_cents", evidence.get("subtotal_cents"))
        if stated != footed:
            out.append(
                Finding(
                    rule, Status.FAIL, loc,
                    f"the evidence subtotal reads {fmt(stated)} against {fmt(footed)} "
                    f"footed from its own {len(rows)} rows -- a subtotal that is not "
                    "the sum of the rows above it has been typed over",
                )
            )
        if stated != 0:
            out.append(
                Finding(
                    rule, Status.FAIL, loc,
                    f"the evidence subtotal is {fmt(stated)}; a harvested ledger "
                    "foots to zero, and a non-zero support tab means an account was "
                    "left behind or counted twice",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-",
                f"the evidence subtotal foots to zero across {len(rows)} harvested rows",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 16. Evidence: the citation block
# --------------------------------------------------------------------------- #
_SEV_CITE = _sev("citation_block_correct", Status.FAIL)


@check("citation_block_correct")
def check_citation_block_correct(ctx: Context) -> list[Finding]:
    """The citation names the source file, tab, balance column and harvest date.

    A citation is a promise that a reviewer can open the same thing the build
    opened. Naming the wrong tab, or the activity column instead of the balance
    column, breaks that promise silently: the tab still exists, the column still
    holds numbers, and the reviewer's independent check reconciles to a different
    figure with no explanation available.
    """
    rule = "citation_block_correct"
    (built, source), missing = _need(ctx, rule, DOC_BUILT_PACKAGE, DOC_LOCKED_SOURCE)
    if missing:
        return missing
    out: list[Finding] = []
    citation = _sub(_sub(built, "evidence"), "citation")
    for fld in CITATION_FIELDS:
        want = source.get(fld)
        got = citation.get(fld)
        if got != want:
            out.append(
                Finding(
                    rule, Status.FAIL,
                    ctx.loc(built, f"evidence/citation/{fld}"),
                    f"the citation names {fld} as {got!r}; the locked source "
                    f"declares {want!r} -- a citation a reviewer cannot follow back "
                    "is not evidence",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-",
                "the citation names the source file, tab, balance column and "
                "harvest date the build actually read",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 17. Custody: the locked source digest
# --------------------------------------------------------------------------- #
_SEV_SRC_DIGEST = _sev("locked_source_digest_matches", Status.FAIL)


@check("locked_source_digest_matches")
def check_locked_source_digest_matches(ctx: Context) -> list[Finding]:
    """The locked source still hashes to the digest the manifest recorded.

    "Locked" is a claim, and this is the control that makes it one. A source
    re-exported, re-run or moved after the build does not announce itself: the
    file opens, the tab is there, the numbers look like numbers. The digest is
    the only thing that knows the build harvested a different document.
    """
    rule = "locked_source_digest_matches"
    (source, manifest), missing = _need(ctx, rule, DOC_LOCKED_SOURCE, DOC_MANIFEST)
    if missing:
        return missing
    out: list[Finding] = []
    got = digest_payload(source)
    want = manifest.get("locked_source_digest")
    if got != want:
        out.append(
            Finding(
                rule, Status.FAIL, ctx.loc(manifest, "locked_source_digest"),
                f"the locked source hashes to {got[:16]}... and the manifest records "
                f"{str(want)[:16]}... -- the extract the package cites is not the "
                "extract it was built from, so every harvested figure is unproved",
            )
        )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-",
                f"the locked source hashes to the manifest digest ({got[:16]}...)",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 18. Custody: the pre-build image
# --------------------------------------------------------------------------- #
_SEV_PRE_DIGEST = _sev("prebuild_image_digest_matches", Status.FAIL)


@check("prebuild_image_digest_matches")
def check_prebuild_image_digest_matches(ctx: Context) -> list[Finding]:
    """The backup taken before the build is still the backup the manifest names.

    Edit scope is only meaningful against an image nobody has touched. A backup
    re-taken *after* the build agrees with the built package by construction, so
    the diff comes back empty and the scope control passes without having looked
    at anything. Custody has to be proved before scope can be.
    """
    rule = "prebuild_image_digest_matches"
    (image, manifest), missing = _need(ctx, rule, DOC_PREBUILD_IMAGE, DOC_MANIFEST)
    if missing:
        return missing
    out: list[Finding] = []
    got = digest_payload(prebuild_digest_payload(image))
    want = manifest.get("prebuild_image_digest")
    if got != want:
        out.append(
            Finding(
                rule, Status.FAIL, ctx.loc(manifest, "prebuild_image_digest"),
                f"the pre-build image hashes to {got[:16]}... and the manifest "
                f"records {str(want)[:16]}... -- the custody backup on file is not "
                "the one the build took, so the edit-scope diff proves nothing",
            )
        )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-",
                f"the pre-build image hashes to the manifest digest ({got[:16]}...)",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 19. Custody: edit scope
# --------------------------------------------------------------------------- #
_SEV_SCOPE = _sev("edit_scope_matches_register", Status.FAIL)


@check("edit_scope_matches_register")
def check_edit_scope_matches_register(ctx: Context) -> list[Finding]:
    """Only cells the build register names differ from the pre-build image.

    This is the control that makes the build reviewable. A reviewer reads the
    register, ticks the derivations and signs; anything that changed outside the
    register was never in front of them. The diff is taken cell by cell and keyed
    by row identity rather than position, so a re-sorted schedule is not reported
    as a thousand edits -- that failure has its own control.
    """
    rule = "edit_scope_matches_register"
    (built, image, register), missing = _need(
        ctx, rule, DOC_BUILT_PACKAGE, DOC_PREBUILD_IMAGE, DOC_BUILD_REGISTER
    )
    if missing:
        return missing
    out: list[Finding] = []
    built_cells = flatten_cells(built)
    pre_cells = image.get("cells")
    pre_cells = pre_cells if isinstance(pre_cells, dict) else {}
    registered = register_cell_ids(register)
    touched = sorted(
        {k for k in built_cells if k in pre_cells and built_cells[k] != pre_cells[k]}
        | {k for k in built_cells if k not in pre_cells}
    )
    for cell_id in touched:
        if cell_id in registered:
            continue
        before = pre_cells.get(cell_id, "(absent)")
        out.append(
            Finding(
                rule, Status.FAIL, ctx.loc(built, cell_id),
                f"cell {cell_id!r} changed from {before!r} to "
                f"{built_cells[cell_id]!r} and the build register does not name it "
                "-- an edit nobody declared is an edit nobody reviewed",
            )
        )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-",
                f"{len(touched)} cells differ from the pre-build image and the "
                f"register declares all of them ({len(registered)} entries)",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 20. Completeness: cross-schedule reciprocity
# --------------------------------------------------------------------------- #
_SEV_RECIP = _sev("cross_schedule_reciprocity", Status.FAIL)


@check("cross_schedule_reciprocity")
def check_cross_schedule_reciprocity(ctx: Context) -> list[Finding]:
    """Intercompany and investment figures agree with their counterparts.

    Two of the package's rows have a second copy somewhere else: the
    intercompany balance is presented again on the balance sheet, and the
    investment has a matching stub in the counterpart entity's file. Both are
    accounts nobody reconciles because both sides look reasonable in isolation,
    and a difference between them nets out of a consolidation without ever
    unbalancing anything.
    """
    rule = "cross_schedule_reciprocity"
    (built, prior, stub), missing = _need(
        ctx, rule, DOC_BUILT_PACKAGE, DOC_PRIOR_PACKAGE, DOC_COUNTERPART_STUB
    )
    if missing:
        return missing
    out: list[Finding] = []
    classification = classification_map(prior)
    balances = _tb_balances(built)
    bs_rows = {str(r.get("row_id", "")): r for r in _rows(built, "balance_sheet", "rows")}
    interco = sorted(
        a for a, info in classification.items() if info.get("intercompany") is True
    )
    for account in interco:
        if account not in balances:
            continue
        row = bs_rows.get(account)
        loc = ctx.loc(built, f"balance_sheet/rows[{account}]/amount_cents")
        if row is None:
            out.append(
                Finding(
                    rule, Status.FAIL, loc,
                    f"intercompany account {account!r} is on the trial balance at "
                    f"{fmt(balances[account])} and has no balance-sheet row",
                )
            )
            continue
        with amount_guard(rule, out):
            got = require_cents(
                f"balance_sheet[{account}]/amount_cents", row.get("amount_cents")
            )
            if got != balances[account]:
                out.append(
                    Finding(
                        rule, Status.FAIL, loc,
                        f"intercompany account {account!r} reads {fmt(got)} on the "
                        f"balance sheet and {fmt(balances[account])} on the trial "
                        "balance",
                    )
                )
    investments = sorted(
        a for a, info in classification.items() if info.get("investment") is True
    )
    stub_account = str(stub.get("account", ""))
    for account in investments:
        if account not in balances:
            continue
        loc = ctx.loc(built, f"trial_balance/rows[{account}]/balance_cents")
        if stub_account != account:
            out.append(
                Finding(
                    rule, Status.FAIL, loc,
                    f"the counterpart stub covers account {stub_account!r} and the "
                    f"package holds the investment on {account!r}",
                )
            )
            continue
        with amount_guard(rule, out):
            want = require_cents("counterpart_stub/value_cents", stub.get("value_cents"))
            if balances[account] != want:
                out.append(
                    Finding(
                        rule, Status.FAIL, loc,
                        f"the investment in {stub.get('counterpart_entity', '?')} is "
                        f"carried at {fmt(balances[account])} and the counterpart "
                        f"stub reports {fmt(want)}, a difference of "
                        f"{fmt(balances[account] - want)}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-",
                f"{len(interco)} intercompany rows and {len(investments)} investment "
                "rows agree with their counterparts",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 21. Completeness: nothing left behind
# --------------------------------------------------------------------------- #
_SEV_COMPLETE = _sev("source_completeness", Status.FAIL)


@check("source_completeness")
def check_source_completeness(ctx: Context) -> list[Finding]:
    """Every source account the workpaper leaves off is flat in the source.

    An account with no balance carries no figure, so the workpaper is entitled
    to leave it out. An account *with* a balance is not, and this is the control
    that keeps the first rule from quietly covering the second: a package that
    omits a funded account still foots, because it was footed after the omission.
    """
    rule = "source_completeness"
    (built, source), missing = _need(ctx, rule, DOC_BUILT_PACKAGE, DOC_LOCKED_SOURCE)
    if missing:
        return missing
    out: list[Finding] = []
    carried = set(_tb_balances(built))
    scoped = source_by_account(source, ctx.entity_block)
    for account in sorted(scoped):
        if account in carried:
            continue
        with amount_guard(rule, out):
            balance = require_cents(
                f"locked_source[{account}]/balance_cents",
                scoped[account].get("balance_cents"),
            )
            if balance != 0:
                out.append(
                    Finding(
                        rule, Status.FAIL, ctx.loc(built, "trial_balance/rows"),
                        f"account {account!r} "
                        f"({str(scoped[account].get('title', ''))!r}) carries "
                        f"{fmt(balance)} in the locked source and appears nowhere on "
                        "the built trial balance",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-",
                f"every one of the {len(scoped)} source accounts is either on the "
                "trial balance or flat in the source",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 22. Completeness: the exception register
# --------------------------------------------------------------------------- #
_SEV_EXC = _sev("exception_register_honored", Status.FAIL)


@check("exception_register_honored")
def check_exception_register_honored(ctx: Context) -> list[Finding]:
    """A placeholder or mislabeled account is tolerated only if it is registered.

    Both of these are accepted every year on purpose -- a suspense code the
    ledger has not retired, a title the source system abbreviates -- and both are
    accepted because somebody looked once. The register is that decision written
    down. An account that appears in either state without a registration is a
    decision nobody made, and the build carried it into a signed package.
    """
    rule = "exception_register_honored"
    (built, prior, exceptions), missing = _need(
        ctx, rule, DOC_BUILT_PACKAGE, DOC_PRIOR_PACKAGE, DOC_EXCEPTION_REGISTER
    )
    if missing:
        return missing
    out: list[Finding] = []
    classification = classification_map(prior)
    registered: dict[str, set[str]] = {}
    for entry in _rows(exceptions, "account_exceptions"):
        account = str(entry.get("account", ""))
        registered.setdefault(account, set()).add(str(entry.get("kind", "")))
    for row in _rows(built, "trial_balance", "rows"):
        account = str(row.get("account", ""))
        loc = ctx.loc(built, f"trial_balance/rows[{account}]")
        info = classification.get(account)
        if account.startswith(PLACEHOLDER_PREFIX) or info is None:
            if EXC_PLACEHOLDER not in registered.get(account, set()):
                out.append(
                    Finding(
                        rule, Status.FAIL, loc,
                        f"account {account!r} is a suspense-range or unmapped "
                        "placeholder and carries no registered exception; a "
                        "placeholder nobody accepted has been built into the package",
                    )
                )
            continue
        chart_title = str(info.get("title", ""))
        mislabeled = bool(chart_title) and str(row.get("title", "")) != chart_title
        if mislabeled and EXC_MISLABELED not in registered.get(account, set()):
            out.append(
                Finding(
                    rule, Status.FAIL, loc,
                    f"account {account!r} is titled {str(row.get('title', ''))!r} "
                    f"where the chart says {chart_title!r}, and no exception "
                    "registers the difference",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-",
                f"every placeholder and mislabeled account is registered "
                f"({len(registered)} accounts on the register)",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 23. Hygiene: what the package renders
# --------------------------------------------------------------------------- #
_SEV_HYGIENE = _sev("render_hygiene", Status.FAIL)


@check("render_hygiene")
def check_render_hygiene(ctx: Context) -> list[Finding]:
    """No formula error, external link or local path survives into the package.

    Three things that are invisible to arithmetic and fatal to a delivered file:
    an error marker where a figure belongs, a link to a workbook the recipient
    cannot open, and a path off somebody's own machine. None of them changes a
    total, so nothing else in this registry would ever mention them.
    """
    rule = "render_hygiene"
    (built,), missing = _need(ctx, rule, DOC_BUILT_PACKAGE)
    if missing:
        return missing
    out: list[Finding] = []
    for path, text in rendered_strings(built):
        for marker in FORMULA_ERROR_MARKERS:
            if marker in text:
                out.append(
                    Finding(
                        rule, Status.FAIL, ctx.loc(built, path),
                        f"the package renders {marker!r} at {path} -- an error "
                        "marker where a figure belongs is a cell that never "
                        "computed, delivered as if it had",
                    )
                )
        for marker in EXTERNAL_MARKERS:
            if marker in text:
                out.append(
                    Finding(
                        rule, Status.FAIL, ctx.loc(built, path),
                        f"the package renders a local path or external address "
                        f"({marker!r}) at {path}; a delivered workpaper must stand "
                        "on its own",
                    )
                )
        if _EXTERNAL_LINK_RE.search(text):
            out.append(
                Finding(
                    rule, Status.FAIL, ctx.loc(built, path),
                    f"the package renders an external workbook link at {path}; the "
                    "recipient opens the file and sees a prompt rather than a figure",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-",
                "no formula-error marker, external link or local path in the "
                "rendered package",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 24. Carry: the surviving history labels
# --------------------------------------------------------------------------- #
_SEV_LABELS = _sev("history_labels_survive", Status.FAIL)


@check("history_labels_survive")
def check_history_labels_survive(ctx: Context) -> list[Finding]:
    """No prior-year history label is dropped by the roll.

    A figure without its label is not history, it is a number in a column. The
    labels most often lost are the ones a roll rewrites wholesale -- a member's
    year-block caption, an accumulated-E&P heading -- and they are lost quietly,
    because the other member's copy of the same year is still on the page and the
    schedule reads complete.
    """
    rule = "history_labels_survive"
    (built, prior), missing = _need(ctx, rule, DOC_BUILT_PACKAGE, DOC_PRIOR_PACKAGE)
    if missing:
        return missing
    out: list[Finding] = []

    def _labels(package: dict[str, Any]) -> list[str]:
        found: list[str] = []
        for row in _rows(package, "equity", "rows"):
            if isinstance(row.get("caption"), str):
                found.append(row["caption"])
        for block in _rows(package, "member_capital", "blocks"):
            if isinstance(block.get("caption"), str):
                found.append(block["caption"])
        for block in _rows(package, "earnings_and_profits", "blocks"):
            if isinstance(block.get("caption"), str):
                found.append(block["caption"])
        return found

    history = _labels(prior)
    surviving = set(_labels(built)) | set(_sub(built, "captions").values())
    for label in history:
        if label not in surviving:
            out.append(
                Finding(
                    rule, Status.FAIL, ctx.loc(built, "captions"),
                    f"the prior package labelled a row {label!r} and the built "
                    "package carries no such label; the figure survived the roll and "
                    "the thing that said what it was did not",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-",
                f"all {len(history)} prior-year history labels survive the roll",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one build file."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path.name}: not valid JSON ({exc})") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name}: top level must be a JSON object")

    ctx = Context(path=path, data=raw)
    report = DocumentReport(document=ctx.file_id)
    for _rule_id, fn in REGISTRY:
        report.findings.extend(fn(ctx))
    return report


def analyze_folder(folder: Path) -> list[DocumentReport]:
    """Analyze every ``.json`` build file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of build-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
