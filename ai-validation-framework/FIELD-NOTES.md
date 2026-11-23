# Field Notes — What the Authority Hierarchy Actually Caught

> 🔒 **Confidentiality posture.** This note describes a *pattern* observed while applying the
> Triangulate model to real work. It reproduces **no** employer or client entity, person,
> structure, figure, file path, or workpaper. Every specific below is generalized to the
> mechanics of the control. The point is the failure mode, not the engagement.

The framework's claim is easy to state and hard to prove: **a multi-LLM majority vote is not a
control.** Separation of duties is. This note records what happened the first time the full
hierarchy ran end-to-end on a live, high-stakes schedule — and what it caught that nothing
upstream did.

---

## The setup

A recurring schedule of ~150 line items had to be rolled forward. A reviewer with authority over
the subject matter returned **43 answered decision items** in a workbook — one answer per row, in a
designated answer column.

The pipeline that ran:

| Stage | Who | Mandate |
|---|---|---|
| 1 | **Preparer** | Apply the 43 answers to the schedule; build the deliverable |
| 2 | **Reviewer A** | Independent LLM review — re-derive the answers, audit integrity, sweep completeness |
| 3 | **Reviewer B** | Independent LLM review, **different vendor**, same brief, no access to A's findings |
| 4 | **Reconciler** | Source-first pass: rebuild the answer set from scratch; treat A and B as *unchecked* |
| 5 | **Deterministic audit** | Re-derive every formula, recount, diff every carried-over cell |
| 6 | **Human gatekeeper** | Final sign-off |

---

## Catch #1 — the off-grid answer

One of the 43 answers was not in the answer column.

The reviewer had typed it **one column to the right** of where every other answer lived — same row,
adjacent cell, distinct font colour. A human reading the workbook would see it immediately. Three
automated passes did not:

- **The preparer** read the designated answer column, found the cell blank, and carried the item
  forward as *unresolved* — then wrote an email asking the reviewer a question the reviewer had
  already answered.
- **Reviewer A** validated "was each answer applied?" by iterating the same column. Same blind spot,
  inherited. It reported the item as correctly open.
- **Reviewer B** — different vendor, different prompt, independent run — **also** reported it as
  correctly open.

Two independent AI reviewers agreed with the preparer. Consensus was unanimous and wrong.

**The reconciler caught it** for one structural reason: its mandate was to *rebuild the answer set
from the source*, not to *verify the preparer's answer set*. Sweeping the full used range of the
reviewer's workbook — every column, not the expected one — surfaced the orphan cell. The item was
not open. It had been answered, and the answer reversed the treatment.

The failure mode has a name worth remembering: **inherited scope.** A reviewer that checks the
preparer's work by re-running the preparer's method inherits the preparer's blind spots, no matter
how independent the model is. Independence of *inference* is not independence of *scope*.

## Catch #2 — the confident false positive

The same reconciliation pass ran in the other direction.

One reviewer flagged a line as wrongly excluded, reasoning from a status field in a registry
system: the registry showed the item **active**, so excluding it looked like an error. Plausible,
well-argued, and the kind of finding a tired preparer accepts.

The reconciler opened the **signed source document** instead. The document was explicitly captioned
as a final filing, with the corresponding indicator box checked and a countersignature. The registry
status was simply stale — the record had never been updated after the filing.

Exclusion was correct. The finding was withdrawn on documentary evidence, not on argument.

This is the authority model doing its job in the direction people forget: **a control has to be
able to reject the reviewer, not just the preparer.** A framework that only ever ratchets toward
"more findings" is a ratchet, not a control.

---

## What the two catches have in common

| | Catch #1 | Catch #2 |
|---|---|---|
| Upstream consensus | Unanimous | Confident single finding |
| What it rested on | The expected column | A status field |
| What overturned it | The full source sweep | The signed document |
| Direction of error | False negative (missed answer) | False positive (invented error) |

Both resolved for the same reason: **something in the hierarchy was required to go back to the
source and had no standing to defer to a prior conclusion.**

That is the whole design. Not more reviewers — a *differently-mandated* one.

---

## What this changed in the model

Three rules earned their place in the framework's operating brief:

1. **Rebuild, don't diff.** A verification stage that begins from the preparer's output inherits its
   scope. The reconciler starts from the source and builds its own answer set before looking at
   anything downstream.
2. **Sweep the whole surface.** Read the full used range, every column, not the schema you expect.
   Data placed by humans lands outside the grid; the off-grid cell is exactly where the answer
   nobody applied will be.
3. **The document outranks the registry, and the registry outranks the filename.** Status fields go
   stale, filenames lie, and a confident reviewer citing either is still citing neither. When a
   conclusion is material, open the signed artifact.

Rule 3 has a corollary the pipeline now enforces explicitly: a reviewer's finding is a *hypothesis*
until a source document confirms it. Findings are not evidence — including this framework's own.

---

## The honest scoreboard

The deterministic gates — formula re-derivation, cell-by-cell mapping, recounts — passed on the
first full run and found nothing the preparer had not already fixed. They are necessary and they
are not where the value was.

**Both material catches came from the source-first mandate, and neither came from adding a model.**
Reviewer B was a different vendor with a clean context, and it reproduced Reviewer A's blind spot
exactly, because it was handed the same scope.

If there is one line to take from this note: **three systems agreeing on the same blind spot is
still a blind spot.** Verification is not a vote. It is a mandate to go somewhere the others
did not.

---

*See also: [Triangulate README](./README.md) · [prompt engineering notes](./prompt-engineering.md) ·
[Case Study](../docs/CASE-STUDY.md)*
