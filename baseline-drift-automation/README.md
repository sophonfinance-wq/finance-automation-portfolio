# Baseline & Version Drift — `SFS-E52-BDR`

A deterministic, **read-only** control engine for the problem of one project
budget existing in four authoritative copies at once.

A joint venture is signed against a contractual exhibit. The sponsor maintains a
working model. Draws are billed on a Schedule-II style instrument carrying
approved-plus-changes columns. A summary memo is circulated to a lender. Four
copies of one budget — and each of them can foot perfectly, re-derive its own
margin, balance sources against uses, and still disagree with the other three.

That is the whole subject of this engine. **It does not check whether a single
budget foots.** That is a within-document question and a separate engine
(`SFS-E23-QPR`) owns it. This engine starts where that one stops, because every
failure mode it exists for *survives* a within-document check.

## Why the copies drift, and why nobody notices

**A copy is internally consistent and materially wrong.** Sources equal uses in
all four. They simply carry different totals. Nothing inside any one of them can
detect it.

**A reclassification reads as a change.** Two lines move by equal and opposite
amounts and the total never budges. That is a re-carve of the same money, not a
budget change — and grading it as a change buries the genuine ones among the
noise.

**A category exists in one copy and not another.** A line renamed or split in the
working model has no counterpart in the exhibit. A comparison that walks one
version's lines and looks each up in the other comes back clean on everything it
*can* pair, and silently skips the line that moved.

**A copy is stale rather than wrong.** It was right when it was prepared. Its
cost-through date is months behind the period being reported, or its prepared
date falls before the agreement it purports to be an exhibit to. Every figure
read off it since has been quoted with confidence.

**A derived schedule loses its inputs.** A fee amortised across a construction
period depends on milestone dates. Blank a milestone and the schedule does not
error — it silently keeps the last amortisation it was handed, and the instalment
it drives stops matching the term it is meant to span.

## What the controls do

Twenty-five controls in seven families, run in registry order:

| Family | Question |
|---|---|
| `set` | Is every artifact present and the reporting period legible? |
| `ver` | Is there exactly one governing copy, named by the agreement, plausibly dated? |
| `lin` | Do the category sets reconcile, the paired values agree, the totals tie? |
| `stl` | Is each copy still speaking about this period? |
| `amd` | Does every movement re-derive and trace to an approved amendment? |
| `drv` | Are a derived schedule's inputs present, and does it conserve its base? |
| `eqt` | Do commitments agree across copies and match the phase's split? |

The load-bearing design decisions:

- **Category sets are reconciled before any value is compared.** A category
  present in one copy and absent from another is a finding in its own right,
  never an absence to skip.
- **Totals are summed from the lines**, then compared to the stated figure. A
  stated total that disagrees with its own lines was typed, not computed.
- **Materiality grades a difference that has already been found.** It never
  decides whether one exists. A sub-threshold difference is reported as a review
  flag so it is reconciled now rather than after it has grown.
- **Offsetting movements with an unchanged total are graded as reclassification**,
  not as change — and still require an approval behind them.
- **Every date is tested against the reporting period the file carries**, never
  the system clock.

Exact `==`, integer cents, no tolerance band.

## Run it

```
python run.py
```

Regenerates the fictional corpus into `samples/`, runs every control, writes
`baseline_report.json` and `baseline_report.md`, and exits with the verdict code
(`0` PASS / `1` REVIEW / `2` FAIL / `3` usage). The bundled corpus carries a
planted defect for every control, so a non-zero exit is the engine working.

```
python -m baseline_engine samples            # analyze without regenerating
python -m pytest baseline_engine/tests -q    # 10,224 tests
```

## Scope

The engine reads the six artifacts a reporting cycle emits — the governing
agreement, every budget version in circulation, the amendment log, the milestone
set, the derived schedules and the funding register — and stops. It never
prepares a budget, approves an amendment, issues a draw, or writes to a source
artifact.

All shipped data is **fictional**. No real project, entity, place, budget figure
or path appears anywhere in this package.
