# Buyer upgrade automation

A deterministic, **read-only** control engine for a homebuilder's buyer-upgrade
programme.

A buyer pays for an upgrade months before the home closes. That money is not
revenue when it arrives — it is a liability, and it stays one until the unit
actually closes. Between those two dates the same figure has to appear
consistently in four places, each maintained by a different person on a different
cadence, and each a spreadsheet:

| Where | What it holds |
|---|---|
| The closings schedule | Per unit: recognised revenue and the deferred balance |
| The general ledger | The unearned, revenue, cost-of-sales, contra-WIP and tax accounts |
| The cost-to-complete | Per unit: revenue, committed cost, cost to date, budgeted/actual |
| The proforma | Upgrade income, the offsetting job-cost line, the variance tab |

So the failure mode is almost never a wrong number. It is the *same* number
failing to move everywhere at once — a unit closes and the deferred balance is
released in the schedule but not the ledger; an upgrade is repriced and the
proforma keeps the old figure; a change order is executed and the committed cost
never lands.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 20 controls, writes
`upgrade_report.json` and `upgrade_report.md`, and exits with the verdict code.
The corpus contains planted defects on purpose, so a non-zero exit is the engine
working.

## The 20 controls

| Family | Count | Asks |
|---|---|---|
| `set_` | 2 | Is the book complete and internally consistent enough to read? |
| `unit_` | 3 | Does every upgrade belong to a real unit, exactly once? |
| `def_` | 4 | Is deferred revenue released when the unit closes, and only then? |
| `cos_` | 4 | Does the closing entry balance, and is cost coded where it belongs? |
| `tax_` | 2 | Is sales tax carried as a liability rather than as revenue? |
| `tie_` | 4 | Do the four schedules agree with each other? |
| `flag_` | 1 | Has the budgeted/actual marker kept up with reality? |

Three are worth calling out.

**Recognition is gated on close of escrow and nothing else.** This is the rule a
hand-maintained schedule is most likely to get wrong, because every other signal
says the money is earned: the buyer has paid, the work is finished, the invoice
is settled. None of that recognises revenue. There is a test that sets all three
of those flags on an open unit and asserts the control stays silent, and another
that recognises a single cent early and asserts it fails.

**The sign conventions are enforced in both directions.** The cost-to-complete
states cost as a positive figure; the proforma posts it to a job-cost line as a
negative, so income and cost sum directly on the variance tab. The tie negates
one side deliberately — comparing raw would fire on every correctly-prepared book
*and hold on one where the sign was wrong*, which is exactly backwards.

**Sales tax is a liability, never revenue.** Folding it into the revenue figure
inflates the top line and understates what is owed onward — and because both move
together, the schedule still foots.

## Design guarantees

- **Read-only.** Books are parsed and never written back. The engine cannot
  introduce a defect; it can only report one.
- **Integer cents, exact comparison.** No floats accumulate, and there is no
  tolerance band. A value that should be integer cents but is not produces an
  `AMOUNT_INVALID` finding — contained to the one row it was read on — rather
  than being coerced.
- **Deterministic and byte-stable.** Same inputs, same findings, same order. The
  generator takes no seed and rewrites byte-identical files.
- **Absent evidence is not a passing control.** A missing ledger balance fails
  the tie that needed it, rather than skipping quietly; there are parametrized
  tests for all four accounts.

## Tests

279 tests, all passing:

```bash
python -m pytest
```

- Every one of the 20 controls has a planted defect that trips it, asserted by
  name, and coverage is asserted too — no control ships without one.
- The clean baseline is asserted rule-by-rule, so a regression names the control
  that broke.
- Semantics are pinned, not just firing: recognition ignores payment and
  completion, one cent early fails, a partial release fails, a flipped contra
  credit fails, and a positive proforma cost line fails.

The baseline is *derived*, not typed: only the units and their upgrade orders are
stated, and contracted totals, the recognised/deferred split, sales tax, every
cost-to-complete row and total, the proforma lines and all five ledger balances
are computed from them. A book that has to satisfy twenty interlocking tie-outs
cannot be maintained by hand without rotting the first time a rule is added.

## Fictional data

Everything shipped here is invented — projects (`Alderpoint Terraces`,
`Brightwater Commons`), units, buyers and selections — and the periods are set in
a fictional future. No real buyer, project, unit, document number or path appears
anywhere.
