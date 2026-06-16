# Reconciliation Evidence Log (FICTIONAL)

> 🔒 Fully synthetic, seeded data. Invented entities, banks, lenders, and
> balances for demonstration. Not real data.

**Period:** March 2026 · **Statement date:** 2026-03-31 · **Materiality threshold:** $50.00

## 1. Summary

- Accounts in scope: **9** (4 cash, 4 debt; 1 dormant skipped)
- Clean ties: **5**
- Timing / immaterial: **1**
- Flagged for review: **2**

| Entity | Cash status | Debt status | Open flags |
|--------|-------------|-------------|------------|
| Birchwood Op Co | ✅ Clean | 🟡 Timing | 0 |
| Cedar Ridge Partners LLC | ✅ Clean | 🔴 Flag | 1 |
| Demo Holdings LLC | ✅ Clean | ✅ Clean | 0 |
| Maple Fund LP | 🔴 Flag | ✅ Clean | 1 |

## 2. Cash Reconciliations

| Entity | Account | GL cash | Bank ending | Variance | Result | Evidence |
|--------|---------|--------:|------------:|---------:|--------|----------|
| Birchwood Op Co | CASH-1002 | 207,462.20 | 207,462.20 | 0.00 | ✅ Clean | Summit Sandbox Bank, ending 2026-03-31 |
| Cedar Ridge Partners LLC | CASH-1003 | 382,998.46 | 382,998.46 | 0.00 | ✅ Clean | Lakeside Test Bank, ending 2026-03-31 |
| Demo Holdings LLC | CASH-1000 | 690,033.93 | 690,033.93 | 0.00 | ✅ Clean | Northgate Demo Bank, ending 2026-03-31 |
| Maple Fund LP | CASH-1001 | 751,205.22 | 753,080.62 | (1,875.40) | 🔴 FLAG-001 | Riverstone Mock Bank, ending 2026-03-31 |

## 3. Debt Reconciliations

Lender total = **principal + current interest/reserve + late paydown** (3-part formula).

| Entity | Account | GL loan | Principal | Interest/Reserve | Late paydown | Lender total | Variance | Result |
|--------|---------|--------:|----------:|-----------------:|-------------:|-------------:|---------:|--------|
| Birchwood Op Co | DEBT-2002 | 3,386,059.19 | 3,380,732.17 | 5,308.27 | 0.00 | 3,386,040.44 | 18.75 | 🟡 Timing |
| Cedar Ridge Partners LLC | DEBT-2003 | 2,432,184.77 | 2,414,349.91 | 5,334.86 | 0.00 | 2,419,684.77 | 12,500.00 | 🔴 FLAG-002 |
| Demo Holdings LLC | DEBT-2000 | 2,846,629.29 | 2,829,837.76 | 9,291.53 | 7,500.00 | 2,846,629.29 | 0.00 | ✅ Clean |
| Maple Fund LP | DEBT-2001 | 2,936,205.07 | 2,926,267.92 | 9,937.15 | 0.00 | 2,936,205.07 | 0.00 | ✅ Clean |

## 4. Flagged for Review

| Flag | Entity | Account | Type | Variance | Likely cause |
|------|--------|---------|------|---------:|--------------|
| FLAG-001 | Maple Fund LP | CASH-1001 | cash | (1,875.40) | Deposit in transit: bank ending exceeds GL cash by $1,875.40 (deposit cleared bank, not yet booked to GL). |
| FLAG-002 | Cedar Ridge Partners LLC | DEBT-2003 | debt | 12,500.00 | Outright error: GL debt overstated by $12,500.00 versus the lender 3-part total (keying error). |

## 5. Notes

**Method notes:**

- Values targeted **by account number, not row** (defeats off-by-one errors).
- Variances at or below the materiality threshold are commented as timing/noise; larger variances become numbered flags.
- Debt reconciled with the 3-part lender formula shown in Section 3.
- Dormant zero-activity accounts are skipped with a documented note:
  - `CASH-1900` (Demo Holdings LLC) — Dormant zero-activity account skipped per policy (no reconciliation required).

**Timing vs. structural items:**

- `DEBT-2002` (Birchwood Op Co) — timing item, variance 18.75; expected to clear.

*Real evidence logs embed live bank/lender screenshots and are never published.*
