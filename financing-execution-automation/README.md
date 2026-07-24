# Financing execution & schedule-variance automation

A deterministic, **read-only** control engine for a developer's monthly
capital-markets "Upcoming Financings" report — every financing workstream proved,
milestone by milestone, to have a variance that re-derives from its dates, a
`Prior` column that ties last month's `Current`, a frozen `Original` baseline, the
standard milestone playbook for its financing type, and no overdue milestone left
unflagged.

This is the schedule-and-execution half of the capital-markets story. Whether a
wire cleared, a note accrued or cash settled is another engine's job — this engine
never touches money in motion. It asks the narrower, entirely evidentiary
question: does the pipeline report the deal team circulated reconcile to itself
and to the month before it?

An "Upcoming Financings" report is a snapshot of a pipeline that moves every
month, and it drifts in ways nobody watches. Four failures hide inside that, and
none of them look wrong in a spreadsheet.

**The variance stops reconciling.** The `Variance` column is meant to be
`Current - Prior` in days, but a hand-edited `Current` date leaves the variance
behind, so the report says a milestone slipped by a number that no longer matches
its own dates.

**The month-over-month chain breaks.** This month's `Prior` column is supposed to
be last month's `Current` column, and the `Original` baseline is supposed to be
frozen forever. When either is quietly overwritten, the report looks current while
its history no longer ties.

**The playbook or the portfolio has a hole.** A live workstream is missing one of
its financing type's standard milestones, or a project on the master tracker has
no workstream in the report at all.

**The rollup drifts from the schedule.** The summary counts an active pipeline, an
overdue list or a financing total on figures nobody recomputed from the
workstreams underneath them, and the Gantt places a bar in a month that is not the
month the deal is set to close.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 21 controls, writes
`financing_report.json` and `financing_report.md`, and exits with the verdict
code. The corpus contains planted defects on purpose, so a non-zero exit is the
engine working.

## The 21 controls

| Family | Count | Asks |
|---|---|---|
| `set_`   | 1 | Is the financing report complete, and is the report date readable? |
| `mem_`   | 8 | Are the workstream ids unique, typed and statused, is each milestone attributable, is each playbook defined and complete, and does the report tie both ways to the master portfolio? |
| `var_`   | 3 | Are the milestone dates readable, does each variance re-derive as `Current - Prior`, and does each Gantt bar sit in its closing month? |
| `roll_`  | 1 | Does this month's `Prior` date equal last month's `Current` date? |
| `base_`  | 1 | Is the `Original` baseline frozen across months? |
| `date_`  | 2 | Is the report date the period-end, and does each overdue flag match the date gate? |
| `ord_`   | 2 | Are the milestone sequence numbers unique and their current dates non-decreasing? |
| `rpt_`   | 3 | Do the active count, the overdue count and the financing total recompute from the workstreams they summarise? |

Three are worth calling out.

**The figure recomputes, it is not read back.** Every variance, overdue flag,
Gantt month and rollup count is a *derivation*, and a derivation that is not
recomputed from the schedule is an assertion. The engine rebuilds each one from the
base milestone dates and workstream register and compares it to the figure on file.

**The month-over-month chain is walked, not assumed.** `roll_prior_ties_current`
proves this month's `Prior` is a verbatim carry of last month's `Current`, and
`base_original_immutable` proves the frozen baseline never moved — so a slipped
milestone cannot be re-based into looking on-plan.

**Every variance is measured to the day.** `var_recomputes` compares with exact
`==` on whole calendar days. A variance one day off its own `Current - Prior` is a
number the deal team reads and trusts while it silently lies.

## The overdue flag is a flag, not a failure

`date_overdue_flag` marks a milestone whose stated overdue flag does not match the
date gate `ACTIVE and Current < ReportDate`: an overdue milestone is a live signal
for the deal team, not a broken report, so a stale flag is worth a human's eyes,
not a hard stop. It is `REVIEW`-severity.

## Tests

```bash
python -m pytest financing_engine/tests -q
```

A clean baseline parametrized over the registry, one planted-defect file per named
control, boundary tests on every day, count and status threshold, and read-only /
determinism proofs that hash the corpus before and after a full run.

## The baseline is derived, not typed

Only the workstreams, the milestone dates, the playbooks and the master tracker
are stated. The generator computes everything the engine later checks as a
re-derivation — each milestone's variance and overdue flag, each Gantt month, and
the portfolio's active / overdue / financing-total counts — through the *same*
schedule kernel the engine recomputes with.

So the relationships the engine tests are the same relationships that produced the
data.

---

🔒 **All data is fictional.** The developers, the projects, the regions, the
financial partners and every milestone date and financing amount are invented, and
the report period is set in a fictional future. No employer or client workpaper,
entity, methodology, path or figure is reproduced.
