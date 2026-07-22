# Project draw automation

A deterministic, **read-only** control engine for the construction loan draw cycle
in real-estate development.

A draw request is the moment a developer asks a lender for money, and it is almost
entirely arithmetic. The package has to prove three things at once:

1. **Cumulative draws equal cumulative costs.** Total draws to date, less costs to
   date net of retention, must be exactly zero.
2. **The form agrees with the working paper behind it.** What the lender receives
   must tie to the reconciliation, the trial balance and the cost detail.
3. **The money was incurred inside the period being billed.** Costs dated or posted
   outside the cycle belong to a different draw.

Each of those is a tie-out with a right answer, which is what a deterministic
control can assert. The failure modes are not exotic — a retention release moved in
one schedule but not the other, a contingency line drawn faster than the work it
covers, a cost posted two days after cutoff and billed anyway. Each is invisible in
a spreadsheet and obvious to a rule.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 34 controls, writes
`draw_report.json` and `draw_report.md`, and exits with the verdict code. The corpus
contains planted defects on purpose, so a non-zero exit is the engine working.

## What it reads

Six fixed-format artifacts a draw cycle emits:

| Artifact | What it carries |
|---|---|
| `job_cost_to_draw_reconciliation` | The project accountant's working paper: fundings, costs and retention by category |
| `draw_request_form` | The lender-facing form: budget, previous applications, this request, remaining |
| `cost_transaction_detail` | Current-period transactions with accounting, posting and approval dates |
| `funding_ledger` | Equity and debt funding events, plus the ledger balances they must tie to |
| `supporting_documentation_index` | Signatures, invoice backup coverage, schedule of values, distribution |
| `draw_cycle_calendar` | Cutoff, posting deadline, prep start, submittal, funding, and the SLAs |

## The 34 controls

| Family | Count | Asks |
|---|---|---|
| `set_` | 2 | Is the package complete and internally consistent enough to read? |
| `recon_` | 8 | Do cumulative draws equal cumulative costs? |
| `form_` | 8 | Does the lender's form agree with the working paper behind it? |
| `cont_` | 2 | Was contingency drawn only as fast as the work was earned? |
| `cut_` | 5 | Were the costs incurred inside the period being billed? |
| `acc_` | 2 | Were accruals used within policy, and reversed afterwards? |
| `doc_` | 4 | Is the package supportable: signed, backed up, distributed? |
| `fund_` | 3 | Did the money arrive, and was a late draw chased? |

Two are worth calling out.

**The reconciliation identity has no tolerance band.** `total draws to date - costs
to date net of retention` must be exactly `0`. There are tests proving that one cent
of drift in either direction fails. A control that tolerates a penny has not proved
the draw ties.

**Contingency is capped by percent complete, and the denominator excludes itself.**
Hard-cost contingency may only be drawn up to the actual percent complete of hard
costs, soft-cost contingency up to that of soft costs — the two classes are governed
separately, because a project 80% through its sitework has not thereby earned the
right to spend its soft-cost contingency. The percent-complete denominator is the
*productive* lines only: if the contingency line counted toward its own class's
progress, a project could bootstrap entitlement by spending contingency to raise the
figure that authorises spending it.

## Design guarantees

- **Read-only.** Packages are parsed and never written back. The engine cannot
  introduce a defect; it can only report one.
- **Integer cents, exact comparison.** No floats accumulate, and there is no
  tolerance band anywhere. A value that should be integer cents but is not produces
  an `AMOUNT_INVALID` finding — contained to the one row it was read on — rather
  than being silently coerced. Rounding a source figure would make the engine the
  author of the number it is meant to audit.
- **Deterministic and byte-stable.** Same inputs, same findings, same order. The
  generator takes no seed and rewrites byte-identical files, so a diff in the
  committed report means a change in the controls, not a change in when it ran.
- **Absent evidence is not a passing control.** `set_complete` runs first and fails
  a package missing any artifact the registry reads, so no rule can hold vacuously.

## Tests

392 tests, all passing:

```bash
python -m pytest
```

- Every one of the 34 controls has a planted defect that trips it, asserted by name.
- The clean baseline is asserted rule-by-rule, so a regression names the control
  that broke.
- Boundaries are pinned: contingency passes exactly at its ceiling and fails one
  cent past it; the posting deadline is inclusive; the period's first and last day
  are inside it.
- Read-only, determinism and byte-stability are asserted by hashing the corpus
  before and after a full run.

The baseline is *derived*, not typed: line disbursements are chosen and every
dependent figure is computed from them, so a planted defect is guaranteed to be the
only thing wrong and the clean package cannot silently rot as rules are added.

## Fictional data

Everything shipped here is invented — projects (`Alderpoint Terraces`,
`Brightwater Commons`), the lender (`Meridian Sandbox Bank, N.A.`), vendors, signers
and cost codes — and the periods are set in a fictional future. No real project,
lender, bank, person, document number or path appears anywhere.
