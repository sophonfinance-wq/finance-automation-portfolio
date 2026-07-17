"""Tests for the sentinel-aware CLI and the guardrail demo mode.

Covers the exit-code contract (clean close + zero CRITICAL findings == 0),
the ``--demo-guardrails`` PASS/FAIL table, the ``--sentinel/--no-sentinel``
switch, and the report wiring (Control findings section + ``sentinel.json``).
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from close_engine import cli, faults, report
from close_engine.engine import CloseEngine
from close_engine.faults import FAULTS
from close_engine.generate import generate_dataset
from close_engine.sentinel import Finding, SentinelReport, Severity

PACKAGE_ROOT = Path(__file__).resolve().parents[2]

SEEDS = [3, 42, 2026]
PERIODS = ["2026-01", "2026-03", "2026-08"]
GRID = [(p, s) for p in PERIODS for s in SEEDS]

CONTROL_LABELS = {
    "C1": "re_balance",
    "C2": "interco_mirror",
    "C3": "completeness_calendar",
    "C4": "asset_life_guard",
    "C5": "driver_provenance",
    "C6": "crossfoot",
    "C7": "step_change",
    "C8": "rounding_policy",
    "C9": "shadow_recompute",
    "C10": "period_lock",
}


def _run_main(argv: list[str]) -> tuple[int, str]:
    """Run ``cli.main`` in-process, capturing stdout."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cli.main(argv)
    return code, buf.getvalue()


class _TamperingEngine(CloseEngine):
    """A close engine whose posted output is tampered by a single cent.

    The tampered entry still balances, so only the sentinel's shadow
    recompute (C9) can see the manipulation.
    """

    def run(self):
        result = super().run()
        tampered, _desc = faults.inject_shadow_tamper(result)
        return tampered


# --------------------------------------------------------------------------- #
# --demo-guardrails: clean baseline + every fault caught
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module", params=[("2026-03", 2026), ("2026-08", 42)])
def demo_run(request) -> tuple[int, str]:
    """One full guardrail demo run (exit code, captured stdout)."""
    period, seed = request.param
    return _run_main(
        ["--demo-guardrails", "--period", period, "--seed", str(seed)]
    )


def test_the_guardrail_demo_exits_zero_when_every_control_holds(demo_run) -> None:
    code, _out = demo_run
    assert code == 0


def test_the_guardrail_demo_runs_the_clean_baseline_first(demo_run) -> None:
    _code, out = demo_run
    lines = [ln for ln in out.splitlines() if "->" in ln]
    assert lines, "expected a PASS/FAIL table"
    assert "baseline (no fault)" in lines[0]
    assert "PASS" in lines[0]
    assert "zero findings on clean data" in lines[0]


def test_the_guardrail_demo_table_shows_no_failures(demo_run) -> None:
    _code, out = demo_run
    assert "FAIL" not in out
    assert "GUARDRAIL GAP" not in out


def test_the_guardrail_demo_prints_the_verdict_line(demo_run) -> None:
    _code, out = demo_run
    assert "Demo verdict: ALL GUARDRAILS HELD" in out
    assert len(FAULTS) == 12
    assert "(12 faults, baseline clean)" in out


def test_the_demo_table_includes_the_trial_balance_and_step_rows(demo_run) -> None:
    _code, out = demo_run
    c1_row = next(
        ln for ln in out.splitlines()
        if ln.strip().startswith("unbalanced_opening")
    )
    assert "PASS: caught by C1 re_balance (CRITICAL)" in c1_row
    c7_row = next(
        ln for ln in out.splitlines()
        if ln.strip().startswith("uncorroborated_step")
    )
    # For the reviewer-escalation control C7 a WARN counts as caught; the
    # table names the severity so the rule is visible in the output.
    assert "PASS: caught by C7 step_change (WARN)" in c7_row


@pytest.mark.parametrize("period", ["2025-06", "2026-03", "2026-07", "2026-12"])
def test_the_guardrail_demo_passes_at_any_valid_period(period) -> None:
    # Periods before any policy incepts, mid-year, at the renewal month, and
    # at year-end: injectors with period preconditions must guard themselves
    # (substituting a same-class fault where needed) so the demo still holds.
    code, out = _run_main(["--demo-guardrails", "--period", period])
    assert code == 0
    assert "Demo verdict: ALL GUARDRAILS HELD" in out
    assert "FAIL" not in out


def test_the_guardrail_demo_output_is_plain_ascii(demo_run) -> None:
    _code, out = demo_run
    non_ascii = {ch for ch in out if ord(ch) > 127}
    assert not non_ascii, f"non-ASCII characters in demo output: {non_ascii!r}"


@pytest.mark.parametrize("fault_name", list(FAULTS))
def test_each_fault_row_reports_pass_by_its_expected_control(
    demo_run, fault_name
) -> None:
    _code, out = demo_run
    _injector, expected_id = FAULTS[fault_name]
    row = next(
        (ln for ln in out.splitlines() if ln.strip().startswith(fault_name)),
        None,
    )
    assert row is not None, f"no demo table row for {fault_name}"
    assert "-> PASS: caught by" in row
    assert f"caught by {expected_id} {CONTROL_LABELS[expected_id]}" in row


def test_every_registered_fault_appears_exactly_once_in_the_table(demo_run) -> None:
    _code, out = demo_run
    for fault_name in FAULTS:
        rows = [
            ln for ln in out.splitlines() if ln.strip().startswith(fault_name)
        ]
        assert len(rows) == 1, f"expected exactly one row for {fault_name}"


def test_the_demo_fails_when_a_control_does_not_catch_its_fault(
    monkeypatch,
) -> None:
    # Map a balanced tamper to C1 (re-balance): the entry still balances, so
    # C1 stays silent and the demo must report the guardrail gap.
    monkeypatch.setattr(
        faults, "FAULTS", {"shadow_tamper": (faults.inject_shadow_tamper, "C1")}
    )
    code, out = _run_main(["--demo-guardrails", "--period", "2026-03"])
    assert code == 1
    assert "FAIL: C1 re_balance did not fire" in out
    assert "Demo verdict: GUARDRAIL GAP DETECTED" in out


def test_the_demo_fails_when_the_clean_baseline_is_not_silent(monkeypatch) -> None:
    # A control layer that cries wolf on clean data is as broken as one that
    # misses faults: any baseline finding (even INFO) fails the demo.
    noisy = SentinelReport(
        [Finding("C7", Severity.INFO, None, "noise", "spurious note")]
    )
    monkeypatch.setattr(cli, "run_sentinel", lambda *a, **k: noisy)
    code, out = _run_main(["--demo-guardrails", "--period", "2026-03"])
    assert code == 1
    assert "baseline (no fault)" in out
    assert "FAIL: 1 unexpected finding(s) on clean data" in out
    assert "Demo verdict: GUARDRAIL GAP DETECTED" in out


def test_demo_guardrails_exits_zero_via_subprocess() -> None:
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "close_engine", "--demo-guardrails"],
        cwd=PACKAGE_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for fault_name in FAULTS:
        assert fault_name in proc.stdout
    assert "ALL GUARDRAILS HELD" in proc.stdout


# --------------------------------------------------------------------------- #
# Normal runs: --sentinel default ON, exit-code contract
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("period,seed", GRID)
def test_a_clean_close_with_the_sentinel_on_exits_zero(
    period, seed, tmp_path
) -> None:
    code, out = _run_main(
        ["--period", period, "--out", str(tmp_path), "--seed", str(seed)]
    )
    assert code == 0
    assert "Sentinel: all controls passed (no findings)." in out


def test_the_sentinel_is_on_by_default_and_writes_sentinel_json(tmp_path) -> None:
    code, _out = _run_main(["--period", "2026-03", "--out", str(tmp_path)])
    assert code == 0
    data = json.loads((tmp_path / "sentinel.json").read_text(encoding="utf-8"))
    assert data["clean"] is True
    assert data["findings"] == []
    assert data["critical_count"] == 0


def test_the_close_report_states_all_controls_passed_on_a_clean_close(
    tmp_path,
) -> None:
    code, _out = _run_main(["--period", "2026-03", "--out", str(tmp_path)])
    assert code == 0
    text = (tmp_path / "close_report.md").read_text(encoding="utf-8")
    assert "## Control findings" in text
    assert "All controls passed." in text


def test_no_sentinel_skips_the_controls_and_their_outputs(tmp_path) -> None:
    code, out = _run_main(
        ["--period", "2026-03", "--out", str(tmp_path), "--no-sentinel"]
    )
    assert code == 0
    assert "Sentinel:" not in out
    assert not (tmp_path / "sentinel.json").exists()
    text = (tmp_path / "close_report.md").read_text(encoding="utf-8")
    assert "## Control findings" not in text


def test_a_tampered_close_exits_nonzero_when_the_sentinel_is_on(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(cli, "CloseEngine", _TamperingEngine)
    code, out = _run_main(["--period", "2026-03", "--out", str(tmp_path)])
    assert code == 1
    assert "Sentinel: NOT CLEAN" in out
    assert "[CRITICAL] C9" in out


def test_a_tampered_close_slips_through_without_the_sentinel(
    monkeypatch, tmp_path
) -> None:
    # The tampered entry still balances, so the engine's own gate stays green:
    # the sentinel is the only control that blocks the manipulation.
    monkeypatch.setattr(cli, "CloseEngine", _TamperingEngine)
    code, _out = _run_main(
        ["--period", "2026-03", "--out", str(tmp_path), "--no-sentinel"]
    )
    assert code == 0


def test_critical_findings_render_in_the_close_report_and_json(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(cli, "CloseEngine", _TamperingEngine)
    _run_main(["--period", "2026-03", "--out", str(tmp_path)])
    text = (tmp_path / "close_report.md").read_text(encoding="utf-8")
    assert "## Control findings" in text
    assert "CRITICAL" in text
    assert "C9" in text
    data = json.loads((tmp_path / "sentinel.json").read_text(encoding="utf-8"))
    assert data["clean"] is False
    assert data["critical_count"] >= 1
    assert any(f["control_id"] == "C9" for f in data["findings"])


def test_warn_only_findings_do_not_block_the_close(monkeypatch, tmp_path) -> None:
    warn_only = SentinelReport(
        [Finding("C7", Severity.WARN, "ENT-01", "uncorroborated step", "detail")]
    )
    monkeypatch.setattr(cli, "run_sentinel", lambda *a, **k: warn_only)
    code, out = _run_main(["--period", "2026-03", "--out", str(tmp_path)])
    assert code == 0
    assert "Sentinel: CLEAN - 0 critical, 1 warning, 0 info." in out
    assert "[WARN] C7 ENT-01: uncorroborated step" in out


def test_a_clean_close_with_sentinel_exits_zero_via_subprocess(tmp_path) -> None:
    proc = subprocess.run(
        [
            sys.executable, "-X", "utf8", "-m", "close_engine",
            "--period", "2026-03", "--out", str(tmp_path),
        ],
        cwd=PACKAGE_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Sentinel: all controls passed" in proc.stdout
    assert (tmp_path / "sentinel.json").exists()


# --------------------------------------------------------------------------- #
# Parser and control-label plumbing
# --------------------------------------------------------------------------- #


def test_the_sentinel_flag_defaults_on() -> None:
    args = cli._build_parser().parse_args([])
    assert args.sentinel is True
    assert args.demo_guardrails is False


@pytest.mark.parametrize(
    "flag,expected", [("--sentinel", True), ("--no-sentinel", False)]
)
def test_the_sentinel_flag_parses_both_spellings(flag, expected) -> None:
    args = cli._build_parser().parse_args([flag])
    assert args.sentinel is expected


def test_the_demo_guardrails_flag_parses() -> None:
    args = cli._build_parser().parse_args(["--demo-guardrails"])
    assert args.demo_guardrails is True


def test_demo_guardrails_still_validates_the_period() -> None:
    with pytest.raises(SystemExit):
        cli.main(["--demo-guardrails", "--period", "2026-13"])


@pytest.mark.parametrize("control_id,label", sorted(CONTROL_LABELS.items()))
def test_control_labels_derive_from_the_registered_controls(
    control_id, label
) -> None:
    assert cli._control_labels()[control_id] == label


# --------------------------------------------------------------------------- #
# report.sentinel_json / close_report_markdown wiring
# --------------------------------------------------------------------------- #


def _mixed_report() -> SentinelReport:
    return SentinelReport(
        [
            Finding("C4", Severity.CRITICAL, "ENT-02", "over-accrual", "excess 1.00"),
            Finding("C7", Severity.WARN, None, "unexplained step", "no event"),
            Finding("C7", Severity.INFO, "ENT-01", "step-up explained", "renewal"),
        ]
    )


def test_sentinel_json_counts_reconcile_to_the_findings() -> None:
    data = report.sentinel_json(_mixed_report())
    assert data["critical_count"] == 1
    assert data["warning_count"] == 1
    assert data["info_count"] == 1
    assert len(data["findings"]) == 3
    assert data["clean"] is False
    assert data["summary"] == _mixed_report().summary_line()


@pytest.mark.parametrize("severity", list(Severity))
def test_sentinel_json_serializes_each_severity_as_its_value(severity) -> None:
    rep = SentinelReport([Finding("C1", severity, None, "s", "d")])
    data = report.sentinel_json(rep)
    assert data["findings"][0]["severity"] == severity.value


def test_sentinel_json_of_a_clean_report_is_clean_and_empty() -> None:
    data = report.sentinel_json(SentinelReport([]))
    assert data["clean"] is True
    assert data["findings"] == []
    assert data["summary"] == "Sentinel: all controls passed (no findings)."


def test_sentinel_json_round_trips_through_json() -> None:
    data = report.sentinel_json(_mixed_report())
    assert json.loads(json.dumps(data)) == data


def test_the_close_report_lists_each_finding_and_never_calls_it_clean(
    capsys,
) -> None:
    period = "2026-03"
    result = CloseEngine(generate_dataset(period)).run()
    md = report.close_report_markdown(result, sentinel=_mixed_report())
    assert "## Control findings" in md
    assert "| C4 | CRITICAL | ENT-02 | over-accrual | excess 1.00 |" in md
    assert "| C7 | WARN | group | unexplained step | no event |" in md
    assert "| C7 | INFO | ENT-01 | step-up explained | renewal |" in md
    assert "Close status: NOT CLEAN" in md

    cli._print_summary(result, ".", _mixed_report())
    assert "Close status: NOT CLEAN" in capsys.readouterr().out


def test_the_close_report_omits_the_section_without_a_sentinel_report() -> None:
    result = CloseEngine(generate_dataset("2026-03")).run()
    md = report.close_report_markdown(result)
    assert "## Control findings" not in md


@pytest.mark.parametrize("period,seed", GRID)
def test_write_outputs_with_sentinel_adds_exactly_the_sentinel_json(
    period, seed, tmp_path
) -> None:
    dataset = generate_dataset(period, seed=seed)
    result = CloseEngine(dataset).run()
    from close_engine.sentinel import run_sentinel

    rep = run_sentinel(dataset, result)
    written = report.write_outputs(result, tmp_path, sentinel=rep)
    names = {p.name for p in written}
    assert "sentinel.json" in names
    data = json.loads((tmp_path / "sentinel.json").read_text(encoding="utf-8"))
    assert data["clean"] is True


def test_write_outputs_without_sentinel_writes_no_sentinel_json(tmp_path) -> None:
    result = CloseEngine(generate_dataset("2026-03")).run()
    written = report.write_outputs(result, tmp_path)
    assert not any(p.name == "sentinel.json" for p in written)
    assert not (tmp_path / "sentinel.json").exists()
