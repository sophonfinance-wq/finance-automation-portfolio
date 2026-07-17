# Month-End Close Report — 2026-03

> FICTIONAL demonstration data. Generated deterministically (seed 2026).

## Entity group

- `DH` — Demo Holdings LLC
- `MF` — Maple Fund LP
- `BW` — Birchwood Op Co

## Recurring-entry checklist

| # | Recurring entry | Entry | Debits | Credits | Balanced |
|---|-----------------|-------|-------:|--------:|:--------:|
| 1 | Prepaid amortization (straight-line) | `JE-2026-03-PREPAID` | 3,400.00 | 3,400.00 | [x] |
| 2 | Fixed-asset depreciation (straight-line, monthly) | `JE-2026-03-DEPREC` | 9,000.00 | 9,000.00 | [x] |
| 3 | Deferred rent + CAM straight-lining (intercompany split) | `JE-2026-03-LEASE` | 17,812.50 | 17,812.50 | [x] |
| 4 | Fixed-fee accrual (settlements already in opening GL) | `JE-2026-03-FIXEDFEE` | 12,250.00 | 12,250.00 | [x] |
| 5 | Management-fee accrual (net of in-month payments) | `JE-2026-03-MGMTFEE` | 14,000.00 | 14,000.00 | [x] |
| 6 | Related-party note interest accrual | `JE-2026-03-INTEREST` | 6,875.00 | 6,875.00 | [x] |
| 7 | G&A cost allocation (fixed ratio, sums to 100%) | `JE-2026-03-GNA` | 24,000.00 | 24,000.00 | [x] |
| 8 | Insurance premium allocation (shared policies) | `JE-2026-03-INSUR` | 2,600.00 | 2,600.00 | [x] |

## Tie-out summary

| Schedule | GL account | Schedule | GL balance | Tie |
|----------|-----------|---------:|-----------:|:---:|
| Prepaid amortization | 1400 · Prepaid expenses | 8,100.00 | 8,100.00 | [x] |
| Fixed-fee accrual | 2350 · Fixed fee payable | 62,250.00 | 62,250.00 | [x] |
| Insurance allocation | 1450 · Prepaid insurance | 10,950.00 | 10,950.00 | [x] |

## Controls

- [x] Every posted entry balances (debits == credits).
- [x] Trial balance is in balance (3,599,487.50 == 3,599,487.50).
- [x] Every schedule ties to the GL.
- [x] No entries refused for being out of tie (0 refused).

## Control findings

_Sentinel: all controls passed (no findings)._

All controls passed.

**Close status: CLEAN — ready for review.**
