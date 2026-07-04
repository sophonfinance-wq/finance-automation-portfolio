"""Sentinel runner: execute every control in order and aggregate findings."""

from __future__ import annotations

import inspect

from ..engine import CloseResult
from ..generate import Dataset
from .controls import ALL_CONTROLS, Waiver
from .findings import Finding, SentinelReport


def run_sentinel(
    dataset: Dataset,
    result: CloseResult,
    *,
    calendar_waivers: list[Waiver] | None = None,
    locked: dict[str, str] | None = None,
) -> SentinelReport:
    """Run all controls (C1-C10) over a finished close, in id order.

    Args:
        dataset: The source dataset the close was (supposedly) built from.
        result: The posted close result to audit.
        calendar_waivers: Optional ``(entity, category, reason)`` tuples
            excusing an expected recurring entry for the period (C3).
        locked: Optional ``{period: register_hash}`` map of signed-off
            periods to verify against a deterministic recompute (C10).

    Returns:
        A :class:`~close_engine.sentinel.findings.SentinelReport` aggregating
        every control's findings in control order.
    """
    findings: list[Finding] = []
    for control in ALL_CONTROLS:
        parameters = inspect.signature(control).parameters
        kwargs = {}
        if "calendar" in parameters:
            kwargs["calendar"] = calendar_waivers
        if "locked" in parameters:
            kwargs["locked"] = locked
        findings.extend(control(dataset, result, **kwargs))
    return SentinelReport(findings)
