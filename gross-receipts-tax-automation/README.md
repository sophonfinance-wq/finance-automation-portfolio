# Gross-receipts & excise tax automation

A deterministic, **read-only** control engine for a developer's gross-receipts &
excise tax filings — every worksheet's tax re-derived, jurisdiction by
jurisdiction, from the general-ledger revenue pull and the classification rate
that was actually in force for the period, tied to the number the worksheet
filed, with the filing calendar proved complete, timely and approved.

A developer that manages projects across several taxing jurisdictions owes a
gross-receipts or excise tax in each one — a state Business & Occupation tax, a
city excise, a territorial general-excise tax — each with its own rate, filing
cadence (monthly, quarterly, annual), deductions, thresholds and due dates, and
each rate can change mid-year. The tax on a worksheet is a *derived* figure, and
it goes wrong in ways that look right on the page.

**The base does not tie the ledger.** A revenue line is omitted, a non-taxable
back-out is overstated, or the monthly lines do not sum to the total the rate is
struck against — and the tax is computed on a base nobody reconciled to the GL.

**The rate is the wrong rate.** A classification rate changed mid-year and the
worksheet applied last quarter's rate to this quarter's receipts; the arithmetic
is internally consistent and still wrong.

**A deduction or credit is misapplied.** A standard deduction already exhausted
is taken again, a below-threshold no-tax rule is claimed above the threshold, or
a small-business credit is read off the wrong bracket.

**The calendar has a hole.** An entity-jurisdiction-period that should have a
filing has none, a return was filed after its due date, or filed before anyone
approved it — invisible until an assessment arrives.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 27 controls, writes
`grt_report.json` and `grt_report.md`, and exits with the verdict code. The
corpus contains planted defects on purpose, so a non-zero exit is the engine
working.

## The 27 controls

| Family | Count | Asks |
|---|---|---|
| `set_`   | 1 | Is the reconciliation file complete, and is the review date readable? |
| `ent_`   | 2 | Are the entity ids unique, and is each active entity's filing scope declared and known? |
| `jur_`   | 2 | Does every jurisdiction carry a known cadence and classification, and do its rate windows run forward? |
| `rev_`   | 5 | Is the GL pull well-formed, uniquely keyed, attributable, mapped to a worksheet, and does each worksheet's gross sum the lines under it? |
| `fil_`   | 3 | Is every worksheet well-formed, unique per obligation, and attributable to a known entity and jurisdiction? |
| `eff_`   | 1 | Was the rate the worksheet applied the rate in force for the period? |
| `rate_`  | 2 | Does the pre-credit tax equal base × rate, and the tax due equal pre-credit tax net of credit? |
| `ded_`   | 3 | Does the base re-derive, does the back-out tie the ledger, and does the credit follow the jurisdiction's threshold and small-business rules? |
| `cal_`   | 4 | Is every expected filing present, on time, due-soon-flagged, and approved before it was filed? |
| `lic_`   | 2 | Is each business licence active, and is any renewal due inside the lead window? |
| `rpt_`   | 2 | Does each summarised tax figure recompute from the receipts, and do the portfolio totals tie the summary? |

Three are worth calling out.

**The determination recomputes, it is not read back.**
`rpt_summary_recomputes` is the control the engine exists for. The tax summary is
a *determination*, and a determination that is not recomputed from the receipts
and the rate table is an assertion. The engine rebuilds every tax-due figure from
the worksheet's gross, back-out and standard deduction — base, rate, credit and
net — and compares it to the one on file.

**The rate in force is the rate the period is taxed at.** `eff_rate_matches_period`
looks up the classification rate whose window covers the period's start date and
compares it to the rate the worksheet applied — so a rate that was right last
quarter, applied to a period inside the new window, is caught even though the
arithmetic on it is internally consistent.

**Every tax is re-derived to the cent.** `rate_tax_before_credit_recomputes` and
`rate_tax_due_recomputes` compare with exact `==` using the platform's truncating
basis-point arithmetic. A tax that re-derives to a different cent is a tax nobody
recomputed from the base and the rate.

## The due-soon and renewal windows are flags, not failures

`cal_due_soon` marks an unfiled worksheet whose due date is inside the file's own
lead-time window, and `lic_renewal_current` marks a business licence due to renew
inside it. Both are `REVIEW`-severity: the obligation is not yet late and the
licence is still active, but each needs a human to act before the date passes.

## Tests

```bash
python -m pytest grt_engine/tests -q
```

A clean baseline parametrized over the registry, one planted-defect file per
named control, boundary tests on every cent, rate and date threshold, and
read-only / determinism proofs that hash the corpus before and after a full run.

## The baseline is derived, not typed

Only the entities, the jurisdiction rate table, the GL revenue lines and the
worksheet calendar facts are stated. The generator computes everything the engine
later re-derives — each worksheet's gross, back-out, base, rate, pre-credit tax,
credit and tax due, the per-filing tax summary, and the portfolio totals —
through the *same* computation kernel the engine recomputes with.

So the relationships the engine tests are the same relationships that produced the
data.

---

🔒 **All data is fictional.** The filers, the entities, the taxing jurisdictions,
the classification rates, the GL accounts, the receipts and every filing date are
invented, and every period is set in a fictional future. No employer or client
workpaper, entity, methodology, path or figure is reproduced.
