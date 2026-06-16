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
construction/JV audit support — inside a large, owner-operated real-estate development group. I also
built an internal **knowledge brain**: I recorded every engagement meeting, transcribed it, and
loaded it into a queryable knowledge base so prior decisions could be cited word-for-word in
workpapers. Then I re-engineered each *class* of that work into tested, deterministic, audit-ready
Python systems on **fully synthetic data**, and built a control framework so AI can accelerate it
without becoming the weakest link. This portfolio is that proof: **seven runnable systems, 232
tests, CI.**

---

## What the work actually involved (described generically)

| The real work (public-concept level) | The system that demonstrates the skill |
|---|---|
| **An internal "finance brain."** Recording engagement meetings, transcribing them, and loading them into a queryable knowledge base used *before* the work to prep, and *during* the work to cite a prior decision **word-for-word, with date + timestamp**, in a workpaper or disclosure note. | [`knowledge-brain-engine`](../knowledge-brain-engine/) |
| **Canadian foreign-affiliate surplus & ACB (CRA Form T1134).** Maintaining — year by year, entity by entity, across a large multi-tier US structure owned through Canada — the **exempt / taxable / pre-acquisition** surplus pools and the **adjusted cost base** of each investment, for eventual tax-efficient repatriation. | [`tax-surplus-engine`](../tax-surplus-engine/) |
| **US partnership tax with IRC §704(c).** Form 1065 / Schedule K-1 assembly *and* **built-in gain** on contributed property — book vs. tax capital, the **traditional method / ceiling rule**, tax-basis financials. | [`partnership-1065-automation`](../partnership-1065-automation/) |
| **Multi-entity month-end close.** Recurring journal entries (prepaid amortization, depreciation, deferred rent/CAM, accrued management fees, intercompany note interest) and cross-entity G&A/insurance allocations, with schedule-to-GL tie-outs. | [`monthly-close-automation`](../monthly-close-automation/) |
| **Construction / JV project audits.** Pulling GL, job-cost, and check-register detail from a construction-accounting ERP for annual partner and Big-Four audits; classifying materiality; tracing a selection to source. | [`cash-reconciliation`](../cash-reconciliation/) + [`audit-automation`](../audit-automation/) |
| **Reviewer-driven QA, formalized.** Building a deliverable, then having it **independently reviewed against the reviewer's own words** before sign-off — a discipline I turned into a separation-of-duties control framework for AI-assisted work. | [`ai-validation-framework`](../ai-validation-framework/) (Triangulate) |

---

## The knowledge brain, in detail

This is the system most people have never seen built properly. The real workflow:
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
- **Governance:** every answer carries a source; if nothing clears the relevance floor, the engine
  **refuses to guess** rather than fabricating an uncited answer.

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
| AI knowledge management — citation-governed retrieval over meeting transcripts (prep + verbatim cite) | `knowledge-brain-engine` | 50 |
| Cross-border foreign-affiliate tax (T1134, surplus pools, ACB, repatriation waterfall) | `tax-surplus-engine` | 26 |
| Partnership tax — Form 1065 / K-1 assembly + §704(c) built-in gain (ceiling rule) | `partnership-1065-automation` | 40 |
| Multi-entity month-end close (recurring JEs, tie-outs, allocations) | `monthly-close-automation` | 41 |
| Reconciliation & materiality (GL-to-bank/lender, evidence logs) | `cash-reconciliation` | 31 |
| Automated, read-only verification (formula/lineage/tie-out checks) | `audit-automation` | 23 |
| AI orchestration with controls (separation of duties, human gate) | `ai-validation-framework` | 21 |
| **Total** | **7 systems** | **232** |

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
