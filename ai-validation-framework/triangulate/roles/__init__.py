"""Pluggable pipeline roles for the Triangulate Orchestrator.

Each role is a small, single-responsibility component behind a clean interface
(see :mod:`triangulate.roles.base`). The orchestrator wires them together; any
role can be swapped for another implementation (e.g. a real-LLM Reviewer) as
long as it honours the contract.
"""

from triangulate.roles.base import (
    Auditor,
    Preparer,
    Reviewer,
    Specialist,
)
from triangulate.roles.preparer import DemoPreparer
from triangulate.roles.reviewer import (
    AdversarialReviewer,
    AnthropicReviewer,
    LLMReviewer,
    MockLLMReviewer,
)
from triangulate.roles.specialist import DemoSpecialist
from triangulate.roles.auditor import DeterministicAuditor

__all__ = [
    "Preparer",
    "Reviewer",
    "Specialist",
    "Auditor",
    "DemoPreparer",
    "AdversarialReviewer",
    "LLMReviewer",
    "MockLLMReviewer",
    "AnthropicReviewer",
    "DemoSpecialist",
    "DeterministicAuditor",
]
