# AI Validation Framework: Triangulate

<p align="center"><img src="../assets/systems/triangulate.gif" alt="Triangulate AI validation pipeline live demo" width="100%"></p>
<p align="center"><img src="../assets/flows/triangulate-flow.svg" alt="Triangulate AI validation flow chart" width="100%"></p>

Triangulate is the AI control framework at the center of this portfolio: a multi-agent
LLM review pipeline with guardrails, built so AI can accelerate financial workpapers without
becoming an unaccountable single point of failure. It ships with 8,320 tests covering the roles,
the authority model, the automated verdict policy, and the external human-approval boundary.

The principle is straightforward: no high-stakes workpaper should rely on one AI system reporting
"looks good." Instead, the work is split into separate roles, each with a defined mandate:

- **Preparer** - builds the draft
- **Reviewer** - challenges the draft and flags issues
- **Specialist** - supports with narrow second opinions or source analysis
- **Deterministic audit** - re-derives formulas and checks rules
- **Policy gate + human approver** - automation marks work eligible or blocked; a person makes the final sign-off decision

That is separation of duties applied to AI: an explicit authority hierarchy, not a multi-LLM
majority vote. AI assumptions rank below source data and signed work, and a deterministic policy
turns severity into PASS, FLAG, or FAIL. In the public demo, `HumanGate` is that automated policy;
PASS means eligible for a person's approval, not that a person has already signed.

---

## Run it

The default demo needs no API key and no network access.

```bash
# from this folder
python -m triangulate                 # defective sample -> VERDICT: FAIL
python -m triangulate --sample clean  # clean sample     -> VERDICT: PASS
python -m triangulate --xlsx          # also emits a small .xlsx workpaper
python run.py --sample clean          # equivalent entrypoint

# tests
python -m pytest -q
```

The CLI exits `0` on PASS and non-zero on FLAG/FAIL, so it can operate as a CI gate.

Artifacts are written to `./output`:

- builder memo
- fix packet
- change log
- QA summary
- machine-readable `verdict.json`

All sample data is fictional and seeded.

---

## What you see in the defective sample

```text
TRIANGULATE ORCHESTRATOR -- AI VALIDATION PIPELINE

VERDICT: FAIL  [cannot sign off]
  Rationale     : 2 Critical finding(s) present; deliverable cannot be signed off and is returned for rebuild.
  Severity      : Critical=2 High=1 Medium=2 Low=1

Fix Packet (Critical/High -> back to Preparer)
  [Critical] B5 TIE_OUT_MISMATCH: Stated value does not tie out to formula.
  [Critical] B5 AUDIT_TIE_OUT_FAIL: Audit tie-out failed on re-derivation.
  [High] B7 HARDCODED_NO_FORMULA: Estimated Tax is hard-coded with no formula support.
```

The clean sample runs the same flow and returns PASS, proving the gate discriminates instead of
always failing.

---

## Adversarial demo: catch an injected hallucination

The framework's whole thesis in one command — **deterministic verification beats asking an AI
whether a workbook "looks right."** Inject one made-up figure into an otherwise-clean workpaper and
watch it get caught:

```bash
python -m triangulate --demo-adversarial
```

An AI asserts a **Total Revenue $49,000 over** what the revenue streams actually sum to, backed
only by an "AI assumption" (the lowest authority). Because that cell feeds the tax and net cells,
the single bad figure **cascades** through the workpaper. A human skim might accept a
plausible-looking total — the pipeline cannot:

```text
VERDICT: FAIL  [cannot sign off]
  Severity      : Critical=6 High=0 Medium=1 Low=0

Fix Packet (Critical/High -> back to Preparer)
  [Critical] B5 TIE_OUT_MISMATCH:   Stated 593000.0 does not tie out to =B2+B3+B4 (expected 544000.0).
  [Critical] B5 AUDIT_TIE_OUT_FAIL: Audit re-derived =B2+B3+B4 to 544000.0.
  [Critical] B7 TIE_OUT_MISMATCH:   =B5*B6 no longer ties (the error propagated).
  [Critical] B8 TIE_OUT_MISMATCH:   =B5-B7 no longer ties.
  ...
```

The injected cell is flagged **independently by two roles** — the LLM-style Reviewer *and* the
deterministic Auditor, which mechanically re-derives every formula. No model is asked "does this
look OK?"; the arithmetic decides. The verdict is **FAIL**, the process **exits non-zero**, and the
workpaper is blocked from sign-off. The behavior is pinned by
[`tests/test_adversarial_demo.py`](./triangulate/tests/test_adversarial_demo.py).

---

## 🔁 Review loop: arithmetic self-heals, judgment escalates

The adversarial demo proves *detection*. The review loop proves **bounded remediation** — it
automates exactly the part of a rebuild a machine is entitled to do, and nothing more:

**observe → detect → remediate → re-review → gate → repeat**

Each turn takes the lowest broken formula cell (a `TIE_OUT` finding carries the auditor's
re-derived expected value), re-derives it **from the cell's own formula on a clone** — a new
workpaper version with a new digest, so the hash-enforced read-only guard is never touched — and
sends the new version back through the **full pipeline**: reviewer, specialist, deterministic
auditor, gate. The loop's fix gets no shortcut; it faces the same three challengers as any preparer.

What it refuses to touch is the point of the framework: an AI-assumption input, a hardcoded cell
with no formula — there is nothing to re-derive those *from*. They stay in the fix packet for a
human. **The loop clears arithmetic; it cannot manufacture authority.**

```bash
# the injected $49k hallucination self-clears — one re-derivation, then a clean re-review:
python -m triangulate.loop --sample adversarial     # FAIL -> PASS, exit 0

# the defective sample: arithmetic fixed, judgment escalated:
python -m triangulate.loop --sample defective       # FAIL -> FLAG, exit 1 (fix packet to human)
```
```text
adversarial:  Turn 1  re-derive B5 = =B2+B3+B4 -> 544,000.00  · criticals 6 -> 0 · PASS
defective:    Turns 1-2 clear the tie-outs; UNSUPPORTED_AI_ASSUMPTION + HARDCODED_NO_FORMULA
              remain in the fix packet — ESCALATED to a human.
```

## Code map

| Concept | Code |
|---|---|
| Preparer | [`triangulate/roles/preparer.py`](./triangulate/roles/preparer.py) |
| Reviewer | [`triangulate/roles/reviewer.py`](./triangulate/roles/reviewer.py) |
| Specialist | [`triangulate/roles/specialist.py`](./triangulate/roles/specialist.py) |
| Deterministic audit | [`triangulate/roles/auditor.py`](./triangulate/roles/auditor.py) |
| Severity and authority model | [`triangulate/model.py`](./triangulate/model.py) |
| Finding reconciliation and automated gate policy | [`triangulate/reconcile.py`](./triangulate/reconcile.py) |
| Role orchestration | [`triangulate/orchestrator.py`](./triangulate/orchestrator.py) |

The reviewer role is read-only by design. The orchestrator hashes the workpaper before and after
review steps so a reviewer cannot quietly mutate the thing it is supposed to inspect.

---

## Two operating modes

### Enterprise-safe mode

This is the default mode in the public repository.

- deterministic mock reviewer
- no API key
- no network call
- no dependency on any orchestration layer
- runnable in conservative corporate IT environments

This mode exists because many finance teams cannot approve agentic tooling on day one. The control
framework still operates because the evidence layer is deterministic.

### Agent-accelerated mode

Where approved by the client, the same framework can be accelerated with live model and agent
orchestration layers:

- a live Claude/LLM reviewer adapter can replace the mock reviewer
- an optional orchestration layer can coordinate longer-running background workflows
- the same layer can help manage handoffs, role separation, and unattended task queues
- fix packets and QA summaries can be generated with less manual steering

The control rule stays the same: AI can accelerate preparation and review, but it does not replace
source evidence, deterministic validation, or human sign-off.

See **[../docs/DEPLOYMENT-TRACKS.md](../docs/DEPLOYMENT-TRACKS.md)** for the client-facing version
of this distinction.

---

## Optional live-model adapter

The repo includes an optional live Anthropic Claude reviewer adapter in
[`roles/reviewer.py`](./triangulate/roles/reviewer.py). It calls the API with the Python
standard library (`urllib`, no SDK) and requests JSON-schema structured output. It is not used by
the default pipeline, which ships with a deterministic offline mock so the demo runs with no key.

To use a live reviewer, set an API key and swap the reviewer backend:

```python
from triangulate.orchestrator import TriangulateOrchestrator
from triangulate.roles.preparer import DemoPreparer
from triangulate.roles.reviewer import AdversarialReviewer, AnthropicReviewer

orch = TriangulateOrchestrator(
    preparer=DemoPreparer(kind="defective"),
    reviewer=AdversarialReviewer(AnthropicReviewer()),
)

print(orch.run().verdict.status)
```

Model names and provider options change over time, so production use should pin the model approved
for that client environment. The public demo avoids this issue by running offline.

---

## Why this matters

LLMs are useful, but they fail in ways that matter for accounting:

- they can agree too easily
- they can invent support
- they can miss the same issue twice
- they can explain a number without tying it to source

Triangulate assumes those failures will occur and builds the workflow around them.

The result is not "the AI said yes." The result is a fix packet, a severity ranking, a read-only
audit trail, an automated policy verdict, and an explicit human-approval boundary — AI for speed,
controls for defensibility.

How the review prompts themselves are engineered as controls — role injection, scope-bracketed
templates, and negative constraints — is documented in
[Prompt Engineering](./prompt-engineering.md).

What the model caught the first time it ran end-to-end on a live, high-stakes schedule — including
an answer two independent LLM reviewers both missed, and a confident reviewer finding overturned by
a signed source document — is written up in [Field Notes](./FIELD-NOTES.md).

---

## Portfolio bullets

- Designed a multi-role AI validation framework for high-stakes financial workpapers.
- Proved the control in the field: the source-first mandate caught an answer that unanimous multi-model review missed, and rejected a plausible reviewer finding on documentary evidence.
- Applied separation of duties across AI roles, deterministic audit, an automated gate policy, and an external human approver.
- Built deterministic read-only validation so the checker cannot corrupt the file it checks.
- Created fix packets, QA summaries, and machine-readable verdicts for review evidence.
- Designed the framework for two client realities: enterprise-safe operation and agent-accelerated operation with an optional orchestration layer for approved, agent-enabled environments.
