# Home Sale Closing & Settlement Tie-Out (SFS-E32-COE)

A deterministic, **read-only** tie-out engine for a residential developer's
home-sale closings. When a home reaches close of escrow the accounting team
assembles a package -- a settlement statement, a balanced closing journal entry,
a revenue-recognition line, a loan release tied to the lender's statement, and a
cost-of-sale relief. This engine proves, unit by unit, that the package agrees
with itself.

Engine 32 of the finance-automation portfolio. Mnemonic **COE**, package
**SFS-E32-COE**.

## What it checks

This is a **tie-out** check, not an underwriting one. What a home should have
sold for, whether the proforma was right, whether the loan should have been
made -- those are questions a different engine owns. A close-of-escrow package is
a stack of spreadsheets assembled under deadline, and it goes wrong in ways
nobody watches:

- **The entry does not foot.** Debits and credits do not balance, or the Accounts
  Receivable plug was typed rather than derived.
- **The statement does not recompute.** The total settlement charges, the total
  closing costs or the net to seller was keyed instead of summed, or a
  rate-derived fee -- the LISTING sales fee, the warranty reserve -- was struck at
  the wrong rate.
- **Revenue lands in the wrong month.** Residential sales revenue is earned only
  at close of escrow, so its recognition month must be the close month.
- **The loan release does not tie.** The internal release schedule and the
  lender's loan statement disagree, or the bank remittance falls short of the
  scheduled release price.
- **The rollup drifts from the units.** The report states a closed count or a
  total net to seller, or a per-unit tie-out flag, that nobody recomputed from
  the settlements and entries underneath it.

The engine recomputes every unit's tie-out determination from the settlement, the
entry, the revenue line, the loan release and the cost-of-sale schedule, and
compares.

## The controls

The registry has 25 controls across nine families (rule-id prefixes):

| Family   | Concern |
|----------|---------|
| `set_`   | the closing file is complete |
| `unit_`  | the unit register is sound and every closed unit has its full package |
| `je_`    | each closing entry foots, with a derived receivable |
| `ss_`    | the settlement statement recomputes |
| `fee_`   | the rate-derived fees strike at their proforma rates (variance is a FLAG) |
| `rev_`   | revenue is recognized in the close month |
| `loan_`  | each loan release ties to the lender's loan statement |
| `cos_`   | the cost-of-sale / margin relief recomputes |
| `rpt_`   | the rollup recomputes from the units it summarises |

Every control is a hard equality, a threshold, a date-gate, a membership check or
a re-derivation -- never a judgement.

### Severity and verdict

- **FAIL** -- a hard control failure (an entry that does not foot, a settlement
  line that does not recompute, a fee off its rate, revenue in the wrong month, a
  loan release that does not tie, a flag or count that does not recompute).
- **FLAG** -- a human-review signal (a booked fee that varies from the proforma
  assumption, a concession above the assumed allowance).
- **PASS** -- the rule ran and the control held.

A closing file with any FAIL rolls up to **FAIL**; FLAGs without FAILs roll up to
**REVIEW**; everything clean is **PASS**. The CLI exit code is the verdict:
`0` PASS, `1` REVIEW, `2` FAIL, `3` usage/IO error.

## Invariants

- **Read-only.** Closing files are parsed and never written back.
- **Integer cents, exact comparison.** Every figure is compared with exact `==`
  or `>=`; there is no tolerance band.
- **Byte-stable output.** No timestamps, absolute paths or hash-ordered iteration,
  so the committed report is diffable.
- **Missing artifact fails first.** `set_complete` owns the "missing artifact"
  finding; a control never passes because its input was absent.
- **One tie-out predicate.** Controls and the generator share the kernel in
  `closing_engine/settlement.py`, so a determination cannot disagree with the
  data that produced it.

## Usage

```
py -3 run.py
```

Regenerates the fictional corpus into `samples/`, runs every control, writes
`closing_report.json` and `closing_report.md`, and exits with the verdict code.
The corpus deliberately contains planted defects, so a non-zero exit is the
engine working.

Analyze an existing folder directly:

```
py -3 -m closing_engine <folder> [--json PATH] [--md PATH] [--generate] [--quiet]
```

Run the tests:

```
py -3 -m pytest -q
```

## Fictional data

All shipped data is **fictional**. The developers, projects, units, sale prices,
fees, loan balances, lenders and closing dates are invented, and the closing
period is set in a fictional future. No real entity, person, project, lender or
path appears anywhere. The generator is deterministic and takes no seed.
