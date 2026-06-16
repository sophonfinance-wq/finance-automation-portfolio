# Prompt Engineering — Making AI Review Repeatable and Safe

The pipeline only works because the prompts are engineered like controls, not chat. The
techniques below turn "review this workbook" (open-ended, unreliable) into a deterministic
verification harness.

## 1. Role injection per system
Each AI receives a standing "workflow intro" as its first message defining its identity
("you are the Reviewer"), its teammates, what it must do, and — critically — **what it must
not do**. The Reviewer is explicitly told its job is *friction*: "if you agree with
everything, you aren't doing your job." This deliberately counteracts the agreeableness
bias of chat models.

## 2. Scope-bracketed reusable templates
The reusable workbook prompt is a fill-in-the-blanks SOP:

```
CONTEXT          (fixed — assume domain fluency, no re-explaining)
ENTITY INPUTS    (editable — the only thing that changes per run)
CALCULATION RULES (fixed — mandatory cascade/tie-out logic)
TASK SOP         (fixed — step by step)
CRITICAL CONSTRAINTS / DON'T  (fixed — negative constraints)
```

Only the bracketed scope changes between runs; the guardrails are constant. The same
prompt library runs identically across an entire portfolio of entities.

## 3. Negative constraints as first-class content
Every prompt carries an explicit "do not" list, e.g.:
- don't build a web app/macro for work that needs judgment
- don't guess on missing inputs — **flag** instead
- don't touch prior-period signed numbers
- don't let AI/process language leak into client-facing cells
- don't redesign structure unnecessarily

## 4. The "Safe Fixes" pattern (a verification harness, not a vibe check)
The review prompt opens with:

> **Do not edit files. Do not save files. Do not create backups. Inspect only.**

It then enumerates the *exact* changes that were supposed to have been made, gives the
*expected* formula for each target cell, and asks the AI to confirm each one and **flag any
deviation**. This converts an open-ended review into a binary PASS/FAIL per item.

## 5. Self-running verification built into the prompt
The reusable prompt ends with "run N independent cross-checks before saving" and demands a
**PASS/FAIL scorecard** — building automated tie-out logic directly into the AI's
instructions so it self-audits before handing off.

## 6. Severity taxonomy + structured output schema
Reviews must return a fixed structure:

```
structural inventory
→ defects (with cell reference + severity: Critical/High/Medium/Low)
→ assumptions needing verification
→ missing source documents
→ questions for the human
→ per-deliverable verdict
```

Forcing a schema makes outputs **comparable** across runs and across systems — which is
what lets three different AIs' findings be reconciled at all.

---

> All concrete examples above are described generically. The real prompts reference real
> entities, cell values, and file paths and are not included in this repository.
