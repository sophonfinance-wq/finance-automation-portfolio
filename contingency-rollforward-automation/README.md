# Contingency rollforward & adequacy

A deterministic, **read-only** control engine for the contingency status block a
developer restates in every periodic project report — construction contingency and
project contingency rolled forward, project by project, from the prior period's
balance through the draws allocated against them to the balance remaining, and
called adequate only when what is left covers the projected potential use.

Every active project carries two contingency buckets. Each period the block is
restated by hand: the prior balance, the amount allocated this period, the amount
allocated to date, the balance remaining, the projected potential use, and a word
that says whether the remaining balance is adequate. Beside the block sits the
draw detail that the allocated figure is meant to summarise, the project budget
that funded the bucket in the first place, and a portfolio rollup that adds every
block together for the report that goes upstairs.

Nothing here forecasts. Whether the projected potential use is a sound estimate is
a judgement no engine can make. Three failures hide inside the block, and none of
them look wrong on a printed tab.

**The rollforward stops rolling.** Prior balance less allocated this period is the
balance remaining, until somebody types over the current figure for a single
project. From then on the block is a mixture of rolled and typed balances that no
longer follows from the period before it, and the mixture survives every period
after.

**The allocated total stops matching the draws.** The allocated-this-period figure
is maintained beside the draw detail rather than footed from it. A draw never
reaches the total, or a single draw is written for more than the balance it draws
against, and the bucket goes overdrawn in a column nobody re-added.

**The adequacy word goes stale.** Adequate is a comparison, not a label. It gets
carried forward from a period in which it was true while the projected potential
use climbs past the balance behind it, and the block keeps saying adequate.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 22 controls, writes
`contingency_report.json` and `contingency_report.md`, and exits with the verdict
code. The corpus contains planted defects on purpose, so a non-zero exit is the
engine working.

## The 22 controls

| Family | Count | Asks |
|---|---|---|
| `set_` | 1 | Is the period file complete, and is the reporting period readable? |
| `prj_` | 3 | Are the project ids unique, is every status one the block understands, and does every project carry a budget? |
| `alc_` | 6 | Is every draw complete, uniquely identified, on a declared project, in a known bucket, inside the period and positive? |
| `ctg_` | 6 | Is the block complete, do both rollforwards re-derive, does the allocated total foot to the draw detail, does the bucket reconcile to the budget that funded it, and is anything overdrawn? |
| `adq_` | 3 | Is the projection non-negative, does the adequacy call rebuild from the two amounts that define it, and what sits inside the watch band? |
| `rpt_` | 3 | Does the portfolio rollup foot to the blocks, and do the inadequate count and the exposure watchlist tie? |

Three are worth calling out.

**The rollforward is recomputed, not read back.**
`ctg_current_rolls_forward` and `ctg_to_date_rolls_forward` rebuild the balance
remaining and the allocated-to-date from the prior period's figures and the draws
booked against them, then compare with exact `==` in integer cents. Both
directions matter: a period that rolls forward correctly but reports the wrong
to-date total has a bucket whose history no longer adds up, and the discrepancy
compounds every period after.

**The adequacy word is rebuilt from the two amounts underneath it.**
`adq_flag_recomputes` is the control the engine exists for. Adequate means the
balance remaining covers the projected potential use. The engine strikes that
comparison itself and checks the word against it, so a label carried forward from
a period in which it was true cannot survive the period in which it stopped being
true.

**The draw detail is footed both ways.** `ctg_allocated_ties_line_items` adds the
draws and compares to the allocated total, and `ctg_no_overdraw` tests each single
draw against the balance it draws against. The second is the one that catches a
bucket drawn past empty by one large draw while the period total still looks
reasonable.

## The watch band and the watchlist are flags, not failures

`adq_headroom_watch` marks a bucket whose remaining balance still covers the
projection but sits inside the file's own watch band: the block is arithmetically
correct and the contingency is thin, which is a conversation rather than an error.
`rpt_watchlist_ties` marks a disagreement between the exposure watchlist and the
blocks behind it. Both are `REVIEW`-severity: worth a human's eyes, not a hard
stop.

## Tests

```bash
python -m pytest contingency_engine/tests -q
```

A clean baseline parametrized over the registry, one planted-defect file per named
control, boundary tests on every cent and day, and read-only / determinism proofs
that hash the corpus before and after a full run.

## The block is derived, not typed

Only the projects, the budgets, the prior-period balances, the individual draws
and the projections are stated. The generator computes everything the engine later
checks as a derived figure — both rollforwards, the allocated totals, the adequacy
call on every bucket and the portfolio rollup — through the *same* rollforward
kernel the engine recomputes with.

So the relationships the engine tests are the same relationships that produced the
data.

---

🔒 **All data is fictional.** The developers, the projects, the budgets, the draw
numbers and every balance, projection and reporting date are invented, and the
reporting period is set in a fictional future. No employer or client workpaper,
entity, methodology, path or figure is reproduced.
