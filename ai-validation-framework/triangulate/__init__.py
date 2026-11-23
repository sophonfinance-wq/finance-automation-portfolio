"""Triangulate Orchestrator -- a runnable AI validation pipeline.

Operationalises the framework's separation-of-duties model as real code:
a Preparer builds a workpaper, an adversarial Reviewer flags (never fixes), a
Specialist supports, a deterministic Audit verifies, findings are reconciled
with a severity taxonomy and authority hierarchy, and an automated HumanGate
policy marks the work eligible or blocked for external human approval.

Runs fully offline with a deterministic mock LLM backend; real-LLM-ready via
the :class:`~triangulate.roles.reviewer.AnthropicReviewer` extension stub.
"""

from triangulate.model import (
    AuthoritySource,
    Finding,
    ReadOnlyWorkpaperView,
    Severity,
    Workpaper,
    WorkpaperCell,
    WorkpaperMutationError,
)
from triangulate.orchestrator import (
    PipelineResult,
    SeparationOfDutiesError,
    TriangulateOrchestrator,
)
from triangulate.reconcile import HumanGate, Verdict, VerdictStatus

__version__ = "1.0.0"

__all__ = [
    "Severity",
    "AuthoritySource",
    "Finding",
    "Workpaper",
    "WorkpaperCell",
    "ReadOnlyWorkpaperView",
    "WorkpaperMutationError",
    "TriangulateOrchestrator",
    "PipelineResult",
    "SeparationOfDutiesError",
    "Verdict",
    "VerdictStatus",
    "HumanGate",
    "__version__",
]
