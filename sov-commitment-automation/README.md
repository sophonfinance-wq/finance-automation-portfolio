# Subcontract SOV & change-order automation

A deterministic, **read-only** control engine for a residential developer's
subcontract commitment billing — every schedule of values (SOV) proved to foot
to its original contract, every revised commitment re-derived as original plus
net *approved* change orders, every pay-application column recomputed from the
columns beneath it, and every conditional lien release tied to the certified
payment due.

The neighbouring questions stay with their engines. Which lender draw funds a
pay app is a funding question owned by the draw engine; whether a lien waiver's
statutory form is right is a document-compliance question owned by the waiver
engine. This engine owns the arithmetic chain those two stand on.

A pay application is a page of derived columns, and every one of them is typed
by hand somewhere. Three failures hide inside that, and none of them look wrong
on the page.

**The contract drifts from its paper.** The revised commitment stops equalling
original plus net approved change orders — a pending CO counted early, a
soft-cost CO booked as a brand-new commitment instead of a `#-N` amendment —
and the committed-cost roster no longer states what was actually signed.

**The billing chain breaks a line at a time.** A line's completed-to-date stops
equalling previously-billed plus this period, a line quietly bills past its
scheduled value, or this month's "previously billed" no longer equals last
month's "total billed" — and the overbilling compounds under a column that
still foots.

**The money math is asserted, not derived.** Retention stops being the contract
rate on the billing, the sales tax stops being the rate on the taxable request,
the payment due stops being request minus retention plus tax — and the
conditional release is signed for an amount nobody recomputed.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 29 controls, writes
`sov_report.json` and `sov_report.md`, and exits with the verdict code. The
corpus contains planted defects on purpose, so a non-zero exit is the engine
working.

## The 29 controls

| Family | Count | Asks |
|---|---|---|
| `set_`  | 1 | Is the billing file complete, one of each artifact? |
| `cmt_`  | 4 | Are the commitment ids unique and the terms readable, does the committed-cost roster tie the register, and does every revised contract equal original + net approved COs? |
| `co_`   | 5 | Does every change order name a registered commitment, number sequentially as `#-N`, carry a known status — and is no commitment born from a change order or misnamed off the project-vendor-count pattern? |
| `sov_`  | 2 | Are the SOV lines unique and attributable, and does each commitment's schedule foot exactly to its original contract? |
| `line_` | 5 | Does every pay app bill scheduled lines, does each line's completed re-derive as D+E and its percent as floored basis points, do the headers foot, and is the request exactly completed minus previously billed? |
| `cap_`  | 2 | Is every line billed within its scheduled value, and does its balance to finish re-derive exactly? |
| `ret_`  | 2 | Is the retention rate on the standard 5% / 10% menu, and is the retention held exactly the contract rate on the request? |
| `tax_`  | 2 | Do the sales tax and the payment due including tax re-derive at the contract rate? |
| `roll_` | 2 | Does each app open at the prior app's close (the first at zero), and are the apps numbered 1..N with periods that advance? |
| `port_` | 2 | Do the roster's Total columns foot to their rows, and does revised total = original total + changes total? |
| `lien_` | 2 | Does every pay app carry exactly one conditional release, signed for exactly the certified payment due? |

Three are worth calling out.

**Only an approved change order moves the contract.**
`cmt_revised_rederives` recomputes every commitment's net change from the
change-order log through the shared kernel — approved orders only — and holds
both the stated net and the stated revised to it. A pending order re-priced ten
times moves nothing; the same order approved moves everything, exactly once.

**The cap is per line, because overbilling foots.** A line billed past its
scheduled value hides perfectly inside an app whose totals still add up, so
`cap_not_overbilled` tests every line with exact `<=`: completed to the cent of
the scheduled value is fully billed, and a cent past it is overbilled.

**The roll-forward is the chain that makes twelve certificates one billing.**
`roll_previously_ties_prior` proves each app's "previously billed" equals the
prior app's "total completed" — and that the first app opens at zero — while
`roll_apps_sequential` proves the sequence 1..N has no gap, no repeat, and
periods that advance with the numbering.

## Two flags, not failures

`line_percent_rederives` and `ret_rate_known` are `REVIEW`-severity. The money
columns are checked by the hard equalities, so a stated percent that drifts
steers the reviewer's eye, not the cash — and a retention rate off the 5% / 10%
menu is a contract term to confirm against the contract, not a broken figure
(the arithmetic control holds the retention to whatever rate is stated either
way). Worth a human's eyes; not a hard stop.

## Tests

```bash
python -m pytest sov_engine/tests -q
```

A clean baseline parametrized over the registry, one planted-defect file per
named control, boundary tests on every cent and sequence threshold, and
read-only / determinism proofs that hash the corpus before and after a full run.

## The baseline is derived, not typed

Only the commitments, the change orders, the SOV lines and each pay app's
work-this-period figures are stated. The generator computes everything the
engine later re-derives — previously billed, completed, percents, balances,
headers, the request / retention / tax / payment-due chain, the committed-cost
roster and the conditional releases — through the *same* billing kernel the
engine recomputes with.

So the relationships the engine tests are the same relationships that produced
the data.

---

🔒 **All data is fictional.** The developers, the projects, the vendors, the
escrow agent, the jurisdiction and its tax rate, every contract amount and every
billing period are invented, and the periods sit in a fictional future. No
employer or client workpaper, entity, methodology, path or figure is reproduced.
