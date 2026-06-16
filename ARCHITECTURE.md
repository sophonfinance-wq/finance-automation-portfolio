# Platform Architecture

This repo is a seven-system, AI-driven finance and tax automation platform — five deterministic
calculation engines, the Knowledge Brain retrieval engine, plus the Triangulate AI control
framework — with an optional 24/7 agent operations layer:

1. mobile command intake
2. Mac mini worker nodes
3. seeded fictional data generators
4. calculation engines
5. evidence artifacts
6. independent validation
7. CEO-ready reporting and human-gated verdicts

The design principle is simple: the system that produces a number should not be the only system
allowed to bless that number.

---

## Big picture: core finance platform

<p align="center"><img src="./assets/architecture.svg" alt="Core finance platform architecture" width="100%"></p>

---

## Stage by stage

### 1. Mobile or CLI command

The same workflow can start from a phone, approved AI assistant access, a Python command, or CI.
The command surface is flexible; the control trail stays the same.

### 2. Seeded fictional data

Each engine ships with a generator that creates fake but realistic finance data. Fixed seeds make
the output reproducible.

### 3. Calculation engines

| Engine | Folder | What it computes |
|---|---|---|
| Close Engine | `monthly-close-automation` | recurring journal entries, intercompany balancing, close evidence |
| Reconciliation Engine | `cash-reconciliation` | GL-to-bank/lender matching with materiality classification |
| Surplus / ACB Model | `tax-surplus-engine` | foreign-affiliate surplus pools, distribution waterfall, ACB ledger |
| Partnership 1065 Automation | `partnership-1065-automation` | source intake, book-to-tax bridge, 1065 line mapping, K-1 preview, IRC §704(c) built-in gain |

### 3a. Knowledge / retrieval engine

Not every engine computes a number. The Knowledge Brain is a retrieval engine: it ingests
timestamped meeting transcripts into a citation-governed knowledge base and serves them back as
verbatim, sourced citations.

| Engine | Folder | What it serves |
|---|---|---|
| Knowledge Brain | `knowledge-brain-engine` | meeting transcripts -> citation-governed knowledge base; meeting prep and verbatim, timestamped citations for workpapers; review -> remediation where a review meeting's recorded corrections become cited directives and an auto-generated, apply-ready remediation prompt (plus a change-log mapping each directive -> source -> status) that a downstream AI or operator uses to apply the changes — the transcript is the instruction set, and application and verification happen downstream; refuses when no source clears its relevance floor |

### 4. Evidence artifacts

The engines emit Markdown, JSON, and optional `.xlsx` workbooks. These artifacts are the handoff
between "producer" systems and "checker" systems.

### 5. Independent validation

The validation layer does not trust the output just because the output exists.

- **Validation Engine:** read-only rules over workbook and JSON artifacts.
- **Triangulate Orchestrator:** AI separation of duties (preparer / reviewer / specialist) plus a deterministic audit gate and human sign-off.

### 6. Verdicts

The platform produces review-ready artifacts:

- PASS / REVIEW / FAIL verdicts
- fix packets
- QA summaries
- change logs
- machine-readable JSON

The human reviewer remains the final authority.

---

## Deployment architecture: mobile command center

The platform has two deployment tracks.

### Enterprise-safe track

This is the public demo mode.

<p align="center"><img src="./assets/flows/enterprise-safe-flow.svg" alt="Enterprise-safe deployment flow" width="100%"></p>

It uses Python, Excel-compatible files, `openpyxl`, `pytest`, Markdown, JSON, and CI. It does not
require Hermes or OpenClaw.

### Agent-accelerated track

This is the advanced workflow for environments that permit AI workstation orchestration.

<p align="center"><img src="./assets/agent-command-center.svg" alt="Mobile command channel to 24/7 Mac mini agents to finance automation systems" width="100%"></p>

Hermes/OpenClaw can coordinate longer-running work, handoffs, and background review passes.
Telegram or approved mobile access can act as the command surface: send a job, check status, receive
exceptions, and approve the final communication. Dedicated Mac mini workers keep the workspace
available. The final output is a report package plus an executive-ready email draft. The agent layer
does not replace deterministic validation or human sign-off.

## Executive package

<p align="center"><img src="./assets/executive-package.svg" alt="Finance automation outputs to CEO-ready email package" width="100%"></p>

After validation, the system can produce:

- executive summary
- findings and exceptions
- validation status
- files generated
- recommended next action
- CEO/CFO-ready email draft

Sending can be gated by human approval or by a client-approved routing policy.

---

## Design principles

- **Determinism first.** Seeded generators and exact arithmetic make reruns reproducible.
- **Separation of duties.** Builders do not get to bless their own work.
- **Read-only validation.** Checkers should not mutate the files they inspect.
- **Refuse, do not fudge.** Engines reject out-of-tie entries rather than plugging them — and the
  Knowledge Brain refuses to answer when no source clears its relevance floor.
- **Evidence by default.** Every run leaves a reviewable trail, and prior decisions stay citable:
  the Knowledge Brain turns meeting transcripts into verbatim, timestamped citations for workpapers.
- **Client-aware deployment.** The same control pattern can run with or without Hermes/OpenClaw,
  depending on the client's IT rules.
- **Executive-ready communication.** The output is not just technical artifacts; it is packaged so
  leadership can understand what happened and what needs a decision.

---

*Capability-level architecture demonstrated on fictional data, with confidential engagement detail withheld.*
