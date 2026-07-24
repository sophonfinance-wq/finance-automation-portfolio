# Depreciation & prepaid amortization automation

A deterministic, **read-only** control engine for an entity's fixed-asset
depreciation register and prepaid amortization schedule — every straight-line
charge re-derived from cost, life and convention; every prepaid waterfall figure
re-derived from its stated amortization window; the accumulated-depreciation and
prepaid balances rolled forward; and the register totals tied back to the GL
control accounts and the posted monthly recurring journal entry.

The engine owns the subledgers, not their neighbours. The JE-posting cadence of
the close, debt and loan amortization, and the prepaid-insurance entity
allocation each belong to a separate engine — this engine is the register
underneath them.

A depreciation register is a spreadsheet of tiny derived numbers, and it drifts
in ways nobody watches. Three failures hide inside that, and none of them look
wrong in a register that still foots.

**The derivation drifts.** A useful life is keyed off the class table, a monthly
charge is overtyped, an asset keeps depreciating past its end date or starts
before it enters service, and every downstream month inherits the error.

**The roll-forward breaks.** Accumulated depreciation is a running balance —
opening plus the month's charge less what a disposal removed equals closing —
and a balance maintained by hand drifts the first time a row is edited and
nobody re-adds the column. Prepaid balances break the same way.

**The totals stop tying.** The register says one number, the GL control account
says another, and the recurring JE posts a third. Each looks plausible alone;
the tie-out is the only thing that can say they are the same number.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 30 controls, writes
`dep_report.json` and `dep_report.md`, and exits with the verdict code. The
corpus contains planted defects on purpose, so a non-zero exit is the engine
working.

## The 30 controls

| Family | Count | Asks |
|---|---|---|
| `set_`  | 1 | Is the close file complete, and is the close month readable? |
| `cap_`  | 2 | Does every expense-log item sit on the correct side of the capitalization threshold, and does every capitalized asset meet it? |
| `life_` | 3 | Is every asset's class in the life table, is its life the class's (or its lease term), and is everything straight-line? |
| `sl_`   | 2 | Does the monthly charge re-derive as cost over life, and is the close month's expense exactly the schedule's charge? |
| `date_` | 3 | Is the end-of-depreciation month in-service plus life, is everything past it fully accumulated at zero NBV, and does nothing depreciate before service? |
| `nbv_`  | 3 | Is months-used capped at the life, does the accumulated balance re-derive, and does NBV equal cost less accumulated inside [0, cost]? |
| `roll_` | 3 | Do the accumulated and prepaid roll-forwards close on themselves, and do they foot the registers they summarise? |
| `pre_`  | 5 | Is every amortization window usable, and do the monthly charge, the close-month expense (catch-up included), and both balances re-derive — with a watch on windows about to end? |
| `disp_` | 3 | Is every disposed asset off the register, is each write-off exactly the NBV removed, and is anything sitting long past its end date flagged for disposal review? |
| `gl_`   | 3 | Do the cost, accumulated-depreciation and prepaid control accounts tie the register footings? |
| `je_`   | 2 | Do the posted recurring-JE depreciation and amortization lines equal the register totals? |

Three are worth calling out.

**The remainder lands in the final month.** The monthly charge is
`cost // life` in integer cents, and the final month of the schedule absorbs
whatever is left, so the schedule sums back to cost exactly — no penny drifts,
ever. `sl_expense_rederives` checks the close month's charge against exactly
that schedule: base charge mid-life, the remainder in the final month, zero
before service and zero after.

**The first booked month takes the catch-up.** A prepaid item set up after its
window opened books the whole scheduled cumulative in its first month — two
periods late means twice the monthly charge, at once. The clean baseline itself
carries one of these, so the catch-up path is exercised by data that passes.

**The register total is the only defensible amount.** `je_depreciation_ties`
and `je_prepaid_amort_ties` compare the posted recurring JE to the register
footings with exact `==`. The JE is posted *from* the schedule; an amount that
differs is a month of expense the books took on a number nobody derived.

## The watches are flags, not failures

`disp_fully_depreciated_watch` marks an asset sitting more than the
disposal-review band past its end month — arithmetically clean, but almost
certainly gone from the building. `pre_window_ending_watch` marks a prepaid
window ending inside the look-ahead — the schedule is fine, but the underlying
term needs a renewal decision. Both are `REVIEW`-severity: worth a human's eyes,
not a hard stop. Both bands come from the file's own figures, never a clock.

## Tests

```bash
python -m pytest depreciation_engine/tests -q
```

A clean baseline parametrized over the registry, one planted-defect file per
named control, boundary tests on every cent, month and threshold edge, and
read-only / determinism proofs that hash the corpus before and after a full run.

## The baseline is derived, not typed

Only the base facts are stated: each asset's cost, class, in-service month and
life; each prepaid item's additions and window; the policy threshold; the
disposal facts. The generator computes everything the engine later re-checks —
every derived register column, both roll-forwards, the GL balances and the
recurring JE — through the *same* schedule kernel the engine recomputes with.

So the relationships the engine tests are the same relationships that produced
the data.

---

🔒 **All data is fictional.** The entities, the projects, the vendors, the asset
descriptions, the account numbers and every cost, life, window and balance are
invented, and the close month is set in a fictional future. No employer or
client workpaper, entity, methodology, path or figure is reproduced.
