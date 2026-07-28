# Trial-Balance Roll-Forward — `SFS-E48-TBR`

A deterministic, **read-only** control engine for the annual trial-balance roll-forward: the
state-filing workpaper a group rebuilds every fiscal year — last year's column structure carried
forward, final-year entities retired, renamed entities carried once, first-year entities admitted
with their registration dates, and every column repopulated from the year-end trial-balance extract,
tied to an embedded backup tab, cell by cell.

```bash
python run.py                              # regenerate the corpus, run every control, write reports
python -m rollforward_engine samples       # analyze an existing folder
python -m pytest rollforward_engine/tests -q
```

**24 controls · 10,405 tests · 27 seeded workpaper files · 7 artifacts read · zero tolerance.**

---

## Why this is worth an engine

Every failure mode of an annual roll-forward shares one property: **the workpaper still balances.**
That is what lets them survive review.

- **A column is populated from the wrong source column.** Some books in the extract carry a
  monthly-activity column beside the balance column. Activity foots to zero exactly the way balances
  do, so a column populated from it self-balances, passes a footing check, and carries movement
  instead of balances.
- **A balance rides an equivalent code and disappears.** Two charts of accounts share one workpaper
  row; retained earnings lives on one chart as one code and on the other as another. Drop the
  equivalence and the balance silently lands nowhere — while every column still foots.
- **The eliminations range excludes this year's columns.** A range written over last year's
  structure keeps evaluating after new columns are inserted beyond its end. Nothing errors; the new
  columns simply are not eliminated.
- **The backup tab quotes the wrong text column.** The extract carries a category column beside the
  title column. A backup titled from category reads plausibly — "Cash", "Equity" — and reconciles to
  nothing a reviewer can look up.
- **The two rendered twins drift.** The workpaper ships in two formats; a repair applied to one and
  not the other leaves reviewers reading different numbers.

So the controls here **re-derive rather than trust**: every cell from the declared balance column of
its book, every dual-code row as the sum of its codes through the chart-equivalence map, every column
to zero, every eliminations range over every column, every backup row against the source's own title
column, and both rendered twins against each other. Exact `==`, integer cents, no tolerance band.

## Scope

This engine is the **workpaper**, not the filing. Whether an entity's return was filed by its
statutory date is a calendar question and a separate engine owns it. Nothing here populates a
workpaper, files a return, pays a fee or writes to a source artifact.

## Control families

| Family | Controls | Question |
|---|---|---|
| `set_` | 1 | is the file complete and the fiscal window legible |
| `reg_` | 2 | is the confirmed population sound, and is any first period short |
| `src_` | 3 | were the right rows and the right **column** harvested |
| `scope_` | 4 | does this year's column set match the confirmed register |
| `map_` | 5 | does every cell tie the extract, both directions |
| `col_` | 1 | does every column sum to zero |
| `elim_` | 1 | does the eliminations range cover every column |
| `combined_` | 1 | does the combined column foot |
| `bak_` | 2 | is the backup complete and titled from the title column |
| `lnk_` | 1 | does every figure link to evidence that agrees with it |
| `twin_` | 1 | do both rendered formats match |
| `fee_` | 1 | does the fixed annual fee follow entity status |
| `dormant_` | 1 | is a genuinely empty column confirmed by a human |

Two controls are **FLAG** severity — a dormant column and a short first period are judgements the
engine cannot make, only surface.

## Guarantees

- **Read-only.** Workpaper files are parsed and never written back, so the engine cannot introduce
  the break it reports.
- **Integer cents, exact `==`.** No tolerance band on a cell. A tolerated penny is a figure the
  ledger does not support, and every schedule downstream inherits it.
- **Columns located by declared role, never by position.** Both the balance column and the title
  column. Reading by position is the single error that produces most of the failures that still foot.
- **One derivation kernel.** Controls and generator share `rollforward_engine.workpaper`, so a
  populated cell cannot disagree with the logic that produced it.
- **The footing check is proved insufficient.** A test asserts that `col_self_balance` stays *silent*
  on the activity-column defect — if it could catch it, the basis control would be redundant.
- **No system clock.** Every date is tested against the fiscal window the file carries, so a run in a
  later year returns the same findings.
- **Deterministic and byte-stable.** Same inputs, same findings, same order; no timestamps or
  absolute paths in any output.

## Exit codes

`0` PASS · `1` REVIEW (flags only) · `2` FAIL · `3` usage/IO.

The bundled corpus exits **2 by design** — it carries a planted defect for every registered control.

## Data

All shipped data is **fictional**. The groups, entities, books, chart codes, balances and dates are
invented, and the fiscal year is set in a fictional future. No real entity, project, place, account
balance or path appears anywhere in this package.
