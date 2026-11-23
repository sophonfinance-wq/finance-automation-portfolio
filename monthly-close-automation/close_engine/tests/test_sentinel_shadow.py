"""Shadow-vs-engine grid: two independent computations must agree to the cent.

The shadow module re-derives every recurring amount from the raw dataset with
its own arithmetic and no imports from the engine. On clean data it must
match the posted register exactly for EREDACTED category across a seed/period
grid; a single-cent tamper anywhere in the register must be detected.
"""

from __future__ import annotations

import ast
import copy
import inspect
from dataclasses import replace
from functools import lru_cache

import pytest

from close_engine.engine import CloseEngine
from close_engine.generate import generate_dataset
from close_engine.sentinel import Severity, run_sentinel
from close_engine.sentinel import shadow
from close_engine.sentinel.controls import c9_shadow_recompute

SEEDS = [1, 3, 7, 42, 99, 2026]
PERIODS = ["2026-01", "2026-03", "2026-07", "2026-10"]
GRID = [(p, s) for p in PERIODS for s in SEEDS]

# Every register has one entry per recurring category, in posting order.
REGISTER_SIZE = len(shadow.CATEGORIES)


@lru_cache(maxsize=None)
def _dataset(period: str, seed: int):
    return generate_dataset(period, seed=seed)


@lru_cache(maxsize=None)
def _result(period: str, seed: int):
    return CloseEngine(_dataset(period, seed)).run()


@lru_cache(maxsize=None)
def _expected(period: str, seed: int):
    return shadow.expected_amounts(_dataset(period, seed))


@lru_cache(maxsize=None)
def _actual(period: str, seed: int):
    amounts: dict[tuple[str, str, str], tuple[int, int]] = {}
    for je in _result(period, seed).register:
        for line in je.lines:
            key = (line.entity, je.category, line.account)
            debits, credits = amounts.get(key, (0, 0))
            amounts[key] = (debits + line.debit, credits + line.credit)
    return amounts


# --------------------------------------------------------------------------- #
# Independence of the shadow path
# --------------------------------------------------------------------------- #


def test_the_shadow_module_imports_nothing_from_the_engine() -> None:
    tree = ast.parse(inspect.getsource(shadow))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all("engine" not in alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert "engine" not in (node.module or "")
            assert all("engine" not in alias.name for alias in node.names)


def test_the_shadow_module_imports_nothing_from_the_money_helpers() -> None:
    # The shadow re-implements even the penny-splitting arithmetic so the two
    # computation paths share no code.
    tree = ast.parse(inspect.getsource(shadow))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all("money" not in alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert "money" not in (node.module or "")
            assert all("money" not in alias.name for alias in node.names)


def test_expected_for_category_rejects_an_unknown_category() -> None:
    with pytest.raises(KeyError):
        shadow.expected_for_category(_dataset("2026-03", 2026), "petty_cash")


def test_the_shadow_categories_cover_the_whole_register() -> None:
    result = _result("2026-03", 2026)
    assert [je.category for je in result.register] == list(shadow.CATEGORIES)


# --------------------------------------------------------------------------- #
# Clean data: shadow == engine, per category and in full
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("category", shadow.CATEGORIES)
@pytest.mark.parametrize("period,seed", GRID)
def test_shadow_and_engine_agree_on_clean_data_for_every_category(
    period, seed, category
) -> None:
    expected = shadow.expected_for_category(_dataset(period, seed), category)
    actual = {
        key: value
        for key, value in _actual(period, seed).items()
        if key[1] == category
    }
    for key in sorted(set(expected) | set(actual)):
        assert expected.get(key, (0, 0)) == actual.get(key, (0, 0)), key


@pytest.mark.parametrize("period,seed", GRID)
def test_the_full_shadow_map_matches_the_posted_register(period, seed) -> None:
    assert c9_shadow_recompute(_dataset(period, seed), _result(period, seed)) == []


@pytest.mark.parametrize("period,seed", GRID)
def test_a_clean_close_passes_the_whole_sentinel(period, seed) -> None:
    report = run_sentinel(_dataset(period, seed), _result(period, seed))
    assert report.clean
    assert report.findings == []


# --------------------------------------------------------------------------- #
# Tampering: one cent anywhere is detected
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("entry_index", range(REGISTER_SIZE))
@pytest.mark.parametrize("period,seed", GRID)
def test_a_single_cent_tamper_in_any_entry_is_detected(
    period, seed, entry_index
) -> None:
    res = copy.deepcopy(_result(period, seed))
    je = res.register[entry_index]
    line = je.lines[0]
    if line.debit:
        je.lines[0] = replace(line, debit=line.debit + 1)
    else:
        je.lines[0] = replace(line, credit=line.credit + 1)
    findings = c9_shadow_recompute(_dataset(period, seed), res)
    assert findings, f"tamper in {je.je_id} went undetected"
    assert all(f.severity is Severity.CRITICAL for f in findings)
    assert all(f.subject == "shadow recomputation disagrees" for f in findings)
    assert any(je.category in f.detail for f in findings)


@pytest.mark.parametrize("period,seed", GRID)
def test_a_tampered_close_fails_the_whole_sentinel(period, seed) -> None:
    res = copy.deepcopy(_result(period, seed))
    je = res.register[-1]
    line = je.lines[0]
    je.lines[0] = replace(line, debit=line.debit + 1)
    report = run_sentinel(_dataset(period, seed), res)
    assert not report.clean
    assert any(f.control_id == "C9" for f in report.criticals)
