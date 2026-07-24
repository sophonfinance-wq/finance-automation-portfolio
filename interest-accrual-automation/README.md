# Interest accrual & loan amortization automation

A deterministic, **read-only** control engine for a lender's interest accrual and
loan amortization — every promissory note proved, note by note, to accrue the
interest its own terms produce, to roll its balance forward without a break, to
hold its maturity, default-rate, prepayment and subordination gates, and to tie
its reciprocal receivable/payable and interest journal out to the schedule
underneath them.

This is the arithmetic proof beneath the debt-service note. Where a financing
cost lands, or how a construction draw is funded, are *separate* engines' jobs.
This engine is the check that the interest a note reports is the interest its
rate, day-count and balance produce.

An amortization schedule is a column of numbers that looks self-evidently right,
and it goes wrong in ways nobody re-adds. Four failures hide inside that, and none
of them look wrong.

**The accrual drifts from the terms.** A period accrues at the wrong rate, on the
wrong balance, or over the wrong day count, and the booked interest is off by an
amount too small to notice against a six-figure balance — until it compounds.

**The roll-forward breaks.** One period's ending balance is not the next period's
beginning; an advance is added but never lands; a payment relieves more than was
owed; the payoff leaves a residual cent instead of settling to zero.

**A gate is missed.** Interest keeps accruing past maturity, the default rate
never steps after an event of default, a note prohibited from prepayment is paid
down early, or a subordinated note is paid ahead of the senior it sits behind.

**The two sides stop reconciling.** The lender's receivable and the borrower's
payable drift apart, interest income no longer equals interest expense, or the
monthly journal no longer ties to the accrual it was meant to record.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 28 controls, writes
`interest_report.json` and `interest_report.md`, and exits with the verdict code.
The corpus contains planted defects on purpose, so a non-zero exit is the engine
working.

## The 28 controls

| Family | Count | Asks |
|---|---|---|
| `set_`   | 1 | Is the loan file complete, and is the review date readable? |
| `note_`  | 4 | Are the note ids unique, the term fields present, the rate/day-count/principal well-formed, and the two sides distinct? |
| `acc_`   | 3 | Does every row carry its key fields, does its day count tie its span, and does its accrued interest re-derive from beginning × rate × days? |
| `rf_`    | 4 | Does every row name a real note, does its ending balance rebuild, is each ending the next beginning, and does the schedule open at the principal? |
| `gate_`  | 4 | Does each period accrue at the right rate, does accrual stop at maturity, is a prepayment-barred note left alone before maturity, and what is due to mature soon? |
| `wf_`    | 3 | Is every payment within the balance owed, does a payoff settle to zero, and is a subordinate left unpaid while its senior is? |
| `recip_` | 2 | Does each note's receivable equal its payable, and its interest income equal its expense — and both the schedule? |
| `gl_`    | 4 | Does the journal balance, does it tie the accrual, is every note on the trial balance, and does every trial-balance account map to a note? |
| `rpt_`   | 3 | Does each note's settled flag and accrued total recompute, do the portfolio counts tie the summary, and does the maturity watchlist tie the evidence? |

Three are worth calling out.

**The accrual re-derives, it is not read back.** `acc_interest_rederives` is the
control the engine exists for. The schedule states an accrued figure, and a figure
that is not recomputed from the terms is an assertion. The engine rebuilds every
period's interest through the shared kernel — `beginning × rate_bps × days / year`,
truncated to the cent — and compares with exact `==`. A cent of drift is a cent
the note over- or under-charged.

**The balance rolls forward, begin to end.** `rf_ending_balance_rederives` rebuilds
each ending from `beginning + advance + accrued − payment`, and `rf_continuity`
proves each ending is the next period's beginning — so a balance cannot be quietly
reset between two periods and carry the error forward untraced.

**The gates are dates and thresholds, not judgement.** Accrual stops *on* the
maturity date, the default rate steps *on* the event date, a payment above the
period's accrued interest reduces principal, and a subordinate may service interest
but not pay principal while its senior is unrepaid. Every one is an equality, a
date gate or a membership test — nothing here is discretionary.

## The maturity window is a flag, not a failure

`gate_maturity_approaching` marks an unsettled note maturing inside the file's own
lead-time window: the note is still current, but the payoff or extension needs to
be arranged before it comes due. `rpt_watchlist_ties` proves the stated watchlist
is exactly the set of notes actually due — so the refinancing chase is sent to the
right place and nothing is missed. Both are `REVIEW`-severity: worth a human's
eyes, not a hard stop.

## Tests

```bash
python -m pytest interest_engine/tests -q
```

A clean baseline parametrized over the registry, one planted-defect file per named
control, boundary tests on every cent and date threshold, and read-only /
determinism proofs that hash the corpus before and after a full run.

## The baseline is derived, not typed

Only the note terms and the schedule *events* — each period's dates, advance and
payment intent — are stated. The generator computes everything the engine later
checks — each accrual and ending balance, each note's settled determination and
accrued total, the reciprocal GL, the interest journal, the maturity watchlist and
the portfolio counts — through the *same* accrual kernel the engine recomputes
with.

So the relationships the engine tests are the same relationships that produced the
data.

---

🔒 **All data is fictional.** The lenders, the borrowers, the notes, the rates, the
balances and every GL account are invented, and the accrual period is set in a
fictional future. No employer or client workpaper, entity, methodology, path or
figure is reproduced.
