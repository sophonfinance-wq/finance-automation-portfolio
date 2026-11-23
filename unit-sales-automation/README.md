# Unit sales & commission tie-out

A deterministic, **read-only** control engine for a residential for-sale
project's sales administration — every unit on the Matrix proved, row by row, to
carry a revenue per square foot, a net proceeds and a total commission that
re-derive from the prices beside them, a commission split that sums to the total
it divides, and a closing that reconciles to the Sold/Close tab.

A for-sale project is administered out of one workbook, instantiated from the
same template on every project. The Matrix tab carries every unit: plan, plan
square footage, list price, sales price, concession, revenue per square foot,
closing costs and total commission. The Sold/Close tab logs the offer date, the
actual date sold, the closing date and whether proof of closing came back. The
Commission Log splits each unit's total commission across the named selling
agents who earned it.

Nothing here posts a journal entry, releases a commission payment or files a
closing statement. Three failures hide inside the workbook, and none of them look
wrong on the tab.

**A derived column stops deriving.** Revenue per square foot, net proceeds and
total commission are formulas until somebody types over one of them for a single
unit. From then on the column is a mixture of computed and typed figures that no
longer follows from the prices beside it, and the mixture is invisible in a
printed tab.

**The commission splits stop adding up.** The Commission Log pays named agents,
and the sum of the splits on a unit is meant to be the total commission the
Matrix authorised. A split edited after the fact, or an agent added without
reducing another, leaves the log paying an amount no row ever approved.

**The tabs stop reconciling.** A unit is marked Sold and never reaches the
Sold/Close tab; a closing is logged with the sale date before the offer date; the
rollup that goes upstairs counts a project the Matrix does not support.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 21 controls, writes
`sales_report.json` and `sales_report.md`, and exits with the verdict code. The
corpus contains planted defects on purpose, so a non-zero exit is the engine
working.

## The 21 controls

| Family | Count | Asks |
|---|---|---|
| `set_`   | 1 | Is the sales file complete, and is the review date readable? |
| `plan_`  | 2 | Are the plan codes unique, and does every plan carry a usable square footage? |
| `unit_`  | 4 | Is every Matrix row complete, uniquely identified, on a declared plan and in a known status? |
| `price_` | 4 | Do revenue per square foot and net proceeds re-derive, does the concession sit inside the price, and was the discount inside the approved band? |
| `comm_`  | 4 | Is the channel rate scheduled, does the total commission re-derive, do the agent splits sum to it, and is every payee registered? |
| `close_` | 3 | Do sold units reconcile one-to-one to the Sold/Close tab, in offer-sale-closing order, with proof on file? |
| `rpt_`   | 3 | Do the sold count, the revenue totals and the commission total recompute from the Matrix? |

Three are worth calling out.

**The splits tie the row that authorised them.** `comm_splits_tie` is the control
the engine exists for. The Commission Log is what names an agent and an amount;
the Matrix row is what authorised the total. Compared with exact `==` in integer
cents — a cent of drift is a cent paid to nobody or a cent paid twice, and it
recurs on every unit the template produced. The three-way split on a unit is
allocated by the largest-remainder method, so the residual cent lands on one
named agent rather than disappearing into the rounding.

**The derived columns are recomputed, not read back.**
`price_rev_per_sqft_recomputes`, `price_net_proceeds_recomputes` and
`comm_total_recomputes` rebuild each figure from the base prices — sales price
over plan area, price less concession less closing costs, channel rate on sales
price — and compare. Truncation is the contract in both directions: revenue per
square foot floors, and the commission rate is applied with truncating
basis-point arithmetic, so a figure derived here can be compared with exact `==`
to the figure on the tab.

**The reconciliation runs both ways.** `close_sold_reconciles` reports a unit
marked Sold with no closing row *and* a closing row for a unit the Matrix does not
call Sold. The second direction is the harder one to notice, and it is the one
that leaves a settled sale out of the period.

## The band and the proof are flags, not failures

`price_discount_to_list` marks a sold unit discounted past the file's own
`max_discount_bps`: the price was struck and the sale is real, but the discount
was outside the sales office's own authority and wants a signature behind it.
`close_proof_received` marks a closing whose date has arrived without its proof of
closing on file — the sale closed, and what is missing is the evidence of it.
Both are `REVIEW`-severity: worth a human's eyes, not a hard stop.

## Tests

```bash
python -m pytest sales_engine/tests -q
```

A clean baseline parametrized over the registry, one planted-defect file per
named control, boundary tests on every cent, day and basis point, and read-only /
determinism proofs that hash the corpus before and after a full run.

## The Matrix is derived, not typed

Only the plans, the commission schedule, the unit base prices, the Sold/Close
dates and the agent split weights are stated. The generator computes everything
the engine later checks as a derived figure — revenue per square foot, net
proceeds, total commission, each agent's split in cents, and the three rollup
totals — through the *same* tie-out kernel the engine recomputes with.

So the relationships the engine tests are the same relationships that produced the
data.

---

🔒 **All data is fictional.** The developers, the projects, the plans, the unit
numbers, the selling agents and every price, commission and closing date are
invented, and the sales period is set in a fictional future. No employer or client
workpaper, entity, methodology, path or figure is reproduced.
