# Premium Audit Response — `SFS-E51-PRA`

Once a year a general-liability carrier audits the policy: did the insured actually incur the cost
the premium was underwritten on? The raw evidence is a fixed-width job-cost print report — a format
designed for paper — and the traditional workpaper is somebody re-keying it into a spreadsheet,
checked by the person who typed it, against the file they typed.

This engine reads the print instead, and keeps the one safeguard a re-key destroys: **the report's
own printed per-job totals**. Every parsed job must tie its printed total **to the cent, over the
union of jobs parsed and jobs printed**, or the engine refuses to produce a workpaper at all — the
refusal names each failing job and its cent delta. What survives is cut to the policy audit window
(inclusive on both boundary dates), cross-referenced against a certificate-of-insurance coverage
listing, and triaged line by line under a fixed precedence: journal entries that never had a
vendor, clearing accounts (numeric id or the ERP's literal "summary vendor" name), wrap-enrolled
vendors, materials-only and professional exemptions, vendors whose required coverage is current at
the window end, and the remainder marked for certificate chase. The output is a byte-stable
audit-response package — sorted-key JSON plus a Markdown summary, integer cents throughout, every
line in exactly one bucket.

## Run it

```bash
python -m premaudit_engine --seed 7        # generate a fictional print, parse, verify, package
python -m pytest -q                        # 9,648 tests
SWEEP=1 python -m pytest -q                # widen the pipeline grid tenfold
```

Exit codes: `0` package built · `2` refused (printed-total reconciliation failed).

## What the tests pin

- **Printed-total reconciliation** — every seed of the generator round-trips through the parser and
  ties the report's own totals exactly; three planted defect classes (a printed total off by one
  cent, a missing total line, a malformed amount) must each produce a refusal, not a workpaper.
- **Parser edge cases from the field** — vendor continuation across `(Rev)` reversal rows,
  journal lines carrying one reference token instead of two, numeric clearing-account vendors with
  lowercase names, jobs that print a total but carry zero lines, page-break boilerplate mid-job.
- **Window semantics** — inclusive on both ends, asserted against raw date arithmetic across a
  400-day sweep.
- **Triage as a partition** — fixed precedence in code; every line lands in exactly one bucket;
  an unreceived certificate never counts as coverage.
- **Determinism** — same seed, same bytes: the print text, the package JSON, the Markdown.

All data is fictional and seeded. The engine never contacts a carrier, never decides the period
basis, and never writes to its inputs — it reads, re-derives, ties, and reports.
