# Payroll & benefit reconciliation automation

A deterministic, **read-only** control engine for one pay period's payroll
benefit reconciliation — every 401(k), HSA and FSA deduction on the payroll
register proved, employee by employee and plan by plan, to have reached each
provider, the general ledger and cash in the same amount, with the employer match
recomputed from its formula, every statutory limit respected, and every
participant deposit inside the DOL small-plan safe harbor.

Every pay period a payroll run fans one register out to several benefit
providers, to cash, and to the ledger, and the money has to arrive intact at each
one. Four failures hide inside that, and none of them look wrong in a stack of
provider upload files.

**The hand-off drifts.** A per-employee deduction on the register is not the
amount that reached the provider, or a plan total ties to the recordkeeper but
not the custodian, or the cash transfer is a dollar off the liability it settles.

**The employer match is wrong.** The booked match does not recompute from the
plan formula applied to eligible compensation, or it was computed on compensation
above the 401(a)(17) cap.

**A statutory limit is breached.** An employee is over the 402(g) deferral limit
(before or after the age-50 catch-up), over the HSA tier limit (self-only vs
family, plus the age-55 catch-up), over an FSA cap, or over the 415(c) annual
additions ceiling — and the per-period withholding no longer recomputes from the
remaining room over the remaining periods.

**The deposit is late.** Participant money reached the provider outside the DOL
small-plan seven-business-day safe harbor, or the reconciliation rollup calls a
plan tied on a determination nobody recomputed from the evidence underneath it.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 29 controls, writes
`benefit_report.json` and `benefit_report.md`, and exits with the verdict code.
The corpus contains planted defects on purpose, so a non-zero exit is the engine
working.

## The 29 controls

| Family | Count | Asks |
|---|---|---|
| `set_` | 1 | Is the reconciliation file complete, and is the review date readable? |
| `emp_` | 3 | Are the employee ids unique, the entities known, and the DOB, tier and comp fields valid? |
| `pln_` | 2 | Are the plan codes unique and each plan of a known type? |
| `ded_` | 3 | Do the register deductions reference real rows, sit one-per-pair, and reach each provider per employee? |
| `tie_` | 3 | Does each plan's register total tie to every provider, the ledger liability, and the cash transfer? |
| `ent_` | 2 | Do the per-entity subtotals recompute from the register and sum to the consolidated total? |
| `mat_` | 2 | Does the employer match recompute from the formula, and is an above-cap match limited to the cap? |
| `lim_` | 5 | Is every employee inside the 402(g), HSA-tier, FSA and 415(c) ceilings — and who is approaching one? |
| `whh_` | 2 | Does the per-period HSA withholding recompute from the remaining room, and stay under the pro-rated ceiling? |
| `dol_` | 2 | Did participant money remit inside the safe harbor, on or after the pay date? |
| `je_`  | 2 | Does the journal entry balance, and does every benefit clearing account zero out after remittance? |
| `rpt_` | 2 | Does each plan's tie flag recompute, and does the statutory exception watchlist tie the evidence? |

Three are worth calling out.

**The determination recomputes, it is not read back.**
`rpt_tie_status_recomputes` is the control the engine exists for. The
reconciliation report calls a plan *tied*; a tie flag that is not recomputed from
the legs beneath it is an assertion, not a reconciliation. The engine rebuilds the
determination from the register, every provider upload, the ledger liability
credit and the cash transfer, and compares it to the one on file.

**The 401(k) ties to two destinations.** A deferral is remitted to both the
recordkeeper and the custodian, so `ded_matches_provider` and `tie_provider_total`
require the register to tie to *each* provider — a plan that reaches the
recordkeeper but not the custodian is not reconciled.

**Every limit is met at the boundary.** The `lim_` and `whh_` controls compare
with exact `>` and `==`. A deferral a cent over the 402(g) limit is over the
limit; a match computed on uncapped compensation is a match the formula does not
produce; a per-period HSA deduction a cent above the level base was not set from
the room it consumes.

## Two flags, not failures

`lim_deferral_watch` marks a year-to-date deferral inside the file's own watch
band of the 402(g) limit: still under, but on track to breach if the election is
not trimmed for the periods that remain. `rpt_exception_watchlist_ties` proves the
stated exception watchlist is exactly the set the numbers support. Both are
`REVIEW`-severity: worth a human's eyes, not a hard stop.

## Tests

```bash
python -m pytest benefit_engine/tests -q
```

A clean baseline parametrized over the registry, one planted-defect file per named
control, boundary tests on every cent and date threshold, and read-only /
determinism proofs that hash the corpus before and after a full run.

## The baseline is derived, not typed

Only the employees, the plan catalog, the register deductions and the pay/remit
dates are stated. The employer match and the per-period HSA withholding are
computed through the *same* `benefit_engine.reconcile` kernel the engine recomputes
with, and every rollup the engine later checks — the provider uploads, the entity
subtotals, the cash transfers, the journal entry, and the report's tie flags and
exception watchlist — is rebuilt from those base facts through the same helpers the
controls use.

So the relationships the engine tests are the same relationships that produced the
data.

---

🔒 **All data is fictional.** The employers, the employees, the benefit providers,
the plan codes, the compensation and every contribution amount are invented, and
the pay period is set in a fictional future. No employer or client workpaper,
entity, methodology, path or figure is reproduced.
