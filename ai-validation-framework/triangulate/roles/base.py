"""Role interfaces (the pluggable contracts).

These abstract base classes define the separation of duties at the type level:

* A :class:`Preparer` is the *only* role handed a live, mutable
  :class:`~triangulate.model.Workpaper`.
* A :class:`Reviewer`, :class:`Specialist` (in its review capacity) and
  :class:`Auditor` only ever receive a
  :class:`~triangulate.model.ReadOnlyWorkpaperView` and can only *return
  findings*. They have no API surface through which to mutate anything.

Swapping an implementation (e.g. a real-LLM Reviewer for the deterministic
mock) is a one-line change in :mod:`triangulate.orchestrator` precisely because
everything is behind these interfaces.
"""

from __future__ import annotations

import abc
from typing import List

from triangulate.model import (
    Finding,
    ReadOnlyWorkpaperView,
    Workpaper,
)


class Preparer(abc.ABC):
    """Builds and normalises a workpaper. The only role that may mutate it."""

    name: str = "Preparer"

    @abc.abstractmethod
    def build(self) -> Workpaper:
        """Produce a fresh, normalised workpaper from source inputs."""

    @abc.abstractmethod
    def builder_memo(self, wp: Workpaper) -> List[str]:
        """Return the Builder Memo: sources, assumptions and risks."""


class Reviewer(abc.ABC):
    """Adversarial reviewer. Flags issues by reference; never mutates."""

    name: str = "Reviewer"

    @abc.abstractmethod
    def review(self, view: ReadOnlyWorkpaperView) -> List[Finding]:
        """Inspect a read-only view and return findings (never fixes)."""


class Specialist(abc.ABC):
    """Supporting transforms / second opinions.

    A Specialist has two capabilities. In its *review* capacity
    (:meth:`second_opinion`) it is read-only like the Reviewer. In its
    *transform* capacity (:meth:`apply_transform`) it may normalise data, but
    only when explicitly invoked by the orchestrator with a live workpaper --
    it never silently edits.
    """

    name: str = "Specialist"

    @abc.abstractmethod
    def second_opinion(self, view: ReadOnlyWorkpaperView) -> List[Finding]:
        """Read-only supporting review."""

    @abc.abstractmethod
    def apply_transform(self, wp: Workpaper) -> List[str]:
        """Apply supporting transforms in place; return a change log."""


class Auditor(abc.ABC):
    """Deterministic, read-only automated audit. Cannot hallucinate 'yes'."""

    name: str = "Auditor"

    @abc.abstractmethod
    def audit(self, view: ReadOnlyWorkpaperView) -> List[Finding]:
        """Run mechanical checks and return findings."""
