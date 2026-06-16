# Optional Orchestration Layer

This is the advanced operating model for clients that approve agentic tooling: an optional layer
that coordinates longer-running finance work and routes results through the same deterministic
controls, with a human gate that never moves. The platform runs fully without it.

The layer coordinates work across the seven finance systems, manages background review passes, and
assembles the final executive package — all in approved, agent-enabled environments.

---

## Overview

A request is dispatched, and the orchestration layer coordinates the work. The seven finance systems
run underneath. Validation checks the output. Triangulate challenges the work. Status is routed back
to the operator, and the system packages the result for leadership.

The output is not only a workbook. It is a report, an exception list, a validation status, and an
executive-ready email draft for human approval.

---

## Command surfaces

In approved, agent-enabled environments, the orchestration layer can be driven through an approved
command surface to:

- start a close run
- request a reconciliation review
- request a surplus / ACB package
- check the status of a background review queue
- receive exception summaries
- receive finished-package status
- approve or reject a drafted executive email

The command surface is a convenience layer, not the control system. The control system remains the
evidence, logs, validation, and human approval policy.

Where direct AI assistance is approved, the same surface can be used to:

- request an adjustment to a rule
- request a narrative explanation of a finding
- request a draft client memo
- queue a fix packet for background processing

The operator directs the work; the orchestration layer carries out the longer-running tasks.

---

## Layer model

The orchestration layer functions as an always-available operations desk.

| Layer | Purpose |
|---|---|
| Operator | dispatches commands, receives status, approves final action |
| Approved command surface | lightweight intake and updates |
| Orchestration layer | keeps coordinated work moving and available |
| Multi-step coordination | sequences longer-running agent workflows |
| AI assistants | support coding, review, drafting, and reasoning where approved |
| Finance engines | run close, reconciliation, tax, validation, and AI review |
| Human gatekeeper | final sign-off, approval, and judgment |

This is useful because finance work often involves long waits: exports, source gathering, evidence
packaging, review loops, and exception analysis. The orchestration layer can keep this work moving
while the operator is away from the machine.

---

## How the seven systems fit underneath

The orchestration layer does not replace the systems. It coordinates them.

| System | What the orchestration layer can do |
|---|---|
| Close Engine | run the close package, collect outputs, flag out-of-tie entries |
| Reconciliation Engine | run bank/lender matching, summarize flagged reconciling items |
| Surplus / ACB Engine | generate workpapers and summary packages for the tax model |
| Partnership 1065 Automation | build the 1065 support package, K-1 preview, review checks, and summary draft |
| Validation Engine | run read-only checks and turn failures into exception language |
| Triangulate | route work through preparer, reviewer, specialist, audit, and human gate |
| Knowledge Brain | retrieve prior decisions, assemble meeting prep, pull verbatim, timestamped citations for workpapers, and run review -> remediation — a review meeting's recorded corrections become cited directives plus an auto-generated, apply-ready remediation prompt (and a change-log mapping each directive -> source -> status) that a downstream AI or operator uses to apply the changes (the transcript is the instruction set; application and verification happen downstream) — or surface its refusal when no source qualifies |

The differentiator is not automation alone. It is controlled automation.

---

## CEO-ready reporting

<p align="center"><img src="../assets/executive-package.svg" alt="Finance automation outputs to CEO-ready email package" width="100%"></p>

When the systems complete, the orchestration layer can produce an executive package:

- subject line
- greeting and correct title
- one-paragraph executive summary
- key findings
- exceptions requiring decision
- validation status
- files produced
- recommended next step
- attachments or links
- draft email to CEO, CFO, controller, or reviewer

Example structure:

```text
Subject: March Close Automation Review - Exceptions and Sign-Off Items

Hi [CEO/CFO Name],

The March close automation package has completed. The system generated the JE register,
trial balance tie-out, validation report, and exception summary.

Status: REVIEW
Key findings:
- Two reconciling items exceed the materiality threshold.
- One intercompany tie-out requires controller review.
- No formula integrity failures were detected in the close workbook.

Recommended next action:
Please review the attached exception summary and approve the controller follow-up items.

Regards,
[Sender]
```

For conservative environments, this is a draft for approval. For approved environments, routing or
sending can be policy-controlled.

---

## Controls

The platform is built for throughput without compromising governance.

- no final email send unless the approval policy allows it
- no confidential data in public demos
- source files and outputs remain traceable
- deterministic checks run before executive summaries
- AI-generated assumptions rank below source data and signed work
- the human gatekeeper remains responsible for final sign-off
- IT can select the enterprise-safe mode where agents are not permitted

---

## Enterprise-safe fallback

Where an organization does not permit an orchestration layer or autonomous agents, the same
portfolio runs fully without them:

1. Run the Python engines manually or through CI.
2. Generate Markdown/JSON/.xlsx evidence.
3. Run the validation engine.
4. Use Triangulate in offline/mock mode.
5. Draft the executive package manually or with approved tools.
6. The human reviewer sends the final email.

The optional orchestration layer adds speed. The core control framework is what makes the work
defensible.
