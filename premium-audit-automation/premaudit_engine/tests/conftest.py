import datetime as dt

import pytest

from ..model import AuditWindow, TriagePolicy


@pytest.fixture
def window() -> AuditWindow:
    return AuditWindow(dt.date(2025, 10, 15), dt.date(2026, 6, 1))


@pytest.fixture
def policy() -> TriagePolicy:
    return TriagePolicy(
        clearing_vendor_ids=frozenset({"0000"}),
        wrap_enrolled_vendors=frozenset({"FENWICK ELECTRIC LLP"}),
        materials_only_vendors=frozenset({"DOVETAIL PAINT SUPPLY CO"}),
        professional_vendors=frozenset({"ELMGATE LAW GROUP PLLC"}),
    )
