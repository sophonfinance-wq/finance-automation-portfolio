# Project labor charge automation

A deterministic, **read-only** control engine for charging employee labor cost to
projects — the advance authorization a project manager gives before an employee is
charged, the monthly charge that must match it, the invoice those charges foot into,
the project labor budget they must stay inside, and the general-ledger tie-out.

An employee's time is not free to a project just because the company already pays
the salary. The cost has to be charged over — salary plus payroll taxes plus
benefits, the fully-burdened figure — and only where a project manager authorized it
**in advance**, only from the month the authorization takes effect, at the fixed
amount or percentage that was authorized, and only up to the labor budget the project
carries.

Four failures hide inside a monthly invoice run, and none of them look wrong.

**The charge outruns the authorization.** A fixed amount was authorized and the
ledger charges a different one; or a percentage was authorized and the resolved
monthly figure does not re-derive from the burdened cost to the cent. The invoice
still totals cleanly. The project is simply carrying the wrong number.

**The charge predates the authorization.** An employee is charged for a month before
the authorized start date — the notice was given late, or the start slipped and the
charge did not. The month is real, the amount is right, and the charge should not
exist at all.

**The charge lands where nobody authorized it.** An employee is charged to a project,
or on a cost code, that the authorization never named. The money is real and it is on
the wrong job.

**The budget is silently overrun.** Cumulative labor charges cross the project's
labor budget parameter and nobody notices until the job is underwater, because each
individual monthly charge looked ordinary.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 26 controls, writes
`labor_report.json` and `labor_report.md`, and exits with the verdict code. The
corpus contains planted defects on purpose, so a non-zero exit is the engine working.

## The 26 controls

| Family | Count | Asks |
|---|---|---|
| `set_`   | 1 | Is the charge-run file complete, and is the review date readable? |
| `emp_`   | 3 | Is the employee register sound — unique ids, a positive burdened cost? |
| `prj_`   | 3 | Is the project register sound — unique codes, cost codes, a positive budget? |
| `auth_`  | 8 | Is each authorization complete, valid, given in advance, and correctly resolved? |
| `chg_`   | 5 | Does every monthly charge match the authorization that permits it? |
| `bud_`   | 2 | Does cumulative labor charge stay inside — and clear of — the project's budget? |
| `inv_`   | 2 | Does each monthly invoice foot to the charges beneath it, one per charged period? |
| `gl_`    | 2 | Does the charge ledger, and the invoiced total, tie the general ledger? |

Three are worth calling out.

**The charge re-derives, it is not read back.** `auth_charge_derives` resolves a
percentage authorization the same way it should have been resolved — the truncating
rate applied to the employee's fully-burdened cost — and `chg_amount_matches_auth`
then proves every monthly charge equals that resolved figure to the cent. A charge
can foot perfectly into its invoice and still be a cent adrift of what was
authorized; these two controls are where that cent is caught.

**Notice comes before the charge, not after.** The whole process exists so the
project accountant is told *in advance*. `auth_notice_before_start` proves the notice
date is on or before the authorized start, and `chg_not_before_start` proves no
charge falls in a month before that start — the two halves of "authorized ahead of
time, charged only from then on".

**The budget has a hard line and a warning band.** `bud_within_budget` fails a
cumulative charge that exceeds the project's labor budget; `bud_near_budget` flags,
for review rather than failure, a cumulative charge that has reached the warning band
the project itself carries — so the next authorization gets a human's eyes before the
line is crossed.

## The charge only lands where it was authorized

`chg_authorized` compares every charge's employee-project pair against the
authorizations on file, `chg_cost_code_matches_auth` proves the charge posts to the
cost code that was named (not merely a valid one on the same project), and
`auth_cost_code_on_project` proves that authorized cost code exists on the project at
all. Between them, a labor charge cannot reach a project, or a bucket inside it, that
nobody agreed to.

## Tests

```bash
python -m pytest labor_engine/tests -q
```

A clean baseline parametrized over the registry, one planted-defect file per named
control, boundary tests on every cent and date threshold, and read-only /
determinism proofs that hash the corpus before and after a full run.

## The baseline is derived, not typed

Only the employees, the projects and the authorizations are stated. The generator
computes everything the engine later checks as a tie-out: each authorization's
resolved monthly charge from its method, the monthly charge lines from each start
date, the invoice totals they foot into, and the two general-ledger control totals.

So the relationships the engine tests are the same relationships that produced the
data.

---

🔒 **All data is fictional.** The contractor entities, the employees, the projects,
the cost codes and every burdened cost and authorization are invented, and the charge
cycle is set in a fictional future. No employer or client workpaper, entity,
methodology, path or figure is reproduced.
