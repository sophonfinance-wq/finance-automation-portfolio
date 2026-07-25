# Outstanding check aging & escheatment automation

A deterministic, **read-only** control engine for outstanding-check aging and
escheatment — every check an entity has issued and the bank has not yet been
asked to keep, re-derived from the register, aged to a stated as-of date, tied to
the bank reconciliation, and tested against the stale-dating and dormancy
thresholds.

This is the back half of the disbursement story. Whether a payment was approved,
coded and released is somebody else's control. This engine starts after the check
has left the building and asks a narrower question: of everything issued, what has
never cleared, how old is it, and what has to happen to it now?

A check register is a list of promises the bank has not yet been asked to keep.
Three failures hide inside it, and none of them look wrong in a spreadsheet of
check numbers.

**The outstanding set is asserted, not reconciled.** The schedule of outstanding
checks is a filtered view of the register — nothing cleared, no cleared date, not
withdrawn — and the moment somebody maintains it beside the register rather than
deriving it from the register, it drifts. A check that cleared last month stays on
the schedule; a check issued this month never reaches it; and the bank
reconciliation's outstanding line ties to the schedule instead of to the evidence.

**A withdrawn check keeps living.** A voided, zero-dollar or stop-payment check
still occupies a row. If the void never nets the amount to zero, or the check is
still counted as outstanding, the reconciliation carries an obligation that was
cancelled — and that cancelled obligation can age all the way through the dormancy
period and be escheated to a state.

**The clock runs and nobody hears it.** Past the stale-dating threshold the bank
may refuse the item and somebody has to chase, re-issue or re-void it. Past the
dormancy period it stops being the entity's money at all: it is unclaimed property
owed to the escheat jurisdiction of the account it was drawn on. Both are pure
date arithmetic, and both are missed because the register looks identical the day
before and the day after.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 20 controls, writes
`checkage_report.json` and `checkage_report.md`, and exits with the verdict code.
The corpus contains planted defects on purpose, so a non-zero exit is the engine
working.

## The 20 controls

| Family | Count | Asks |
|---|---|---|
| `set_`   | 1 | Is the aging file complete, and is the as-of date readable? |
| `acct_`  | 2 | Are the bank account ids unique, and does each declare the escheat jurisdiction it reports to? |
| `chk_`   | 7 | Is every check row complete, uniquely numbered within its account, drawn on a real account, typed, dated on or before the as-of date, paired on its clearing, and cleared for the amount it was issued for? |
| `void_`  | 3 | Are the withdrawn checks classified, off the outstanding schedule, and netted to zero? |
| `age_`   | 3 | Does the outstanding set re-derive from the register, does each item's age and band re-derive from its check date, and is every stale-dated item marked for follow-up? |
| `esc_`   | 2 | Is the escheatment schedule exactly the items past dormancy, each reported to its account's jurisdiction? |
| `rpt_`   | 2 | Does the reconciliation's outstanding-checks line tie the evidence, and do the aging subtotals tie the bands? |

Four are worth calling out.

**The outstanding set re-derives, it is not read back.**
`age_outstanding_set_recomputes` is the control the engine exists for. The
schedule is a *filtered view* of the register, and a view that is maintained
rather than derived drifts. The engine rebuilds the set — nothing cleared, no
cleared date, not withdrawn — and compares it key by key and amount by amount.

**The reconciliation is tied to the register, not to the schedule.**
`rpt_outstanding_total_ties` deliberately re-derives from the check register
rather than summing the stated schedule. Tying the reconciliation to the schedule
proves only that two documents agree; a schedule and a reconciliation that drifted
together would still tie. This one breaks.

**The check number is only half the identity.** Two disbursement accounts run
their own number series, and both baseline accounts open at the same number.
`chk_number_unique_per_account` is therefore scoped to the account: a control that
keyed on the number alone would call an honest register duplicated, and one that
never checked at all would let a single number carry two obligations.

**Both halves of a clearing, or neither.** The outstanding test reads a cleared
amount of exactly zero *and* an absent cleared date, so a row carrying one without
the other is the single shape that makes the test ambiguous.
`chk_cleared_pairing` owns it: an amount with no date is a clearing nobody dated,
and a date with no amount is an item the schedule would report as outstanding
forever.

## Two thresholds, two responses

Stale-dating and dormancy are both one day wide and they mean different things.

`age_stale_dated_flagged` marks every outstanding item past the file's own
stale-dating threshold — 180 days in the shipped corpus — and is `REVIEW`
severity, because the item is still a real obligation and what it needs is a
human: chase the payee, re-issue, or re-void. `esc_set_recomputes` is `FAIL`
severity, because past the dormancy period the item is no longer the entity's
money and the schedule that says so is a filing obligation, not a to-do.

Both thresholds are crossed *strictly*: an item sitting exactly on the threshold
day has not passed it. `esc_jurisdiction_assigned` then proves each escheatable
item names the jurisdiction its own account declares, so an item is never remitted
to a jurisdiction owed nothing while the one that is owed it goes unfiled.

## Tests

```bash
python -m pytest checkage_engine/tests -q
```

A clean baseline parametrized over the registry, one planted-defect file per named
control, boundary tests on every cent and every day threshold, and read-only /
determinism proofs that hash the corpus before and after a full run — including one
that proves no age in the corpus moves because a day passed on the build machine.

## The baseline is derived, not typed

Only the bank accounts, the check register and the void register are stated. The
generator computes everything the engine later checks as a re-derivation — the
outstanding schedule with its ages, bands and follow-up markers, the escheatment
schedule, the reconciliation's outstanding line and aging subtotals — through the
*same* aging kernel the engine recomputes with.

So the relationships the engine tests are the same relationships that produced the
data.

## What this engine will not do

It never voids, never re-issues, never stops a payment, never escheats, never pays
and never writes to a source artifact. It reads, re-derives and reports. Every age
is measured against the `as_of` date carried in the file, never the system clock.

---

🔒 **All data is fictional.** The entities, the bank accounts, the payees, the
check numbers, the amounts, the check dates and the escheat jurisdictions are
invented, and the reporting period is set in a fictional future. No employer or
client workpaper, entity, methodology, path or figure is reproduced.
