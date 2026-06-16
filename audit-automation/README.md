# 🔍 Audit Automation

<p align="center"><img src="../assets/systems/validation.gif" alt="Validation Engine — live demo" width="100%"></p>
<p align="center"><img src="../assets/flows/validation-flow.svg" alt="Validation Engine flow chart" width="100%"></p>

> A **deterministic, read-only validation engine** that runs a registry of rules
> over finished financial workbooks (`.xlsx`) and their JSON exports — plus a
> seeded synthetic generator so it runs **end-to-end on fully fictional
> data**, no real files required. This is the deterministic backbone underneath the
> [AI Validation Framework](../ai-validation-framework/) — the unfalsifiable
> ground truth an LLM reviewer cannot talk its way around.

> 🔒 Everything here is generic and runs on **dummy workbooks** with obviously
> fake entities ("Demo Holdings LLC", "Maple Fund LP", "Birchwood Op Co"). It
> contains no employer procedures, entities, or figures. The engine **never
> writes to an audited file** — it can only report, never introduce a defect.

---

## The problem it solves
Large, formula-heavy workbooks need checking before sign-off: are the totals
*driven by formulas* (not quietly hardcoded)? Does the trial balance tie out
(debit == credit)? Were any "to-do" notes or internal/process words left behind?
Does the lineage flow the right way — evidence cells as raw *inputs*, detail
cells as *formulas*? Were draft-only `MIN/MAX` cap formulas ever replaced? Does
the published JSON still agree with the workbook it came from?

Performing these checks by eye across many near-identical workbooks is slow and
error-prone — and an LLM asked "did you fix everything?" will readily respond
"yes" whether or not it is true.

## The system
This began as a single read-only audit script. It is now a complete **rules-based
validation engine** — a registry of independent checks, a structured report
(markdown **and** JSON), and an overall verdict — packaged as
[`validation_engine/`](./validation_engine/).

Each check opens the workbook **read-only** (twice — once for *formulas*, once
for cached *values*), inspects the relevant cells, and yields findings tagged
`PASS` / `FAIL` / `FLAG`, each with a `Sheet!Cell` (or `json:<key>`) location.

### The rule registry
| Rule id | What it catches | Severity |
| --- | --- | --- |
| `expected_formula` | a total that should be formula-driven is **hardcoded** | `FAIL` |
| `debit_credit_balance` | the trial balance does **not** tie out (debit ≠ credit) | `FAIL` |
| `forbidden_text` | stale review notes / internal / process words (TODO, "reviewer decision", tool names…) | `FLAG` |
| `lineage_direction` | lineage is inverted — evidence holds a formula, or a detail driver is a literal | `FLAG` |
| `cap_logic_leftover` | draft-only `MIN/MAX` cap formula was never replaced | `FLAG` |
| `json_tieout` | the sibling JSON export disagrees with the workbook | `FAIL` |

**Verdict roll-up:** any `FAIL` ⇒ workbook verdict `FAIL`; otherwise any `FLAG`
⇒ `REVIEW`; otherwise `PASS`. The run's overall verdict is the worst of these.

Adding a rule is a single function: write a `(WorkbookContext) -> list[Finding]`
function and decorate it with `@check("my_rule")`. It joins the registry — the
runner, report, and CLI pick it up automatically.

**Why a script and not an LLM:** it is deterministic and unfalsifiable. The
read-only constraint means the check cannot *introduce* a defect — only report.
The same checks run identically every time, catching the regression human eyes
miss on the 14th workbook. Synthetic data is generated with the stdlib `random`
module under a **fixed seed**, so the corpus and every finding are reproducible.

## ▶️ Run it (fictional data)
```bash
pip install openpyxl pytest          # the only third-party deps

# One-shot: generate the fictional corpus + write both reports
python run.py

# Or drive the engine directly:
python -m validation_engine.generate                 # write dummy workbooks -> ./samples
python -m validation_engine ./samples                # validate a folder, print findings
python -m validation_engine ./samples --generate \   # (re)generate, then validate,
    --json report.json --md report.md                #   and write structured reports
```
The generator plants **exactly one defect per rule** (plus one clean workbook)
so you can watch each rule fire. Exit code encodes the verdict:
`0` = PASS · `1` = REVIEW (flags only) · `2` = FAIL · `3` = usage error.

### Real example output
```text
=== clean__Demo_Holdings_LLC.xlsx === verdict: PASS
  all checks passed

=== hardcoded_total__Maple_Fund_LP.xlsx === verdict: FAIL
  [FAIL] expected_formula @ Surplus-Detail!B6: expected a formula but found hardcoded value: 900
  [FLAG] lineage_direction @ Surplus-Detail!B6: detail driver should be a formula but is a literal: 900

=== unbalanced_tb__Birchwood_Op_Co.xlsx === verdict: FAIL
  [FAIL] debit_credit_balance @ Trial-Balance!B:C: trial balance does NOT tie out: debit=885 vs credit=875 (diff=10)

=== stale_note__Cedar_Ridge_Trust.xlsx === verdict: REVIEW
  [FLAG] forbidden_text @ Surplus-Detail!D2: forbidden text 'todo' in cell: 'TODO: reviewer decision pending on FY2024 income'

=== reversed_lineage__Harborview_Partners_LP.xlsx === verdict: REVIEW
  [FLAG] lineage_direction @ Evidence!B2: evidence input should be a literal but is a formula: =Opening+0

=== cap_leftover__Sandbox_Capital_LLC.xlsx === verdict: REVIEW
  [FLAG] cap_logic_leftover @ Summary!B2: leftover MIN/MAX cap logic: =MAX(0, 'Surplus-Detail'!B6)

=== json_mismatch__Demo_Holdings_LLC.xlsx === verdict: FAIL
  [FAIL] json_tieout @ json:closing_surplus: JSON closing_surplus=1725 != workbook closing surplus=1700

Overall verdict: FAIL  (7 workbook(s))
```

The structured JSON report carries the same findings machine-readably:
```json
{
  "tool": "validation_engine",
  "overall_verdict": "FAIL",
  "workbook_count": 7,
  "registry": ["expected_formula", "debit_credit_balance", "forbidden_text",
               "lineage_direction", "cap_logic_leftover", "json_tieout"],
  "reports": [
    {
      "workbook": "unbalanced_tb__Birchwood_Op_Co.xlsx",
      "verdict": "FAIL",
      "counts": {"PASS": 6, "FAIL": 1, "FLAG": 0},
      "findings": [
        {
          "rule": "debit_credit_balance",
          "status": "FAIL",
          "location": "Trial-Balance!B:C",
          "message": "trial balance does NOT tie out: debit=885 vs credit=875 (diff=10)"
        }
      ]
    }
  ]
}
```

## ✅ Tests
```bash
python -m pytest -q
```
Real result:
```text
.......................                                                  [100%]
23 passed in 31.28s
```
The suite proves the contract: **every planted defect is caught by its rule**
(one per rule), the **clean workbook passes** with no FAIL/FLAG, the
**report structure** (markdown + JSON) is well-formed, the engine is
**strictly read-only** (audited files are byte-identical before/after a run),
and generation + findings are **deterministic** across runs.

## Layout
```
audit-automation/
├── run.py                       # zero-arg quickstart: generate + validate + write reports
├── validation_engine/
│   ├── __init__.py
│   ├── __main__.py              # enables `python -m validation_engine`
│   ├── generate.py              # seeded synthetic corpus (fictional, one defect per rule)
│   ├── engine.py                # data model, check registry, rules, runner, reporting
│   ├── cli.py                   # folder-validation CLI
│   └── tests/                   # pytest: defects caught, clean passes, report shape, read-only
└── samples/                     # generated dummy workbooks + JSON exports (gitignorable)
```

## What this demonstrates
- Delivers **practical Python** controls around spreadsheet work — a real
  registry-based engine, not a one-off script.
- Demonstrates *why* deterministic verification outperforms asking an AI to self-check.
- Targets the errors that **survive human review** — hardcoded totals,
  out-of-balance tie-outs, leftover draft logic, inverted lineage, stale notes.
- Ships **runnable and tested**, on confidentiality-safe fictional data.
