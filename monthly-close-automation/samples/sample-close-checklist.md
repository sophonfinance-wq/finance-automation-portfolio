# Sample — Month-End Close Checklist (FICTIONAL)

> 🔒 Entirely invented entities, owners, and dates for demonstration. Not real data.

**Entity group:** Demo Holdings (3 operating entities · 1 database)
**Period:** FY2026 — March close · **Target close:** Business day +4

| # | Task | Type | Owner | Status | Tie-out | Notes |
|---|------|------|-------|--------|---------|-------|
| 1 | Bank feeds imported & coded | Prep | A. Operator | ✅ Done | n/a | All 6 accounts current |
| 2 | Prepaid amortization | Recurring JE | A. Operator | ✅ Done | ✅ ties | 4 active prepaids |
| 3 | Fixed-asset depreciation | Recurring JE | A. Operator | ✅ Done | ✅ ties | 1 new asset added |
| 4 | Deferred rent & CAM allocation | Recurring JE | A. Operator | 🟡 In progress | — | Awaiting March CAM invoice |
| 5 | Management-fee accrual | Recurring JE | A. Operator | ✅ Done | ✅ ties | Netted 1 in-month payment |
| 6 | Note-payable interest accrual | Recurring JE | A. Operator | ✅ Done | ✅ ties | Simple flat-rate note |
| 7 | G&A cost allocation | Recurring JE | A. Operator | ⬜ Not started | — | Depends on task 4 |
| 8 | Cash & debt reconciliation | Recon | A. Operator | 🟡 In progress | — | See reconciliation sample |
| 9 | Intercompany tie-out | Review | Reviewer | ⬜ Not started | — | Due-to / due-from must net to 0 |
| 10 | Controller wrap email | Report | A. Operator | ⬜ Not started | — | Timing vs. structural items |

**Close rule:** no recurring entry posts unless its schedule **ties to the ledger**. An
out-of-tie schedule stops the process until resolved.

**Legend:** ✅ Done · 🟡 In progress · ⬜ Not started
