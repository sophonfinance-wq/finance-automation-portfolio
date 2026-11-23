# Equity Waterfall & JV Promote — control engine (SFS-E22-WFL)

A deterministic, **read-only** control engine for a real-estate joint-venture
distribution waterfall. It re-derives every distributed dollar from the executed
operating agreement's mechanics and the contribution history — the
preferred-return accrual, the capital-account roll-forward, the tier sequencing
and pari-passu splits, the hurdle boundary, the promote/carry split, the
capital-call dilution and the realized-returns summary — and compares each
recomputed figure to the one the workpaper states, with exact integer-cent
equality and no tolerance band.

A JV waterfall is a chain of dependent computations, and a wrong number early
travels silently to the bottom line: a mis-compounded month of preferred return,
a tier paid out of order, a pari-passu split struck off the wrong weights, a
promote tier entered as though the hurdle were already cleared, or a
realized-returns table that nobody recomputed from the waterfall underneath it.

Every figure is rebuilt through a single shared kernel
(`waterfall_engine/waterfall.py`) that both the corpus generator and the controls
import, so a figure the engine recomputes cannot disagree with the arithmetic
that produced the data. The engine never pays, never files and never writes to a
source artifact. Every accrual and covenant window is measured against an
`as_of_period` month index carried in the file, never the system clock.

**All shipped data is fictional.** No real entity, person, project or path
appears anywhere.

## Control families

| Prefix    | Family                                   |
|-----------|------------------------------------------|
| `set_`    | Structural precondition (all artifacts present) |
| `mbr_`    | Member register soundness / venture well-formed |
| `pref_`   | Preferred-return accrual (monthly compounding)  |
| `cap_`    | Capital-account roll-forward & zero-out tie-out |
| `wf_`     | Waterfall tier sequencing & pari-passu split    |
| `hurdle_` | Hurdle-IRR boundary re-solution                 |
| `promo_`  | Promote / carried-interest split re-derivation  |
| `loan_`   | Member / default loan rates & repayment order   |
| `dil_`    | Capital-call dilution recompute (2× penalty)    |
| `dist_`   | Distribution completeness / no-leakage tie-out  |
| `ret_`    | Equity-multiple & realized-return tie-out       |
| `cov_`    | Financing covenants (LTC, maturity) — secondary |
| `syn_`    | Syndicate capital-call ratio & reporting — secondary |

Severity: hard re-derivation and threshold breaks are `FAIL`; a financing
maturing inside its warning window and a syndicate report due inside its lead
time are `FLAG`. Any `FAIL` rolls the file up to `FAIL`; `FLAG`-only rolls up to
`REVIEW`; a clean file is `PASS`. The CLI exit code is the verdict
(`0` PASS / `1` REVIEW / `2` FAIL / `3` usage).

## Run it

```
python run.py
```

Regenerates the fictional corpus into `samples/`, runs every control over it,
writes `waterfall_report.json` and `waterfall_report.md`, and exits with the
verdict code. The corpus deliberately contains planted defects — one per
registered control — so a non-zero exit here is the engine working.

Analyze an existing folder of deal files:

```
python -m waterfall_engine <folder> [--json OUT.json] [--md OUT.md] [--quiet]
```

## Tests

```
python -m pytest -q
```

The corpus is generated fresh into a temporary directory for the suite, so the
tests prove the generator and the engine agree. Each registered control has one
clean-baseline pass, one planted defect that must trip it, and a boundary test
that pins the cent / basis-point / month where it fires.
