"""The registry, the severity table and the fixture set must stay in step.

A rule can never be added without a fixture that exercises it, a severity the
design table agrees with, and an applier that plants the defect. These tests are
the mechanism that enforces that.
"""

from __future__ import annotations

from ap_engine.engine import REGISTRY, RULE_FAMILIES, SEVERITY
from ap_engine.generate import DEFECT_APPLIERS, DEFECTS
from ap_engine.model import Status


def _rule_ids() -> list[str]:
    return [rule_id for rule_id, _ in REGISTRY]


def test_every_rule_has_exactly_one_planted_defect() -> None:
    """The coverage contract: fixtures and registry describe the same set."""
    assert {d.rule for d in DEFECTS} == {rid for rid, _ in REGISTRY}


def test_defect_rules_are_unique() -> None:
    """Exactly one defect per rule, not two fixtures for the same rule."""
    rules = [d.rule for d in DEFECTS]
    assert len(rules) == len(set(rules))
    assert len(DEFECTS) == len(REGISTRY)


def test_defect_keys_are_unique_and_filename_safe() -> None:
    """Keys become filename stems and the conftest index key."""
    keys = [d.key for d in DEFECTS]
    assert len(keys) == len(set(keys))
    assert "clean" not in keys
    for key in keys:
        assert key and key.replace("_", "").isalnum(), key


def test_registry_is_an_ordered_list_of_pairs() -> None:
    """Report order is the registry order; a dict or set would lose it."""
    assert isinstance(REGISTRY, list)
    for entry in REGISTRY:
        assert isinstance(entry, tuple) and len(entry) == 2
        rule_id, fn = entry
        assert isinstance(rule_id, str) and callable(fn)


def test_rule_ids_are_unique() -> None:
    ids = _rule_ids()
    assert len(ids) == len(set(ids))


def test_every_rule_belongs_to_a_declared_family() -> None:
    """Rule ids carry their family prefix; the report rollup depends on it."""
    for rule_id in _rule_ids():
        assert rule_id.split("_", 1)[0] in RULE_FAMILIES, rule_id


def test_registry_is_grouped_by_family_in_order() -> None:
    """Families appear contiguously and in the declared order."""
    seen: list[str] = []
    for rule_id in _rule_ids():
        family = rule_id.split("_", 1)[0]
        if not seen or seen[-1] != family:
            seen.append(family)
    assert seen == list(RULE_FAMILIES)


def test_severity_table_covers_exactly_the_registry() -> None:
    assert set(SEVERITY) == set(_rule_ids())
    for rule_id, status in sorted(SEVERITY.items()):
        assert status in (Status.FAIL, Status.FLAG), rule_id


def test_every_defect_key_has_an_applier() -> None:
    assert {d.key for d in DEFECTS} == set(DEFECT_APPLIERS)


def test_defects_are_declared_in_registry_order() -> None:
    """Fixture order mirrors registry order so the corpus reads like the design."""
    assert [d.rule for d in DEFECTS] == _rule_ids()


#: Families that guard the other controls rather than covering a domain. These are
#: deliberately small -- ``set_complete`` alone proves the registry had something to
#: read -- so they are held to a floor of one instead of three.
STRUCTURAL_FAMILIES = frozenset({"set"})


def test_each_family_is_populated() -> None:
    """Every domain family in the design ships at least three controls."""
    for family in RULE_FAMILIES:
        members = [r for r in _rule_ids() if r.startswith(f"{family}_")]
        floor = 1 if family in STRUCTURAL_FAMILIES else 3
        assert len(members) >= floor, family


def test_defect_labels_are_plain_ascii_and_informative() -> None:
    for defect in DEFECTS:
        assert defect.label
        assert all(ord(ch) < 128 for ch in defect.label), defect.label
        assert len(defect.label) >= 12, defect.label
