# Earnest-money deposit trust automation

A deterministic, **read-only** control engine for a residential developer's
pre-close earnest-money deposit trust — the internal deposit ledger, the escrow
agent's record and the construction-loan paydown register proved, unit by unit,
to describe the same money, to the cent.

Before a for-sale unit closes, its buyer's earnest money is receipted into
escrow, split from any upgrade deposit, and swept to the construction loan as a
principal paydown. If the buyer cancels, the deposit decomposes into a retained
termination fee, a refund, and a reversal of the earlier paydown. The
fully-closed unit's settlement-statement tie-out belongs to the close-of-escrow
engine, and the upgrade deposit's selection/pricing story to the buyer-upgrades
engine — here the upgrade column is only the segregation counterpart that must
sum with earnest money to the cash that moved.

Three failures hide inside that, and none of them look wrong on any single page.

**The agent's record and the books disagree.** The escrow agent shows a deposit
our ledger never booked (a completeness gap), or our ledger carries pre-close
money the agent no longer holds (an over-release). Each side is internally
consistent; only the per-unit tie-out sees the break.

**The sweep drifts.** A deposit marked posted has no principal paydown behind
it, a deposit still queued need-to-post was already swept — so the next posting
run applies the same money twice — or a cancelled buyer's earlier paydown was
never reversed, leaving the loan paid down with money that was refunded.

**The rollup drifts from the evidence.** The reconciliation summary carries a
variance column, exception flags, posting-bucket totals and trust-bank balances
that nobody recomputed from the deposits underneath them.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 27 controls, writes
`emd_report.json` and `emd_report.md`, and exits with the verdict code. The
corpus contains planted defects on purpose, so a non-zero exit is the engine
working.

## The 27 controls

| Family | Count | Asks |
|---|---|---|
| `set_` | 1 | Is the deposit file complete, and is the ledger cut-off date readable? |
| `led_` | 2 | Are the deposit ids unique, and does every ledger row carry the fields the reconciliation reads? |
| `seg_` | 2 | Does every row's cash amount split exactly into upgrade + earnest money, over non-negative components? |
| `tie_` | 4 | Do the ledger, the escrow agent and the loan paydowns tie three ways per unit — at zero variance, complete in both directions? |
| `swp_` | 3 | Does every swept deposit have exactly one paydown, every paydown a receipt behind it, and every queued deposit none at all? |
| `cxl_` | 4 | Does every cancellation join a cancelled deposit, split exactly into fee + refund, reverse its sweep, and book the fee to forfeitures? |
| `sts_` | 2 | Is every deposit in exactly one known bucket, and does the agent's open-escrow statement carry only pre-close units? |
| `bnk_` | 2 | Do the segregated upgrade-deposit bank balance and forfeiture income recompute from the ledger and the cancellation register? |
| `net_` | 3 | Does each net sale price recompute as price plus a non-positive concession, booked against revenue and never a construction cost? |
| `rpt_` | 4 | Do the summary's unit variances, exception flags, total variance and bucket totals recompute from the evidence? |

Three are worth calling out.

**Zero is the only passing value.** `tie_agent_variance_zero` is the control
the engine exists for. Variance is agent-minus-books, per unit, in integer
cents: a positive variance is buyer money the agent holds that the books never
captured, a negative one is a release the books claim that the agent never
recorded. There is no tolerance band — a variance of one cent is a variance.

**The sweep is tied from both directions.** `swp_posted_has_paydown` proves a
deposit marked posted has exactly one principal paydown behind it, and
`swp_need_to_post_not_swept` proves the queue is honest — a deposit still
marked need-to-post with a paydown already booked is the same money about to
be swept twice. `tie_loan_leg_zero` then nets the whole register per unit
against the ledger's swept earnest money, with cancellations reversing to zero.

**The forfeiture split accounts for every cent.** On cancellation,
`cxl_split_sums` proves retained fee + refund equals the earnest money exactly,
`cxl_reversal_matches_sweep` proves the earlier loan paydown was unwound once
and exactly, and `cxl_fee_account` proves the fee landed in forfeiture income —
never a construction cost code, where it would overstate revenue and cost by
the same amount and leave the margin looking right.

## The stale escrow is a flag, not a failure

`sts_closed_excluded_from_agent` marks a unit whose deposits have all closed or
cancelled but that still shows on the agent's open-escrow statement: money is
not misstated, but the escrow is stale and belongs to the close-of-escrow
handoff. `rpt_exception_flags_tie` proves the summary's flag column — the
reviewer's work queue — matches the recomputed variances. Both are
`REVIEW`-severity: worth a human's eyes, not a hard stop.

## Tests

```bash
python -m pytest deposit_engine/tests -q
```

A clean baseline parametrized over the registry, one planted-defect file per
named control, boundary tests on every cent and membership threshold, and
read-only / determinism proofs that hash the corpus before and after a full run.

## The baseline is derived, not typed

Only the deposit ledger, the agent's statement, the loan register, the
cancellation register and the sales prices are stated. The generator computes
everything the engine later checks as a determination — each unit's variance
and exception flag, the total variance, the posting-bucket totals, the trust
balances and each net sale price — through the *same* reconciliation kernel
the engine recomputes with.

So the relationships the engine tests are the same relationships that produced
the data.

---

🔒 **All data is fictional.** The developers, the projects, the buyers, the
escrow agent, the lender, the units and every amount and date are invented, and
the reporting period is set in a fictional future. No employer or client
workpaper, entity, methodology, path or figure is reproduced.
