# Operational Hardening Patterns

This note documents a public-safe pattern behind the portfolio: turning recurring finance
workflows into controlled automation without publishing employer-specific procedures, entities,
file paths, source documents, or figures.

The private implementations are not in this repository. The public systems here reproduce the
capability class on fictional data only.

---

## What Was Hardened

Recent private build work stress-tested three operational patterns that map directly to the public
portfolio systems:

| Pattern | Public-safe capability | Portfolio analogue |
|---|---|---|
| Advisory prechecks before reconciliation | Detect recurring close risks before final review, route exceptions into a structured advisory report, and keep humans responsible for action. | [`cash-reconciliation`](../cash-reconciliation/) |
| Dry-run annual rollforward planning | Plan copy-only schedule rollforwards with explicit logs, stale-file detection, no overwrites, and no destructive operations. | [`monthly-close-automation`](../monthly-close-automation/) + [`audit-automation`](../audit-automation/) |
| Review package assembly | Assemble a local review bundle, source checklist, prompt, and cover note while preserving human sign-off and avoiding live-file mutation. | [`tax-surplus-engine`](../tax-surplus-engine/) + [`ai-validation-framework`](../ai-validation-framework/) |

The key lesson is that the automation boundary matters as much as the calculation:

- default to dry-run for file operations
- copy, never delete
- write an action log every time
- refuse unsafe output destinations
- separate draft preparation from human approval
- keep real financial data out of code, tests, public docs, and public repos
- test the control behavior repeatedly with fictional fixtures

---

## Stress Test Discipline

For the private implementations, each of the three newest tool suites was run through **1,100
clean repeated local test loops** after build-out. These were looped fixture tests on fictional
data, used to shake out nondeterminism, path handling, copy-plan behavior, and output guards.

That number is not a substitute for domain review. It is an engineering control: repeated tests
prove the code path is stable, while the finance reviewer still decides what ships.

---

## Why It Belongs In A Finance Automation Portfolio

Finance automation fails when it tries to be clever at the wrong boundary. The safest systems are
usually conservative:

1. Read from source without mutating it.
2. Produce a local draft or advisory output.
3. Log exactly what would happen before anything happens.
4. Require explicit approval for copy operations.
5. Preserve a human reviewer as the final decision-maker.

That is the same architecture used across this portfolio: deterministic engines, fictional test
data, evidence trails, read-only validation, and human-gated review.
