<p align="center">
  <img src="./assets/banner.svg" alt="Sophon Finance Systems — AI-Driven Finance & Accounting Automation" width="100%">
</p>

# Sophon Finance Systems — AI-Driven Finance & Accounting Automation

[![CI](https://img.shields.io/github/actions/workflow/status/sophonfinance-wq/finance-automation-portfolio/ci.yml?branch=main&label=CI)](https://github.com/sophonfinance-wq/finance-automation-portfolio/actions/workflows/ci.yml)
[![Open in Codespaces](https://img.shields.io/badge/Codespaces-Open%20%26%20Run-181717?logo=github&logoColor=white)](https://codespaces.new/sophonfinance-wq/finance-automation-portfolio)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)

Seven self-contained Python systems for finance and tax work — month-end close, cash/debt
reconciliation, cross-border surplus & ACB, partnership 1065 / §704(c), read-only workbook
validation, and a NotebookLM-style knowledge brain — plus **Triangulate**, a multi-agent LLM
review framework with a deterministic core and a human sign-off gate. Everything runs on seeded
fictional data, is covered by CI, and is built on one rule: **no material output rests on a single
model's word.**

> 🔒 Fully fictional, seeded data. No employer or client workpaper, entity, methodology, path, or
> figure is reproduced.

---

## Quickstart

```bash
git clone https://github.com/sophonfinance-wq/finance-automation-portfolio
cd finance-automation-portfolio
pip install -r requirements.txt

# run the curated test suite (~10k tests, a few seconds)
pytest

# run a system
cd tax-surplus-engine && python -m surplus_engine --start 2021 --end 2024
```

No install? [Open it in a GitHub Codespace](https://codespaces.new/sophonfinance-wq/finance-automation-portfolio)
and run `bash scripts/demo.sh` for the full tour.

---

## Architecture

<p align="center"><img src="./assets/architecture.svg" alt="seeded data to calculation engine to evidence to validation to human verdict" width="100%"></p>

The same control pattern runs through every system:

**seeded data → calculation engine → cited evidence → read-only validation → human verdict**

- **Deterministic core.** Integer-cent arithmetic, seeded generators, byte-stable outputs — the
  numbers don't move between runs, so every figure is re-derivable and diffable.
- **Separation of duties (Triangulate).** A preparer builds, a reviewer challenges, a specialist
  supports, a deterministic audit re-derives, and a human signs off. Read-only review is
  hash-enforced (any change to a workpaper raises); AI assumptions rank below source data and
  signed work; a severity→verdict gate (PASS / FLAG / FAIL) doubles as a CI exit code.
- **Human-gated.** Every AI-assisted deliverable ends at a person. An optional orchestration layer
  can coordinate longer-running work in approved, agent-enabled environments — it only adds
  throughput; the controls are what make the output defensible. The platform runs fully without it.

Full flow in **[ARCHITECTURE.md](./ARCHITECTURE.md)**.

---

## The seven systems

Every system is self-contained, deterministic, and ships with a seeded fictional-data generator.

| System | Package | Run | What it demonstrates |
|---|---|---|---|
| [Month-End Close](./monthly-close-automation/) | `close_engine` | `python -m close_engine --period 2026-03` | recurring JEs, schedule-to-GL tie-outs, debit/credit controls, refusal to post out-of-tie entries |
| [Cash & Debt Reconciliation](./cash-reconciliation/) | `recon_engine` | `python -m recon_engine` | GL-to-bank/lender matching, materiality classification, evidence log generation |
| [Tax Surplus / ACB](./tax-surplus-engine/) | `surplus_engine` | `python -m surplus_engine --start 2021 --end 2024` | Canadian foreign-affiliate surplus pools, distribution waterfall, per-layer FX, ITA 40(3)-style deemed gain on negative ACB |
| [Partnership 1065](./partnership-1065-automation/) | `partnership_tax` | `python -m partnership_tax` | book-to-tax bridge, 1065 / Sch. K / L / M-1 / M-2 / K-1 mapping, review checks, IRC §704(c) built-in gain (`--section704c`) |
| [Validation Engine](./audit-automation/) | `validation_engine` | `python run.py` | read-only workbook checks, formula integrity, lineage, PASS / REVIEW / FAIL verdicts, byte-identical no-write guarantee |
| [Triangulate](./ai-validation-framework/) | `triangulate` | `python -m triangulate` | AI separation of duties: preparer, reviewer, specialist, deterministic audit, human gate |
| [Knowledge Brain](./knowledge-brain-engine/) | `brain_engine` | `python -m brain_engine ask "..."` | meeting transcripts → citation-governed knowledge base; verbatim, timestamped citations; review → remediation (cited change-directives + an apply-ready remediation prompt); refuses with no source |

**Triangulate** is the centerpiece: a framework for putting AI into financial work without letting a
single model validate its own output. Its reviewer is a live Anthropic Claude integration
(standard-library `urllib`, `claude-opus-4-8`, JSON-schema output) that swaps cleanly with a
deterministic offline mock — so the same pipeline runs air-gapped or against an approved model.

---

## Testing

The suite is **tiered** — a fast curated suite gates CI, and an exhaustive property sweep runs on
demand:

| Tier | Command | Tests | What it is |
|---|---|---:|---|
| **Curated** (default) | `pytest` | **10,010** | Hand-written unit + behavior tests and parametrized coverage across all 7 systems. Runs in seconds; gates CI. |
| **Property sweep** (opt-in) | `SWEEP=1 pytest` | **~1.09M** | Exhaustive `itertools.product` grids asserting sum-preservation, exact integer round-trips, arithmetic identities, frozen-dataclass round-trips, and determinism across the full integer input domain. |

Every test calls real engine code and asserts a true property. The sweep is excluded from the
default run (and CI) for speed and generated at import — the files stay small. It's there for
exhaustive verification when you want it; turn it on with `SWEEP=1`.

Curated tests by system: close **1,800** · partnership **1,605** · knowledge-brain **1,499** ·
tax-surplus **1,486** · validation **1,314** · triangulate **1,305** · recon **1,001**.

---

## Repository layout

```text
finance-automation-portfolio/
├── monthly-close-automation/     close_engine      — JEs, tie-outs, out-of-tie refusal
├── cash-reconciliation/          recon_engine      — GL ↔ bank/lender matching
├── tax-surplus-engine/           surplus_engine    — FA surplus pools, ACB, per-layer FX
├── partnership-1065-automation/  partnership_tax   — 1065 / K-1, §704(c) built-in gain
├── audit-automation/             validation_engine — read-only workbook checks
├── ai-validation-framework/      triangulate       — multi-agent LLM review + guardrails
├── knowledge-brain-engine/       brain_engine      — cited retrieval, review → remediation
├── docs/                         architecture · case study · walkthrough
├── assets/                       diagrams + demo GIFs
├── scripts/                      demo.sh
└── .github/workflows/            CI + runnable demo
```

Each system has its own README with the regime it models, the run commands, and sample output.

---

## See it run

<details>
<summary><b>Watch each engine run (animated demos, all on fictional data)</b></summary>

<br>

**Month-End Close Engine**
<p><img src="./assets/systems/close.gif" alt="Month-End Close Engine live demo" width="100%"></p>

**Cash & Debt Reconciliation**
<p><img src="./assets/systems/recon.gif" alt="Cash and Debt Reconciliation live demo" width="100%"></p>

**Tax Surplus / ACB Model**
<p><img src="./assets/systems/surplus.gif" alt="Tax Surplus and ACB Model live demo" width="100%"></p>

**Partnership 1065 Automation**
<p><img src="./assets/systems/partnership-tax.gif" alt="Partnership 1065 Automation live demo" width="100%"></p>

**Validation Engine**
<p><img src="./assets/systems/validation.gif" alt="Validation Engine live demo" width="100%"></p>

**Triangulate**
<p><img src="./assets/systems/triangulate.gif" alt="Triangulate AI validation live demo" width="100%"></p>

**Knowledge Brain Engine**
<p><img src="./assets/systems/brain.gif" alt="Knowledge Brain Engine live demo" width="100%"></p>

</details>

The **[Guided Demo & Walkthrough](./docs/DEMO-WALKTHROUGH.md)** shows the command to run for each
system, what to inspect, and what it proves. For how these map to specific finance, tax, and
engineering competencies, see the **[Case Study](./docs/CASE-STUDY.md)**.

---

## Stack

`Python 3.12+` · `openpyxl` · `pytest` · `Anthropic Claude API` (stdlib `urllib`, no SDK) ·
`GitHub Actions CI` · `LibreOffice headless` (Excel recalculation) · Excel-compatible workbooks ·
Markdown / JSON evidence.

No agent or orchestration dependency is required to run the demos or validate the control logic.

---

## Author

**Sophonnarith Hang** — AI Finance Engineer · Founder, Sophon Finance Systems · 18+ yrs senior
accounting & tax (Fortune 100 & 500; GAAP / FAR / CAS).
[linkedin.com/in/sophonnarith](https://www.linkedin.com/in/sophonnarith) · sophonfinance@gmail.com

## License

[MIT](./LICENSE). A public portfolio of original systems and methodology, demonstrated on fully
fictional data with all confidential engagement detail withheld.
