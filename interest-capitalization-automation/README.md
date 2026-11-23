# Interest capitalization automation

A deterministic, **read-only** control engine for a real-estate developer's
Section 263A avoided-cost interest-capitalization schedule — every active
development project proved, quarter by quarter, to capitalize the interest the
method requires into project basis, foot to its annual totals, and tie the
year-over-year comparison.

A developer that builds designated property with borrowed money may not deduct
all of the interest it pays. Under the avoided-cost method of IRC section
263A(f), the interest that production could have avoided — the period rate
applied to the accumulated production expenditures tied up in a project — must be
**capitalized** into the property's basis rather than deducted in the year paid.
The rest is deducted. The annual schedule lays every active project across a grid
of calendar quarter-ends, pulls each project's interest expense by quarter, and
computes that split. It is rebuilt every fiscal year, and it goes stale in ways
nobody watches. Four failures hide inside it, and none of them look wrong in a
grid of quarters.

**A row stops footing.** A quarter column is edited and the annual total beside
it is not re-added, so the project's interest, capitalized and deducted columns
no longer cross-foot — the schedule looks complete and the total is wrong.

**The split leaks.** The interest a project incurred no longer equals the
capitalized portion plus the deducted portion, so a slice of interest is neither
capitalized into basis nor deducted — it has simply left the schedule.

**A project is missing.** A construction project carrying an interest balance on
the entity trial balance never reaches the schedule, so its interest is deducted
in full and none is capitalized, and nothing in the workbook notices.

**The capitalized figure is asserted, not derived.** The capitalized interest is
typed in rather than recomputed as accumulated production expenditures times the
period rate rolled by quarter, or the rate is applied at one level for one
project and another for the next, or the comparison does not carry the prior
year's capitalized balance forward.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 19 controls, writes
`capitalize_report.json` and `capitalize_report.md`, and exits with the verdict
code. The corpus contains planted defects on purpose, so a non-zero exit is the
engine working.

## The 19 controls

| Family | Count | Asks |
|---|---|---|
| `set_`  | 1 | Is the capitalization file complete, over a readable quarter grid? |
| `prj_`  | 4 | Are the project keys unique and named, is each status known, and does every trial-balance project reach the schedule? |
| `data_` | 4 | Are the accumulated expenditures present, non-negative and non-decreasing, and is each rate a valid basis-point rate? |
| `cap_`  | 6 | Does each quarter's capitalized interest re-derive, close without leakage, stay within the interest incurred, foot to the annual totals, and cease at completion? |
| `cmp_`  | 2 | Does the comparison tie the schedule's current-year capitalized and roll the prior year forward? |
| `rpt_`  | 2 | Do the schedule's total capitalized and project count recompute from the projects they summarise? |

Three are worth calling out.

**The capitalized figure re-derives, it is not read back.** `cap_rederives` is
the control the engine exists for. The capitalized column is a *derivation*, and
a capitalized figure that is not recomputed from the accumulated production
expenditures times the period rate is an assertion. The engine rebuilds every
quarter's capitalized interest through the shared kernel — expenditures rolled at
the rate — and compares.

**The split closes exactly.** `cap_no_leakage` compares with exact `==`: the
interest a project incurred is either capitalized into basis or deducted, and
there is no third destination. A cent that is neither is a cent that has left the
schedule. `cap_within_interest` holds the other edge — a quarter cannot
capitalize more interest than it actually incurred.

**Every project on the trial balance reaches the schedule.** `prj_tb_complete`
is the completeness control. The trial balance is the authoritative population; a
construction project carrying an interest balance there but absent from the
schedule has all of its interest deducted and none capitalized, and nothing else
in the workbook notices.

## Completion is a flag, not a failure

`cap_ceased_on_completion` marks a project placed in service that is still
capitalizing interest: the capitalization period ends at the in-service date, so
the figure needs a human's eyes to confirm the date and stop the capitalization.
It is `REVIEW`-severity — worth attention, not a hard stop.

## Tests

```bash
python -m pytest capitalize_engine/tests -q
```

A clean baseline parametrized over the registry, one planted-defect file per
named control, boundary tests on every cent and quarter threshold, an extended
invariant grid over the shared money kernel, and read-only / determinism proofs
that hash the corpus before and after a full run.

## The schedule is derived, not typed

Only the roster, the trial balance, the accumulated production expenditures, the
period rate, the quarterly interest and each project's prior-year capitalized
balance are stated. The generator computes everything the engine later checks as
a re-derivation — each quarter's capitalized and deducted interest, the annual
totals, the year-over-year ending balance and the schedule rollups — through the
*same* capitalization kernel the engine recomputes with.

So the relationships the engine tests are the same relationships that produced
the data.

---

🔒 **All data is fictional.** The developers, the projects, the company and job
numbers, the expenditures, the interest and the capitalization rate are invented,
and the fiscal year is set in a fictional future. No employer or client
workpaper, entity, methodology, path or figure is reproduced.
