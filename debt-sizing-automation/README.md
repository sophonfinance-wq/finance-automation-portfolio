# Debt term-sheet sizing automation

A deterministic, **read-only** control engine for a borrower's debt term-sheet
sizing — every active deal proved, deal by deal, to be sized within its advance
rate, to carry an all-in rate and fees that re-derive from their own inputs, to
reconcile its term and extensions to the stated maturity, and to foot into a
portfolio rollup that ties across the deals.

This is the sizing half of the debt story. Whether a draw is actually advanced
against a budget line is a *funding* question owned by a separate engine — and
that engine explicitly declines to re-foot a term sheet. This engine is that
tie-out, run before anything closes.

A term sheet is a one-page summary re-keyed from a longer credit memo, and it
drifts in ways nobody re-foots. Three failures hide inside that, and none of them
look wrong in a tidy side-by-side grid.

**The loan is sized over the advance rate.** The stated max loan amount creeps a
cent or a million above max loan-to-cost times the cost basis, and the
over-advance rides in the workbook while the cap sits in a cell nobody
recomputed.

**A build-up figure is re-keyed, not re-derived.** The all-in rate is typed as
index plus spread when the floor actually governs, or a fee is struck on the
wrong base — commitment where it should be drawn, facility where it should be
undrawn — so the fee is the wrong number against the right rate.

**The rollup drifts from the deals.** The portfolio total commitment, the total
fees, or the count of active deals is maintained beside the side-by-side rather
than footed from it, and it drifts the first time a deal moves and nobody re-adds
the column.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 21 controls, writes
`sizing_report.json` and `sizing_report.md`, and exits with the verdict code. The
corpus contains planted defects on purpose, so a non-zero exit is the engine
working.

## The 21 controls

| Family | Count | Asks |
|---|---|---|
| `set_`  | 1 | Is the sizing file complete, and is the pricing date readable? |
| `deal_` | 5 | Are the deal ids unique, and are the loan type, index and recourse on their allowed lists, with a cost basis and advance rate declared? |
| `size_` | 3 | Is the loan within the advance rate, the draw within the commitment, and the maturity reconciled to base term plus extensions? |
| `rate_` | 2 | Does every deal have a build-up, and does its all-in rate recompute as the greater of index-plus-spread and the floor? |
| `fee_`  | 4 | Is every fee line well-typed, struck on a known base, attributable to a deal, and does its amount recompute from base and rate? |
| `exp_`  | 2 | Is the term sheet still live at the pricing date, and what is due to expire inside the lead window? |
| `rpt_`  | 4 | Do the deal count, total commitment and total fees foot the deals, and does the expiry watchlist tie them? |

Three are worth calling out.

**The all-in rate recomputes, it is not read back.** `rate_all_in_recomputes`
rebuilds every deal's all-in rate as `max(index + spread, floor)` from its
components and compares it to the one on file. A rate typed as index-plus-spread
where the floor governs — or the other way round — is caught at the basis point.

**Every fee is struck on its correct base.** `fee_amount_recomputes` re-derives
each fee as the truncating basis-point product of its rate and its base —
commitment, drawn, undrawn or facility — so a fee copied across from another line
or struck on the wrong base is caught with exact `==`.

**The loan is capped at the advance rate.** `size_ltc_not_exceeded` recomputes
max loan-to-cost times the cost basis and compares with exact `<=`. A loan a cent
above the cap is a loan over the advance rate, and an over-advance is the plainest
sizing failure there is.

## The lead window is a flag, not a failure

`exp_termsheet_lead_time` marks a term sheet expiring inside the file's own
lead-time window: the commitment is still live, but the deal needs to close before
it lapses. `rpt_expiry_watchlist_ties` proves the stated watchlist is exactly the
set of term sheets actually due — so the close chase is sent to the right deal and
no lapse is missed. Both are `REVIEW`-severity: worth a human's eyes, not a hard
stop.

## Tests

```bash
python -m pytest sizing_engine/tests -q
```

A clean baseline parametrized over the registry, one planted-defect file per named
control, boundary tests on every cent, basis point, month and date threshold, and
read-only / determinism proofs that hash the corpus before and after a full run.

## The baseline is derived, not typed

Only the deals, the rate build-ups and the fee lines are stated. The generator
computes everything the engine later checks as a rollup — each all-in rate, each
fee amount, the expiry watchlist, and the portfolio count and totals — through the
*same* term-sheet kernel the engine recomputes with.

So the relationships the engine tests are the same relationships that produced the
data.

---

🔒 **All data is fictional.** The borrowers, the projects, the reference indices,
the cost bases, the loan amounts, the fee rates and every term-sheet date are
invented, and the workbook period is set in a fictional future. No employer or
client workpaper, entity, methodology, path or figure is reproduced.
