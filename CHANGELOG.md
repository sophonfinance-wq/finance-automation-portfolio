# Changelog

## 2026-07-17

- Added a fictional, validation-only construction budget-variance preflight with
  exact integer-cent equations, cost-code and total crossfoots, explicit overrun
  controls, permanent posting denial, and manual source/approval gates.

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Accounts Payable engine** (`SFS-E10-APX`, `accounts-payable-automation/ap_engine`) — the
  platform's tenth system: a deterministic, read-only control engine for the payables cycle,
  running thirty controls in six families over seeded fictional posting document sets. Posting
  integrity (including a control for a run that aborted and was filed as though it succeeded),
  the payment release gate, approver routing with duties segregated, information reporting, and
  commitment hygiene. Integer cents throughout with exact comparison and no tolerance band; no
  remediation loop, because a read-only sensor must not mutate what it inspects.
- **Structural precondition control** (`set_complete`) — registered first so a document set
  missing an artifact type cannot report clean merely because the controls that read it never
  ran. Absent evidence is not a held control.
- Seeded fictional corpus carrying exactly one planted defect per registered control plus a
  clean baseline, with a coverage test asserting the defect set and the registry are identical,
  so a control cannot be added without a fixture that exercises it.
- Public datasheet at `docs/engines/ap.html` from `site-datasheets/specs/ap.json`, plus the
  engine tile, flow diagram, and homepage/test-page registration for a tenth system.
- Fictional postage-allocation engine for signed meter detail: exact one-route-per-project
  gating, structured project/job/cost schedules, per-entity intercompany mirrors, refund
  reversals, and per-entity clearing of unallocated postage.
- Independent postage coverage in the C3 completeness calendar, C6 population and
  crossfoot checks, C8 clearing control, C9 shadow recompute, C10 period lock, and the
  autonomous close category order.
- Tests for missing and duplicate routes, source-to-job crossfoots, zero/refund behavior,
  blank and noncanonical identifiers, exact structured provenance, prefix-related batch
  ids, metadata-only loop repair, one-cent tamper detection, deterministic output,
  prior-period immutability, CLI/JSON exposure, and repository confidentiality.
- Release hardening now rejects malformed batch periods before period filtering and
  unknown entities from the full opening/post-close ledger universe, validates the
  canonical JE header, memo, and structured provenance, and makes both console and
  report CLEAN verdicts depend on the engine and Close Sentinel.
- Regenerated deterministic close artifacts now include all nine entries and the new
  structured `schedules.json`; freshness assertions compare every committed close and
  autonomous-loop artifact to a clean regeneration.

## [1.1.0] - 2026-07-04

Monthly-close automation: deterministic controls layer, insurance allocation, and a
fault-injection guardrails demo.

### Added
- **Close Sentinel** — ten deterministic close controls that run after every close; any
  critical finding blocks the close.
  - C1 re-balance — independently recomputes every journal entry's debit/credit totals and
    per-entity nets from raw lines, and verifies that the opening trial balance nets to zero
    group-wide and that the post-close trial balance still balances.
  - C2 intercompany mirror — both legs of every cross-entity entry must exist and agree to
    the cent; one-sided entries are flagged with the missing side named.
  - C3 completeness calendar — every expected recurring entry is present exactly once;
    omissions and duplicates are flagged, and explicit waivers are recorded.
  - C4 asset-life guard — flags fully depreciated assets still depreciating and quantifies
    accumulated depreciation in excess of cost, re-derived from the sub-ledger and the
    posted register rather than the workpaper schedule.
  - C5 driver provenance — allocation drivers must equal current-period activity, never a
    cumulative balance.
  - C6 cross-foot — per-entity shares must sum exactly to each policy's monthly total, and
    every allocation split map must pass dataset integrity (exactly 100 percent, group
    entities only); the engine refuses to post on an invalid map instead of crashing.
  - C7 step-change corroboration — material period-over-period movements in either
    direction require a corroborating sub-ledger event of the same entity (renewals,
    in-service dates, new prepaids, item expiry or end of life).
  - C8 rounding policy — clearing legs must equal the sum of the rounded detail lines,
    never a rounded total.
  - C9 shadow recompute — an independent re-implementation of every entry category must
    agree with the posted register to the cent.
  - C10 period lock — closed periods are hash-locked; any subsequent mutation of a locked
    period is detected.
- Insurance-allocation engine: shared policies amortized across entities with basis-point
  splits, largest-remainder rounding so entity lines sum exactly to each policy total, and
  mid-year renewal step-up handling.
- Fault-injection guardrails demo (`python -m close_engine --demo-guardrails`): injects
  twelve classic close errors covering all ten controls (including the C1 trial-balance
  gate) and verifies that each is caught by its designated control
  at a qualifying severity (CRITICAL for blocking controls, WARN or above for the C7
  reviewer escalation), after confirming a clean baseline produces zero findings; the demo
  holds at any valid period.
- 3,742 new tests covering the controls layer, insurance allocation, shadow
  recomputation, and fault round-trips.

## [1.0.0] - 2026-07-01

Initial public release.

### Added
- Seven self-contained Python systems for finance and tax work — month-end close, cash & debt
  reconciliation, surplus/ACB, partnership 1065 / §704(c), a read-only validation engine, a
  knowledge-brain engine, and **Triangulate**, a multi-agent LLM review framework with a
  deterministic core and human-gated guardrails.
- Tiered `pytest` suite and GitHub Actions **CI** on every push and pull request.
- **Codespaces** devcontainer for one-click, zero-setup runs.
- Cash-reconciliation deep-dive: *Verification & Completeness Patterns*.
- Architecture overview, per-system READMEs, and audit-ready evidence samples.
- MIT license; **fully synthetic** sample data throughout.
