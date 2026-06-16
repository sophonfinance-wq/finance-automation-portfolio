<p align="center">
  <img src="./assets/banner.svg" alt="Sophon Finance Systems — AI-Driven Finance & Accounting Automation" width="100%">
</p>

# Sophon Finance Systems — AI-Driven Finance & Accounting Automation

[![CI](https://img.shields.io/github/actions/workflow/status/sophonfinance-wq/finance-automation-portfolio/ci.yml?branch=main&label=CI)](https://github.com/sophonfinance-wq/finance-automation-portfolio/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)

**Finance. Automated. Intelligence. Applied.**

A 24/7 AI-driven finance automation command center: mobile command intake, Mac mini agent workers,
seven runnable finance systems, AI review under separation-of-duties controls, and CEO-ready reporting.

This is not a slide deck. It is a working portfolio: real Python packages, seeded fictional data,
deterministic outputs, CI, and 232 tests that pin the behavior.

The pitch is simple: finance teams should not be waiting on manual spreadsheet work, scattered
review notes, or one-off AI chats. A request can start from a phone, route through a 24/7 agent
desk, run the finance engines, validate the results, package the findings, and draft a clean
executive email for the CEO or finance leadership. The mobile layer becomes an operations control
surface: dispatch the job, receive status, approve the final communication.

## What this proves

Most finance teams use AI as a helper. This portfolio shows a stronger pattern:

1. Build the finance engine.
2. Generate traceable evidence.
3. Validate the output with read-only rules.
4. Challenge AI-assisted work through separation of duties.
5. Keep a human gatekeeper responsible for final sign-off.

That is the core idea behind **Triangulate**, the AI validation framework in this repo: no important
financial deliverable should rest on a single model's word.

**Sophonnarith Hang** — AI Finance Engineer / AI Engineering Accountant · Founder, Sophon Finance Systems (18+ yrs senior accounting; GAAP/FAR/CAS)
**Email:** sophonfinance@gmail.com
**LinkedIn:** [linkedin.com/in/sophonnarith](https://www.linkedin.com/in/sophonnarith)

---

## See it run

The systems below are not mockup slides. Each GIF shows a runnable engine producing evidence from
fictional data, with mobile dispatch/status cues in the header, followed by the animated flow chart
that explains what is happening.

### Month-End Close Engine

<p><img src="./assets/systems/close.gif" alt="Month-End Close Engine live demo" width="100%"></p>
<p align="center"><img src="./assets/flows/close-flow.svg" alt="How the Month-End Close Engine works, step by step" width="100%"></p>

### Cash and Debt Reconciliation

<p><img src="./assets/systems/recon.gif" alt="Cash and Debt Reconciliation live demo" width="100%"></p>
<p align="center"><img src="./assets/flows/recon-flow.svg" alt="How the Cash and Debt Reconciliation Engine works, step by step" width="100%"></p>

### Tax Surplus and ACB Model

<p><img src="./assets/systems/surplus.gif" alt="Tax Surplus and ACB Model live demo" width="100%"></p>
<p align="center"><img src="./assets/flows/surplus-flow.svg" alt="How the Tax Surplus and ACB Model works, step by step" width="100%"></p>

### Partnership 1065 Automation

<p><img src="./assets/systems/partnership-tax.gif" alt="Partnership 1065 Automation live demo" width="100%"></p>
<p align="center"><img src="./assets/flows/partnership-tax-flow.svg" alt="Partnership 1065 Automation flow chart" width="100%"></p>

### Validation Engine

<p><img src="./assets/systems/validation.gif" alt="Validation Engine live demo" width="100%"></p>
<p align="center"><img src="./assets/flows/validation-flow.svg" alt="Validation Engine flow chart" width="100%"></p>

### Triangulate AI Validation

<p><img src="./assets/systems/triangulate.gif" alt="Triangulate AI validation live demo" width="100%"></p>
<p align="center"><img src="./assets/flows/triangulate-flow.svg" alt="Triangulate AI validation flow chart" width="100%"></p>

### Knowledge Brain Engine

Meeting transcripts become a citation-governed knowledge base: prep for meetings and pull verbatim,
timestamped citations for workpapers and disclosure notes — and the brain refuses when it has no
source. See **[Knowledge Brain Engine](./knowledge-brain-engine/)**.

<p><img src="./assets/systems/brain.gif" alt="Knowledge Brain Engine live demo" width="100%"></p>
<p align="center"><img src="./assets/flows/brain-flow.svg" alt="How the Knowledge Brain Engine works, step by step" width="100%"></p>

All seven demos run on synthetic data. The **[Guided Demo & Walkthrough](./docs/DEMO-WALKTHROUGH.md)**
shows the command to run, what to inspect, and what each system proves.

---

## The operating model: phone to CEO package

The platform can be deployed two ways.

### Agent command center

For approved environments, Hermes/OpenClaw agents can sit above the seven systems as a 24/7
coordination layer. Dedicated Mac mini worker nodes keep the agent workspace online. A mobile phone
can send work instructions through a private Telegram command channel or through approved mobile
access to Codex/Claude-style assistants. The agents coordinate the work, run background review
queues, and send status updates back to the operator, so the phone becomes the command channel while
the Mac mini workers do the long-running finance work.

<p align="center"><img src="./assets/agent-command-center.svg" alt="Mobile command channel to 24/7 Mac mini agents to finance automation systems" width="100%"></p>

That makes the system feel less like "open a chatbot and ask for help" and more like an accounting
operations desk: send an instruction, let the agent layer coordinate the work, receive a fix packet
or exception report, then receive an executive-ready summary.

### CEO-ready output

The system does not stop at "the report is done." It produces the management package:

- executive summary
- key findings
- exceptions and risk levels
- files produced
- validation status
- open items
- recommended next action
- CEO/CFO-ready email draft with proper title, tone, and attachments/links

For conservative environments, the email is drafted for approval. For approved workflows, routing
or sending can be policy-controlled.

### Enterprise-safe mode

If IT does not allow Hermes, OpenClaw, Telegram, or autonomous agents, the platform still works.
The public demo runs with a conservative stack:

- Python
- `openpyxl`
- `pytest`
- Excel-compatible workbooks
- Markdown/JSON evidence
- GitHub Actions CI
- human-gated review

No Hermes or OpenClaw dependency is required to run the demo or validate the control logic. The
agent layer makes the workflow faster and more convenient; the controls are what make it defensible.

See **[docs/DEPLOYMENT-TRACKS.md](./docs/DEPLOYMENT-TRACKS.md)** and
**[docs/AGENT-OPERATIONS.md](./docs/AGENT-OPERATIONS.md)** for the detailed architecture.

---

## Scope and proof

<p align="center"><img src="./assets/scope.svg" alt="Scope and proof - built for real engagements on fictional data" width="100%"></p>

**Confidentiality note:** this repo demonstrates capability on fully fictional, seeded sample data.
It does not reproduce any employer or client workpaper, entity list, methodology, path, file, or
financial amount. The public systems are intentionally sanitized and reusable.

For how these systems map to specific finance, tax, and engineering competencies, see the
**[Case Study](./docs/CASE-STUDY.md)**.

---

## Platform at a glance

<p align="center"><img src="./assets/architecture.svg" alt="Platform architecture: seeded synthetic data to calculation engines to evidence to validation to human verdict" width="100%"></p>

See **[ARCHITECTURE.md](./ARCHITECTURE.md)** for the full flow.

---

## The seven systems

Every system is self-contained, deterministic, and ships with a seeded fictional-data generator.

| System | Run command | What it demonstrates |
|---|---|---|
| [Month-End Close Engine](./monthly-close-automation/) | `python -m close_engine --period 2026-03` | recurring JEs, schedule-to-GL tie-outs, debit/credit controls, refusal to post out-of-tie entries |
| [Cash & Debt Reconciliation](./cash-reconciliation/) | `python -m recon_engine` | GL-to-bank/lender matching, materiality classification, evidence log generation |
| [Tax Surplus / ACB Model](./tax-surplus-engine/) | `python -m surplus_engine --start 2021 --end 2024` | Canadian foreign-affiliate surplus pools, distribution waterfall, ACB ledger behavior, ITA 40(3)-style deemed gain when a return of capital drives ACB below zero |
| [Partnership 1065 Automation](./partnership-1065-automation/) | `python -m partnership_tax` | AI-assisted source intake, book-to-tax bridge, 1065/Schedule K/Schedule L/M-1/M-2/K-1 mapping, review checks, and IRC §704(c) built-in gain (`--section704c`) |
| [Validation Engine](./audit-automation/) | `python run.py` | read-only workbook checks, formula integrity, lineage checks, PASS / REVIEW / FAIL verdicts |
| [Triangulate Orchestrator](./ai-validation-framework/) | `python -m triangulate` | AI separation of duties: preparer, reviewer, specialist, deterministic audit, human gate |
| [Knowledge Brain](./knowledge-brain-engine/) | `python -m brain_engine ask "..."` | meeting transcripts -> citation-governed knowledge base; meeting prep + verbatim, timestamped citations for workpapers; refuses when it has no source |

## Why Triangulate matters

The centerpiece is **[Triangulate](./ai-validation-framework/)**, a framework for using AI in
financial work without letting one AI system mark its own homework.

It separates roles:

- a preparer builds
- a reviewer challenges
- a specialist supports
- a deterministic audit re-derives
- a human gatekeeper signs off

The framework can run in an enterprise-safe offline mode with deterministic mock reviewers, or be
adapted to approved live-model / Hermes / OpenClaw workflows where a client permits them.

In an agent-accelerated deployment, Triangulate becomes the control brain behind the 24/7 agent
desk: Hermes/OpenClaw can coordinate tasks, but Triangulate defines who prepares, who reviews, who
audits, and when the human must step in.

---

## Quickstart

```bash
# one-time setup
python -m pip install -r requirements.txt

# run the full test suite
python -m pytest -q
```

Each system has its own README and run command.

---

## Capabilities demonstrated

| Capability | What it means in practice |
|---|---|
| Month-end close automation | Repeatable close workflows for recurring entries, tie-outs, and review evidence |
| Reconciliation systems | Bank/lender-to-GL reconciliation with materiality flags and structured evidence logs |
| International tax modeling | Traceable surplus / ACB logic for complex cross-border tax analysis |
| Partnership tax preparation | AI-assisted 1065 workpaper build, book-to-tax bridge, K-1 allocation preview, and review package |
| Automated verification | Read-only validation that catches formula, tie-out, lineage, and documentation issues |
| AI orchestration and controls | AI review under separation of duties — distinct preparer/reviewer/audit roles, an authority hierarchy, and human sign-off |
| AI knowledge management | Citation-governed retrieval over meeting transcripts — meeting prep and verbatim, timestamped workpaper citations, with a refuse-if-no-source control |
| Mobile command surface | Phone, Telegram-style intake, approved mobile assistant access, status return, and human approval prompts |
| 24/7 agent operations | Dedicated Mac mini worker nodes, mobile command intake, Telegram updates, and background review queues where approved |
| Hermes / OpenClaw workflow design | Advanced-agent orchestration for approved environments, paired with deterministic controls |
| Executive reporting package | CEO-ready summaries, findings, exceptions, attachments, and email drafts after the engines finish |

---

## Tools and stack

`Python` - `openpyxl` - `pytest` - `Excel` - `LibreOffice headless` - `ERP general ledger`
`Excel-GL connector` - `Claude Code / Cowork` - `OpenAI Codex` - `ChatGPT` - `NotebookLM`
`Hermes` - `OpenClaw`

---

## Let's talk

If your finance team is still closing, reconciling, and reviewing high-risk work by hand, this is
the conversation I want to have: what can be automated, what must stay controlled, and what can run
24/7 without losing the evidence trail.

**Email:** sophonfinance@gmail.com
**LinkedIn:** [linkedin.com/in/sophonnarith](https://www.linkedin.com/in/sophonnarith)

---

*A public portfolio of original systems and methodology, demonstrated on fictional data with all
confidential engagement detail withheld.*
