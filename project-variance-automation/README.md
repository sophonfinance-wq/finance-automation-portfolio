# Project variance & business-plan compare

A deterministic, **read-only** control engine for the periodic project report a
developer re-issues off every development proforma — the current period restated
against the prior period and against the approved Business Plan baseline, each cost
line broken into Total Budget / Cost to Date / Cost to Complete, and each milestone
date reported Current vs Prior vs Variance against a frozen schedule.

On a fixed calendar every active project's proforma becomes a project report.
Dedicated tabs restate six metrics — gross revenue, net project revenue, total
project expense, project profit, margin on cost and project IRR — in three columns:
what it is now, what it was last period, and what the approved plan said. A
budget-variance tab breaks each cost line into three columns of its own. A milestone
block reports each schedule date against a baseline frozen at the version the
project was approved under, with `+` meaning ahead. A rollup adds every project
together for the committee.

Nothing here underwrites a development. Whether the proforma behind the report is a
good proforma is somebody else's question. Three failures hide inside the grid, and
none of them look wrong on a tidy page.

**A variance column stops deriving.** The variance is a formula until somebody
types over one cell, and from then on it no longer equals the difference of the two
columns it sits between. It is the single most-read number on the page and the one
nobody re-foots.

**Cost to Complete stops being the remainder.** It is maintained beside the budget
rather than struck as Total Budget less Cost to Date. Spending climbs, the
remainder does not move, and an overrun rides in a column nobody re-added.

**The plan column gets re-based.** The Business Plan column is quietly pointed at a
revision nobody approved. Every plan variance gets smaller at once, which is
exactly what makes it hard to see: nothing looks wrong, everything looks better.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 22 controls, writes
`variance_report.json` and `variance_report.md`, and exits with the verdict code.
The corpus contains planted defects on purpose, so a non-zero exit is the engine
working.

## The 22 controls

| Family | Count | Asks |
|---|---|---|
| `set_` | 1 | Is the project report complete, and is the reporting period readable? |
| `prj_` | 3 | Are the project ids unique, is every project type known, and does every project carry both comparatives? |
| `bud_` | 4 | Is every cost line complete, in a known category, on a declared project, and is Cost to Complete the remainder? |
| `eco_` | 4 | Do net revenue, the expense tie to the budget, profit and margin on cost re-derive from their own inputs? |
| `var_` | 4 | Do the comparative columns foot inside themselves, do both variance columns re-foot, and is the plan column the frozen approved plan? |
| `mst_` | 4 | Is every milestone complete, does the prior variance carry the right sign, does the baseline variance re-foot, and what has slipped past tolerance? |
| `rpt_` | 2 | Does the rollup foot across all projects, and does the slippage watchlist tie? |

Three are worth calling out.

**The variance columns are re-struck, not read back.** `var_prior_column_ties` and
`var_plan_column_ties` rebuild each variance cell as the current figure less the
column it is measured to, and compare with exact `==`. The same subtraction serves
money and basis points, so the margin row re-foots by the same rule as the revenue
row, and a cell typed over is caught wherever it sits.

**A comparative that never footed cannot be compared to.**
`var_comparative_columns_foot` is the control that is easy to leave out. The Prior
and Business Plan columns each carry their own gross revenue, deductions and
expense, so each has its own net revenue, profit and margin that must re-derive
from them. A variance measured against a column that does not foot inside itself is
measuring nothing, and the current-period controls would never notice.

**The sign convention is a definition, enforced.**
`mst_variance_sign_convention` holds that a schedule variance is `+` when the
project is ahead, so it is `prior - current` in days and never the other way round.
A definition that lives in two places eventually disagrees with itself, so it lives
once in `variance.py` and both the generator and the control import it. A flipped
sign turns two weeks of slippage into two weeks of progress on the page a committee
reads.

## The tolerance and the watchlist are flags, not failures

`mst_slippage_lead_time` marks a milestone behind the frozen baseline past the
file's own `slippage_tolerance_days`: the report is arithmetically correct and the
date has simply moved. Behind by *exactly* the tolerance is **at** it and not yet on
the watchlist. Only milestones still ahead of the report date are raised — a date
already passed is history, and the chase is for the ones in front of the team.
`rpt_slippage_watchlist_ties` marks a disagreement between the stated watchlist and
the schedule behind it. Both are `REVIEW`-severity: worth a human's eyes, not a hard
stop.

## Tests

```bash
python -m pytest variance_engine/tests -q
```

A clean baseline parametrized over the registry, one planted-defect file per named
control, boundary tests on every cent, basis point and day, and read-only /
determinism proofs that hash the corpus before and after a full run. The corpus puts
a real row on each edge that matters: one milestone is behind the baseline by exactly
the tolerance, and two are ahead by exactly the same span in the other direction.

## The grid is derived, not typed

Only the projects, the cost-line budgets and spend, the base revenue and expense
figures, the plan baseline and the schedule dates are stated. The generator computes
everything the engine later checks as a derived figure — every Cost to Complete,
net revenue, profit, margin, both variance columns on all six metrics, every
milestone variance in days and the whole rollup — through the *same* restatement
kernel the engine recomputes with.

So the relationships the engine tests are the same relationships that produced the
data.

---

🔒 **All data is fictional.** The developers, the projects, the jurisdictions, the
cost lines, the plan versions and every revenue, expense, margin and milestone date
are invented, and the reporting period is set in a fictional future. No employer or
client workpaper, entity, methodology, path or figure is reproduced.
