# Case Study — From Real Engagements to Runnable Systems

> 🔒 **Confidentiality posture.** This case study describes the *class* of finance and tax work
> behind this portfolio and the competencies it demonstrates, using only **public tax/accounting
> concepts** and this repo's **fully fictional** systems. It reproduces **no** employer or client
> entity, person, structure, methodology, figure, file path, meeting, or workpaper. The discretion
> is the point: the way to prove I can handle sensitive financial data is to rebuild the
> *capability* while protecting the *source*.

---

## The short version

For years I did genuinely hard finance and tax work by hand under partner review — Canadian
cross-border foreign-affiliate tax, US partnership tax, multi-entity month-end close, and
construction/JV audit support — inside a privately held real-estate group. I also
built an internal **knowledge brain**: I recorded every engagement meeting, transcribed it, and
loaded it into a queryable knowledge base so prior decisions could be cited word-for-word in
workpapers. Then I re-engineered each *class* of that work into tested, deterministic, audit-ready
Python systems on **fully synthetic data**, and built a control framework so AI can accelerate it
without becoming the weakest link. This portfolio is that proof: **fifty runnable systems, a
504,712-test curated suite (plus an opt-in ~1.65M-case property sweep), CI.**

---

## What the work actually involved (described generically)

| The real work (public-concept level) | The system that demonstrates the skill |
|---|---|
| **An internal "finance brain."** Recording engagement meetings, transcribing them, and loading them into a queryable knowledge base used *before* the work to prep, and *during* the work to cite a prior decision **word-for-word, with date + timestamp**, in a workpaper or disclosure note. | [`knowledge-brain-engine`](../knowledge-brain-engine/) |
| **Canadian foreign-affiliate surplus & ACB (CRA Form T1134).** Maintaining — year by year, entity by entity, across a multi-tier cross-border ownership structure — the **exempt / taxable / pre-acquisition** surplus pools and the **adjusted cost base** of each investment, for eventual tax-efficient repatriation. | [`tax-surplus-engine`](../tax-surplus-engine/) |
| **US partnership tax with IRC §704(c).** Form 1065 / Schedule K-1 assembly *and* **built-in gain** on contributed property — book vs. tax capital, the **traditional method / ceiling rule**, tax-basis financials. | [`partnership-1065-automation`](../partnership-1065-automation/) |
| **Multi-entity month-end close.** Recurring journal entries (prepaid amortization, depreciation, deferred rent/CAM, accrued management fees, intercompany note interest) and cross-entity G&A/insurance allocations, with schedule-to-GL tie-outs. | [`monthly-close-automation`](../monthly-close-automation/) |
| **Construction / JV project audits.** Pulling GL, job-cost, and check-register detail from a construction-accounting ERP for annual partner and external audits; classifying materiality; tracing a selection to source. | [`cash-reconciliation`](../cash-reconciliation/) + [`audit-automation`](../audit-automation/) |
| **Reviewer-driven QA, formalized.** Building a deliverable, then having it **independently reviewed against the reviewer's own words** before sign-off — a discipline I turned into a separation-of-duties control framework for AI-assisted work. | [`ai-validation-framework`](../ai-validation-framework/) (Triangulate) |

---

## The knowledge brain, in detail

This is the least common system in the set, so it is worth describing in full. The real workflow:
**record → transcribe → ingest → query.** Meetings stop evaporating; they become institutional
memory that can be *cited*, not paraphrased from recall.

The public [`knowledge-brain-engine`](../knowledge-brain-engine/) reproduces it on fictional
transcripts, with three query modes and one non-negotiable control:

- **`ask`** — retrieve the top matching decision/rule, each with a citation block.
- **`--prep`** — before a meeting, assemble every prior decision, rule, and open item on a topic,
  each already cited.
- **`--cite`** — while writing workpaper logic or a disclosure note, get the single authoritative
  prior statement back as a **paste-ready footnote**, quoted verbatim with `[Title — Date —
  HH:MM:SS — Speaker]`.
- **`remediate` — review → remediation.** After a recorded **review meeting**, the
  reviewer's spoken corrections are captured as cited **change-directives** (verbatim quote + date +
  `HH:MM:SS` + speaker), and the engine **generates an apply-ready, cited remediation prompt** plus a
  **cited change-log** mapping each directive → source → status. A downstream AI or operator uses that
  prompt to apply the changes — **the transcript is the instruction set**, and application and
  verification happen downstream.
- **Governance:** every answer carries a source; if nothing clears the relevance floor — and if a
  review topic has no directives on record — the engine **refuses to guess** rather than fabricating
  an uncited answer or inventing corrections.

That is retrieval with the discipline a workpaper or an auditor actually requires: provenance
travels with every quote, and the quote is byte-identical to the transcript.

---

## Three lessons from real reviews that became engineering

Each is now encoded as a control in the portfolio:

1. **Evidence has to foot to an anchor.** A reviewer trusts a running balance that ties to the
   workpaper, not a pasted screenshot. → every engine emits a reviewable evidence trail; the
   [validation engine](../audit-automation/) is **read-only** and hashes files before/after to prove
   it never mutated what it checked.
2. **Formulas have to survive a copy/paste.** A single cell reference drifting to the wrong column
   silently corrupts a roll-forward across every year. → the engines are formula-driven and **pinned
   by tests**, not hand-keyed.
3. **A return of capital beyond basis is a taxable event, not a floor.** Clamping basis at zero hides
   a real gain. → the [surplus engine](../tax-surplus-engine/) **surfaces the deemed gain**
   (ITA 40(3)-style) when a return of capital drives ACB below zero, rather than silently flooring it.

---

## Skills → evidence (at a glance)

| Competency | Proof in this repo | Tests |
|---|---|---|
| AI knowledge management — citation-governed retrieval over meeting transcripts (prep + verbatim cite) plus review -> remediation (reviewer's recorded corrections -> cited directives -> auto-generated apply-ready prompt + cited change-log mapping each directive -> source -> status, applied downstream by an AI or operator) | `knowledge-brain-engine` | 7,011 |
| Cross-border foreign-affiliate tax (T1134, surplus pools, ACB, repatriation waterfall) | `tax-surplus-engine` | 7,498 |
| Partnership tax — Form 1065 / K-1 assembly + §704(c) built-in gain (ceiling rule) | `partnership-1065-automation` | 8,605 |
| Multi-entity month-end close (recurring JEs, tie-outs, allocations) | `monthly-close-automation` | 15,687 |
| Self-healing control loops — engines detect drift, re-derive it from source, re-verify, and escalate only what they cannot certify (human-gated on tax-surplus; autonomous with quarantine on close) | `surplus_engine.loop` + `close_engine.loop` | *(23, counted in tax-surplus and close above)* |
| Reconciliation & materiality (GL-to-bank/lender, evidence logs) | `cash-reconciliation` | 7,511 |
| Cash-manager controls (bank-rec bridge, outstanding/void checks, wire dual-approval, register continuity, concentration sweep) | `cash-management` | 5,290 |
| Automated, read-only verification (formula/lineage/tie-out checks) | `audit-automation` | 4,814 |
| Accounts payable controls — read-only posting integrity, payment release gates, duty segregation, information reporting | `accounts-payable-automation` | 12,223 |
| AI orchestration with controls (separation of duties, human gate) | `ai-validation-framework` | 8,320 |
| Finance operations mapping — a deterministic data model rendering an interactive department atlas (drives, workstreams, directory, calendar), with deny-list confidentiality linting | `finance-atlas` | 2,952 |
| Construction loan draw controls — reconciliation identity at zero tolerance, lender-form tie-out, contingency by percent-complete, cutoff | `project-draw-automation` | 10,392 |
| Intercompany reciprocity & consolidation — due-from/due-to reciprocity, ledger roll-forward, funding-protocol routing, guarantor liquidity | `intercompany-automation` | 10,310 |
| Warranty reimbursement controls — finite coverage pool, quarter / policy-period / close-of-escrow boundaries | `warranty-reimbursement-automation` | 10,299 |
| Revenue recognition on buyer upgrades — deferred revenue released on close of escrow, four-way schedule tie-out | `buyer-upgrade-automation` | 10,279 |
| Property tax controls — parcel completeness through platting and split, each jurisdiction's own statutory calendar and delinquency arithmetic, ownership traced through closing, and the accrual behind it (26 controls) | `property-tax-automation` | 10,389 |
| Surety bond & collateral controls — bond-register continuity, cash-collateral recovery on release, premium stopped on released bonds, aggregate penal sum held to the indemnity limit (29 controls) | `surety-bond-automation` | 10,420 |
| Insurance cost allocation — one master premium apportioned across every project's job cost to the residual cent, allocation basis tied to the data, builder's-risk term and value, and the carrier audit true-up returned to the deposit-bearers (24 controls) | `insurance-allocation-automation` | 10,364 |
| Insurance compliance controls — certificate-of-insurance completeness, coverage limits and additional-insured endorsements, policy-period and expiry tracking (22 controls) | `coi-compliance-automation` | 10,340 |
| Expense & P-Card controls — receipt completeness, policy-limit and category enforcement, approval routing, duplicate and split-transaction detection (23 controls) | `expense-report-automation` | 10,346 |
| Project labor charge controls — timecard-to-job-cost allocation, labor-rate and burden tie-out, cost-code completeness, period cutoff (26 controls) | `labor-charge-automation` | 10,382 |
| Lien waiver tracking controls — conditional/unconditional waiver completeness by pay application, through-date tie-out, joint-check and supplier coverage (25 controls) | `lien-waiver-automation` | 10,373 |
| Equity waterfall & JV promote — preferred-return accrual, capital-account roll-forward, tier sequencing and pari-passu splits, hurdle-IRR re-solution, promote/carry split and dilution recompute, each distributed dollar re-derived from the executed operating agreement | `equity-waterfall-automation` | 10,449 |
| Project proforma integrity — source-and-use balance, cost/budget equalities, interest-reserve adequacy, the profit→waterfall→distribution tie-out chain, margin/return re-derivation and reporting-calendar completeness across every quarterly proforma | `proforma-integrity-automation` | 10,381 |
| Gross-receipts & excise tax — each jurisdiction's tax re-derived from the GL revenue pull times the in-force classification rate, tied to the filed worksheet, with deductions, thresholds, rate-effective dates and filing-calendar completeness | `gross-receipts-tax-automation` | 10,400 |
| Filing obligation calendar — every entity × jurisdiction obligation proved filed or validly extended before its statutory due date, fixed-amount vouchers re-derived, and the status register tied to filed evidence with nothing missing or orphaned | `filing-calendar-automation` | 10,369 |
| Energy-efficient home credit (§45L) — every claimed dwelling unit gated on close-of-escrow date and RESNET/HERS certification, multiplied by the dated statutory per-unit amount, rolled up per project/region/fiscal year with net-benefit and partner allocation and a full cross-artifact tie-out | `energy-credit-automation` | 10,390 |
| Interest accrual & loan amortization — each note's accrued interest re-derived as balance × rate × days, the balance rolled forward period to period, the maturity, rate-step, prepayment and subordination gates enforced, and the reciprocal receivable, payable and interest journal tied to the schedule | `interest-accrual-automation` | 10,402 |
| Financing execution & schedule variance — a monthly upcoming-financings report re-derived milestone by milestone: each variance as Current − Prior, each Prior tied to last month's Current, the original baseline held frozen, the playbook complete and every Gantt bar in its closing month | `financing-execution-automation` | 10,337 |
| Wire & transfer release control — every outbound wire, ACH and book transfer gated on two distinct authorized signers within limit, an approved-template or callback-cleared beneficiary, a routing number resolving to the named bank, and a funded source account before release | `wire-release-automation` | 10,347 |
| Payroll & benefit reconciliation — every 401(k), HSA and FSA deduction from a pay period proved to reach the recordkeeper, custodian, ledger liability and cash to the cent, the employer match and statutory limits recomputed, and each deposit timely under the DOL safe harbor | `payroll-benefit-automation` | 10,414 |
| Non-resident withholding & 1042-S — every cross-border FDAP withholding rate recomputed from the payee's FATCA status, portfolio exemption and a treaty reduction gated on a valid W-8, with the tax, the deposits and Form 1042 tied to the 1042-S slips | `withholding-automation` | 10,410 |
| Home sale closing & settlement tie-out — each closed home's settlement statement, closing entry, revenue, loan release and cost-of-sale relief recomputed from base facts and proforma rates, and the rollup's closed count and net-to-seller total tied to the units beneath | `closing-settlement-automation` | 10,379 |
| Entity good-standing — each entity proved in good standing in every registered state: annual report filed on time, flat franchise tax paid, Secretary-of-State status ACTIVE, registered agent and license current, with the compliance rollup rebuilt from the records | `good-standing-automation` | 10,385 |
| Subcontract SOV & change orders — a subcontract commitment's schedule of values footed, only approved change orders moving the revised contract, every pay-application column, retention and tax re-derived, the commitment rolled forward, and the conditional release tied to the certified payment | `sov-commitment-automation` | 10,412 |
| Equity-method pickup & eliminations — every equity-method pickup re-derived as ownership × investee result, the investment roll-forward and preferred-return accrual recomputed, each intercompany elimination paired to net to zero, and the whole tied to the trial balance | `equity-pickup-automation` | 10,423 |
| Depreciation & prepaid amortization — every fixed-asset depreciation and prepaid amortization figure re-derived from cost, life and in-service window, both roll-forwards rebuilt, and the register totals tied to the GL control accounts and the posted recurring entry | `depreciation-register-automation` | 10,440 |
| Earnest-money deposit trust — each unit's pre-close earnest money tied three ways to zero variance across the deposit ledger, the escrow agent's statement and the construction-loan paydowns, cancellations split between forfeited and refunded, and the reconciliation recomputed | `deposit-trust-automation` | 10,407 |
| Capital spending request gate — every capital request's dollar triggers proved to fire only after approval, its five phase gates cleared in sequence, and every contingency floor, fee, total and gate summary re-derived and tied across the package's artifacts | `spending-gate-automation` | 10,424 |
| Section 263A interest capitalization &mdash; each project's avoided-cost capitalized interest re-derived from accumulated production expenditures at the period rate, the quarterly grid footed to annual totals, completeness enforced against the entity trial balance, and the year-over-year comparison tied to the prior filing | `interest-capitalization-automation` | 10,323 |
| Franchise tax combined apportionment &mdash; the combined-group roster reconciled as prior-year members plus additions less removals, group revenue tied to the consolidated tax trial balance, the single receipts factor recomputed and bounded, and the margin tax re-derived as margin times apportionment times rate | `franchise-tax-automation` | 10,344 |
| Debt term-sheet sizing and loan terms &mdash; each deal's maximum loan held to the recomputed advance-rate cap, the all-in rate re-derived as the greater of index plus spread or the floor, every fee struck on its correct base, maturity proved to equal base term plus exercised extensions, and the portfolio rollup footed | `debt-sizing-automation` | 10,338 |
| Unit sales and commission tie-out &mdash; every derived matrix column re-derived from price and plan size, total commission struck on the actual sales price with the agent splits summing back to it to the cent, each sold unit reconciled one-for-one to the closings tab, and the offer-to-sold-to-closing date sequence enforced | `unit-sales-automation` | 10,355 |
| G&A expense allocation &mdash; a holding entity's monthly overhead pool apportioned on driver counts with the shares footing to exactly 100% and the allocated dollars to exactly the pool, the residual cent placed deterministically, the allocation entry balanced and netting to zero at consolidation, and the postage allocation reconciled to the meter delta | `ga-allocation-automation` | 10,404 |
| Outstanding check aging and escheatment &mdash; the outstanding population re-derived from cleared amounts and dates rather than the stated column, each item aged to the as-of date, the total tied to the bank reconciliation's outstanding-checks line, voided and stop-paid items proved excluded, and stale-dating separated from the dormancy threshold that drives escheatment | `check-aging-automation` | 10,361 |
| Project variance and business-plan compare &mdash; Cost to Complete struck as the remainder of the budget, net revenue, profit and margin on cost re-derived from their own inputs, every variance column re-footed as the difference of the two columns beside it in cents and basis points alike, both comparative columns proved to foot inside themselves, the plan column proved against the frozen approved version, and each milestone variance re-derived under the plus-is-ahead convention | `project-variance-automation` | 10,411 |
| Contingency rollforward and adequacy &mdash; construction and project contingency rolled forward from the prior balance through the draws allocated against them, the period total footed to the draw detail, each bucket reconciled to the budget line that funded it, every draw walked against the balance earlier draws left, and the word "adequate" rebuilt from the balance remaining against the projected potential use | `contingency-rollforward-automation` | 10,368 |
| Information return issuance &mdash; the annual payee population reassembled entity by entity, every box amount footed back to the payment lines it came from, a form proved to exist exactly where the threshold met at the cent or the backup-withholding override obliges one and nowhere else, withholding recomputed at the statutory rate in both directions, and every transmittal and the annual rollup recounted from the forms | `info-return-automation` | 10,382 |
| Trial-balance roll-forward &mdash; last year's column structure carried forward, final-year entities retired and renames carried once, every column re-derived from the year-end extract's declared balance column rather than its position, completeness swept both directions so a balance riding a dropped chart equivalence cannot vanish, each dual-chart row summed through the equivalence map, the eliminations range proved to reach this year's new columns, and every figure linked to a backup row that agrees with it | `tb-rollforward-automation` | 10,405 |
| JV investor reporting package &mdash; the monthly package issued to a joint-venture equity partner, re-derived from the five sources that produce it: the trial balance agreed to the ledger by account number rather than row position, a credit intercompany balance reclassified rather than netted against assets, every member's capital footed, cross-footed and rolled forward with the Total column summing the row it sits on, the job cost bridge closed exactly with every difference itemized and disclosed, contributions agreed per member to the executed equity draw schedule, each caption tested against its schedule's type, the cover held consistent with the notes, the reviewer's tie-out rows kept out of the print area, and nothing released over an open exception | `investor-reporting-automation` | 10,432 |
| Tax workpaper build &amp; carry-down &mdash; the new fiscal year's tax workpaper package **built** from a locked ledger extract and the signed prior year rather than edited out of last year's file: the trial balance harvested by exact account number and scoped to one entity block, the balance sheet and statement of operations classified from the prior-year map and footing to zero, every prior-year layer frozen byte-equal, every rolling caption advanced by exactly one year, each current-year contribution and distribution computed as source less prior rather than typed, the member allocation splits carried down in integer basis points, new member-capital and E&amp;P year blocks appended, the evidence tab constructed with its citation block and a zero-footing subtotal, and every constructed cell named in a build register that bounds what the build was allowed to touch | `workpaper-build-automation` | 10,367 |
| **Total** | **50 systems** | **504,712** |

---

## Why this matters to an employer or client

Three things are scarce together: the **domain judgment** to know what "right" means in a workpaper,
the **engineering** to make a system get there and prove it, and the **information discipline** to
turn an organization's meetings into citable, governed memory. Most AI builders can't read a tie-out
or a surplus pool; most accountants can't ship a tested pipeline with a live-model integration or a
citation-governed knowledge base. This portfolio is the evidence that I do all three — the way a
regulated finance function needs it done: **deterministic, evidence-backed, human-gated, and discreet
with the source data.**

— **Sophonnarith Hang** · [github.com/sophonfinance-wq](https://github.com/sophonfinance-wq) · sophonfinance@gmail.com
