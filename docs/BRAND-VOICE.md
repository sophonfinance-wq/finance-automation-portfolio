# Brand & Voice Standard

This document defines how this project communicates — in product documentation, the public
repository, profiles, and collateral. The objective is one consistent enterprise voice: confident,
precise, and benefit-led, with claims that hold up to scrutiny.

## Voice

- **Lead with the work.** Open with what a system does and the evidence it produces — runnable code,
  tests, deterministic outputs, CI — not with adjectives.
- **Measured, not loud.** State capabilities plainly. Avoid superlatives, exclamation, and hype.
- **Product voice.** Prefer third-person or measured first-person ("the platform…", "the engine…").
  Avoid bravado.
- **Precise.** Use exact terms — separation of duties, deterministic, read-only, integer-cent,
  byte-identical. Specificity is the credibility.

## What we do not say

Avoid casual or promotional filler: "slide deck," "vibes," "marks its own homework," "press play"
(use "run"), "wow moment," "command center," "game-changer," and exclamation-driven hype. Replace
idioms with plain, professional equivalents.

## The orchestration layer

The optional automation capability is always framed as **"an optional orchestration layer for
approved, agent-enabled environments; the platform runs fully without it."** Do not name specific
consumer or third-party tooling, and do not describe it as an always-on "command center." The
deterministic controls and the human gate are the message; orchestration is a convenience, not the
product.

## Accuracy and confidentiality (non-negotiable)

- Every claim is true and demonstrable. Current facts: **fourteen runnable systems, a 71,191-test curated suite (plus an opt-in ~1.26M-case property/invariant sweep), fully
  fictional data (seeded where the engine declares it), MIT-licensed, CI-backed.** (Verified via `pytest --collect-only -m "not site_tooling"` 2026-07-21.) A separate **51-test `site_tooling` suite** validates the generated public datasheets and is excluded from the curated engine total. Keep numbers current with the repository.
- The Knowledge Brain **generates** an apply-ready, cited remediation prompt and a change-log; a
  downstream AI or operator applies the changes. Never state or imply that the engine itself applies
  or verifies changes ("hands-free").
- Reproduce no employer or client entity, person, methodology, figure, or workpaper. Every example is
  invented.

## Terminology and mechanics

- Capitalize **"Tax"** when it is part of a title or label phrase (e.g., "Finance & Tax").
- Use the canonical system names consistently: Month-End Close, Cash & Debt Reconciliation,
  Partnership Tax · Form 1065, Validation Engine, Tax Surplus / ACB, Triangulate,
  Knowledge Brain, Finance Operations Atlas, Cash Management, Accounts Payable,
  Project Draw, Buyer Upgrades, Warranty Reimbursement, Intercompany Reciprocity.
- Write provider names plainly: "Anthropic Claude," and "ChatGPT" without a version number.

## Design

- Clean and premium: generous whitespace, clear hierarchy, restrained accent color.
- The primary call to action is **"run it"** — the work is meant to be executed, not only read.
- Diagrams and visuals hold the same standard: measured labels, no consumer tooling, no hype.
