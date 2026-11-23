# Accounts Payable Engine — Design

**Date:** 2026-07-21 · **Rev:** 1
**Status:** Approved design; implementation pending owner review before push or merge · **Owner:** Sophonnarith Hang · **Prepared with:** Claude Code

> This document records the design intent. For current implementation truth, use
> `accounts-payable-automation/ap_engine/`, its test suite, and
> `site-datasheets/specs/ap.json`.

## 1. Goal

Add the platform's **tenth** engine: a read-only control engine for the accounts-payable
cycle in construction and real-estate development — the highest-volume, highest-headcount
finance function in that industry, and the one with the least deterministic tooling.

The engine consumes the fixed-format posting artifacts a construction ERP emits (invoice
posting reports, check-run reports, commitment and change-order journals, payment
selection registers) and applies a registry of controls that answer four questions a
controller actually asks:

1. **Did the post actually happen, and did it balance?**
2. **Is this payment allowed to be released yet?**
3. **Is every job routed to a valid approver chain, with duties segregated?**
4. **Will year-end information reporting be complete and correct?**

It never posts, never pays, never writes to a source artifact. Like the Validation Engine,
it is a **sensor**: the deterministic ground truth other systems and reviewers consume.

## 2. Why this engine, and why it is credible

AP is where controls are asserted and least often proven. Three failure modes recur across
the industry, and all three are invisible to the people running the cycle:

- **A posting run that silently did nothing.** ERP batch contention aborts a post; the
  operator files the report as though it succeeded. The invoices are not in the ledger.
- **A payment released before its compliance gate cleared** — missing lien waiver, expired
  certificate of insurance, no W-9 on a first payment to a new vendor.
- **A routing matrix that has drifted** — a job with no workflow, a workflow with no
  approver, or the same person on both data entry and final review.

Each is deterministic to detect from artifacts that already exist. None requires a model's
judgment. That is exactly the shape this platform is built for.

## 3. Scope boundaries — confidentiality

**This engine ships on seeded fictional data only, like every other engine in the
platform.** The design was informed by studying a real AP function's *report grammar* and
*written procedures*; no figure, name, identifier or path from that study appears in this
repository, and none ever will.

Specific rules, binding on all code, tests, docs, fixtures and commit messages here:

- **Never name the real software stack.** The engine describes its inputs generically —
  "a construction ERP", "an invoice-capture and approval-routing system", "a subcontractor
  progress-billing platform", "an electronic payment provider". Several real product names
  are already on the repository's hashed deny-list; the rest are treated as equally
  off-limits regardless of whether the list happens to cover them.
- **Never write a real person's name.** The deny-list does not cover personal names at
  all — authoring discipline is the only control. Approver identities in fixtures are
  fictional role-holders (`approver-a`, `Reviewer One`).
- **Never write a real vendor, entity, invoice, purchase-order, commitment, bank, routing
  or general-ledger identifier**, nor a real network path or source file name.
- The generator invents every value in the platform's established fictional register
  (§7). "Lightly anonymizing" a real record is a leak that the deny-list would not catch.

**Recommended follow-up, outside this engine's scope:** the deny-list currently misses
several product names in the same class as the terms it does cover. Closing that gap is a
one-line-per-term change to `finance-atlas/atlas_tests/test_deny_list.py` (remember to bump
the `len(DENYLIST)` assertion). Digests must be computed outside the repo tree.

## 4. Identity

| Field | Value |
|---|---|
| Engine number | 10 |
| Part no. | `SFS-E10-APX` |
| Slug | `ap` |
| Folder | `accounts-payable-automation/` |
| Package | `ap_engine/` |
| Canonical display name | **Accounts Payable** |

The platform already ships nine engines (Cash Management is `SFS-E09-CSH`). Every
hard-coded "nine" in copy, counts and tests moves to "ten"; the homepage "your engine"
tile moves from `10+` to `11+`.

## 5. Architecture

```
accounts-payable-automation/
├── README.md
├── run.py                     # zero-arg quickstart
├── pytest.ini
├── ap_report.md / ap_report.json
├── samples/                   # generated corpus (.json committed, .xlsx gitignored)
└── ap_engine/
    ├── __init__.py            # docstring + __all__ + __version__
    ├── __main__.py
    ├── cli.py                 # argparse only; main(argv) -> int
    ├── money.py               # integer cents
    ├── model.py               # Status / Verdict / Finding / documents
    ├── engine.py              # check registry + runner
    ├── generate.py            # seeded fictional corpus
    ├── report.py              # markdown + JSON artifacts
    └── tests/
```

**Data model** follows the Validation Engine: `Status` (PASS/FAIL/FLAG) and `Verdict`
(PASS/REVIEW/FAIL) as UPPERCASE `str, Enum`; a frozen `Finding(rule, status, location,
message)` with `to_dict()`; verdict as a derived property with precedence
FAIL > FLAG → REVIEW > PASS. The registry is an ordered `list[tuple[str, CheckFn]]`
populated by a `@check("rule_id")` decorator, so report order is deterministic.

**No `loop.py`.** A remediation loop's core step — resync to authority and book
adjustments — is a mutation, which is incompatible with a read-only control engine. This
engine is a sensor other loops consume, matching the Validation Engine's documented
stance.

**Exit codes:** `0` PASS · `1` REVIEW · `2` FAIL · `3` usage/IO error, via a module-level
`_EXIT_BY_VERDICT` dict. `main()` returns the code and never calls `sys.exit`.

**Output is plain ASCII.** No emoji in stdout or artifacts, so Windows terminals need no
encoding fallback.

## 6. Determinism contract

- **Integer cents everywhere.** `ap_engine/money.py` follows the Close Engine's
  discipline: `to_cents` half-up, float-free `fmt` via `divmod`, `allocate_by_ratio` by
  largest-remainder raising `ValueError` unless weights sum to 10000 bps. Dataclass fields
  and JSON keys carry a `_cents` suffix. Floats appear only at the formatting edge.
  Comparisons are exact `==` — **no tolerance**. Non-`int` amounts raise the finding code
  `AMOUNT_INVALID` rather than being coerced.
- **One seed**, `SEED = 20260731`, threaded as an explicit `rng` parameter. No module-level
  `random.*`. Later sub-ledgers get named derived streams so existing sequences do not
  shift.
- **Byte-stable artifacts.** Markdown built as `lines: list[str]` joined with `"\n"`; JSON
  via `json.dumps(..., indent=2)` with no `sort_keys` (literal dict order is the contract);
  every glob, dict and set iteration forced through `sorted()` with a tiebreaker key.
- `.xlsx` is **not** byte-reproducible (openpyxl writes timestamps); determinism tests
  compare `.json` only.

## 7. Seeded fictional data

`generate_corpus(out_dir, *, seed=SEED) -> list[Path]` wipes stale artifacts first (skipping
`~$` lock files), builds a deterministic plan list, and writes one document per plan plus a
sibling `.json`.

Vocabulary extends the platform's shared fictional register — entities such as Demo
Holdings LLC, Maple Fund LP, Birchwood Op Co, Cedar Ridge Trust; banks such as Northgate
Demo Bank. AP adds vendors in the same key (Ironwood Sandbox Supply Co, Foxglove Mock
Freight LLC, Harborview Demo Services Inc), `AP-3000`-style ledger codes, and
`INV-2026-0001` / `PO-2026-0001` document numbers. Periods are fictional-future (2026).

**Exactly one planted defect per registered rule, plus a clean baseline.** A test asserts
`{d.rule for d in DEFECTS} == {rule_id for rule_id, _ in REGISTRY}`, so a rule can never be
added without a fixture that exercises it.

## 8. The rule registry

Every rule carries the control rationale in its message, so an exception teaches the reason
rather than only the verdict.

### 8.1 Posting integrity (`post_*`)

| Rule | Severity | Check |
|---|---|---|
| `post_proof_zero` | FAIL | the posting proof figure is exactly zero |
| `post_gl_balanced` | FAIL | ledger recap debits equal credits |
| `post_totals_balanced` | FAIL | posting-total debit equals credit |
| `post_no_rejects` | FAIL | rejected counts are zero across invoices, entries and job-cost entries |
| `post_actually_posted` | FAIL | a posting report records more than zero posted documents |
| `post_no_error_marker` | FAIL | no blocking ERP error (batch contention, aborted update) |
| `post_jobcost_ties` | FAIL | job-cost recap total equals the payable cost total |
| `post_header_date_agrees` | FLAG | header date agrees with the date encoded in the file name |

`post_actually_posted` and `post_no_error_marker` are the two that catch a run which
aborted and was filed as though it succeeded. A benign "job-cost entries not created"
notice — normal for a ledger-only invoice — is explicitly **not** a failure; conflating the
two produces false positives and was the single most important distinction found while
validating the grammar.

### 8.2 Payment release gate (`gate_*`)

| Rule | Severity | Check |
|---|---|---|
| `gate_w9_on_file` | FAIL | a taxpayer-identification certificate exists before a first payment |
| `gate_lien_waiver` | FAIL | waivers received from the subcontractor and its lower tiers |
| `gate_insurance_current` | FAIL | insurance certificate present and unexpired at the payment date |
| `gate_insurance_limits` | FLAG | coverage meets the contract minimums |
| `gate_funding_confirmed` | FAIL | funding confirmation recorded before release |
| `gate_no_duplicate` | FAIL | no duplicate vendor + document number + amount in the selection |
| `gate_retention_present` | FLAG | retention and tax lines present and rate-consistent on progress billings |
| `gate_offcycle_approved` | FLAG | an off-cycle payment carries the required approval and is within limit |

### 8.3 Routing and segregation of duties (`route_*`)

| Rule | Severity | Check |
|---|---|---|
| `route_every_job_mapped` | FAIL | every active job maps to exactly one workflow |
| `route_workflow_has_approver` | FAIL | every workflow has at least one approver |
| `route_final_review_present` | FAIL | every workflow names a final-review group |
| `route_duties_segregated` | FAIL | data-entry and final-review roles are not the same person |
| `route_preapproved_declared` | FLAG | direct-post workflows are explicitly enumerated |

### 8.4 Information reporting (`ir_*`)

| Rule | Severity | Check |
|---|---|---|
| `ir_threshold_coverage` | FAIL | every vendor over the reporting threshold is evaluated |
| `ir_tin_present` | FAIL | each reportable vendor has a taxpayer identification number |
| `ir_tin_structure` | FLAG | the identifier is structurally valid |
| `ir_no_split_vendor` | FLAG | no two vendor records share an identifier (split-payment risk) |
| `ir_filed_reconciles` | FAIL | filed-form count per entity reconciles to the expected list |

### 8.5 Commitment hygiene (`cmt_*`)

| Rule | Severity | Check |
|---|---|---|
| `cmt_sov_not_lump_sum` | FAIL | the commitment schedule of values mirrors the contract, not a single lump line |
| `cmt_id_convention` | FLAG | commitment identifiers follow the project/vendor convention |
| `cmt_co_attaches_to_original` | FLAG | change orders attach to the original commitment |

## 9. Validation of the design

The report grammar and the posting-integrity rules were validated against a corpus of
1,135 real posting artifacts before any code was written for this repository. That
exercise established: eight distinct report types; a stable section vocabulary; negative
amounts carried with a trailing minus; labels sometimes letter-spaced by the text
extractor; and roughly 9% of files in such folders are scanned images with no text layer,
which the classifier must reject gracefully rather than crash on.

It also confirmed the rules fire on real defects rather than hypothetical ones, and forced
the benign/blocking distinction in §8.1. **No artifact, value or name from that corpus is
reproduced here** — only the structural conclusions, which are properties of a commercial
report format rather than of any client's data.

## 10. Tests

Nested at `ap_engine/tests/`, run per-package as CI does:
`cd accounts-payable-automation && python -m pytest -q`.

Required contract tests, following the Validation Engine:

1. **Read-only** — digest every source artifact before and after a run; assert unchanged.
2. **Generation determinism** — generate twice into separate temp dirs; compare `.json`.
3. **Finding stability** — two report payloads identical after popping any timestamp.
4. **Defect/registry coverage** — every registered rule has exactly one planted defect.
5. **Curated invariant grid** — bounded, gates CI.
6. **Bulk invariant grid** — file named exactly `test_bulk_invariant_grid.py`, gated behind
   `SWEEP=1` by the standard `pytest_ignore_collect` hook in `conftest.py`.

## 11. Registration

Adding an engine touches roughly seventy points. The two that fail silently and matter most:

- **`.github/workflows/ci.yml` lines 44 and 68** carry two byte-identical directory lists.
  `accounts-payable-automation` must be appended to **both**, or the engine runs zero tests
  in CI while CI stays green and meaningless.
- **`site-datasheets/counts.json`** — repo-root collection auto-discovers the new tests, and
  `test-count.yml` hard-asserts the total. That workflow runs on push to `main` and **not**
  on pull requests, so the failure appears only after merge. Counts must be re-derived, not
  guessed, and updated in the same change.

`docs/BRAND-VOICE.md` is the naming authority read by the roster test; the canonical display
name must be added there verbatim. Full checklist lives with the implementation plan.

## 12. Out of scope

- Any write path into an ERP, payment provider or approval system.
- Optical character recognition. Text-layer artifacts only; image-only files are reported
  as unclassifiable, not guessed at.
- A remediation loop (§5).
- Any adapter, credential or path that would let this repository read real records. Running
  the same registry against a private corpus is a local exercise that leaves no trace here.
