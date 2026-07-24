# Expense & P-Card automation

A deterministic, **read-only** control engine for employee expense reports and
company purchasing-card (P-Card) spending — every charge on a bank statement
reconciled to a receipted, coded, approved line on an expense report.

A company does not reimburse a card statement on trust. It issues a card, the
bank issues a statement, and the cardholder owes a matching expense report: one
line per charge, each with a receipt on file, a business purpose, a valid GL code
and a real project, filed inside the submission window, under the per-charge
limit, approved by somebody other than the cardholder.

Three failures hide inside that, and none of them look wrong in a page of small
numbers.

**The charge that never gets reported.** A statement line with no matching report
line is a company expense nobody coded and nobody has a receipt for. It does not
fail a total — the total is simply lower than the bank's — so it surfaces only
when the report is reconciled line by line against the statement.

**The residual cent between the report and the bank.** A report can foot to a
tidy round number and still be a penny off the statement it is meant to mirror.
Reconciliation is exact here: every statement line ties its report line to the
cent, and the report total ties the statement total to the cent.

**The charge that should never have been on the card.** A charge over the limit,
in a disallowed merchant category, coded to a project that does not exist, or
approved by the person who incurred it — each is a control break that a footed,
receipted report will still carry straight through.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 23 controls, writes
`expense_report.json` and `expense_report.md`, and exits with the verdict code.
The corpus contains planted defects on purpose, so a non-zero exit is the engine
working.

## The 23 controls

| Family | Count | Asks |
|---|---|---|
| `set_`  | 1 | Is the cycle file complete, and is the review date readable? |
| `card_` | 4 | Is every cardholder fully described, with a unique id, a valid card last four and a known home entity? |
| `stmt_` | 4 | Are the statement lines complete, uniquely identified, integer cents, and tagged with the cardholder's own card? |
| `rpt_`  | 3 | Does every report line carry its fields, a receipt on file and a stated business purpose? |
| `rec_`  | 4 | Does every charge reconcile to exactly one report line to the cent, with no orphan line, and do the report and ledger totals tie? |
| `cod_`  | 3 | Is every line coded to a valid GL account and a real project, and is any disallowed category flagged? |
| `pol_`  | 3 | Filed within the window, under the per-charge limit, and approved by a second person? |
| `dup_`  | 1 | Is any charge a duplicate of another on the same card? |

Three are worth calling out.

**Every charge reconciles, it is not just totalled.** `rec_every_charge_reported`
is the control the engine exists for. A statement line with no report line is a
company expense nobody coded and nobody has a receipt for; one with two report
lines is a charge claimed twice; one whose report line differs by a cent has not
reconciled. All three are invisible in a footed total, so the engine matches
every charge to exactly one report line and ties the amount to the cent. Its
sibling `rec_report_total_ties` catches the whole report drifting from the bank,
and `rec_no_orphan_report_line` catches a reimbursement claimed for a charge the
bank never made.

**A receipt and a purpose are the evidence, not decoration.**
`rpt_receipt_on_file` and `rpt_purpose_present` hold every line to the two things
that make a charge auditable after the fact — proof it happened at the amount
claimed, and a stated reason it was an appropriate use of the card. A blank
purpose passes the schema and fails the test.

**The card's spending controls are controls.** `pol_per_charge_limit`,
`pol_approver_distinct` and `cod_disallowed_category` are the checks that a
footed, receipted report will still walk straight past: a charge one cent over the
limit, a report the cardholder signed off themselves, a cash advance or bar tab a
reviewer should always see by hand.

## Integer cents, no tolerance

Every amount is an integer number of cents, and every reconciliation is compared
with exact `==`. A value that should be integer cents but arrived as a float is
**reported, never coerced** — silently rounding a source figure would make the
engine the author of the number it is meant to audit. One malformed amount is
contained to its row, so the rest of the file is still read.

## Tests

```bash
python -m pytest expense_engine/tests -q
```

A clean baseline parametrized over the registry, one planted-defect file per
named control, boundary tests on every cent and day threshold, and read-only /
determinism proofs that hash the corpus before and after a full run.

## The baseline is derived, not typed

Only the cardholders, the policy, the projects and the charges are stated. The
generator computes everything the engine later checks as a tie-out: each report
line's amount from its statement charge, and the general-ledger P-Card total from
the report lines. So the relationships the engine tests are the same
relationships that produced the data.

---

🔒 **All data is fictional.** The companies, the cardholders, the merchants, the
card numbers and every amount are invented, and the statement cycle is set in a
fictional future. No employer or client workpaper, entity, methodology, path or
figure is reproduced.
