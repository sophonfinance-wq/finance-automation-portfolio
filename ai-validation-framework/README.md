# AI Validation Framework: Triangulate

<p align="center"><img src="../assets/systems/triangulate.gif" alt="Triangulate AI validation pipeline live demo" width="100%"></p>
<p align="center"><img src="../assets/flows/triangulate-flow.svg" alt="Triangulate AI validation flow chart" width="100%"></p>

Triangulate is the AI control framework at the center of this portfolio: a multi-agent
LLM review pipeline with guardrails, built so AI can accelerate financial workpapers without
becoming an unaccountable single point of failure. It ships with 156,285 tests covering the roles,
the authority model, and the human-gated verdict.

The principle is straightforward: no high-stakes workpaper should rely on one AI system reporting
"looks good." Instead, the work is split into separate roles, each with a defined mandate:

- **Preparer** - builds the draft
- **Reviewer** - challenges the draft and flags issues
- **Specialist** - supports with narrow second opinions or source analysis
- **Deterministic audit** - re-derives formulas and checks rules
- **Human gatekeeper** - makes the final sign-off decision

That is separation of duties applied to AI: an explicit authority hierarchy, not a multi-LLM
majority vote. AI assumptions rank below source data and signed work, and a deterministic gate
turns severity into a verdict.

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

## Code map

| Concept | Code |
|---|---|
| Preparer | [`triangulate/roles/preparer.py`](./triangulate/roles/preparer.py) |
| Reviewer | [`triangulate/roles/reviewer.py`](./triangulate/roles/reviewer.py) |
| Specialist | [`triangulate/roles/specialist.py`](./triangulate/roles/specialist.py) |
| Deterministic audit | [`triangulate/roles/auditor.py`](./triangulate/roles/auditor.py) |
| Severity and authority model | [`triangulate/model.py`](./triangulate/model.py) |
| Finding reconciliation and human gate | [`triangulate/reconcile.py`](./triangulate/reconcile.py) |
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
audit trail, and a human-gated verdict — AI for speed, controls for defensibility.

---

## Portfolio bullets

- Designed a multi-role AI validation framework for high-stakes financial workpapers.
- Applied separation of duties across AI roles: preparer, reviewer, specialist, audit, and human gate.
- Built deterministic read-only validation so the checker cannot corrupt the file it checks.
- Created fix packets, QA summaries, and machine-readable verdicts for review evidence.
- Designed the framework for two client realities: enterprise-safe operation and agent-accelerated operation with an optional orchestration layer for approved, agent-enabled environments.
