# Sophon Finance Systems — LinkedIn content queue

Each post is ready to paste. Post 1 is the launch (self-healing loops). Posts 2–15 are one per engine.
Drop the GitHub link as the FIRST COMMENT on each (LinkedIn suppresses reach on posts with outbound links in the body).

First comment for every post:
    Code + tests (public, fictional data): github.com/sophonfinance-wq/finance-automation-portfolio

Cadence suggestion: 1 post/week, Tue or Wed ~9am your time. I can render a matching graphic for each on request.

---

## Post 2 — Month-End Close

Close week is five days of copying numbers between spreadsheets and praying they tie.

We built an engine that does the mechanical part and — this is the part that matters — proves it.

It drafts every recurring entry, rolls the schedules forward, ties each balance back to its support, and runs a ten-control checklist over its own work: Does every intercompany entry mirror to the cent? Did a fully-depreciated asset quietly keep depreciating? Did a closed period get edited after sign-off?

We test that layer by trying to break it — we inject twelve classic close errors and confirm the controls catch every one. Then a shadow recomputation re-derives every posted amount from scratch and refuses to agree with a number that's off by a single penny.

The close still ends where it should: with your controller approving it. But they're approving finished, evidenced work — not assembling it.

Close in days, not weeks. Every entry with its receipts attached.

#Finance #Accounting #MonthEndClose #Controllership #AI #Automation

---

## Post 3 — Cash & Debt Reconciliation

"It's off by $312 and I've been staring at it for an hour."

Every accountant has lived this. One figure won't tie, and finding it is a manual hunt across statements, the GL, and a dozen reconciling items.

Our reconciliation engine matches the GL to the bank and the lender automatically, classifies what's left by materiality, and writes the evidence log as it goes — so the reconciling items come with their explanation, not a question mark.

The point isn't just speed. It's that the engine has to *show its work*: every match is cited, every residual is quantified, and nothing is called "reconciled" that the numbers don't support.

Your team stops hunting for the $312 and starts reviewing why it's there.

Every account. Every dollar. Proven.

#Finance #Accounting #Reconciliation #CashManagement #AI #Automation

---

## Post 4 — Cross-Border Tax (Surplus / ACB)

Here's a $660 error that a blended exchange rate will hide from you every time.

An entity contributes capital in one year and returns it the next. In its own currency, the cost base nets to zero — contribution in, contribution out. Translate that net-zero balance at one year's FX rate and the Canadian dollar cost base looks like zero too.

But Canadian tax law translates each capital event at the rate in effect *when it happened*. Do it layer by layer and the CAD cost base is actually **(660.35)** — negative. The sign flips. That's a real deemed gain a single rate silently buries.

Our surplus/ACB engine tracks foreign-affiliate surplus pools and cost base year by year, entity by entity, translating every layer at its own rate — and it checks fifteen named reconciliation identities before it prints a number.

Cross-border tax done as a re-runnable system, not a heroic spreadsheet.

#Tax #InternationalTax #Finance #Accounting #AI #Automation

---

## Post 5 — Triangulate (AI validation)

The most important thing our AI does is get told "no."

Putting a language model into financial work is easy. Trusting it is the hard part — because a model that checks its own answer will happily approve its own mistake.

So Triangulate never lets one model validate its own output. A preparer builds the work, a reviewer challenges it, a specialist weighs in, and then a deterministic auditor re-derives every figure from the source and can reject the whole thing. A human signs off last.

We proved it on ourselves: we fed in a report with one made-up revenue figure that quietly cascaded into the tax and net lines. The controls raised six critical tie-out breaks and returned FAIL — before it could ship. No model was asked "does this look right?" The arithmetic decided.

Three independent checks argue so you don't have to. And any one of them can stop the work — including ours.

#AI #Finance #Accounting #AIGovernance #Automation #FinTech

---

## Post 6 — Knowledge Brain

Your best accountant is a flight risk, and their knowledge walks out with them.

We built an engine that keeps it. Feed it meeting transcripts and workpapers and it becomes a queryable memory of how your team actually decides things — but with one rule that makes it trustworthy: it will not answer without a source.

Ask it something the record doesn't support and it refuses, rather than inventing a confident-sounding guess. Every answer comes with a verbatim, timestamped citation you can click back to. And its review pass turns a reviewer's corrections into cited change-directives — so a fix gets applied, not lost in an inbox.

Institutional knowledge that doesn't quit, retire, or misremember — and never makes something up.

#KnowledgeManagement #Finance #Accounting #AI #Automation #FinTech

---

## Posts 7-15 — the engines shipped in the 39-47 build cycle

Posts 2-6 above predate the current voice rules in `SKILL.md` (they still carry em-dashes and
Title-Case hashtags). Posts 7-15 below follow the current standard: hard opener, credentials for
credit, no em-dashes in the body, short uneven sentences, three lowercase hashtags, site and email in
the body, GitHub as the FIRST COMMENT, soft CTA. Rewrite 2-6 into that voice before reusing them.

Every figure below is live from the repo: control counts are `len(REGISTRY)`, test counts are
`pytest --collect-only` on that engine's own directory.

| # | Post | Engine | Controls | Tests |
|---|---|---|---:|---:|
| 39 | 7  | Section 263A Interest Capitalization | 19 | 10,323 |
| 40 | 8  | Franchise Tax Combined Apportionment | 21 | 10,344 |
| 41 | 9  | Debt Term-Sheet Sizing & Loan Terms | 21 | 10,338 |
| 42 | 10 | Unit Sales & Commission Tie-Out | 21 | 10,355 |
| 43 | 11 | G&A Expense Allocation | 22 | 10,404 |
| 44 | 12 | Outstanding Check Aging & Escheatment | 20 | 10,361 |
| 45 | 13 | Project Variance & Business-Plan Compare | 22 | 10,411 |
| 46 | 14 | Contingency Rollforward & Adequacy | 22 | 10,368 |
| 47 | 15 | Information Return Issuance | 22 | 10,382 |

Pair each with its house-style tile from `docs/assets/engine-<slug>.svg`.

---

## Post 7 — Section 263A Interest Capitalization

```
Most capitalized interest numbers I've reviewed were last recomputed the year they were set up.

18 years closing the books for Fortune 100 and 500 companies. Sophonnarith Hang, senior accounting and tax, GAAP/FAR/CAS.

Here's the thing about 263A(f). The avoided-cost method isn't complicated. Accumulated production expenditures times the period rate, quarter by quarter, project by project. It's just tedious, and it lives in a spreadsheet somebody built once.

So the grid stops footing. A quarter gets restated and the annual total doesn't move. Interest capitalized plus interest deducted stops equalling the interest that was actually incurred, which means some of it went nowhere. And the prior-year column gets typed in from last year's return instead of tied to it.

We built an engine that re-derives all of it. 19 controls. It rebuilds every quarter's capitalized interest from the expenditures and the rate, foots the grid both directions, proves capitalized plus deducted equals incurred, checks completeness against the entity trial balance so a project can't quietly drop out, and ties the year-over-year comparison to the prior filing rather than accepting a typed number.

10,323 tests. Integer cents, compared exactly. No tolerance band, because a cent off a re-derivation isn't rounding, it's a break.

It's read-only. It never posts anything. It hands your preparer a list of exceptions and the reason each control exists.

All fictional data, MIT licensed. Run it yourself: sophonfinance.com
sophonfinance@gmail.com

If your 263A workpaper hasn't been re-derived since the year it was built, message me. I'll show you what I'd check first, free.

#finance #accounting #ai
```

**First comment:** `Code and all 10,323 tests: github.com/sophonfinance-wq/finance-automation-portfolio/tree/main/interest-capitalization-automation`

---

## Post 8 — Franchise Tax Combined Apportionment

```
A combined franchise return is four numbers multiplied together. I've seen all four go wrong at once.

18 years closing the books for Fortune 100 and 500 companies. Sophonnarith Hang, senior accounting and tax, GAAP/FAR/CAS.

Taxable margin, times apportionment, times rate. That's the tax. The trouble is upstream.

The affiliate roster drifts. Last year's members plus additions less removals should equal this year's roster, and when it doesn't, an entity is either being taxed twice or not at all. Group revenue gets keyed off a summary tab instead of tied to the consolidated tax trial balance. The receipts factor comes back above 100% or below zero, which is arithmetically impossible and still gets filed. And then the tax itself is a typed figure that nobody re-multiplied.

21 controls that settle each of those. The roster reconciled as a set, not eyeballed. Group revenue tied to the trial balance underneath it. The single receipts factor recomputed and bounded. The tax re-derived as margin times apportionment times rate and compared exactly.

10,344 tests behind it.

Whether your combined group is drawn correctly is a judgment call. I'm not automating that. What the engine does is prove the return foots to the workpapers it came from, which is the part that shouldn't require judgment and usually gets it anyway.

Fictional data throughout, MIT licensed: sophonfinance.com
sophonfinance@gmail.com

If your combined return is assembled by hand every year, message me. Happy to show you where these break.

#finance #tax #ai
```

**First comment:** `Code and all 10,344 tests: github.com/sophonfinance-wq/finance-automation-portfolio/tree/main/franchise-tax-automation`

---

## Post 9 — Debt Term-Sheet Sizing & Loan Terms

```
The loan gets sized in a term sheet, and the term sheet gets checked by whoever isn't busy.

18 years closing the books for Fortune 100 and 500 companies. Sophonnarith Hang, senior accounting and tax, GAAP/FAR/CAS.

Four things go wrong before close, and none of them look wrong on the page.

The maximum loan drifts past the advance rate. Not by much, and the cap is a multiplication nobody redoes. The all-in rate gets quoted as index plus spread when there's a floor in the document, and the floor is higher. A fee gets struck on the wrong base, commitment fee on the funded amount instead of the commitment. And maturity gets stated as a date rather than base term plus the extensions actually exercised.

21 controls. The engine holds the maximum loan to advance rate times cost basis, re-derives the all-in rate as the greater of index plus spread or the floor, checks every fee against its correct base, proves maturity equals base term plus exercised extensions, and foots the portfolio rollup back to the deals underneath it.

10,338 tests. Truncating basis-point arithmetic, so a derived rate can be compared to a stated one exactly instead of within a band.

It reads the term sheet and stops. It doesn't approve anything, and it has no opinion on whether the deal is a good deal.

Fictional data, MIT licensed, runnable: sophonfinance.com
sophonfinance@gmail.com

If your term sheets get checked by hand before close, message me. I'll show you what I'd automate first, free.

#finance #realestate #ai
```

**First comment:** `Code and all 10,338 tests: github.com/sophonfinance-wq/finance-automation-portfolio/tree/main/debt-sizing-automation`

---

## Post 10 — Unit Sales & Commission Tie-Out

```
A cent of commission drift doesn't sound like a problem until you remember it's on every unit in the project.

18 years closing the books for Fortune 100 and 500 companies. Sophonnarith Hang, senior accounting and tax, GAAP/FAR/CAS.

A for-sale housing project runs out of one workbook, instantiated from the same template every time. The Matrix tab carries every unit. A Sold/Close tab logs the dates. A Commission Log splits each unit's commission across the agents who earned it.

Three things fail in every instantiation.

A derived column stops deriving. Revenue per square foot, net proceeds, total commission. All formulas until somebody types over one cell for one unit, and then the column is a mixture of computed and typed figures that doesn't follow from the prices beside it. You cannot see that on a printed tab.

The splits stop adding up. The Matrix authorised a total. The log pays named agents. A split edited after the fact, or an agent added without reducing another, and the log is paying an amount no row ever approved.

And the tabs stop reconciling. A unit marked sold that never reaches the Sold/Close tab. Worse, a closing logged for a unit the Matrix doesn't call sold, which is a settled sale nobody counted. That second direction is the one people don't check.

21 controls. Every derived column rebuilt from the base prices. Splits compared to the authorising row in integer cents, exactly. The reconciliation run both ways. The residual cent on a three-way split placed by largest remainder so it lands on a named agent instead of vanishing into rounding.

10,355 tests.

Read-only. It never releases a commission payment. It tells your sales administrator which row to look at and why.

Fictional data, MIT licensed: sophonfinance.com
sophonfinance@gmail.com

If your sales matrix gets re-added by hand every week, message me. I'll show you what I'd check first, free.

#finance #accounting #ai
```

**First comment:** `Code and all 10,355 tests: github.com/sophonfinance-wq/finance-automation-portfolio/tree/main/unit-sales-automation`

---

## Post 11 — G&A Expense Allocation

```
"The allocation adds up to 99.97%." It never gets fixed, because nobody's sure which entity is short.

18 years closing the books for Fortune 100 and 500 companies. Sophonnarith Hang, senior accounting and tax, GAAP/FAR/CAS.

A holding entity pushes overhead across a dozen operating entities every month on driver counts. Headcount, square footage, whatever the policy says. It's simple arithmetic and it breaks constantly.

Driver shares that total 99.97% or 100.02%, because somebody rounded percentages to two decimals and moved on. Allocated dollars that don't total the pool, so overhead is either stranded in the holding entity or invented in the operating ones. A residual cent that gets dropped rather than placed. An allocation entry that balances within one entity but doesn't net to zero at consolidation, which means the elimination is wrong and nobody notices until the auditors do.

22 controls. Shares proved to total exactly 100%. Allocated dollars proved to total exactly the pool, to the cent. The residual cent placed deterministically by largest remainder, so it lands somewhere defensible and lands in the same place every run. The journal entry balanced and proved to net to zero at consolidation. And the postage allocation reconciled to the meter reading delta, because that one is always a plug.

10,404 tests. Integer cents throughout.

The engine flags exceptions. It doesn't post the entry. Your controller still approves it, just with the arithmetic already settled.

Fictional data, MIT licensed, run it yourself: sophonfinance.com
sophonfinance@gmail.com

If your monthly allocation is a spreadsheet with a plug in it, message me. Free, and I'll be specific.

#finance #accounting #ai
```

**First comment:** `Code and all 10,404 tests: github.com/sophonfinance-wq/finance-automation-portfolio/tree/main/ga-allocation-automation`

---

## Post 12 — Outstanding Check Aging & Escheatment

```
An uncashed check isn't a stale payable forever. At some point it becomes the state's money, and you're holding it.

18 years closing the books for Fortune 100 and 500 companies. Sophonnarith Hang, senior accounting and tax, GAAP/FAR/CAS.

Most outstanding-check lists I've seen are trusted, not derived. There's a column that says outstanding and everyone reads it.

So the population is wrong. A check that partially cleared still shows outstanding. A voided check and a stop-payment sit in the list even though nothing is owed on either. And the real problem is that stale-dating and dormancy get treated as one thing. They aren't. Stale-dated means the bank may refuse it and you should follow up. Past dormancy means it's unclaimed property that belongs to a state, and which state depends on the account, not on where your office is.

20 controls. The outstanding set rebuilt from cleared amounts and cleared dates rather than the stated column. Every item aged from check date to the file's own as-of date, never the system clock, so a run in a later month returns the same answer. Six aging bands. The total tied to the outstanding-checks line on the bank reconciliation. Voids and stop-payments proved absent from the population, with the reversal proved to net to zero. And stale-dating kept separate from dormancy, so your follow-up list isn't confused with your escheatment list.

10,361 tests. Both thresholds crossed strictly, so an item exactly at the threshold isn't yet past it.

It never voids or reissues anything. It produces a list and the reason each item is on it.

Fictional data, MIT licensed: sophonfinance.com
sophonfinance@gmail.com

If nobody owns your unclaimed property filing, message me. That's usually the answer, and it's usually expensive.

#finance #accounting #ai
```

**First comment:** `Code and all 10,361 tests: github.com/sophonfinance-wq/finance-automation-portfolio/tree/main/check-aging-automation`

---

## Post 13 — Project Variance & Business-Plan Compare

```
The variance column is the most-read number in a project report and the one nobody re-adds.

18 years closing the books for Fortune 100 and 500 companies. Sophonnarith Hang, senior accounting and tax, GAAP/FAR/CAS.

Every period each development proforma gets re-issued as a project report. Six metrics in three columns: this period, last period, and what the approved Business Plan said. A budget tab splitting each cost line into Total Budget, Cost to Date, Cost to Complete. A milestone block with dates against a frozen baseline.

Four things break, and three of them are the same mistake.

A variance stops being a formula. Somebody types over one cell and it no longer equals the difference of the two columns it sits between. Cost to Complete stops being the remainder, maintained beside the budget instead of struck as Total Budget less Cost to Date, so spending climbs, the remainder doesn't move, and an overrun rides in a column nobody re-added. And the Business Plan column gets quietly pointed at a revision nobody approved, which is the worst of the three because it makes every plan variance smaller at once. Nothing looks wrong. Everything looks better.

The fourth one nobody checks at all: a comparative column that doesn't foot inside itself. The Prior and Business Plan columns each carry their own revenue, deductions and expense, so each has its own profit and margin that have to re-derive. A variance measured against a column that never added up is measuring nothing, and no current-period control would ever notice.

22 controls. Every derived figure rebuilt from its own inputs. Every variance re-struck as the difference of the two columns beside it, in cents and in basis points alike. Both comparatives proved to foot inside themselves. The plan column proved against the version each project was actually approved under. And every milestone variance re-derived under one convention: plus means ahead, so it's the comparison date less the current date, never the other way round. A flipped sign turns two weeks of slippage into two weeks of progress on the page a committee reads.

10,411 tests. Behind by exactly the tolerance is at the tolerance, not past it.

It reads the report and stops. It never re-forecasts anything.

Fictional data, MIT licensed, run it yourself: sophonfinance.com
sophonfinance@gmail.com

If your project reports get re-added by hand every period, message me. I'll show you what I'd check first, free.

#finance #realestate #ai
```

**First comment:** `Code and all 10,411 tests: github.com/sophonfinance-wq/finance-automation-portfolio/tree/main/project-variance-automation`

---

## Post 14 — Contingency Rollforward & Adequacy

```
"Adequate" is a comparison. It gets stored as a label. That's the whole problem.

18 years closing the books for Fortune 100 and 500 companies. Sophonnarith Hang, senior accounting and tax, GAAP/FAR/CAS.

Every active project carries two contingency buckets, and every period somebody restates the block by hand. Six numbers and a word. Prior balance, allocated this period, allocated to date, balance remaining, projected potential use, and whether what's left is adequate.

The word goes stale first. It gets carried forward from a period when it was true while the projected use climbs past the balance behind it, and the block keeps saying adequate because nobody re-struck the comparison that made it so.

Then the rollforward stops rolling. Prior balance less allocated this period is the balance remaining, until somebody types over the current figure for one project. From then on the block is a mixture of rolled and typed balances that doesn't follow from the period before it, and it survives every period after.

And the allocated total stops matching the draws. It's maintained beside the draw detail instead of footed from it. So a draw never reaches the total, or one draw is written for more than the balance it draws against and the bucket goes overdrawn in a column nobody re-added.

22 controls. Both rollforwards recomputed from the period before them. The allocated total footed to the draw detail it summarises. Every bucket reconciled back to the contingency line the project budget actually funded. Each draw walked against the balance earlier draws left it, not against the opening balance, because that's the direction that catches a bucket drawn past empty by one large release while the period total still looks reasonable. And the word adequate rebuilt from the two amounts underneath it, so a label can't outlive the period it stopped being true.

10,368 tests. A draw exactly equal to the balance in front of it spends the bucket to zero and is allowed. A cent more is an overdraw.

I'm not forecasting anything. Whether the projected use is a sound estimate is a judgment no engine makes. This is the narrower question, and it's the one that's pure arithmetic.

Fictional data, MIT licensed: sophonfinance.com
sophonfinance@gmail.com

If your contingency block is restated by hand every period, message me. Free, and I'll be specific.

#finance #construction #ai
```

**First comment:** `Code and all 10,368 tests: github.com/sophonfinance-wq/finance-automation-portfolio/tree/main/contingency-rollforward-automation`

---

## Post 15 — Information Return Issuance

```
A payee who should have been reported and wasn't leaves nothing behind to notice.

18 years closing the books for Fortune 100 and 500 companies. Sophonnarith Hang, senior accounting and tax, GAAP/FAR/CAS.

The payments posted. The invoices closed. The omission exists only in a population nobody re-ran, because the ledger was never organised around who has to receive a form.

Once a year the group rebuilds that population from scratch, entity by entity. Interest to lenders and affiliates. Non-employee compensation to vendors. Card and third-party settlement. Apply the box threshold, issue the form, reconcile each box back to the payment lines it came from.

The missing form is the failure everyone worries about. Its exact opposite is the one nobody builds: a form issued where nothing was owed. That isn't harmless excess. It reports a payee who wasn't reportable, and now that payee reconciles a statement against a return that should never have been filed.

Between them sits a rule that catches people out. Where a box attracts backup withholding and the payee has no taxpayer number on file, tax gets withheld, and withheld tax is reported however small the payment was. So a payee paid far under the threshold can still be owed a form. And a payee with no number isn't a data-quality problem, it's a withholding case. The real problem is a number that was captured and can't be read, because it counts as on file, suppresses the withholding that should have been taken, and prints on the form unusable.

22 controls. Every box amount footed back to the entity's own payment lines instead of re-keyed from a summary. A form proved to exist exactly where the threshold or the withholding override obliges one, and nowhere else, both directions resolved through one predicate so completeness and excess can't disagree. Withholding recomputed at the statutory rate in both directions: missing tax is the group's own liability, tax taken anyway is the payee's money held without cause. And every transmittal recounted from the forms behind it, because that's the one page the authority reads first.

10,382 tests. The threshold is met at the cent. A year total of exactly the threshold is reportable and a cent under it isn't, and the test corpus puts a real row on that edge.

It never issues a form or files a transmittal. It produces the exceptions before the forms go out.

Fictional data, MIT licensed: sophonfinance.com
sophonfinance@gmail.com

If nobody re-runs your 1099 population before it goes out, message me. That's usually the answer.

#finance #tax #ai
```

**First comment:** `Code and all 10,382 tests: github.com/sophonfinance-wq/finance-automation-portfolio/tree/main/info-return-automation`

---

## Optional: engagement heartbeat (once tools are approved)
- Watch the launch post's early comments/DMs and flag anything worth a same-day reply (interest is warmest in the first 24h).
- Weekly: check repo traffic/stars and surface which post drove it, so we double down on what lands.
- Every reply still routes to you before it sends.
