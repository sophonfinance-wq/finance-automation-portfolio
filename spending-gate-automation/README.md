# Capital spending request gate automation

A deterministic, **read-only** control engine for a developer's capital
Spending Request phase gates — before capital is committed to a development
project, the correct dollar trigger proved to have fired *after* the Initial
Commitment approval, the five Investment Committee phase gates entered in
sequence with every prior phase's deliverables complete, and the underwriting
standards re-derived and tied, with every deviation flagged as an exception.

The scope line is deliberate. Whether the *investment itself* is worth making
is genuine business judgment, and no control here opines on it. What this
engine checks is the deterministic standards layer around that judgment:
triggers, floors, sequence, membership, re-derivations and calendar gates.

Three failures hide inside a bound request package, and none of them look
wrong.

**Capital moves before the gate.** Pursuit costs accumulate past the trigger,
or a deposit goes non-refundable, before the Initial Commitment Request was
ever approved — and by the time the package is assembled, the approval that
*is* in it post-dates the spend it was supposed to authorize.

**The standards drift quietly.** A contingency sits a cent under the floor, a
fee is stated a little off its formula, the growth assumption departs from the
standard with no market support documented, the comparison still points at the
template after feasibility was waived. Each figure looks plausible; none of
them was re-derived.

**The gate summary is asserted, not recomputed.** The package says every phase
gate cleared, on a determination nobody rebuilt from the approvals and the
deliverable checklist underneath it.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 29 controls, writes
`srg_report.json` and `srg_report.md`, and exits with the verdict code. The
corpus contains planted defects on purpose, so a non-zero exit is the engine
working.

## The 29 controls

| Family | Count | Asks |
|---|---|---|
| `set_` | 1 | Is the request package complete, and is the review date readable? |
| `trg_` | 3 | Did the cumulative pursuit-cost, first non-refundable-deposit and cumulative refundable-deposit triggers each fire only *after* the Initial Commitment approval? |
| `seq_` | 5 | Are the phases well-formed, the gate approvals in date order with no phase skipped, the current phase itself approved, and does the stated gate summary recompute? |
| `del_` | 5 | Is every checklist row known and unique, every prior-phase deliverable complete, the current phase's outstanding work flagged, and the estimate basis the one the phase prescribes? |
| `cty_` | 4 | Do the hard and soft contingencies meet their regional floors to the cent, does the construction-start site/vertical split foot, and is the separate escalation reserve in place where required? |
| `gro_` | 1 | Is the growth assumption the standard 3/3 default, or a documented market-supported alternative? |
| `fee_` | 4 | Do the CM Fee (1.5% × hard cost), the Development Fee (3% × (total − financing)), the total-cost footing and every plan-comparison variance re-derive exactly? |
| `cal_` | 2 | Is the comparison basis on the right side of the feasibility-waiver switch, and does a template-basis comparison stand on the current January/June refresh? |
| `evt_` | 2 | Is every logged event a known interim trigger, and does each one link to an interim request that actually exists? |
| `bid_` | 2 | At construction start, is ≥80% of hard cost (third-party GC) or ≥80% of line items (owner-GC) competitively bid, and does an owner-GC project hold a bindable GMP? |

Three are worth calling out.

**The trigger is a date gate on a running total.** `trg_ic_before_pursuit_spend`
re-derives the cumulative pursuit spend in date order and finds the exact entry
that carried it past the threshold — no single invoice has to be large for the
project to be past the gate. The breach date is then held against the Initial
Commitment approval date: approved *on* the breach date satisfies the trigger,
one day later does not.

**The determination recomputes, it is not read back.**
`seq_gate_summary_recomputes` rebuilds every phase's gate-cleared flag from the
approval log and the deliverable checklist — through the same standards kernel
that generated the data — and compares it to the one on file. A gate summary
that is not recomputed from the evidence is an assertion.

**Every floor is met at the floor.** The contingency and bid-coverage tests are
compared cross-multiplied in integer cents (`part × 10000 >= base × floor`), so
a contingency met to the cent passes, a cent under fails, and no floating-point
ratio ever sits between the figure and the standard. In Marran the hard floor
splits at construction start — 10% on site work, 5% on vertical — and each leg
is tested on its own base.

## Two flags, not failures

`del_current_phase_outstanding` marks current-phase deliverables not yet
complete: they are due by the phase's *exit* gate, not its entry, so they are
work to chase rather than a gate already breached. `cal_template_current` marks
a template-basis comparison standing on a stale January/June refresh: the
comparison was made, just against the previous template. Both are
`REVIEW`-severity — worth a human's eyes, not a hard stop.

## Tests

```bash
python -m pytest spending_engine/tests -q
```

A clean baseline parametrized over the registry, one planted-defect file per
named control, boundary tests on every cent and date threshold, and read-only /
determinism proofs that hash the corpus before and after a full run.

## The baseline is derived, not typed

Only the profile, the approvals, the spend ledger, the cost stack, the
checklist, the bid schedule and the comparison figures are stated. The
generator computes everything the engine later checks as a determination — the
CM and Development Fees and the footed total (the Development Fee solved as an
integer fixed point of its own formula), the per-phase gate summary, and every
plan-comparison variance — through the *same* standards kernel the engine
recomputes with.

So the relationships the engine tests are the same relationships that produced
the data.

---

🔒 **All data is fictional.** The developers, the projects, the regions, the
vendors, the dollar figures and every date are invented, and the underwriting
period is set in a fictional future. No employer or client workpaper, entity,
methodology, path or figure is reproduced.
