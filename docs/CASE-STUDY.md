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
without becoming the weakest link. This portfolio is that proof: **thirty-eight runnable systems, a
80,574-test curated suite (plus an opt-in ~1.26M-case property sweep), CI.**

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
| Self-healing control loops — engines detect drift, re-derive it from source, re-verify, and escalate only what they cannot certify (human-gated on tax-surplus; autonomous with quarantine on close) | `surplus_engine.loop` + `close_engine.loop` | 23 |
| Reconciliation & materiality (GL-to-bank/lender, evidence logs) | `cash-reconciliation` | 7,511 |
| Cash-manager controls (bank-rec bridge, outstanding/void checks, wire dual-approval, register continuity, concentration sweep) | `cash-management` | 5,290 |
| Automated, read-only verification (formula/lineage/tie-out checks) | `audit-automation` | 4,814 |
| Accounts payable controls — read-only posting integrity, payment release gates, duty segregation, information reporting | `accounts-payable-automation` | 2,223 |
| AI orchestration with controls (separation of duties, human gate) | `ai-validation-framework` | 8,320 |
| Finance operations mapping — a deterministic data model rendering an interactive department atlas (drives, workstreams, directory, calendar), with deny-list confidentiality linting | `finance-atlas` | 2,952 |
| Construction loan draw controls — reconciliation identity at zero tolerance, lender-form tie-out, contingency by percent-complete, cutoff | `project-draw-automation` | 392 |
| Intercompany reciprocity & consolidation — due-from/due-to reciprocity, ledger roll-forward, funding-protocol routing, guarantor liquidity | `intercompany-automation` | 310 |
| Warranty reimbursement controls — finite coverage pool, quarter / policy-period / close-of-escrow boundaries | `warranty-reimbursement-automation` | 299 |
| Revenue recognition on buyer upgrades — deferred revenue released on close of escrow, four-way schedule tie-out | `buyer-upgrade-automation` | 279 |
| Property tax controls — parcel completeness through platting and split, each jurisdiction's own statutory calendar and delinquency arithmetic, ownership traced through closing, and the accrual behind it (26 controls) | `property-tax-automation` | 389 |
| Surety bond & collateral controls — bond-register continuity, cash-collateral recovery on release, premium stopped on released bonds, aggregate penal sum held to the indemnity limit (29 controls) | `surety-bond-automation` | 420 |
| Insurance cost allocation — one master premium apportioned across every project's job cost to the residual cent, allocation basis tied to the data, builder's-risk term and value, and the carrier audit true-up returned to the deposit-bearers (24 controls) | `insurance-allocation-automation` | 364 |
| Insurance compliance controls — certificate-of-insurance completeness, coverage limits and additional-insured endorsements, policy-period and expiry tracking (22 controls) | `coi-compliance-automation` | 340 |
| Expense & P-Card controls — receipt completeness, policy-limit and category enforcement, approval routing, duplicate and split-transaction detection (23 controls) | `expense-report-automation` | 346 |
| Project labor charge controls — timecard-to-job-cost allocation, labor-rate and burden tie-out, cost-code completeness, period cutoff (26 controls) | `labor-charge-automation` | 382 |
| Lien waiver tracking controls — conditional/unconditional waiver completeness by pay application, through-date tie-out, joint-check and supplier coverage (25 controls) | `lien-waiver-automation` | 373 |
| Equity waterfall & JV promote — preferred-return accrual, capital-account roll-forward, tier sequencing and pari-passu splits, hurdle-IRR re-solution, promote/carry split and dilution recompute, each distributed dollar re-derived from the executed operating agreement | `equity-waterfall-automation` | 449 |
| Project proforma integrity — source-and-use balance, cost/budget equalities, interest-reserve adequacy, the profit→waterfall→distribution tie-out chain, margin/return re-derivation and reporting-calendar completeness across every quarterly proforma | `proforma-integrity-automation` | 381 |
| Gross-receipts & excise tax — each jurisdiction's tax re-derived from the GL revenue pull times the in-force classification rate, tied to the filed worksheet, with deductions, thresholds, rate-effective dates and filing-calendar completeness | `gross-receipts-tax-automation` | 400 |
| Filing obligation calendar — every entity × jurisdiction obligation proved filed or validly extended before its statutory due date, fixed-amount vouchers re-derived, and the status register tied to filed evidence with nothing missing or orphaned | `filing-calendar-automation` | 369 |
| Energy-efficient home credit (§45L) — every claimed dwelling unit gated on close-of-escrow date and RESNET/HERS certification, multiplied by the dated statutory per-unit amount, rolled up per project/region/fiscal year with net-benefit and partner allocation and a full cross-artifact tie-out | `energy-credit-automation` | 390 |
| Interest accrual & loan amortization — each note's accrued interest re-derived as balance × rate × days, the balance rolled forward period to period, the maturity, rate-step, prepayment and subordination gates enforced, and the reciprocal receivable, payable and interest journal tied to the schedule | `interest-accrual-automation` | 402 |
| Financing execution & schedule variance — a monthly upcoming-financings report re-derived milestone by milestone: each variance as Current − Prior, each Prior tied to last month's Current, the original baseline held frozen, the playbook complete and every Gantt bar in its closing month | `financing-execution-automation` | 337 |
| Wire & transfer release control — every outbound wire, ACH and book transfer gated on two distinct authorized signers within limit, an approved-template or callback-cleared beneficiary, a routing number resolving to the named bank, and a funded source account before release | `wire-release-automation` | 347 |
| Payroll & benefit reconciliation — every 401(k), HSA and FSA deduction from a pay period proved to reach the recordkeeper, custodian, ledger liability and cash to the cent, the employer match and statutory limits recomputed, and each deposit timely under the DOL safe harbor | `payroll-benefit-automation` | 414 |
| Non-resident withholding & 1042-S — every cross-border FDAP withholding rate recomputed from the payee's FATCA status, portfolio exemption and a treaty reduction gated on a valid W-8, with the tax, the deposits and Form 1042 tied to the 1042-S slips | `withholding-automation` | 410 |
| Home sale closing & settlement tie-out — each closed home's settlement statement, closing entry, revenue, loan release and cost-of-sale relief recomputed from base facts and proforma rates, and the rollup's closed count and net-to-seller total tied to the units beneath | `closing-settlement-automation` | 379 |
| Entity good-standing — each entity proved in good standing in every registered state: annual report filed on time, flat franchise tax paid, Secretary-of-State status ACTIVE, registered agent and license current, with the compliance rollup rebuilt from the records | `good-standing-automation` | 385 |
| Subcontract SOV & change orders — a subcontract commitment's schedule of values footed, only approved change orders moving the revised contract, every pay-application column, retention and tax re-derived, the commitment rolled forward, and the conditional release tied to the certified payment | `sov-commitment-automation` | 412 |
| Equity-method pickup & eliminations — every equity-method pickup re-derived as ownership × investee result, the investment roll-forward and preferred-return accrual recomputed, each intercompany elimination paired to net to zero, and the whole tied to the trial balance | `equity-pickup-automation` | 423 |
| Depreciation & prepaid amortization — every fixed-asset depreciation and prepaid amortization figure re-derived from cost, life and in-service window, both roll-forwards rebuilt, and the register totals tied to the GL control accounts and the posted recurring entry | `depreciation-register-automation` | 440 |
| Earnest-money deposit trust — each unit's pre-close earnest money tied three ways to zero variance across the deposit ledger, the escrow agent's statement and the construction-loan paydowns, cancellations split between forfeited and refunded, and the reconciliation recomputed | `deposit-trust-automation` | 407 |
| Capital spending request gate — every capital request's dollar triggers proved to fire only after approval, its five phase gates cleared in sequence, and every contingency floor, fee, total and gate summary re-derived and tied across the package's artifacts | `spending-gate-automation` | 424 |
| **Total** | **38 systems** | **80,574** |

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
