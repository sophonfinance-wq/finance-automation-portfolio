# G&A expense allocation automation

A deterministic, **read-only** control engine for a management or holding
entity's recurring G&A expense allocation — shared overhead, corporate G&A and
metered postage pushed out every month to the operating entities and projects
that consumed them, on a driver, with every share, every allocated amount and
the generated journal entry re-derived and compared.

The workbook this engine watches is the classic recurring one: one tab per month,
a driver tab and a lookup tab behind it, a stamped accounting date per period,
and a formula column that turns a driver share into a dollar figure. It is copied
forward every month, which is exactly why it drifts.

Four failures hide inside that, and none of them look wrong on the face of the
tab.

**The percentages stop summing to one hundred.** A recipient is added, a project
closes, a share is typed over — and the column now sums to 99.97%. The allocation
still runs. It simply pushes out slightly less than the pool it was dividing, and
the holding entity quietly retains the difference every month for the rest of the
year.

**The allocated amounts stop tying the pool.** The shares are right and the
amounts beside them are stale, or were rounded recipient by recipient rather than
by a largest-remainder split, so the column sums to a cent or two off the cost
pool it was supposed to exhaust.

**The journal entry drifts from the schedule.** The workbook is one artifact and
the entry posted from it is another. A debit is retyped, a credit is left on the
prior month's figure, an entity is charged and relieved inside the same entry —
and the entry still balances, so nothing downstream objects.

**A month goes missing, or is stamped to the wrong date.** The tab was never
rolled, or was rolled and dated to the month it was copied from, so a period is
absent from the year or posts into the wrong accounting period.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 22 controls, writes
`gaalloc_report.json` and `gaalloc_report.md`, and exits with the verdict code.
The corpus contains planted defects on purpose, so a non-zero exit is the engine
working.

## The 22 controls

| Family | Count | Asks |
|---|---|---|
| `set_` | 1 | Is the allocation file complete, and does it name its opening month and its holding entity? |
| `per_` | 2 | Does the year run month by month, and does every tab carry every artifact, stamped to its own month end? |
| `rcp_` | 3 | Are the recipient ids unique and well-formed, and is the holding entity kept out of its own allocation? |
| `drv_` | 2 | Are the driver counts whole and non-negative, and does every recipient have exactly one in every month? |
| `pol_` | 2 | Does the cost pool add to its stated total, and did it step month over month beyond the file's band? |
| `alc_` | 5 | Does every recipient have a row, do the shares sum to 100.00% and re-derive from the drivers, and do the amounts tie the pool and re-derive from the shares? |
| `je_`  | 3 | Does the generated entry balance, tie the re-derived allocation, and net to zero at consolidation? |
| `pst_` | 3 | Does the meter roll forward, does the per-code split tie the meter delta, and does the pool's postage component equal it? |
| `rpt_` | 1 | Does the year-to-date rollup recompute from the tabs beneath it? |

Four are worth calling out.

**The amount recomputes, it is not read back.** `alc_amounts_rederive` is the
control the engine exists for. An allocated column is the product of two things
the file already carries — a driver share and a cost pool — and the only way to
know it is still that product is to compute it again. Every amount is rebuilt
through the same kernel that produced it and compared to the cent.

**The residual cent belongs to exactly one recipient.** Both derivations run by
largest remainder: `driver_shares_bps` places the leftover basis points so the
share column lands on exactly 10000 bps, and `allocate_pool` places the leftover
cents so the allocated column lands on exactly the pool. Rounding each recipient
independently satisfies neither identity, which is precisely how a workbook ends
up pushing out 99.98% of its own cost pool every month.

**The entry is read net, not gross.** `je_ties_allocation` compares each
recipient's *net* debit to the re-derived allocation, so a line pair that appears
to correct itself is not mistaken for the right answer — and
`je_consolidation_nets_zero` catches that pair separately, because an entity both
charged and relieved inside one entry nets to nothing at that entity while
inflating both sides of the entry.

**Postage ties to something outside the workbook.** Postage is the one component
of the pool with a physical counter behind it. `pst_meter_rolls_forward` proves
each month opens where the last one closed, `pst_allocations_tie_meter_delta`
proves the per-code split exhausts the metered spend exactly, and
`pst_pool_component_ties` proves the pool line equals the meter delta — so the
figure being allocated is the postage that was actually bought.

## The variance band is a flag, not a failure

`pol_month_over_month_variance` marks a cost pool that steps beyond the file's own
band from the month before it. The entry built on that pool is arithmetically
correct either way, so this is `REVIEW` severity: a recurring workbook is copied
forward precisely because the figures are stable, and a step outside the band is
either a real change in the group's cost base or a component typed into the wrong
month. A human should say which.

## Tests

```bash
python -m pytest gaalloc_engine/tests -q
```

A clean baseline parametrized over the registry, one planted-defect file per
named control, boundary tests on every cent and basis point threshold, a
containment test proving each planted defect trips its own control and no other,
and read-only / determinism proofs that hash the corpus before and after a full
run.

## The baseline is derived, not typed

Only the month calendar, the recipient lookup, the driver counts, the two
discretionary pool components and the postage meter readings are stated. The
generator computes everything the engine later checks as a derivation — the
shares, the allocated amounts, the per-code postage split, the pool's postage
component and total, the journal entry and the year-to-date rollup — through the
*same* allocation kernel the engine re-derives with.

So the relationships the engine tests are the same relationships that produced the
data.

## What it does not do

It does not post the entry it re-derives, does not file, and does not pay. It
does not write to a source artifact. It does not judge whether the cost should
have been incurred, or whether the driver is the right driver — that is an
allocation-policy question, and a policy the engine invented would be a policy
nobody approved. Every accounting-date test is made against the period stamped in
the file, never the system clock.

---

🔒 **All data is fictional.** The holding entity, the operating entities, the
projects, the GL accounts, the driver counts, the cost pools and the postage
meter readings are invented, and the fiscal year is set in a fictional future. No
employer or client workpaper, entity, methodology, path or figure is reproduced.
