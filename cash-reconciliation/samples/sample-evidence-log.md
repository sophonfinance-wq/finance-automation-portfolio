# Sample — Reconciliation Evidence Log (FICTIONAL)

> 🔒 Invented banks, entities, and balances for demonstration. Not real data.

**Period:** March 2026 · **Materiality threshold:** $50

## 1. Summary
| Entity | Cash status | Debt status | Open flags |
|--------|-------------|-------------|-----------|
| Demo Op Co. A | ✅ Clean | ✅ Clean | 0 |
| Demo Op Co. B | 🔴 Flag | ✅ Clean | 1 |
| Demo Holdings | ✅ Clean | ✅ Clean | 0 |

## 2. Cash Reconciliations
| Entity | GL cash | Bank ending | Variance | Result | Evidence |
|--------|---------|-------------|----------|--------|----------|
| Demo Op Co. A | 482,150.22 | 482,150.22 | 0.00 | ✅ Tie | acct …1234, stmt 3/31 |
| Demo Op Co. B | 91,300.00 | 92,100.00 | (800.00) | 🔴 FLAG-001 | acct …5678, stmt 3/31 |

## 3. Debt Reconciliations
| Entity | GL loan | Lender stmt + 3-part calc | Variance | Result |
|--------|---------|---------------------------|----------|--------|
| Demo Op Co. A | 1,250,000 | 1,250,000 (principal + 0 interest + 0 paydown) | 0.00 | ✅ Tie |

## 4. Flagged for Review
| Flag | Entity | Issue | Amount | Likely cause | For |
|------|--------|-------|--------|--------------|-----|
| FLAG-001 | Demo Op Co. B | GL cash below bank by $800 | (800.00) | Deposit in transit not yet booked | Controller |

## 5. Screenshots
*(In the real log: source captures of each bank statement and GL screen. Omitted here —
fictional sample.)*

---
**Method notes:** values targeted **by account number, not row**; dormant zero-activity rows
skipped with a comment; variances ≤ $50 commented as noise; tabs colored green (clean) /
red (open flag).
