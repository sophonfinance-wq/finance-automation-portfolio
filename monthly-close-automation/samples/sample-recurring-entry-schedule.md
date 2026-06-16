# Sample — Recurring Entry: Prepaid Amortization (FICTIONAL)

> 🔒 Invented amounts and vendors for demonstration. Not real data.

## The schedule (formula-driven)
A new annual insurance policy is added, then amortized straight-line over its service period.

| Prepaid item | Vendor | Total | Start | Months | Monthly | Booked to date | Remaining |
|--------------|--------|-------|-------|--------|---------|----------------|-----------|
| Annual insurance | Demo Insure Co. | 12,000 | 2026-01-01 | 12 | 1,000 | 3,000 | 9,000 |
| Software license | Demo SaaS Inc. | 6,000 | 2026-02-01 | 12 | 500 | 1,000 | 5,000 |

*Monthly = Total ÷ Months (a formula, never hardcoded). Booked-to-date and Remaining are
formulas off the period driver.*

## The journal entry (March)
| Account | Description | Debit | Credit |
|---------|-------------|-------|--------|
| 6400 · Insurance expense | March insurance amortization | 1,000 | |
| 6500 · Software expense | March software amortization | 500 | |
| 1400 · Prepaid expenses | Relieve prepaid | | 1,500 |
| | **Totals** | **1,500** | **1,500** |

✅ **Ties:** debits = credits, and prepaid balance after = schedule "Remaining" total.
