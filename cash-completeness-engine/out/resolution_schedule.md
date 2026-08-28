# Resolution Schedule - Cash Completeness [FICTIONAL DATA]

**As of:** 2026-06-30 &nbsp;|&nbsp; **Exceptions:** 6 &nbsp;|&nbsp; **Phantom TB rows:** 1

Every item below is classified; nothing is netted away or silently dropped. Class D items block sign-off until explained.

## Class A - Unmapped successor account (3)

**Action:** Map the live successor account into the trial balance. This is a completeness gap in the TB, not a cash gap.

| Entity | GL account | Register balance | TB balance | Difference | Traced destinations | Note |
|--------|------------|-----------------:|-----------:|-----------:|---------------------|------|
| Harbor 17 Investor LLC | `417-001-1010` | 28,090.12 | n/a | 28,090.12 | - | live Union National Bank account with no trial-balance row; map it into the GL. A TB-first reconciliation would never see this account. |
| Juniper 42 Development LLC | `424-002-1020` | 63,205.88 | n/a | 63,205.88 | - | live Union National Bank account with no trial-balance row; map it into the GL. A TB-first reconciliation would never see this account. |
| Wrenfield 28 Development LLC | `628-001-1010` | 154,777.40 | n/a | 154,777.40 | - | live Union National Bank account with no trial-balance row; map it into the GL. A TB-first reconciliation would never see this account. |
| **Total** | | **246,073.40** | **0.00** | **246,073.40** | | |

## Class B - Stale close-out balance (2)

**Action:** Book the close-out entry. The stale TB figure is the traced pre-sweep balance; every sweep destination is named below.

| Entity | GL account | Register balance | TB balance | Difference | Traced destinations | Note |
|--------|------------|-----------------:|-----------:|-----------:|---------------------|------|
| Bluffside 9 Townhomes LLC | `309-002-1015` | 0.00 | 75,310.66 | (75,310.66) | 2026-05-28 Kestrel Capital Partners LLC 75,310.66 | TB still carries the traced pre-sweep balance 75,310.66; account closed and swept to 1 named destination(s) totalling 75,310.66. Book the close-out entry. |
| Wrenfield 28 Development LLC | `628-002-1015` | 0.00 | 231,000.00 | (231,000.00) | 2026-06-05 Harbor 17 Investor LLC 138,600.00; 2026-06-05 Demo Holdings LLC 92,400.00 | TB still carries the traced pre-sweep balance 231,000.00; account closed and swept to 2 named destination(s) totalling 231,000.00. Book the close-out entry. |
| **Total** | | **0.00** | **306,310.66** | **(306,310.66)** | | |

## Class C - Timing difference (1)

**Action:** No entry. Post-cutoff activity explains the difference and clears next period; re-check at the next close.

| Entity | GL account | Register balance | TB balance | Difference | Traced destinations | Note |
|--------|------------|-----------------:|-----------:|-----------:|---------------------|------|
| Kestrel Capital Partners LLC | `501-001-1010` | 96,155.75 | 71,155.75 | 25,000.00 | - | 1 trailing in-transit transaction(s) (no cutoff configured; isolated from the register's running balances) (2026-07-01 to 2026-07-01) totalling 25,000.00 fully explain the difference; no entry, clears next period. |
| **Total** | | **96,155.75** | **71,155.75** | **25,000.00** | | |

## Phantom / no-register TB rows (1)

**Action:** Retire or remap each line. No register account has ever matched these GL keys -- typically a mis-keyed BAL row or a placeholder that survived a mapping change.

| Sheet | GL (raw) | GL (normalized) | Title | TB balance |
|-------|----------|-----------------|-------|-----------:|
| Saltgrass 6 Services | `760-001-1010` | `760-001-1010` | Cash - Union National Bank - Operating | 5,118.27 |
| **Total** | | | | **5,118.27** |
