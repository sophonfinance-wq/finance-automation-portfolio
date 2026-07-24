# Project-proforma integrity automation

A deterministic, **read-only** control engine for a real-estate developer's
quarterly project-proforma reporting (QPR) — every active development project's
proforma re-derived, figure by figure, from its own base ledger and held to the
tie-out registry the workbook is built around.

A quarterly proforma is a workbook that was internally consistent the day a
formula last recalculated, and it drifts when cells are overtyped or tabs rolled
forward without their precedents. The error-check tab keeps showing zeros because
the zeros themselves were typed. Three families of drift hide inside a clean-looking
workbook, and none of them look wrong in a grid of formatted numbers.

**The balances stop balancing.** Total sources drift from total uses; hard plus
soft stops equalling total project cost; the dev-cost budget no longer matches the
proforma's unlevered cost.

**The profit chain stops tying.** Net profit no longer equals revenue minus cost;
the waterfall's distributed profit stops matching the budgeted profit; the sponsor
and investor splits stop summing to the whole.

**The report drifts from the evidence.** A margin is quoted off a stale cost, a
variance column is typed rather than subtracted, a project's QPR never makes the
cycle or lands after its region's due date, and the cycle count is maintained
beside the filings rather than derived from them.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 26 controls, writes
`proforma_report.json` and `proforma_report.md`, and exits with the verdict code
(0 PASS / 1 REVIEW / 2 FAIL / 3 usage). The corpus contains planted defects on
purpose, so a non-zero exit is the engine working.

## The 26 controls

| Family | Count | Asks |
|---|---|---|
| `set_`  | 1 | Is the proforma file complete, and is the review date readable? |
| `src_`  | 3 | Do the source and use totals tie their lines, and do total sources balance total uses? |
| `cost_` | 3 | Does hard+soft equal total project cost, does the dev-cost budget equal the unlevered cost, and does the contingency roll up? |
| `int_`  | 2 | Is the interest reserve adequate, and is equity funded before construction? |
| `prof_` | 2 | Does net profit re-derive from revenue and cost, and does unlevered profit re-derive? |
| `wfl_`  | 5 | Do the waterfall, budgeted and distributed profits tie net profit, does the sponsor share re-derive, and do the splits sum to the whole? |
| `mgn_`  | 3 | Do the margin on cost, margin on revenue and per-NSF cost re-derive? |
| `var_`  | 3 | Is each variance current-minus-prior, does each schedule variance re-derive, and is any profit swing beyond materiality? |
| `rpt_`  | 4 | Did every active project file a QPR, on time, is each region's deck complete, and does the cycle count tie the filings? |

Three are worth calling out.

**The figures recompute, they are not read back.** Every stated figure on the
summary tabs — net profit, the margins, the waterfall and the splits — is rebuilt
from the base ledger and compared. A determination that is not recomputed from the
evidence is an assertion.

**Every tie-out is met to the cent.** The balances, the cost equalities and the
profit chain compare with exact `==` on integer cents. A source-and-use error of a
single cent is a source-and-use error, and the workbook's own zero is not trusted
until it is re-derived.

**The waterfall closes on the whole.** `wfl_split_completeness` proves the sponsor
and investor shares sum back to net profit with no leakage, and `wfl_sponsor_share_derivation`
rebuilds the sponsor's share with the same largest-remainder split the proforma
used, so the odd cent lands where the split put it rather than becoming a spurious
break.

## The materiality flag is a flag, not a failure

`var_materiality_flag` marks a period-over-period net-profit swing beyond the
file's own materiality band: the swing is real and correctly derived, but a move
this large between quarters is a reviewer's call. It is `REVIEW`-severity — worth a
human's eyes, not a hard stop.

## Tests

```bash
python -m pytest proforma_engine/tests -q
```

A clean baseline parametrized over the registry, one planted-defect file per named
control, boundary tests on every cent, day and basis-point threshold, and
read-only / determinism proofs that hash the corpus before and after a full run.

## The baseline is derived, not typed

Only each project's base ledger — its source and use lines, hard and soft cost,
interest, revenue, area, equity split, prior-period figures and milestone dates —
is stated. The generator computes everything the engine later checks as a stated
summary figure through the *same* derivation kernel the engine recomputes with.

So the relationships the engine tests are the same relationships that produced the
data.

---

🔒 **All data is fictional.** The developers, the projects, the fictional regions,
the costs, the revenues and every reporting date are invented, and the reporting
period is set in a fictional future. No employer or client workpaper, entity,
methodology, path or figure is reproduced.
