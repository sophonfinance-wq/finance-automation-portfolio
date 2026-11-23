"""The adversarial Reviewer role and its pluggable LLM backend.

Design:

* :class:`LLMReviewer` is the abstract *backend* interface -- "given a
  read-only workpaper rendered as a prompt, return structured findings."
* :class:`MockLLMReviewer` is a **deterministic** implementation that runs the
  whole pipeline with NO API key and NO network. It applies the same
  guardrailed checklist a real reviewer prompt would, but in pure Python so
  tests are stable.
* :class:`AnthropicReviewer` is a clearly-marked **extension stub** showing
  exactly where a real Claude API call would go. It is import-safe and never
  invoked by the default pipeline, so nothing requires a key to run.

The concrete :class:`AdversarialReviewer` is the orchestrator-facing
:class:`~triangulate.roles.base.Reviewer`; it delegates to whichever
:class:`LLMReviewer` backend it was constructed with. This is the
"pluggable component behind a clean interface" requirement: swap the backend,
keep the role.
"""

from __future__ import annotations

import abc
import json
import os
import urllib.error
import urllib.request
from typing import List

from triangulate.formula import FormulaError, evaluate
from triangulate.model import (
    AuthoritySource,
    Finding,
    ReadOnlyWorkpaperView,
    Severity,
)
from triangulate.roles.base import Reviewer

# Phrases that must never leak into client-facing cells/notes. A real reviewer
# prompt carries the same negative-constraint list.
_PROCESS_LANGUAGE_MARKERS = (
    "todo",
    "the llm",
    "the ai",
    "as the ai suggested",
    "ai suggested",
    "placeholder",
    "reviewer confirms",
    "recheck this",
)


class LLMReviewer(abc.ABC):
    """Pluggable review *backend*.

    Implementations receive a read-only view of the workpaper and return a list
    of :class:`~triangulate.model.Finding`. They must treat the workpaper as
    immutable -- they are handed a
    :class:`~triangulate.model.ReadOnlyWorkpaperView`, so mutation raises.
    """

    backend_name: str = "LLMReviewer"

    @abc.abstractmethod
    def generate_findings(self, view: ReadOnlyWorkpaperView) -> List[Finding]:
        """Return findings for the given read-only workpaper view."""


class MockLLMReviewer(LLMReviewer):
    """Deterministic, key-free review backend.

    This stands in for a real LLM call. It encodes the guardrailed review
    checklist directly in Python so the pipeline is fully reproducible:

    1. Every cell that declares a formula must tie out to that formula.
    2. A monetary cell with no formula and no supporting source is suspect
       (hard-coded where a calculation is expected).
    3. AI-generated assumptions (lowest authority) are flagged for verification.
    4. No internal/process language may appear in notes or labels.

    Because it is deterministic, the same workpaper always yields the same
    findings -- which is exactly what makes the tests stable.
    """

    backend_name = "MockLLMReviewer"

    def generate_findings(self, view: ReadOnlyWorkpaperView) -> List[Finding]:
        findings: List[Finding] = []
        values = {
            c.ref: c.value
            for c in view.ordered_cells()
            if c.value is not None
        }

        for cell in view.ordered_cells():
            # Check 1: formula tie-out.
            if cell.formula:
                try:
                    expected = round(evaluate(cell.formula, values), 2)
                except FormulaError as exc:
                    findings.append(Finding(
                        code="FORMULA_UNRESOLVABLE",
                        cell_ref=cell.ref,
                        severity=Severity.HIGH,
                        message=f"Formula {cell.formula!r} could not be resolved: {exc}",
                        raised_by=f"Reviewer:{self.backend_name}",
                        authority=AuthoritySource.WORKBOOK_FORMULA,
                    ))
                    continue
                actual = round(float(cell.value), 2) if cell.value is not None else None
                if actual is None or abs(expected - actual) > 0.01:
                    findings.append(Finding(
                        code="TIE_OUT_MISMATCH",
                        cell_ref=cell.ref,
                        severity=Severity.CRITICAL,
                        message=(
                            f"Stated value {actual} does not tie out to formula "
                            f"{cell.formula} (expected {expected})."
                        ),
                        raised_by=f"Reviewer:{self.backend_name}",
                        authority=AuthoritySource.WORKBOOK_FORMULA,
                        expected=expected,
                        actual=actual,
                    ))

            # Check 2: monetary cell with no formula and weak authority.
            looks_monetary = (
                cell.value is not None
                and isinstance(cell.value, (int, float))
                and abs(cell.value) >= 1_000  # rates (<1) are not "monetary"
            )
            if looks_monetary and not cell.formula and cell.source.name in {
                "AI_ASSUMPTION",
            }:
                findings.append(Finding(
                    code="HARDCODED_NO_FORMULA",
                    cell_ref=cell.ref,
                    severity=Severity.HIGH,
                    message=(
                        f"Cell '{cell.label}' is a hard-coded figure with no "
                        f"formula and only AI-assumption authority."
                    ),
                    raised_by=f"Reviewer:{self.backend_name}",
                    authority=AuthoritySource.AI_ASSUMPTION,
                ))

            # Check 3: AI-generated assumption needing verification.
            if cell.source.name == "AI_ASSUMPTION":
                findings.append(Finding(
                    code="UNSUPPORTED_AI_ASSUMPTION",
                    cell_ref=cell.ref,
                    severity=Severity.MEDIUM,
                    message=(
                        f"Cell '{cell.label}' rests on an AI-generated assumption "
                        f"(lowest authority); requires a supporting source."
                    ),
                    raised_by=f"Reviewer:{self.backend_name}",
                    authority=AuthoritySource.AI_ASSUMPTION,
                ))

            # Check 4: leaked process language in a label.
            if _has_process_language(cell.label):
                findings.append(Finding(
                    code="PROCESS_LANGUAGE_LEAK",
                    cell_ref=cell.ref,
                    severity=Severity.LOW,
                    message=f"Internal/process language leaked into label: {cell.label!r}.",
                    raised_by=f"Reviewer:{self.backend_name}",
                    authority=AuthoritySource.WORKBOOK_FORMULA,
                ))

        # Check 4 (continued): leaked process language in notes.
        for idx, note in enumerate(view.notes):
            if _has_process_language(note):
                findings.append(Finding(
                    code="PROCESS_LANGUAGE_LEAK",
                    cell_ref=f"<note[{idx}]>",
                    severity=Severity.LOW,
                    message=f"Internal/process language leaked into a note: {note!r}.",
                    raised_by=f"Reviewer:{self.backend_name}",
                    authority=AuthoritySource.WORKBOOK_FORMULA,
                ))

        return findings


def _has_process_language(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in _PROCESS_LANGUAGE_MARKERS)


# JSON Schema the live model must return — guarantees a parseable response so
# findings map cleanly onto Finding objects (structured outputs, no prose drift).
_FINDINGS_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "cell_ref": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["Critical", "High", "Medium", "Low"],
                    },
                    "message": {"type": "string"},
                    "authority": {"type": "string"},
                },
                "required": ["code", "cell_ref", "severity", "message", "authority"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["findings"],
    "additionalProperties": False,
}

_ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"


def _authority_from(text: str | None) -> AuthoritySource:
    """Map a model-returned authority label/name back onto the enum (safe default)."""
    if not text:
        return AuthoritySource.AI_ASSUMPTION
    key = str(text).strip().upper().replace(" ", "_")
    try:
        return AuthoritySource[key]
    except KeyError:
        return AuthoritySource.AI_ASSUMPTION


class AnthropicReviewer(LLMReviewer):
    """A real Claude-backed reviewer (live, but NOT used by the default pipeline).

    This is a working integration with the Anthropic Messages API, implemented
    with the **standard library only** (``urllib``) so it adds no dependency to
    the repo's stdlib-only toolchain. It is import-safe and never touches the
    network unless you explicitly construct it *and* call
    :meth:`generate_findings` with a key available — so CI stays key-free and
    the default pipeline (which uses :class:`MockLLMReviewer`) needs no network.

    To use it for real:

    1. Set ``ANTHROPIC_API_KEY`` in the environment (or pass ``api_key=...``).
    2. Pass ``AnthropicReviewer()`` to :class:`AdversarialReviewer` instead of
       the :class:`MockLLMReviewer`::

           reviewer = AdversarialReviewer(AnthropicReviewer())

    The call uses Claude Opus 4.8 with a structured-output schema so the
    response is guaranteed-parseable JSON that maps straight onto
    :class:`~triangulate.model.Finding` objects.
    """

    backend_name = "AnthropicReviewer"

    # A realistic guardrailed system prompt. Kept here so the role injection is
    # versioned alongside the code. Mirrors the framework's prompt-engineering.
    SYSTEM_PROMPT = (
        "You are the Reviewer in a separation-of-duties validation pipeline. "
        "Your job is friction: if you agree with everything you are not doing "
        "your job. You may FLAG issues by cell reference but you must NEVER "
        "propose edits, save files, or mutate the workpaper. Classify every "
        "finding with a severity (Critical/High/Medium/Low) and cite the "
        "authority source. Return findings that match the required schema."
    )

    def __init__(self, model: str = "claude-opus-4-8", api_key: str | None = None) -> None:
        self.model = model
        self._api_key = api_key

    def generate_findings(self, view: ReadOnlyWorkpaperView) -> List[Finding]:
        """Run a live Claude review over the read-only workpaper view.

        Raises a clear :class:`RuntimeError` (with no network call) when no API
        key is available, so importing/constructing this class is always safe.
        """
        api_key = self._api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "AnthropicReviewer needs a key: set ANTHROPIC_API_KEY (or pass "
                "api_key=...) to enable live Claude review. The default pipeline "
                "uses MockLLMReviewer, which needs no key or network."
            )

        rendered = json.dumps(view.to_dict(), indent=2, default=str)
        payload = {
            "model": self.model,
            "max_tokens": 2048,
            "system": self.SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Review this workpaper and FLAG issues only — do not fix "
                        "anything. Return findings matching the schema. Workpaper "
                        f"JSON:\n{rendered}"
                    ),
                }
            ],
            # Structured outputs: constrain the response to valid JSON findings.
            "output_config": {"format": {"type": "json_schema", "schema": _FINDINGS_SCHEMA}},
        }
        request = urllib.request.Request(
            _ANTHROPIC_MESSAGES_URL,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # pragma: no cover - network path
            detail = exc.read().decode("utf-8", "replace")
            raise RuntimeError(f"Claude API error {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:  # pragma: no cover - network path
            raise RuntimeError(f"Could not reach the Claude API: {exc.reason}") from exc

        text = "".join(
            block.get("text", "")
            for block in body.get("content", [])
            if block.get("type") == "text"
        )
        parsed = json.loads(text)
        items = parsed["findings"] if isinstance(parsed, dict) else parsed

        findings: List[Finding] = []
        for item in items:
            findings.append(Finding(
                code=item["code"],
                cell_ref=item["cell_ref"],
                severity=Severity.from_name(item["severity"]),
                message=item["message"],
                raised_by=f"Reviewer:{self.backend_name}",
                authority=_authority_from(item.get("authority")),
            ))
        return findings


class AdversarialReviewer(Reviewer):
    """Orchestrator-facing Reviewer that delegates to a pluggable backend.

    It is constructed with any :class:`LLMReviewer` (the deterministic mock by
    default). It is read-only by contract: :meth:`review` is handed a
    :class:`~triangulate.model.ReadOnlyWorkpaperView` and only returns findings.
    """

    name = "Reviewer:Adversarial"

    def __init__(self, backend: LLMReviewer | None = None) -> None:
        self.backend = backend or MockLLMReviewer()
        self.name = f"Reviewer:{self.backend.backend_name}"

    def review(self, view: ReadOnlyWorkpaperView) -> List[Finding]:
        """Flag issues by reference -- never mutate, never fix."""
        return self.backend.generate_findings(view)
