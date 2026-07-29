"""What each control actually means, tested at its boundary.

Two things are proved here. First, that every one of the twenty-five controls
fires on the defect it was designed for and stays silent on the clean baseline --
asserted against the control function itself rather than against a whole-file
report, so the claim is about the control and not about the run.

Second, and this is where the weight is: that each control fires *at the right
moment*. One cent, one day or one status either side of the line. A control that
fires a cent early is as wrong as one that never fires, and only a boundary test
can tell the two apart.

The tie-out cases carry the most weight, because they are the ones a tolerance
band would quietly break: an identity that holds to the cent must pass and a cent
either side must fail. The draw schedule's period is inclusive at both ends, and
only an executed draw funds anything. A caption has to carry a marker of its own
schedule type and none of the other's, so it cannot straddle both. And the
release gate has to stay silent on a package correctly held over an open
exception, because a gate that fires on the right decision teaches a preparer to
ignore it.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from investor_engine import engine as engine_module
from investor_engine.engine import (
    REGISTRY,
    SEVERITY,
    check_bs_balances,
    check_capital_agrees_ledger,
    check_capital_rollforward,
    check_caption_matches_type,
    check_cash_supported,
    check_contributions_foot,
    check_cover_consistent,
    check_devcost_agrees_wip,
    check_division_coverage,
    check_draw_schedule_agrees,
    check_footnote_figures,
    check_interco_classified,
    check_jobcost_bridge,
    check_net_income_agrees,
    check_nil_is_genuine,
    check_no_preparer_artifacts,
    check_package_complete,
    check_prior_period_continuity,
    check_reciprocal_investment,
    check_release_gate,
    check_tb_agrees_ledger,
    check_tb_completeness,
    check_tb_nets_zero,
    check_total_cross_foots,
)
from investor_engine.generate import (
    DEFECTS,
    PERIOD_END,
    PERIOD_START,
    PROJECT_ENTITIES,
    baseline,
)
from investor_engine.model import (
    CAPITAL_BEGINNING,
    CAPITAL_CONTRIBUTIONS,
    CAPITAL_RATIO_ROW,
    CAPITAL_ROWS,
    DOC_BALANCE_SHEET,
    DOC_CAPITAL_STATEMENT,
    DOC_CASH_SUPPORT,
    DOC_DEVCOST_SCHEDULE,
    DOC_DRAW_SCHEDULE,
    DOC_ENTITY_LEDGER,
    DOC_FOOTNOTES,
    DOC_INCOME_STATEMENT,
    DOC_JOB_COST_DETAIL,
    DOC_JOBCOST_REPORT,
    DOC_PACKAGE_COVER,
    DOC_PARENT_LEDGER,
    DOC_PRIOR_PACKAGE,
    DOC_RELEASE_LOG,
    DOC_TRIAL_BALANCE,
    DRAW_CANCELLED,
    DRAW_EXECUTED,
    DRAW_SCHEDULED,
    RELEASE_HELD,
    RELEASE_RELEASED,
    SECTION_ASSETS,
    SECTION_LIABILITIES,
    TOTAL_COLUMN,
    Context,
    Finding,
    Status,
)
from investor_engine.package import caption_matches, presentation_section

from .conftest import defect_names

#: Every registered control, addressable by rule id.
CHECKS = dict(REGISTRY)

#: Rule ids in registry order.
RULE_IDS = [rule_id for rule_id, _fn in REGISTRY]

#: ``rule id -> the planted defect built to trip it``. A rule with more than one
#: defect keeps the first in sorted order, which is enough to prove it fires.
DEFECT_BY_RULE: dict[str, str] = {}
for _name in sorted(DEFECTS):
    DEFECT_BY_RULE.setdefault(DEFECTS[_name][0], _name)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _payload() -> dict[str, Any]:
    return baseline(PROJECT_ENTITIES[0])


def _ctx(payload: dict[str, Any], prior: list[Finding] | None = None) -> Context:
    return Context(
        path=Path("in-memory.json"), data=payload, prior_findings=list(prior or [])
    )


def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any]:
    return next(d for d in payload["documents"] if d["doc_type"] == doc_type)


def _ledger(payload: dict[str, Any], account_no: str) -> dict[str, Any]:
    return next(
        r for r in _doc(payload, DOC_ENTITY_LEDGER)["accounts"]
        if r["account_no"] == account_no
    )


def _tb(payload: dict[str, Any], account_no: str) -> dict[str, Any]:
    return next(
        r for r in _doc(payload, DOC_TRIAL_BALANCE)["rows"]
        if r["account_no"] == account_no
    )


def _bs(
    payload: dict[str, Any], *, account_no: str = "", member_id: str = ""
) -> dict[str, Any]:
    for row in _doc(payload, DOC_BALANCE_SHEET)["rows"]:
        if account_no and row.get("account_no") == account_no:
            return row
        if member_id and row.get("member_id") == member_id:
            return row
    raise KeyError(account_no or member_id)


def _col(payload: dict[str, Any], key: str) -> dict[str, Any]:
    return _doc(payload, DOC_CAPITAL_STATEMENT)["columns"][key]


def _devcost(payload: dict[str, Any], division_code: str) -> dict[str, Any]:
    return next(
        r for r in _doc(payload, DOC_DEVCOST_SCHEDULE)["rows"]
        if r["division_code"] == division_code
    )


def _draw(payload: dict[str, Any], draw_id: str) -> dict[str, Any]:
    return next(
        r for r in _doc(payload, DOC_DRAW_SCHEDULE)["draws"] if r["draw_id"] == draw_id
    )


def _note(payload: dict[str, Any], note_id: str) -> dict[str, Any]:
    return next(
        r for r in _doc(payload, DOC_FOOTNOTES)["notes"] if r["note_id"] == note_id
    )


def _reconciling(payload: dict[str, Any], item_id: str) -> dict[str, Any]:
    return next(
        r for r in _doc(payload, DOC_JOBCOST_REPORT)["reconciling_items"]
        if r["item_id"] == item_id
    )


def _fired(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.status is not Status.PASS]


def _shift(day: str, days: int) -> str:
    return (date.fromisoformat(day) + timedelta(days=days)).isoformat()


# --------------------------------------------------------------------------- #
# Every control, against its own defect and against the clean baseline
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", defect_names())
def test_control_fires_on_its_defect_and_is_silent_on_the_clean_baseline(
    name: str,
) -> None:
    """Both halves of a semantics test, on one control, in one place.

    Fires: the control the defect targets produces a non-PASS finding. Asserted
    against the single control function rather than a whole-file report, so what
    is proved is that *this* control detects *this* break -- not that something
    somewhere in a twenty-five rule registry noticed.

    Silent: the same control produces nothing but PASS findings on a package its
    own sources produce. Without this half, a control that fired on everything
    would look identical to a control that worked, and a registry of those holds
    every package forever.

    Parametrized over the defects rather than the rules so that a rule carrying
    more than one planted defect is exercised by each of them.
    """
    rule_id, mutate = DEFECTS[name]
    check = CHECKS[rule_id]

    payload = _payload()
    mutate(payload)
    assert _fired(check(_ctx(payload))), (
        f"{rule_id} stayed silent on the {name!r} defect it was built for"
    )

    clean = _fired(check(_ctx(_payload())))
    assert not clean, (
        f"{rule_id} fired on the clean baseline: "
        + "; ".join(f"{f.status.value} @ {f.location}: {f.message}" for f in clean)
    )


# --------------------------------------------------------------------------- #
# tb_nets_zero -- the trial balance nets, to the cent, with no tolerance band
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_trial_balance_nets_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _tb(payload, "1010")["debit_cents"] += delta
    assert bool(_fired(check_tb_nets_zero(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# tb_completeness -- activity is either column moving, never the net
# --------------------------------------------------------------------------- #
def test_an_account_that_cycled_to_nil_still_has_to_appear() -> None:
    """1290 took in 45,000 and released 45,000, so its net is nothing and its
    activity is everything. Dropping it changes no total, which is why it is the
    account a package drops."""
    payload = _payload()
    rows = _doc(payload, DOC_TRIAL_BALANCE)["rows"]
    _doc(payload, DOC_TRIAL_BALANCE)["rows"] = [r for r in rows if r["account_no"] != "1290"]
    fired = _fired(check_tb_completeness(_ctx(payload)))
    assert fired
    assert "1290" in fired[0].message


def test_an_account_with_no_activity_may_be_absent() -> None:
    """2060 never moved, so its absence from the trial balance is correct.

    The mirror image of the case above, and the reason the control reads both
    columns rather than the net: if absence were the test, a nil account would be
    reported every month and the one that mattered would be lost in the noise.
    """
    payload = _payload()
    assert not any(r["account_no"] == "2060" for r in _doc(payload, DOC_TRIAL_BALANCE)["rows"])
    assert not _fired(check_tb_completeness(_ctx(payload)))


# --------------------------------------------------------------------------- #
# tb_agrees_ledger -- matched by account number, never by row position
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_package_balance_agrees_to_its_own_account_to_the_cent(
    delta: int, should_fail: bool
) -> None:
    payload = _payload()
    _tb(payload, "2010")["credit_cents"] += delta
    assert bool(_fired(check_tb_agrees_ledger(_ctx(payload)))) is should_fail


def test_a_positional_paste_is_named_as_one() -> None:
    """The trial balance exports in reading order and the ledger in account order.

    Pasting one column beside the other agrees only where the two orders happen
    to coincide. The control has to catch it *and* say what it is, because two
    figures wrong by an unrelated pair of amounts otherwise costs a reviewer an
    hour before the cause is obvious.
    """
    payload = _payload()
    accounts = _doc(payload, DOC_ENTITY_LEDGER)["accounts"]
    for index, row in enumerate(_doc(payload, DOC_TRIAL_BALANCE)["rows"]):
        row["debit_cents"] = accounts[index]["debit_cents"]
        row["credit_cents"] = accounts[index]["credit_cents"]
    fired = _fired(check_tb_agrees_ledger(_ctx(payload)))
    assert fired
    assert all("same row position" in f.message for f in fired)


# --------------------------------------------------------------------------- #
# bs_balances -- each section foots its rows, and the identity holds across them
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "key",
    ["total_assets_cents", "total_liabilities_cents", "total_equity_cents"],
)
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_each_section_total_foots_its_rows_to_the_cent(
    key: str, delta: int, should_fail: bool
) -> None:
    payload = _payload()
    _doc(payload, DOC_BALANCE_SHEET)[key] += delta
    assert bool(_fired(check_bs_balances(_ctx(payload)))) is should_fail


def test_the_identity_is_struck_even_when_every_section_foots() -> None:
    """A transposition carried into the section total leaves both legs consistent.

    The section still adds to its rows, so only the accounting identity itself
    catches it -- which is why the control strikes both and not one.
    """
    payload = _payload()
    _bs(payload, member_id="MEM-02")["amount_cents"] -= 4_500_000
    _doc(payload, DOC_BALANCE_SHEET)["total_equity_cents"] -= 4_500_000
    fired = _fired(check_bs_balances(_ctx(payload)))
    assert len(fired) == 1
    assert "does not equal total liabilities" in fired[0].message


# --------------------------------------------------------------------------- #
# interco_classified -- a credit balance is a liability; a flat one is not
# --------------------------------------------------------------------------- #
def test_a_flat_intercompany_balance_is_presented_as_an_asset() -> None:
    """Nothing is owed, so there is nothing to reclassify.

    Stated on the kernel and then on the control, because the boundary is the
    whole rule: at exactly zero the account belongs on the asset side, and a
    control that read ``<= 0`` would demand a liability row for an account that
    owes nothing.
    """
    assert presentation_section(-1) == SECTION_LIABILITIES
    assert presentation_section(0) == SECTION_ASSETS
    assert presentation_section(1) == SECTION_ASSETS

    payload = _payload()
    _ledger(payload, "1500")["credit_cents"] = 0
    fired = _fired(check_interco_classified(_ctx(payload)))
    assert fired
    assert SECTION_ASSETS in fired[0].message


def test_an_intercompany_balance_netted_out_of_the_statement_is_reported() -> None:
    """A balance that appears nowhere is the version of this defect nobody sees."""
    payload = _payload()
    rows = _doc(payload, DOC_BALANCE_SHEET)["rows"]
    _doc(payload, DOC_BALANCE_SHEET)["rows"] = [
        r for r in rows if r.get("account_no") != "1500"
    ]
    fired = _fired(check_interco_classified(_ctx(payload)))
    assert fired
    assert "appears nowhere on the balance sheet" in fired[0].message


# --------------------------------------------------------------------------- #
# capital_agrees_ledger -- per member, matched on member id
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_member_capital_agrees_to_its_ledger_account_to_the_cent(
    delta: int, should_fail: bool
) -> None:
    payload = _payload()
    _ledger(payload, "3010")["credit_cents"] += delta
    assert bool(_fired(check_capital_agrees_ledger(_ctx(payload)))) is should_fail


def test_a_member_on_the_roster_with_no_column_is_reported() -> None:
    payload = _payload()
    del _doc(payload, DOC_CAPITAL_STATEMENT)["columns"]["MEM-01"]
    fired = _fired(check_capital_agrees_ledger(_ctx(payload)))
    assert fired
    assert "no column" in fired[0].message


# --------------------------------------------------------------------------- #
# contributions_foot -- the column is a total and the detail is its evidence
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_contribution_column_foots_its_detail_to_the_cent(
    delta: int, should_fail: bool
) -> None:
    payload = _payload()
    _doc(payload, DOC_CAPITAL_STATEMENT)["contribution_detail"][0]["amount_cents"] += delta
    assert bool(_fired(check_contributions_foot(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# total_cross_foots -- every row, including the one that is not money
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("row_key", [*CAPITAL_ROWS, CAPITAL_RATIO_ROW])
def test_total_column_cross_foots_every_row(row_key: str) -> None:
    """A Total cell that is right on five rows and linked on the sixth is the
    defect: it survives review and is wrong exactly when a member column moves."""
    payload = _payload()
    _col(payload, TOTAL_COLUMN)[row_key] += 1
    fired = _fired(check_total_cross_foots(_ctx(payload)))
    assert fired
    assert row_key in fired[0].message


def test_a_capital_statement_with_no_total_column_is_reported() -> None:
    payload = _payload()
    del _doc(payload, DOC_CAPITAL_STATEMENT)["columns"][TOTAL_COLUMN]
    fired = _fired(check_total_cross_foots(_ctx(payload)))
    assert fired
    assert "no Total column" in fired[0].message


# --------------------------------------------------------------------------- #
# capital_rollforward -- ending is beginning plus in, plus result, less out
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_member_capital_rolls_forward_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _col(payload, "MEM-02")["ending_cents"] += delta
    assert bool(_fired(check_capital_rollforward(_ctx(payload)))) is should_fail


def test_a_distribution_is_subtracted_and_not_netted_into_contributions() -> None:
    """Moving a return of capital into the contribution column breaks the identity.

    The two rows are the same money with opposite signs, so a preparer who nets
    them keeps the ending balance and loses the disclosure. The rollforward has
    to notice, because the ending balance still agrees to the ledger.
    """
    payload = _payload()
    column = _col(payload, "MEM-01")
    column[CAPITAL_CONTRIBUTIONS] -= column["distributions_cents"]
    column["distributions_cents"] = 0
    fired = _fired(check_capital_rollforward(_ctx(payload)))
    assert not fired  # the identity still holds: this is a disclosure question
    column[CAPITAL_CONTRIBUTIONS] += 1
    assert _fired(check_capital_rollforward(_ctx(payload)))


# --------------------------------------------------------------------------- #
# net_income_agrees -- the same figure, printed twice, prepared at two moments
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_result_agrees_between_the_two_statements_to_the_cent(
    delta: int, should_fail: bool
) -> None:
    payload = _payload()
    _doc(payload, DOC_INCOME_STATEMENT)["net_income_cents"] += delta
    assert bool(_fired(check_net_income_agrees(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# devcost_agrees_wip -- both legs: the rows foot the total, the total is the WIP
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_development_cost_total_foots_its_rows_to_the_cent(
    delta: int, should_fail: bool
) -> None:
    payload = _payload()
    _doc(payload, DOC_DEVCOST_SCHEDULE)["total_cents"] += delta
    assert bool(_fired(check_devcost_agrees_wip(_ctx(payload)))) is should_fail


def test_development_cost_ties_to_work_in_process_even_when_it_foots() -> None:
    """A row and the total moved together still analyse the wrong amount of cost.

    This is the leg that matters: the schedule is assembled outside the ledger,
    so it can be internally perfect and still not be an analysis of the account
    it claims to analyse.
    """
    payload = _payload()
    _devcost(payload, "SOFT-02")["cost_to_date_cents"] -= 2_700_000
    _doc(payload, DOC_DEVCOST_SCHEDULE)["total_cents"] -= 2_700_000
    fired = _fired(check_devcost_agrees_wip(_ctx(payload)))
    assert len(fired) == 1
    assert "work in process in the ledger" in fired[0].message


# --------------------------------------------------------------------------- #
# jobcost_bridge -- the control is disclosure, not agreement
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_the_bridge_has_to_close_exactly(delta: int, should_fail: bool) -> None:
    """There is no closing tolerance: a bridge that nearly closes has an
    unexplained figure in it."""
    payload = _payload()
    _reconciling(payload, "REC-01")["amount_cents"] += delta
    assert bool(_fired(check_jobcost_bridge(_ctx(payload)))) is should_fail


def test_an_undisclosed_item_fires_even_though_the_bridge_still_closes() -> None:
    """Agreement was never the control. A difference the partner is not told about
    is the defect, and the arithmetic is untouched by it."""
    payload = _payload()
    _reconciling(payload, "REC-01")["disclosed"] = False
    fired = _fired(check_jobcost_bridge(_ctx(payload)))
    assert len(fired) == 1
    assert "not disclosed" in fired[0].message


def test_the_report_has_to_foot_the_cost_detail_behind_it() -> None:
    payload = _payload()
    _doc(payload, DOC_JOB_COST_DETAIL)["divisions"][0]["cost_to_date_cents"] += 1
    fired = _fired(check_jobcost_bridge(_ctx(payload)))
    assert fired
    assert any("division(s) of job cost detail" in f.message for f in fired)


# --------------------------------------------------------------------------- #
# division_coverage -- the schedule or a *disclosed* item, and nothing else
# --------------------------------------------------------------------------- #
def test_a_division_carried_only_by_a_disclosed_item_is_covered() -> None:
    payload = _payload()
    rows = _doc(payload, DOC_DEVCOST_SCHEDULE)["rows"]
    _doc(payload, DOC_DEVCOST_SCHEDULE)["rows"] = [
        r for r in rows if r["division_code"] != "DIV-09"
    ]
    _reconciling(payload, "REC-01")["covers_divisions"].append("DIV-09")
    assert not _fired(check_division_coverage(_ctx(payload)))


def test_an_undisclosed_item_covers_nothing() -> None:
    """An item nobody is told about cannot account for a trade.

    The same arrangement as above with the disclosure withdrawn: the division is
    named in the bridge and the partner never sees it, so it has left the package
    unaccounted for.
    """
    payload = _payload()
    rows = _doc(payload, DOC_DEVCOST_SCHEDULE)["rows"]
    _doc(payload, DOC_DEVCOST_SCHEDULE)["rows"] = [
        r for r in rows if r["division_code"] != "DIV-09"
    ]
    item = _reconciling(payload, "REC-01")
    item["covers_divisions"].append("DIV-09")
    item["disclosed"] = False
    fired = _fired(check_division_coverage(_ctx(payload)))
    assert fired
    assert "DIV-09" in fired[0].message


# --------------------------------------------------------------------------- #
# draw_schedule_agrees -- only an executed draw, only inside the period
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_contributions_agree_to_the_executed_draws_to_the_cent(
    delta: int, should_fail: bool
) -> None:
    payload = _payload()
    _draw(payload, "DRAW-101")["amount_cents"] += delta
    assert bool(_fired(check_draw_schedule_agrees(_ctx(payload)))) is should_fail


@pytest.mark.parametrize(
    "when, should_fail",
    [
        (PERIOD_START, False),
        (_shift(PERIOD_START, -1), True),
        (PERIOD_END, False),
        (_shift(PERIOD_END, 1), True),
    ],
)
def test_the_period_is_inclusive_at_both_ends(when: str, should_fail: bool) -> None:
    """A draw funded after the period end is next month's contribution and one
    funded before the period start is already inside the opening balance."""
    payload = _payload()
    _draw(payload, "DRAW-101")["funded_date"] = when
    assert bool(_fired(check_draw_schedule_agrees(_ctx(payload)))) is should_fail


@pytest.mark.parametrize(
    "status, should_fail",
    [(DRAW_EXECUTED, True), (DRAW_SCHEDULED, False), (DRAW_CANCELLED, False)],
)
def test_only_an_executed_draw_funded_anything(status: str, should_fail: bool) -> None:
    """DRAW-103 is a cancelled draw dated inside the period.

    Executing it adds money the package never recorded as contributed. Leaving it
    cancelled, or making it a plan again, funds nothing -- so a control that
    summed the schedule without filtering on status would pass here and be wrong
    the first month a call was withdrawn.
    """
    payload = _payload()
    _draw(payload, "DRAW-103")["status"] = status
    assert bool(_fired(check_draw_schedule_agrees(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# reciprocal_investment -- two ledgers, one relationship, maintained by hand
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_the_reciprocal_pair_agrees_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _doc(payload, DOC_PARENT_LEDGER)["accounts"][0]["balance_cents"] += delta
    assert bool(_fired(check_reciprocal_investment(_ctx(payload)))) is should_fail


def test_a_parent_ledger_that_names_no_member_cannot_be_matched() -> None:
    payload = _payload()
    del _doc(payload, DOC_PARENT_LEDGER)["parent_member_id"]
    fired = _fired(check_reciprocal_investment(_ctx(payload)))
    assert fired
    assert "which member it holds" in fired[0].message


# --------------------------------------------------------------------------- #
# nil_is_genuine -- a nil bottom line is not the same thing as no activity
# --------------------------------------------------------------------------- #
def test_a_presented_statement_of_operations_has_no_nil_to_audit() -> None:
    """The control looks at the ledger only when the statement claims nil.

    A project entity that reports revenue and expense lines is making a
    presentation the reader can check for themselves, and re-deriving it here
    would be a second income statement rather than a control.
    """
    payload = _payload()
    income = _doc(payload, DOC_INCOME_STATEMENT)
    income["presented_nil"] = False
    income["revenue_rows"] = [
        {"account_no": "4100", "label": "Other income", "amount_cents": 100}
    ]
    findings = check_nil_is_genuine(_ctx(payload))
    assert not _fired(findings)
    assert "no nil presentation to test" in findings[0].message


def test_activity_that_nets_to_nil_is_still_activity() -> None:
    """A fee credit and a marketing cost that happen to net leave the bottom line
    at zero and two accounts nowhere the partner can see them."""
    payload = _payload()
    _ledger(payload, "4100")["credit_cents"] = 6_500_000
    _ledger(payload, "6100")["debit_cents"] = 6_500_000
    fired = _fired(check_nil_is_genuine(_ctx(payload)))
    assert len(fired) == 2
    assert all("presented nil" in f.message for f in fired)


# --------------------------------------------------------------------------- #
# cash_supported -- a FLAG, because the engine cannot produce a bank statement
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_flag", [(-1, True), (0, False), (1, True)])
def test_cash_support_has_to_agree_to_the_reported_balance(
    delta: int, should_flag: bool
) -> None:
    payload = _payload()
    _doc(payload, DOC_CASH_SUPPORT)["reconciliations"][0]["reconciled_balance_cents"] += delta
    fired = _fired(check_cash_supported(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


def test_absent_cash_support_is_flagged_and_never_failed() -> None:
    """The support is a document that does not exist yet.

    Failing it would tell a preparer to invent one; flagging it sends the balance
    to a person, which is the only correct destination for a bank statement that
    has not arrived.
    """
    payload = _payload()
    support = _doc(payload, DOC_CASH_SUPPORT)
    support["reconciliations"] = [
        r for r in support["reconciliations"] if r["account_no"] != "1020"
    ]
    fired = _fired(check_cash_supported(_ctx(payload)))
    assert len(fired) == 1
    assert fired[0].status is Status.FLAG
    assert SEVERITY["cash_supported"] is Status.FLAG


# --------------------------------------------------------------------------- #
# footnote_figures -- a note is prose with a retyped number in it
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_a_quoted_figure_equals_its_cell_to_the_cent(
    delta: int, should_fail: bool
) -> None:
    payload = _payload()
    _note(payload, "NOTE-01")["quoted_cents"] += delta
    assert bool(_fired(check_footnote_figures(_ctx(payload)))) is should_fail


def test_a_note_pointing_at_a_cell_that_is_not_there_quotes_nothing() -> None:
    payload = _payload()
    _note(payload, "NOTE-02")["cell_ref"] = "balance_sheet/row/9999"
    fired = _fired(check_footnote_figures(_ctx(payload)))
    assert fired
    assert "not a cell this package carries" in fired[0].message


def test_a_note_that_names_no_cell_cannot_be_checked() -> None:
    payload = _payload()
    del _note(payload, "NOTE-03")["cell_ref"]
    fired = _fired(check_footnote_figures(_ctx(payload)))
    assert fired
    assert "names no cell" in fired[0].message


# --------------------------------------------------------------------------- #
# caption_matches_type -- the caption is the only thing that says which period
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "caption, should_fail",
    [
        ("Development cost incurred to date", False),
        ("Development cost incurred during the period", True),
        ("Development cost incurred for the period", True),
        ("Development cost by division", True),
        ("Development cost to date and for the period", True),
    ],
)
def test_a_cost_to_date_caption_must_say_to_date_and_nothing_else(
    caption: str, should_fail: bool
) -> None:
    """The last case is the one a checklist misses: a caption carrying both
    markers straddles the two schedule types and tells the reader neither."""
    payload = _payload()
    _doc(payload, DOC_DEVCOST_SCHEDULE)["caption"] = caption
    assert bool(_fired(check_caption_matches_type(_ctx(payload)))) is should_fail
    assert caption_matches("cost_to_date", caption)[0] is not should_fail


def test_a_schedule_that_declares_an_unknown_type_has_no_caption_rule() -> None:
    payload = _payload()
    _doc(payload, DOC_DEVCOST_SCHEDULE)["schedule_type"] = "cumulative"
    fired = _fired(check_caption_matches_type(_ctx(payload)))
    assert fired
    assert "'cumulative'" in fired[0].message


# --------------------------------------------------------------------------- #
# cover_consistent -- the cover is written first and the exceptions found last
# --------------------------------------------------------------------------- #
def test_the_cover_cannot_reference_an_exception_the_package_does_not_disclose() -> None:
    """The reader is sent to a note that is not there."""
    payload = _payload()
    _doc(payload, DOC_PACKAGE_COVER)["referenced_exception_ids"].append("EXC-99")
    fired = _fired(check_cover_consistent(_ctx(payload)))
    assert fired
    assert "EXC-99" in fired[0].message


def test_a_disclosed_exception_the_cover_ignores_is_reported() -> None:
    payload = _payload()
    _doc(payload, DOC_PACKAGE_COVER)["referenced_exception_ids"] = []
    fired = _fired(check_cover_consistent(_ctx(payload)))
    assert fired
    assert "does not reference it" in fired[0].message


# --------------------------------------------------------------------------- #
# no_preparer_artifacts -- part of how the package was built, not of the package
# --------------------------------------------------------------------------- #
def test_a_preparer_artifact_that_stays_in_the_workbook_is_not_an_exception() -> None:
    """Three preparer-only artifacts travel with every file and none of them is
    released; the control is about what left, not about what exists."""
    payload = _payload()
    log = _doc(payload, DOC_RELEASE_LOG)
    assert any(a["preparer_only"] for a in log["artifacts"])
    assert not _fired(check_no_preparer_artifacts(_ctx(payload)))


# --------------------------------------------------------------------------- #
# prior_period_continuity -- the partner holds last month's package
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_opening_capital_continues_the_prior_package_to_the_cent(
    delta: int, should_fail: bool
) -> None:
    payload = _payload()
    row = next(
        r for r in _doc(payload, DOC_PRIOR_PACKAGE)["closing_capital"]
        if r["member_id"] == "MEM-02"
    )
    row["ending_cents"] += delta
    assert bool(_fired(check_prior_period_continuity(_ctx(payload)))) is should_fail


def test_the_opening_total_continues_the_prior_package_as_well() -> None:
    """The member columns can each continue correctly while the total does not.

    A restatement applied to the prior package's total and not to its columns is
    exactly the shape of a late adjustment, so the total is struck separately.
    """
    payload = _payload()
    _doc(payload, DOC_PRIOR_PACKAGE)["closing_total_cents"] += 1
    fired = _fired(check_prior_period_continuity(_ctx(payload)))
    assert len(fired) == 1
    assert CAPITAL_BEGINNING in fired[0].location


# --------------------------------------------------------------------------- #
# package_complete -- one of each, and every promise on the contents page kept
# --------------------------------------------------------------------------- #
def test_two_of_the_same_statement_is_a_package_nobody_can_read() -> None:
    payload = _payload()
    payload["documents"].append(dict(_doc(payload, DOC_TRIAL_BALANCE)))
    fired = _fired(check_package_complete(_ctx(payload)))
    assert fired
    assert "exactly one of each" in fired[0].message


def test_an_unreadable_period_bound_is_reported() -> None:
    """The period is what an executed draw is tested against, so it has to parse."""
    payload = _payload()
    payload["period_start"] = "April 2032"
    fired = _fired(check_package_complete(_ctx(payload)))
    assert fired
    assert "not a readable date" in fired[0].message


def test_a_statement_named_in_the_contents_and_left_empty_is_reported() -> None:
    payload = _payload()
    schedule = _doc(payload, DOC_DEVCOST_SCHEDULE)
    schedule["rows"] = []
    del schedule["total_cents"]
    fired = _fired(check_package_complete(_ctx(payload)))
    assert fired
    assert "carries nothing" in fired[0].message


# --------------------------------------------------------------------------- #
# release_gate -- the control over the other controls
# --------------------------------------------------------------------------- #
def _blocking() -> list[Finding]:
    return [Finding("tb_nets_zero", Status.FAIL, "-", "an open exception, for the gate")]


def test_a_package_correctly_held_over_an_open_exception_is_not_an_exception() -> None:
    """A gate that fires on the right decision teaches a preparer to ignore it."""
    payload = _payload()
    _doc(payload, DOC_RELEASE_LOG)["release_decision"] = RELEASE_HELD
    assert not _fired(check_release_gate(_ctx(payload, _blocking())))


def test_one_open_exception_is_enough_to_hold_the_package() -> None:
    """There is no materiality gate, and there should not be: materiality is a
    judgement about a figure the partner has not seen yet."""
    payload = _payload()
    _doc(payload, DOC_RELEASE_LOG)["release_decision"] = RELEASE_RELEASED
    fired = _fired(check_release_gate(_ctx(payload, _blocking())))
    assert fired
    assert RELEASE_HELD in fired[0].message


def test_a_flag_alone_still_holds_the_package() -> None:
    """A review signal is an open exception until somebody has reviewed it.

    The gate counts every non-PASS finding, not only the failures, because the
    whole point of a FLAG is that a person has not looked yet.
    """
    payload = _payload()
    _doc(payload, DOC_RELEASE_LOG)["release_decision"] = RELEASE_RELEASED
    flag = [Finding("cash_supported", Status.FLAG, "-", "support has not arrived yet")]
    assert _fired(check_release_gate(_ctx(payload, flag)))


def test_an_unreadable_release_decision_is_reported() -> None:
    payload = _payload()
    _doc(payload, DOC_RELEASE_LOG)["release_decision"] = "issued"
    fired = _fired(check_release_gate(_ctx(payload)))
    assert fired
    assert "cannot be read" in fired[0].message


def test_the_gate_ignores_its_own_findings() -> None:
    """A gate that counted itself would hold every package it had already held."""
    payload = _payload()
    own = [Finding("release_gate", Status.FAIL, "-", "a finding the gate itself made")]
    assert not _fired(check_release_gate(_ctx(payload, own)))


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "tb_nets_zero": Status.FAIL,
    "tb_completeness": Status.FAIL,
    "tb_agrees_ledger": Status.FAIL,
    "bs_balances": Status.FAIL,
    "interco_classified": Status.FAIL,
    "capital_agrees_ledger": Status.FAIL,
    "contributions_foot": Status.FAIL,
    "total_cross_foots": Status.FAIL,
    "capital_rollforward": Status.FAIL,
    "net_income_agrees": Status.FAIL,
    "devcost_agrees_wip": Status.FAIL,
    "jobcost_bridge": Status.FAIL,
    "division_coverage": Status.FAIL,
    "draw_schedule_agrees": Status.FAIL,
    "reciprocal_investment": Status.FAIL,
    "nil_is_genuine": Status.FAIL,
    # The one review signal in the registry: the engine can report that a bank
    # reconciliation is absent and cannot manufacture one.
    "cash_supported": Status.FLAG,
    "footnote_figures": Status.FAIL,
    "caption_matches_type": Status.FAIL,
    "cover_consistent": Status.FAIL,
    "checkrows_excluded": Status.FAIL,
    "no_preparer_artifacts": Status.FAIL,
    "prior_period_continuity": Status.FAIL,
    "package_complete": Status.FAIL,
    "release_gate": Status.FAIL,
}


def test_observed_severity_matches_the_design_table(reports) -> None:
    """Severity is a design decision, so it is written down and then checked.

    ``reports`` is requested so the whole registry has executed first: severity
    is declared by running a rule, and a rule that returned early before
    declaring one would default to FAIL invisibly.
    """
    for rule_id in RULE_IDS:
        assert rule_id in SEVERITY, f"{rule_id} never declared a severity"
        assert SEVERITY[rule_id] is DESIGNED_SEVERITY[rule_id], (
            f"{rule_id} runs at {SEVERITY[rule_id].value} and is designed as "
            f"{DESIGNED_SEVERITY[rule_id].value}"
        )


def test_design_table_covers_the_whole_registry(reports) -> None:
    assert set(SEVERITY) == set(DESIGNED_SEVERITY)


def test_every_rule_id_names_its_own_check_function() -> None:
    """``check_<rule_id>`` for all twenty-five, so a finding names its code.

    A registry that registered a function under a different name would still run
    and would leave a reader of the report with no way to find the control that
    produced it.
    """
    for rule_id in RULE_IDS:
        assert hasattr(engine_module, f"check_{rule_id}"), (
            f"{rule_id} has no check_{rule_id} in the engine module"
        )
    assert len(RULE_IDS) == len(DESIGNED_SEVERITY) == 25
    assert set(RULE_IDS) == set(DEFECT_BY_RULE), (
        "every control needs a planted defect for its semantics test to have "
        "something to fire on"
    )
