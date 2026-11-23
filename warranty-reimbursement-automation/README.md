# Warranty reimbursement automation

A deterministic, **read-only** control engine for a homebuilder's warranty
reimbursement programme.

A builder buys a warranty policy at the start of a project, then spends the next
several years claiming against it a few thousand dollars at a time: a leaking
sink in unit 4, a failed circuit in unit 11. Each claim is trivially small. The
policy behind them is not, and it is finite.

So the failure mode is **accumulation**, and the boundaries at the edges of each
period. Any one claim is obviously fine; the running total is what goes wrong,
and nobody reviewing a single claim can see it.

Two things have to hold at once, and neither is visible from a single claim:

1. **The pool is bounded.** Cumulative reimbursement can never exceed the
   coverage limit — a limit derived from the premium, which is derived from
   construction cost. Three numbers typed once at inception and trusted forever.
2. **Every claim has to be inside something.** Inside the policy period, inside
   its own quarterly reporting window, and after the unit it relates to actually
   closed — because coverage begins at close of escrow and not before.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 22 controls, writes
`warranty_report.json` and `warranty_report.md`, and exits with the verdict code.
The corpus contains planted defects on purpose, so a non-zero exit is the engine
working.

## The 22 controls

| Family | Count | Asks |
|---|---|---|
| `set_` | 2 | Is the claim file complete enough to read? |
| `pol_` | 6 | Are the policy terms consistent, and is the pool intact? |
| `clm_` | 6 | Does each claim sit inside its period, and do the periods foot? |
| `cost_` | 3 | Is there a real warranty cost behind every claimed dollar? |
| `unit_` | 2 | Did the unit close before the defect being claimed for? |
| `rem_` | 3 | Is the money being sent to the right place? |

Three are worth calling out.

**The derivation chain is checked, not trusted.** Premium is a rate on
construction cost; the coverage limit is a multiple of the premium. Every later
control measures against that limit, and nobody re-examines it once the policy is
bound — so a single mistyped construction cost silently rescales the whole policy.
All three numbers are re-derived.

**A claim can sit correctly inside its quarter and still be outside the policy.**
Those are two separate controls on purpose. The quarter still foots with an
uncovered claim inside it, which is exactly why the quarterly check cannot find
it. There is a test that asserts precisely this: the policy check fires and the
subtotal check stays silent.

**Duplicates are caught across quarters, not just within one.** The same vendor
invoice re-claimed three periods later is invisible to anyone reviewing either
quarter alone. Matching is on vendor *and* invoice rather than amount — two
repairs of equal value are common and are not each other, and there is a test
asserting that case is not a false positive.

## Design guarantees

- **Read-only.** Claim files are parsed and never written back. The engine cannot
  introduce a defect; it can only report one.
- **Integer cents, exact comparison.** No floats accumulate and there is no
  tolerance band. A value that should be integer cents but is not produces an
  `AMOUNT_INVALID` finding — contained to the one row it was read on — rather
  than being coerced.
- **Deterministic and byte-stable.** Same inputs, same findings, same order.
- **Absent evidence is not a passing control.** An unreadable policy period fails
  the claims that needed it rather than skipping quietly.

## Tests

299 tests, all passing:

```bash
python -m pytest
```

- Every one of the 22 controls has a planted defect that trips it, asserted by
  name, and coverage is asserted too.
- Boundaries are pinned: the pool passes exactly at its limit and fails one cent
  past it; quarter edges are inclusive; a claim on the policy's final day is
  covered and one day later is not; a claim on the close date is covered and one
  day before is not.
- The clean baseline is asserted rule-by-rule, so a regression names the control
  that broke.

The baseline is *derived*, not typed: only construction cost, the two policy
rates and the repair events are stated. Premium, coverage limit, policy end date,
every quarterly subtotal, the cumulative total, coverage remaining, the cost
ledger and the submission are all computed — so the derivation chain the engine
checks is the same chain that produced the data.

## Fictional data

Everything shipped here is invented — the insurer, the insured entity, projects,
units, vendors and invoice numbers — and the policy period is set in a fictional
future. No real policy, insurer, person, bank, unit or path appears anywhere.
