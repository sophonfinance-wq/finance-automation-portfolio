# Verification &amp; Completeness Patterns

> 🔒 This document describes **generalized verification techniques** for automated reconciliation.
> It uses **invented entities, accounts, and figures** and does not reproduce any employer's
> procedures, banks, entities, or data. All examples below are fictional.

A reconciled figure that *looks* right can still be wrong. Tying a balance to the ledger is only
the first layer; a production reconciliation has to survive three failure modes that a
values-only check never sees:

1. the **right number written to the wrong row**,
2. the **right number sourced from the wrong entity**, and
3. an **account — or an entire entity — missing from the population** altogether.

This is the layered check the engine applies before a cycle is marked final.

---

## The verification hierarchy

### 1. Target by account number, never row number
Automated writes that address cells positionally drift by a row and silently corrupt an adjacent
account. Every write resolves its target by matching the **account number** in the key column, not
by row index. As a second confirmation, the process records the **prior value it overwrote** — if
the value replaced does not match what the schedule expected for that account, the write is
rejected for review rather than trusted.

### 2. Entity / title cross-check
Related entities in a real estate or fund structure often share a numbering pattern — an
*Investor → Sponsor → Development* tier where the same trailing account code appears under several
companies. A balance can tie perfectly and still belong to the wrong entity.

> *Fictional example.* Target account `74-002-1150` is populated from a register whose G/L reads
> `9-002-1150`. Both are "operating," so the dollars look plausible — but `9-002` is a
> different company. The register whose G/L is *exactly* `74-002-1150` belongs to the sibling
> "Sponsor" entity and carries a materially different balance. The mismatch is caught by
> confirming the source's **G/L code and bank id match the target**, not just the amount.

### 3. Independent re-derivation
Material balances are re-computed from source **independently of the first pull**, and run through
adversarial review rounds whose default posture is skeptical (a finding must survive an attempt to
refute it). This catches plausible-but-wrong figures before they are booked.

### 4. Completeness sweep (source → target, whole population)
The highest-value check. Every source register on the drive is scanned — **not only the ones on
the worklist** — and each live balance must map to either a booked account or an explicitly
scoped-out one. Anything unmatched is surfaced.

> *Fictional example.* "Riverbend Capital LLC" shares a trial-balance tab with a sibling operating
> entity and was never added to the worklist. A full register-to-ledger sweep surfaces a live
> $48K balance with no home on the ledger, plus a stale $260K predecessor still carried at its old
> value — both invisible to a worklist-only review.

---

## Finding taxonomy

Every difference is classified and routed, so reviewers see structural signal instead of expected noise.

| Finding type | Signal | Routing |
|---|---|---|
| **Timing** | Ledger will catch up within the close window | Note; do not flag |
| **Stale benchmark** | Prior target drifted from the register | Refresh to source |
| **Closed / swept** | Account closed; residual within tolerance of $0 | Write down to $0 |
| **Bank-migration successor** | Cash moved to a new bank/account | Book if on ledger; **flag if off-ledger** |
| **Entity-mapping error** | Right amount, wrong source entity | Correct the source |
| **Cross-region duplicate** | Same account appears in two regions | Flag to avoid double-listing |

---

## Bank-migration &amp; off-ledger successors

The most common structural theme in a long-lived entity set: an operating account is closed and its
cash migrates to a **successor account at a new bank** that has not yet been added to the trial
balance. The tell is a matched pair — a **dead predecessor sitting at $0 on the ledger** and a
**live successor that is off-ledger entirely**.

> *Fictional example.* "Oakline Development" shows a Wells Fargo operating line closed in a prior
> year, correctly at $0. The entity's real cash now sits in a US Bank successor account that is not
> a ledger row. The predecessor is written down; the successor is quantified and **flagged for
> chart-of-accounts scoping** rather than silently booked.

Left unchecked, this pattern understates live cash while the ledger tracks accounts that no longer
transact. Surfacing the full successor population turns a routine reconciliation into a structural
finding worth escalating.

---

## Close-out

- **Color-coded status** per tab: reconciled &amp; final, held (interim, re-pull pending), and
  structural-flag.
- A closing summary that separates **timing** items (expected, will clear) from **structural**
  items (cleanups, migrations, scoping decisions) so the reviewer's attention goes where it counts.
