# Codex Independent Review Prompt

Part of the multi-AI control discipline behind this portfolio: **Claude builds, Codex
independently verifies** — no high-stakes deliverable rests on a single model's word. Paste the
prompt below into Codex (or any independent reviewer) to run an adversarial audit of a change set
in this repo.

> Before sending: update the HEAD and expected test count. Current at last edit:
> **`pytest -m "not site_tooling"` → 474,265 collected (curated suite) · `pytest -m site_tooling` → 54 collected (separate public-datasheet guards) · `SWEEP=1 pytest -m "not site_tooling"` → 1,648,990 (property sweep) · 47 systems** (verified 2026-07-24)
> curated per system: (close 15,687 / partnership 8,605 / triangulate 8,320 / recon 7,511 / surplus 7,498 / knowledge-brain 7,011 / cash-management 5,290 / audit 4,814 / finance-atlas 2,952 / accounts-payable 12,223 / project-draw 10,392 / buyer-upgrades 10,279 / warranty 10,299 / intercompany 10,310 / property-tax 10,389 / surety-bond 10,420 / insurance-allocation 10,364 / coi 10,340 / expense 10,346 / labor 10,382 / lien 10,373 / waterfall 10,449 / proforma 10,381 / grt 10,400 / filing 10,369 / energy 10,390 / interest 10,402 / financing 10,337 / wire 10,347 / payroll 10,414 / withholding 10,410 / closing 10,379 / standing 10,385 / sov 10,412 / pickup 10,423 / depreciation 10,440 / deposit 10,407 / spending 10,424 / capitalize 10,323 / franchise 10,344 / sizing 10,338 / unitsales 10,355 / gaalloc 10,404 / checkage 10,361 / variance 10,411 / contingency 10,368 / inforeturn 10,382). Each engine added in the last build cycle carries a 10,000-case bounded invariant grid over its money kernel on top of its behavior tests.

---

## Full audit prompt

```text
ROLE: You are Codex, an independent senior reviewer. Adversarially audit recent work on my
PUBLIC finance-automation portfolio. Do NOT rubber-stamp. RUN the code, don't just read it.
Assume the author may have made mistakes or oversold things — find them.

REPO: https://github.com/sophonfinance-wq/finance-automation-portfolio
Setup: Python 3.12+, `pip install -r requirements.txt`, then
`python -m pytest -q -m "not site_tooling"` from the repo root. Separately run
`python -m pytest -q -m site_tooling` and confirm its 54-test guard suite. Confirm the reported
totals (and each engine's sub-count) are correct; if any count is wrong, that's a finding. The
framing is forty-eight runnable systems, with public site-tooling guards reported separately from the
474,265-test curated engine suite.

VERIFY EACH AREA INDEPENDENTLY:

1) knowledge-brain-engine (package `brain_engine`) — a citation brain over FICTIONAL transcripts;
   modes `ask` / `--cite` / `--prep` / `remediate`.
   - Citations must be BYTE-IDENTICAL to the source utterance — try to find one that is
     paraphrased or off by a character.
   - refuse-if-no-source must actually refuse (CLI exit 3) on an off-topic query — try to make it
     emit an uncited answer.
   - `remediate "<review meeting>"`: does it extract EREDACTED reviewer change-directive, in spoken
     order, each with full provenance (date / HH:MM:SS / speaker)? Does the generated remediation
     prompt list every directive with its verbatim quote? Does the change-log map 1:1 to the
     directives? Can you make it drop, reorder, or lose provenance on a directive?
   - Determinism: same input -> identical output (it claims stdlib TF-IDF; no embeddings/LLM/net).

2) partnership-1065-automation §704(c) — `partnership_tax/section704c.py`, opt-in `--section704c`.
   Verify the tax logic, hard: built-in gain = FMV - tax basis; traditional method allocates tax
   depreciation to the NON-contributing partner first; the CEILING RULE caps the non-contributor
   at the actual tax item and is SURFACED (flagged, not hidden); on sale the residual built-in
   gain goes to the contributor; book & tax capital each reconcile to equity; the tax-basis
   balance sheet balances. Confirm the DEFAULT `python -m partnership_tax` (no flag) is UNCHANGED.

3) tax-surplus-engine — an ITA 40(3)-style deemed gain when a return of capital drives ACB below
   zero. Verify the math and that it is purely ADDITIVE (existing balances / elevation / waterfall
   and the prior tests are unchanged).

4) Docs vs. reality — README / ARCHITECTURE / docs/CASE-STUDY.md / docs/DEMO-WALKTHROUGH.md and the
   diagrams (assets/flows/brain-flow.svg, assets/systems/brain.gif). Any capability or count
   claimed that the code does NOT actually back = an overclaim finding.

5) GitHub Actions — `.github/workflows/run-finance-engine.yml` ("Run Finance Engine Demo",
   workflow_dispatch). Verify: `permissions: contents: read`, NO secrets, fictional data only,
   every engine command matches its `run.py` CLI, artifact upload paths are correct, and the
   audit-validation non-zero exit (an INTENDED "FAIL verdict" on planted defects) keeps the job
   green unless `fail_on_review=true`. Is there ANY way a visitor run leaks a secret, writes
   outside the workspace, or fails confusingly? Is bundling all engines' sample outputs into a
   single-engine run's artifact a problem?

6) Confidentiality (PUBLIC repo) — grep the ENTIRE current tree, INCLUDING generated `out/` and
   `output/` dirs and the brain transcript corpus in `brain_engine/generate.py`, for anything
   that looks like real confidential data: any EIN-shaped token matching \b\d{2}-\d{7}\b OTHER
   than the placeholder 00-0000000; any real person, company, entity, engagement code, street
   address, or specific real-looking dollar figure. Everything must be obviously FICTIONAL. (A
   real EIN + engagement code were previously leaked in a test file and scrubbed via history
   rewrite — confirm none remain in the working tree; flag if you think GitHub-cache cleanup is
   still warranted.)

RETURN:
- VERDICT: PASS / PASS WITH NOTES / FAIL
- Findings as: [Severity] file:line — issue — concrete fix.
- Anything the author got WRONG or OVERSOLD (be blunt).
- Top 3 highest-value improvements, ranked.
```

---

## Workflow-only variant (the "run it" GitHub Action)

```text
ROLE: You are Codex doing a focused safety + UX review of ONE file:
.github/workflows/run-finance-engine.yml in
https://github.com/sophonfinance-wq/finance-automation-portfolio (a "run it" demo workflow).

Confirm, and try to break, each of these:
- Trigger: workflow_dispatch with a clear "Run workflow" button; an `engine` choice input that
  offers each engine AND `all`; optional period/year/seed/fail_on_review inputs with safe defaults.
- Safety: `permissions: contents: read` (least privilege); NO secrets referenced; runs on
  fictional/seeded data only; nothing writes outside the workspace; no client/employer files.
- Correctness: every `run_*` command matches the target engine's actual `run.py` CLI (run each
  locally to confirm); the `upload-artifact` paths exist and capture each engine's real outputs
  (including cash-reconciliation/evidence-log.md + output/); `if: always()` so artifacts upload
  even on a non-zero engine exit.
- Verdict handling: the validation/triangulate engines can exit non-zero as an INTENDED
  "review/fail verdict"; confirm the job stays GREEN unless `fail_on_review=true`, and that the
  run summary explains this in plain English so a visitor isn't confused.
- README: the "Run Demo" badge and the "Actions -> Run Finance Engine Demo -> Run workflow"
  instructions point to the right place and are clear for a first-time visitor.

RETURN: VERDICT (PASS / PASS WITH NOTES / FAIL); findings as [Severity] line — issue — fix;
and a one-paragraph plain-English "is this safe and ready for strangers to run it?" answer.
```
