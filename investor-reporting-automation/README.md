# JV investor reporting package

A deterministic, **read-only** control engine for the monthly financial reporting
package a developer issues to the joint-venture equity partner of a single project
entity — the trial balance, the balance sheet, the statement of operations, the
statement of members' capital, the development cost schedule, the job cost bridge
and the notes, re-derived from the sources that are supposed to produce them and
compared with exact `==`.

Five sources go in: the project entity's general ledger extract, the job cost
detail by division, the executed equity draw schedule, the parent entity's ledger
carrying the reciprocal investment account, and the package issued for the period
before. Seven statements come out, assembled by hand, every month, per project,
per investor. The failure mode is a wrong figure sent to an outside equity
partner.

Five failures found during a manual build of one such package took three rounds
of human review to surface. None of them looked wrong on the page.

**A difference gets dropped rather than disclosed.** A job cost report and a
ledger differ routinely and for good reasons — interest capitalised in one and
not the other, an accrual posted after the cost cut-off. The control is not that
they agree. The control is that the difference is itemized and disclosed, because
the alternative is what happens: the gap is absorbed into a rounding line and the
partner is told a figure nobody can rebuild.

**A contribution agrees to nothing.** The contribution column is typed from a
funding notice rather than footed from the draw schedule the partner also holds,
and the variance is never quantified.

**A caption outlives its schedule.** A cost-to-date schedule keeps a caption
saying the cost arose in the period, so a reader adds a month of spend that was
really every month since the ground broke. Every figure on the page is right.

**The cover contradicts the notes.** The basis of presentation asserts the
package is free of exceptions while the notes disclose one — on the page most
readers read closest.

**A tie-out check row is left in the print area.** The reviewer's own arithmetic
ships to the investor as though it were a line of the statement.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 25 controls, writes
`investor_report.json` and `investor_report.md`, and exits with the verdict code.
The corpus contains planted defects on purpose, so a non-zero exit is the engine
working.

## The 25 controls

| Area | Count | Asks |
|---|---|---|
| Trial balance | 3 | Does it net to zero, does it cover every ledger account with activity, and does each balance agree to its ledger account **by account number**? |
| Balance sheet | 2 | Does every section foot and does the statement balance, and is a credit intercompany balance reclassified rather than netted against assets? |
| Members' capital | 5 | Does each member's ending balance agree to its ledger capital account, do the contributions foot, does the Total column cross-foot every row, does each member roll forward, and does the result agree to the statement of operations? |
| Development & job cost | 3 | Does the development cost schedule tie to work in process, does the job cost bridge close with every difference itemized and disclosed, and is every division covered? |
| External agreement | 2 | Do contributions agree per member to the executed draw schedule, and does the parent's investment account agree to the capital it represents? |
| Presentation | 5 | Is a nil statement genuinely nil, is cash supported, does every quoted footnote figure match its cell, does every caption fit its schedule, and does the cover agree with what the notes disclose? |
| Release | 5 | Are the tie-out rows and preparer artifacts out, does the package continue from last period, is it complete, and was it allowed to leave? |

Five are worth calling out.

**Balances are matched by account number, never by row position.**
`tb_agrees_ledger` joins the package trial balance to the ledger extract on the
account number and only on the account number. A trial balance is exported in
reading order and a ledger extract comes out in account order, so a package
assembled by pasting one column beside the other agrees on the rows where the two
orders happen to coincide and is wrong everywhere else — and it foots, and it
nets, and it balances. When a stated balance disagrees with its own account but
does match the ledger account in the *same row position*, the finding says so.
That is the fingerprint of a positional paste, and naming it saves the hour it
otherwise takes to work out why two unrelated figures are both wrong by the same
pair of amounts.

**A difference has to be disclosed, not reconciled away.** `jobcost_bridge`
requires the report plus everything itemized against it to reach the ledger
*exactly* — no closing tolerance, because a bridge that nearly closes has an
unexplained figure in it — and it fails any reconciling item carried in the bridge
without being disclosed.

**Activity is not the same thing as a balance.** `tb_completeness` reads either
column, never the net. A clearing account that took in an amount and released the
same amount has a nil balance and is exactly the account a package drops, and
dropping it hides the whole of what it did.

**The Total column is a Total column on every row.** `total_cross_foots` sums the
member columns across every row of the capital statement, including the
sharing-ratio row. The defect it exists for is a Total cell linked somewhere else
instead of summing the row it sits on — to the ledger, to a funding notice, to
last period's total. Such a cell is right often enough to survive review and
wrong exactly when a member column moves, which is the month it matters.

**Nothing leaves over an open exception.** `release_gate` is the only control that
reads the run's own output, and it is the reason the engine is worth running: one
open exception holds the package. There is no materiality gate, and there should
not be — materiality is a judgement about a figure the partner has not seen yet,
and the engine's job is to make sure whoever makes that judgement is looking at
the exception rather than at a package already in the partner's inbox.

## Deliberately out of scope — these need a human

Documenting the boundary matters as much as the controls.

**Classification judgement.** A cost the ledger labels a lender's underwriting
charge, whose payment went to an investor affiliate, and which the draw schedule
calls investor due diligence. The engine reports that two sources disagree; it
must not pick a winner.

**Anything gated on a document that does not exist yet.** `cash_supported` flags
a cash balance whose bank reconciliation has not arrived. It cannot manufacture
the support, which is why it is a `REVIEW` flag and not a failure.

**Disclosure wording.** Whether and how to tell the partner about an exception is
a decision, not a computation. The engine insists the difference is quantified and
disclosed; it writes none of the sentence.

**The ledger extract itself.** The pull stays manual and automation begins
downstream — the same boundary the other systems in this portfolio accept.

## Tests

```bash
python -m pytest investor_engine/tests -q
```

A clean baseline parametrized over the registry, one planted-defect file per named
control, boundary tests on every cent, and read-only / determinism proofs that
hash the corpus before and after a full run.

## The package is derived, not typed

Only the base facts are stated: the non-capital ledger accounts, the job cost
detail by division, the cost carried in the ledger and not in the cost report, the
equity draw schedule, the prior package's closing capital, each member's
distributions and sharing ratio, the presentation the statement of operations
declares, the cover's assertions, the notes' cell references, the tie-out rows and
the artifact list.

The generator computes everything the engine later checks as a derived figure —
the trial balance, the balance sheet and its section totals, every capital column
and the Total column across it, the contribution detail, the development cost
total, the job cost report total, the bank reconciliation balances, the parent's
reciprocal investment and every figure quoted in a note — through the *same*
package kernel and the same `recompute_*` helpers the controls recompute with.

So the relationships the engine tests are the same relationships that produced the
data. A defect that changes a base fact re-derives the package and keeps the break
confined to one control; a defect that targets a stated figure edits that figure
alone.

Every defect file in the corpus is also marked **held**, because a package with a
known exception is held. That is not bookkeeping convenience: a defect file that
stayed marked released would trip the release gate as well as its own control, and
a corpus in which one break fires two controls cannot prove that either of them is
independent. The gate's own file is the exception, because being released over an
open exception is what it is for.

---

🔒 **All data is fictional.** The project entities, the members, the chart of
accounts, the divisions of job cost, the equity draws, the notes and every balance
and reporting date are invented, and the reporting period is set in a fictional
future. No employer or client workpaper, entity, person, project, street,
neighbourhood, methodology, path or figure is reproduced.
