"""Fictional postage allocation: mapping, posting, and control tests."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

from close_engine.cli import main
from close_engine.engine import CloseEngine
from close_engine.generate import PostageMeterLine, PostageRoute, generate_dataset
from close_engine.loop import AUTO_POSTED, autonomous_close_loop
from close_engine.model import JournalLine
from close_engine.sentinel import run_sentinel
from close_engine.sentinel.controls import (
    c2_interco_mirror,
    c3_completeness_calendar,
    c6_crossfoot,
    c9_shadow_recompute,
    c10_period_lock,
    lock_register,
)
from close_engine.sentinel.shadow import expected_for_category


PERIOD = "2026-03"


def _run(seed: int = 2026):
    dataset = generate_dataset(PERIOD, seed=seed)
    return dataset, CloseEngine(dataset).run()


def _entry(result):
    return next(
        je for je in result.register if je.category == "postage_allocation"
    )


def _schedule(result):
    return next(
        schedule
        for schedule in result.schedules
        if schedule.category == "postage_allocation"
    )


def _signed(lines, account: str) -> int:
    return sum(
        line.debit - line.credit for line in lines if line.account == account
    )


def test_every_meter_row_exactly_matches_one_approved_route() -> None:
    dataset, result = _run()
    batch = dataset.postage_batches()[0]
    routes = {route.project_code: route for route in batch.routes}
    assert len(routes) == len(batch.routes)

    entry = _entry(result)
    schedule = _schedule(result)
    rows = {row.fields["meter_line"]: row for row in schedule.rows}
    assert len(rows) == len(batch.meter_lines)
    for meter_line in batch.meter_lines:
        route = routes[meter_line.project_code]
        row = rows[meter_line.line_id]
        assert row.fields["project"] == route.project_code
        assert row.fields["job"] == route.job_code
        assert row.fields["cost_code"] == route.cost_code
        assert row.fields["recipient"] == route.recipient_entity
        expense = [
            line
            for line in entry.lines
            if line.account == "6700"
            and line.source_batch == batch.batch_id
            and line.source_line == meter_line.line_id
        ]
        if meter_line.amount_cents == 0:
            assert expense == []
            assert row.fields["status"] == "zero - no posting"
        else:
            assert len(expense) == 1
            assert expense[0].entity == route.recipient_entity
            assert expense[0].project_code == route.project_code
            assert expense[0].job_code == route.job_code
            assert expense[0].cost_code == route.cost_code
            assert expense[0].debit - expense[0].credit == meter_line.amount_cents


def test_unmapped_project_refuses_the_entire_batch_without_partial_posting() -> None:
    dataset = generate_dataset(PERIOD, seed=5)
    batch = dataset.postage_batches()[0]
    changed = replace(
        batch.meter_lines[0], project_code="PRJ-UNMAPPED"
    )
    dataset.subs.postage_batches[0] = replace(
        batch, meter_lines=(changed, *batch.meter_lines[1:])
    )

    result = CloseEngine(dataset).run()
    assert not any(
        je.category == "postage_allocation" for je in result.register
    )
    refusals = [
        error for error in result.refused
        if error.je.category == "postage_allocation"
    ]
    assert len(refusals) == 1
    assert "unmapped meter projects" in refusals[0].detail
    assert "PRJ-UNMAPPED" in refusals[0].detail
    assert any(
        finding.subject == "postage route table fails exact-match integrity"
        for finding in c6_crossfoot(dataset, result)
    )


def test_duplicate_project_route_refuses_the_entire_batch() -> None:
    dataset = generate_dataset(PERIOD, seed=6)
    batch = dataset.postage_batches()[0]
    duplicate = PostageRoute(
        batch.routes[0].project_code,
        batch.routes[1].recipient_entity,
        "JOB-DUPLICATE-99",
        "COST-DUPLICATE-99",
    )
    dataset.subs.postage_batches[0] = replace(
        batch, routes=(*batch.routes, duplicate)
    )
    result = CloseEngine(dataset).run()

    assert not any(
        je.category == "postage_allocation" for je in result.register
    )
    assert any(
        "duplicate project routes" in error.detail
        for error in result.refused
        if error.je.category == "postage_allocation"
    )


@pytest.mark.parametrize("identifier", ["batch", "line", "project", "job", "cost"])
@pytest.mark.parametrize("bad_value", ["", "   ", " PADDED "])
def test_blank_or_noncanonical_route_identifiers_block_the_batch(
    identifier: str, bad_value: str
) -> None:
    dataset = generate_dataset(PERIOD, seed=7)
    batch = dataset.postage_batches()[0]
    if identifier == "batch":
        changed = replace(batch, batch_id=bad_value)
    elif identifier == "line":
        changed_line = replace(batch.meter_lines[0], line_id=bad_value)
        changed = replace(
            batch, meter_lines=(changed_line, *batch.meter_lines[1:])
        )
    elif identifier == "project":
        original_project = batch.meter_lines[0].project_code
        changed_lines = tuple(
            replace(line, project_code=bad_value)
            if line.project_code == original_project
            else line
            for line in batch.meter_lines
        )
        changed_routes = tuple(
            replace(route, project_code=bad_value)
            if route.project_code == original_project
            else route
            for route in batch.routes
        )
        changed = replace(
            batch, meter_lines=changed_lines, routes=changed_routes
        )
    elif identifier == "job":
        changed = replace(
            batch,
            routes=(replace(batch.routes[0], job_code=bad_value), *batch.routes[1:]),
        )
    else:
        changed = replace(
            batch,
            routes=(replace(batch.routes[0], cost_code=bad_value), *batch.routes[1:]),
        )
    dataset.subs.postage_batches[0] = changed

    result = CloseEngine(dataset).run()
    assert not any(
        entry.category == "postage_allocation" for entry in result.register
    )
    assert any(
        error.je.category == "postage_allocation" for error in result.refused
    )
    assert expected_for_category(dataset, "postage_allocation") == {}
    assert any(
        finding.subject == "postage route table fails exact-match integrity"
        for finding in c6_crossfoot(dataset, result)
    )


def test_meter_project_job_expense_and_clearing_crossfoot_exactly() -> None:
    dataset, result = _run()
    batch = dataset.postage_batches()[0]
    entry = _entry(result)
    meter_total = sum(line.amount_cents for line in batch.meter_lines)

    assert _signed(entry.lines, "6700") == meter_total
    assert -_signed(entry.lines, "1460") == meter_total
    assert result.ledger.balance(batch.holder_entity, "1460") == 0
    assert result.ledger.account_balance("1460") == 0
    ties = [tie for tie in result.ties if tie.account == "1460"]
    assert {tie.entity for tie in ties} == {
        entity.code for entity in dataset.entities()
    }
    assert all(tie.expected_cents == tie.actual_cents == 0 for tie in ties)
    assert all(tie.ties for tie in ties)
    assert c6_crossfoot(dataset, result) == []


def test_equal_and_opposite_entity_clearing_balances_cannot_net_to_clean() -> None:
    dataset = generate_dataset(PERIOD, seed=8)
    offset = 100
    dataset.opening_tb.extend(
        [
            JournalLine("DH", "1460", offset, 0, "Entity clearing defect"),
            JournalLine("DH", "3000", 0, offset, "Entity clearing plug"),
            JournalLine("MF", "3000", offset, 0, "Entity clearing plug"),
            JournalLine("MF", "1460", 0, offset, "Entity clearing defect"),
        ]
    )
    result = CloseEngine(dataset).run()

    assert result.ledger.account_balance("1460") == 0
    assert result.ledger.balance("DH", "1460") == offset
    assert result.ledger.balance("MF", "1460") == -offset
    failed = [
        tie
        for tie in result.ties
        if tie.account == "1460" and not tie.ties
    ]
    assert {tie.entity for tie in failed} == {"DH", "MF"}
    assert not result.all_tie
    findings = c6_crossfoot(dataset, result)
    assert {
        finding.entity
        for finding in findings
        if finding.subject == "per-entity unallocated postage balance not cleared"
    } == {"DH", "MF"}

    # Even an unknown entity with no 1460 balance is part of the opening/GL
    # universe and must fail scope validation instead of disappearing from the
    # configured-entity tie list.
    unknown_dataset = generate_dataset(PERIOD, seed=8)
    unknown_dataset.opening_tb.extend(
        [
            JournalLine("ZZ", "1000", 100, 0, "Unknown entity debit"),
            JournalLine("ZZ", "3000", 0, 100, "Unknown entity credit"),
        ]
    )
    unknown_result = CloseEngine(unknown_dataset).run()
    unknown_tie = next(
        tie
        for tie in unknown_result.ties
        if tie.account == "1460" and tie.entity == "ZZ"
    )
    assert unknown_tie.actual_cents == 0
    assert not unknown_tie.scope_valid
    assert not unknown_tie.ties
    assert not unknown_result.clean
    assert any(
        finding.subject
        == "unknown entity present in postage accounting universe"
        and finding.entity == "ZZ"
        for finding in c6_crossfoot(unknown_dataset, unknown_result)
    )


def test_prefix_related_batch_ids_use_exact_structured_linkage() -> None:
    dataset = generate_dataset(PERIOD, seed=9)
    first = dataset.postage_batches()[0]
    second = replace(first, batch_id=f"{first.batch_id}-B2")
    dataset.subs.postage_batches.append(second)
    total = sum(line.amount_cents for line in second.meter_lines)
    dataset.opening_tb.extend(
        [
            JournalLine(
                second.holder_entity,
                "1460",
                total,
                0,
                "Second fictional meter batch",
            ),
            JournalLine(
                second.holder_entity,
                "3000",
                0,
                total,
                "Second fictional meter plug",
            ),
        ]
    )

    result = CloseEngine(dataset).run()
    assert result.clean
    assert c6_crossfoot(dataset, result) == []
    entry = _entry(result)
    assert sum(
        line.debit - line.credit
        for line in entry.lines
        if line.account == "6700" and line.source_batch == first.batch_id
    ) == sum(line.amount_cents for line in first.meter_lines)
    assert sum(
        line.debit - line.credit
        for line in entry.lines
        if line.account == "6700" and line.source_batch == second.batch_id
    ) == total


def test_intercompany_postage_legs_mirror_and_every_entity_self_balances() -> None:
    dataset, result = _run()
    entry = _entry(result)
    for difference in entry.balances_per_entity().values():
        assert difference == 0

    due_from = _signed(entry.lines, "1800")
    due_to = -_signed(entry.lines, "2800")
    assert due_from == due_to
    assert due_from != 0
    assert c2_interco_mirror(dataset, result) == []


def test_refund_reverses_expense_intercompany_and_clearing() -> None:
    dataset, result = _run()
    batch = dataset.postage_batches()[0]
    refund = next(line for line in batch.meter_lines if line.amount_cents < 0)
    route = next(
        route for route in batch.routes
        if route.project_code == refund.project_code
    )
    lines = [line for line in _entry(result).lines if refund.line_id in line.memo]
    magnitude = -refund.amount_cents

    assert any(
        line.entity == route.recipient_entity
        and line.account == "6700"
        and line.credit == magnitude
        for line in lines
    )
    assert any(
        line.entity == route.recipient_entity
        and line.account == "2800"
        and line.debit == magnitude
        for line in lines
    )
    assert any(
        line.entity == batch.holder_entity
        and line.account == "1800"
        and line.credit == magnitude
        for line in lines
    )
    assert any(
        line.entity == batch.holder_entity
        and line.account == "1460"
        and line.debit == magnitude
        for line in lines
    )


def test_missing_and_duplicate_postage_entries_are_c3_blockers() -> None:
    dataset, result = _run()
    missing = copy.deepcopy(result)
    missing.register = [
        je for je in missing.register if je.category != "postage_allocation"
    ]
    missing_findings = c3_completeness_calendar(dataset, missing)
    assert any(
        finding.subject == "expected recurring entry absent"
        and "postage_allocation" in finding.detail
        for finding in missing_findings
    )

    duplicate = copy.deepcopy(result)
    duplicate.register.append(copy.deepcopy(_entry(result)))
    duplicate_findings = c3_completeness_calendar(dataset, duplicate)
    assert any(
        finding.subject == "duplicate recurring entry"
        and "postage_allocation" in finding.detail
        for finding in duplicate_findings
    )


def test_shadow_recompute_catches_a_one_cent_postage_tamper() -> None:
    dataset, result = _run()
    assert expected_for_category(dataset, "postage_allocation")
    assert c9_shadow_recompute(dataset, result) == []

    corrupted = copy.deepcopy(result)
    entry = _entry(corrupted)
    index = next(i for i, line in enumerate(entry.lines) if line.account == "6700")
    entry.lines[index] = replace(
        entry.lines[index], debit=entry.lines[index].debit + 1
    )
    findings = c9_shadow_recompute(dataset, corrupted)
    assert any(
        finding.subject == "shadow recomputation disagrees"
        and "postage_allocation" in finding.detail
        for finding in findings
    )


@pytest.mark.parametrize("contract_part", ["header", "memo", "provenance"])
def test_c6_and_loop_enforce_the_full_canonical_postage_contract(
    contract_part: str,
) -> None:
    mutations = {
        "header": [
            ("je_id", "JE-2026-03-POSTAGE-FAKE"),
            ("period", "2026-02"),
            ("description", "Postage allocation tampered"),
        ],
        "memo": [("memo", "PST-FAKE LINE-FAKE PRJ-FAKE JOB-FAKE COST-FAKE")],
        "provenance": [
            ("source_batch", "PST-FAKE"),
            ("source_line", "PST-LINE-FAKE"),
            ("project_code", "PRJ-TAMPERED"),
            ("job_code", "JOB-ORCHARD-01-FAKE"),
            ("cost_code", "COST-MAIL-01-FAKE"),
        ],
    }
    for field, mutated in mutations[contract_part]:
        dataset, result = _run(seed=12)
        corrupted = copy.deepcopy(result)
        entry = _entry(corrupted)
        if contract_part == "header":
            setattr(entry, field, mutated)
        else:
            index = next(
                i for i, line in enumerate(entry.lines) if line.account == "6700"
            )
            entry.lines[index] = replace(
                entry.lines[index], **{field: mutated}
            )

        findings = c6_crossfoot(dataset, corrupted)
        assert findings, f"C6 did not reject tampered {field}"
        if contract_part == "header":
            assert any(
                finding.subject
                == "postage journal header does not match canonical contract"
                for finding in findings
            )

        journal = autonomous_close_loop(dataset, corrupted)
        assert journal.verdict == AUTO_POSTED
        assert journal.categories_resynced == ("postage_allocation",)
        assert journal.total_adjustments == 0
        assert _entry(corrupted) == _entry(CloseEngine(dataset).run())
        assert run_sentinel(dataset, corrupted).findings == []


def test_c6_catches_a_valid_intercompany_leg_reassigned_to_another_meter_row() -> None:
    dataset, result = _run(seed=12)
    corrupted = copy.deepcopy(result)
    entry = _entry(corrupted)
    source_ids = [
        line.line_id
        for line in dataset.postage_batches()[0].meter_lines
        if line.amount_cents > 0
    ]
    index = next(
        i
        for i, line in enumerate(entry.lines)
        if line.account == "1800"
    )
    original_source = entry.lines[index].source_line
    other_source = next(
        source_id for source_id in source_ids if source_id != original_source
    )
    entry.lines[index] = replace(entry.lines[index], source_line=other_source)

    findings = c6_crossfoot(dataset, corrupted)
    assert any(
        finding.subject
        == "postage meter line does not crossfoot to its approved job"
        for finding in findings
    )


def test_autonomous_loop_repairs_metadata_only_postage_tamper() -> None:
    dataset, posted = _run(seed=13)
    entry = _entry(posted)
    index = next(i for i, line in enumerate(entry.lines) if line.account == "6700")
    original = entry.lines[index]
    entry.lines[index] = replace(
        original, job_code=f"{original.job_code}-FAKE"
    )
    assert any(
        finding.control_id == "C6"
        for finding in run_sentinel(dataset, posted).findings
    )

    journal = autonomous_close_loop(dataset, posted)
    assert journal.verdict == AUTO_POSTED
    assert journal.categories_resynced == ("postage_allocation",)
    assert journal.total_adjustments == 0
    assert _entry(posted).lines == _entry(CloseEngine(dataset).run()).lines
    assert run_sentinel(dataset, posted).findings == []


def test_prior_period_batch_is_ignored_and_locked_register_stays_immutable() -> None:
    baseline_dataset, baseline_result = _run(seed=14)
    dataset = generate_dataset(PERIOD, seed=14)
    current = dataset.postage_batches()[0]
    old = replace(current, batch_id="PST-PRIOR", period="2026-02")
    dataset.subs.postage_batches.append(old)
    result = CloseEngine(dataset).run()

    assert _entry(result).lines == _entry(baseline_result).lines
    prior_dataset = generate_dataset("2026-02", seed=14)
    prior_result = CloseEngine(prior_dataset).run()
    locked = {"2026-02": lock_register(prior_result)}
    assert c10_period_lock(dataset, result, locked=locked) == []
    assert baseline_dataset.period == result.period

    for malformed in ("", "2026-3", " 2026-03", "2026-00", "2026-13"):
        malformed_dataset = generate_dataset(PERIOD, seed=14)
        current = malformed_dataset.postage_batches()[0]
        malformed_dataset.subs.postage_batches.append(
            replace(
                current,
                batch_id=f"PST-MALFORMED-{malformed!r}",
                period=malformed,
            )
        )
        malformed_result = CloseEngine(malformed_dataset).run()
        assert any(
            "must be canonical YYYY-MM" in error.detail
            for error in malformed_result.refused
            if error.je.category == "postage_allocation"
        )
        assert any(
            finding.subject == "postage route table fails exact-match integrity"
            and "must be canonical YYYY-MM" in finding.detail
            for finding in c6_crossfoot(malformed_dataset, malformed_result)
        )


def test_postage_outputs_are_deterministic_for_period_and_seed() -> None:
    first_dataset, first_result = _run(seed=27)
    second_dataset, second_result = _run(seed=27)
    assert first_dataset.postage_batches() == second_dataset.postage_batches()
    assert _entry(first_result).lines == _entry(second_result).lines
    assert _schedule(first_result).rows == _schedule(second_result).rows
    assert lock_register(first_result) == lock_register(second_result)


def test_report_and_cli_publish_the_postage_category(tmp_path, capsys) -> None:
    exit_code = main(
        [
            "--period", PERIOD,
            "--seed", "31",
            "--out", str(tmp_path),
        ]
    )
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Posted entries : 9" in output
    assert "Postage routes : 4/5 meter rows" in output
    register = json.loads((tmp_path / "je_register.json").read_text("utf-8"))
    postage_entry = next(
        entry
        for entry in register["entries"]
        if entry["category"] == "postage_allocation"
    )
    assert all(
        {
            "source_batch",
            "source_line",
            "project_code",
            "job_code",
            "cost_code",
        }
        <= line.keys()
        for line in postage_entry["lines"]
    )
    schedules = json.loads((tmp_path / "schedules.json").read_text("utf-8"))
    postage_schedule = next(
        schedule
        for schedule in schedules["schedules"]
        if schedule["category"] == "postage_allocation"
    )
    assert postage_schedule["tie_expected_by_entity_cents"] == {
        "BW": 0,
        "DH": 0,
        "MF": 0,
    }
    assert all(
        {"batch", "meter_line", "project", "job", "cost_code", "recipient"}
        <= row.keys()
        for row in postage_schedule["rows"]
    )
    report = (tmp_path / "close_report.md").read_text("utf-8")
    assert "Postage meter allocation" in report


def test_public_postage_sources_contain_no_private_identifiers() -> None:
    import close_engine.generate as generate_module

    package = Path(generate_module.__file__).parent
    system_root = package.parent
    repo_root = system_root.parent
    source_paths = [
        path
        for path in package.rglob("*.py")
        if "__pycache__" not in path.parts
    ]
    source_paths.extend(
        [system_root / "README.md", repo_root / "README.md", repo_root / "CHANGELOG.md"]
    )
    combined = "\n".join(path.read_text("utf-8").lower() for path in source_paths)
    banned = [
        "les" + "lie",
        "inte" + "gral",
        "eg" + "nyte",
        "sage" + chr(45) + "300",
        "y:" + chr(92),
        "z:" + chr(92),
    ]
    assert all(marker not in combined for marker in banned)


def test_all_zero_meter_population_creates_schedule_but_no_postage_entry() -> None:
    dataset = generate_dataset(PERIOD, seed=44)
    batch = dataset.postage_batches()[0]
    zeros = tuple(
        replace(line, amount_cents=0) for line in batch.meter_lines
    )
    # Remove the generated opening meter balance because this replacement
    # models a source population that was zero before the opening TB import.
    dataset.opening_tb = [
        line
        for line in dataset.opening_tb
        if line.account != "1460" and line.memo != "Opening postage plug"
    ]
    dataset.subs.postage_batches[0] = replace(batch, meter_lines=zeros)
    result = CloseEngine(dataset).run()
    assert not any(
        entry.category == "postage_allocation" for entry in result.register
    )
    assert len(_schedule(result).rows) == len(zeros)
    assert all(row.fields["status"] == "zero - no posting" for row in _schedule(result).rows)
    assert c3_completeness_calendar(dataset, result) == []


def test_duplicate_meter_line_id_is_a_population_blocker() -> None:
    dataset = generate_dataset(PERIOD, seed=45)
    batch = dataset.postage_batches()[0]
    duplicate = PostageMeterLine(
        batch.meter_lines[0].line_id,
        batch.meter_lines[1].project_code,
        "Duplicate import row",
        batch.meter_lines[1].amount_cents,
    )
    dataset.subs.postage_batches[0] = replace(
        batch, meter_lines=(batch.meter_lines[0], duplicate, *batch.meter_lines[2:])
    )
    result = CloseEngine(dataset).run()
    assert any(
        "duplicate meter line ids" in error.detail
        for error in result.refused
        if error.je.category == "postage_allocation"
    )
