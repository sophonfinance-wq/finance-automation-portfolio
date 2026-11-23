# Energy-Efficient Home Credit automation (§45L)

A deterministic, **read-only** control engine for the IRC §45L energy-efficient
home credit — every claimed dwelling unit re-derived, unit by unit, from its
close-of-escrow date, its RESNET/HERS certification and the dated statutory
per-unit amount, then rolled up per project, per region and per fiscal year, with
net-benefit and partner-allocation derivation and a full cross-artifact tie-out.

The §45L credit is a *per-unit* credit. A builder earns a fixed statutory amount
for each newly built dwelling it sells, but only for a unit that clears two gates
at once: it closed inside the fiscal-year window being filed, and it holds an
energy certificate from a certified rater. The gross credit is nothing more than
the count of qualifying units times the dated per-unit amount, and every figure
above it — profit addback, tax effect at the effective rate, net benefit, partner
split — is arithmetic on that product.

That is exactly what makes it worth an engine: the arithmetic is simple and the
places it silently drifts are many. Three failures hide inside it, and none of
them look wrong on a footed worksheet.

**A unit is claimed that should not be.** It closed outside the fiscal-year
window, or it closed after the statutory sunset, or it was never certified by a
rater — yet it was counted in the credit anyway. The computation still foots; the
units underneath it do not qualify.

**A unit is counted twice.** The same dwelling is claimed in two successive period
filings, so a credit already taken is taken again. Each filing looks internally
consistent; the overlap is only visible across them.

**The rollup drifts from the units.** The worksheet's gross credit, the report's
certified-unit tie-out, the roll-forward identity, the net-benefit derivation or
the partner allocation is stated on a number nobody recomputed from the unit
register underneath it.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 26 controls, writes
`energy_report.json` and `energy_report.md`, and exits with the verdict code. The
corpus contains planted defects on purpose, so a non-zero exit is the engine
working.

## The 26 controls

| Family | Count | Asks |
|---|---|---|
| `set_`   | 1 | Is the credit file complete, and are the period and sunset dates readable? |
| `unit_`  | 3 | Are the unit ids unique, the fields present, and every unit tied to a project the worksheet carries? |
| `elig_`  | 2 | Did every claimed unit close inside the fiscal-year window and on or before the statutory sunset? |
| `cert_`  | 2 | Is every claimed unit certified, and does its certificate name the rater who signed it? |
| `dup_`   | 1 | Is any unit claimed again that a prior period filing already claimed? |
| `rate_`  | 2 | Does each unit carry the dated statutory rate, and does each project's gross credit re-derive as units × rate? |
| `rpt_`   | 1 | Does the final report's certified units × rate tie its stated total credit? |
| `roll_`  | 3 | Do the project unit counts tie the register, and do the region subtotals and grand totals foot? |
| `fwd_`   | 3 | Does the roll-forward identity hold, are the period windows disjoint, and what remains to close? |
| `net_`   | 3 | Do the profit addback, the tax effect at the effective rate, and the net benefit re-derive? |
| `alloc_` | 2 | Do the partner shares sum to the net benefit and re-derive from ownership at largest-remainder? |
| `recon_` | 3 | Do the report, worksheet and closings schedule reconcile on the credited units — and is any certification gap flagged? |

Three are worth calling out.

**The credit re-derives, it is not read back.** `rate_gross_credit`,
`rpt_units_times_rate` and the `roll_` family rebuild every credit figure from the
unit register and the dated statutory rate and compare — a stated gross credit,
grand total or certified-unit count that is not exactly `units × rate` is a number
nobody re-tallied from the dwellings underneath it.

**The two eligibility gates are independent.** `elig_close_in_period` and
`elig_within_sunset` are separate controls because the statutory sunset sits
*inside* the fiscal-year window: a unit can close in the period yet after the
sunset, qualifying under one gate and failing the other. Each is checked with `<=`
at its boundary — a unit closing exactly on the sunset date is still eligible.

**Only closed *and* certified units flow to the credit.** `recon_closed_ge_credited`
proves no project credits more units than it closed, while `recon_certification_gap`
flags the opposite — more closed than certified — as a review signal, not a
failure: there may be a credit left on the table for units whose certificates were
never chased.

## The review signals are flags, not failures

`fwd_remaining_to_close` marks a project with units still to close in a future
period, and `recon_certification_gap` marks a project that closed more units than
it certified. Neither is an error — one is a credit still to come, the other a
credit possibly left on the table — so both are `REVIEW`-severity: worth a human's
eyes, not a hard stop.

## Tests

```bash
python -m pytest energy_engine/tests -q
```

A clean baseline parametrized over the registry, one planted-defect file per named
control, boundary tests on every cent and date threshold, and read-only /
determinism proofs that hash the corpus before and after a full run.

## The baseline is derived, not typed

Only the units — their close dates, certification and claim status — the projects,
the roll-forward columns, the partner ownership and the statutory parameters are
stated. The generator computes everything the engine later checks as a rollup —
each unit's credited amount, every project's gross credit / addback / tax effect /
net benefit, the region and grand totals, the partner shares, the closings counts
and the final-report tie-out — through the *same* credit kernel the engine
recomputes with.

So the relationships the engine tests are the same relationships that produced the
data.

---

🔒 **All data is fictional.** The builders, the projects, the dwelling addresses,
the rater ids, the unit counts and every closing date are invented, and the fiscal
year is set in a fictional future. No employer or client workpaper, entity,
methodology, path or figure is reproduced.
