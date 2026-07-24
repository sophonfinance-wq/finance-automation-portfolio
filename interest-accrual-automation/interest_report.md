# Interest accrual & loan amortization control report

**Overall verdict:** FAIL

- Loan files analyzed: 30
- Controls in registry: 28
- PASS / REVIEW / FAIL: 1 / 2 / 27

All data is fictional. The engine is read-only and never writes to a source
artifact. Every maturity and gate test is made against the `as_of` date carried
in the file, never the system clock.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `note_unique_ids` | FAIL | 1 |
| 3 | `note_required_fields` | FAIL | 1 |
| 4 | `note_terms_valid` | FAIL | 1 |
| 5 | `note_entities_distinct` | FAIL | 1 |
| 6 | `acc_row_fields_present` | FAIL | 1 |
| 7 | `acc_day_count_ties` | FAIL | 1 |
| 8 | `acc_interest_rederives` | FAIL | 4 |
| 9 | `rf_row_note_exists` | FAIL | 1 |
| 10 | `rf_ending_balance_rederives` | FAIL | 7 |
| 11 | `rf_continuity` | FAIL | 2 |
| 12 | `rf_opening_ties_principal` | FAIL | 2 |
| 13 | `gate_rate_step` | FAIL | 1 |
| 14 | `gate_maturity_stop` | FAIL | 1 |
| 15 | `gate_no_prepayment` | FAIL | 1 |
| 16 | `gate_maturity_approaching` | FLAG | 1 |
| 17 | `wf_payment_within_balance` | FAIL | 2 |
| 18 | `wf_final_settles_zero` | FAIL | 1 |
| 19 | `wf_subordination_order` | FAIL | 1 |
| 20 | `recip_nr_np_equal` | FAIL | 1 |
| 21 | `recip_income_expense_equal` | FAIL | 2 |
| 22 | `gl_journal_balances` | FAIL | 1 |
| 23 | `gl_journal_ties_accrual` | FAIL | 2 |
| 24 | `gl_note_on_tb` | FAIL | 1 |
| 25 | `gl_tb_complete` | FAIL | 1 |
| 26 | `rpt_note_settled_recomputes` | FAIL | 2 |
| 27 | `rpt_report_count_ties` | FAIL | 1 |
| 28 | `rpt_watchlist_ties` | FLAG | 1 |

## Loan files

### accrual_past_maturity__Halbrook_Residential

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `gate_maturity_stop` @ `rollforward_schedule:ROLLFWD-2029/rows/1/accrued_cents`  
  row 1 (NR-1401) accrues 11,890.41 on a period beginning 2029-07-01, on or after maturity 2029-06-15; accrual should have stopped

### accrual_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 5)

- **FAIL** `acc_interest_rederives` @ `rollforward_schedule:ROLLFWD-2029/rows/1/accrued_cents`  
  row 1 (NR-1401) books 11,900.41 accrued on 2,000,000.00 at 700 bps for 31 day(s); re-deriving gives 11,890.41 (off 10.00)
- **FAIL** `rf_ending_balance_rederives` @ `rollforward_schedule:ROLLFWD-2029/rows/1/ending_cents`  
  row 1 (NR-1401) ends 2,000,000.00; 2,000,000.00 + 0.00 + 11,900.41 - 11,890.41 = 2,000,010.00 (off -10.00)
- **FAIL** `recip_income_expense_equal` @ `trial_balance:TB-2029/accounts/9-201-4401/balance_cents`  
  note NR-1401 books interest income 23,397.25 and expense 23,397.25 against 23,407.25 accrued; the reciprocal interest does not tie
- **FAIL** `gl_journal_ties_accrual` @ `interest_journal:JE-2029/lines`  
  the interest journal books 107,343.93 of interest; the schedules accrue 107,353.93 (off -10.00)
- **FAIL** `rpt_note_settled_recomputes` @ `interest_summary:SUMMARY-2029/notes/NR-1401/accrued_total_cents`  
  note NR-1401 is summarised at 23,397.25 accrued; recomputing from its schedule gives 23,407.25

### amount_not_integer__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 4)

- **FAIL** `acc_interest_rederives` @ `amount:row[NR-1401/2029-07-01].beginning_cents`  
  AMOUNT_INVALID: row[NR-1401/2029-07-01].beginning_cents must be integer cents, got 200000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `rf_ending_balance_rederives` @ `amount:row[0].beginning_cents`  
  AMOUNT_INVALID: row[0].beginning_cents must be integer cents, got 200000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `rf_opening_ties_principal` @ `amount:row[NR-1401].beginning_cents`  
  AMOUNT_INVALID: row[NR-1401].beginning_cents must be integer cents, got 200000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `wf_payment_within_balance` @ `amount:row[0].beginning_cents`  
  AMOUNT_INVALID: row[0].beginning_cents must be integer cents, got 200000000.5 -- amounts are integer cents and are never coerced

### bad_day_count__Northmoor_Development_Group

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `note_terms_valid` @ `note_register:NOTES-2029/notes/NR-1402/day_count_denom`  
  note NR-1402 states day-count denominator 364, not one of (360, 365); its accrual year is undefined

### clean__Northmoor_Development_Group

**Verdict:** PASS (PASS 28, FLAG 0, FAIL 0)

All controls held.

### continuity_break__Halbrook_Residential

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 3)

- **FAIL** `acc_interest_rederives` @ `rollforward_schedule:ROLLFWD-2029/rows/1/accrued_cents`  
  row 1 (NR-1401) books 11,890.41 accrued on 2,000,005.00 at 700 bps for 31 day(s); re-deriving gives 11,890.44 (off -0.03)
- **FAIL** `rf_ending_balance_rederives` @ `rollforward_schedule:ROLLFWD-2029/rows/1/ending_cents`  
  row 1 (NR-1401) ends 2,000,000.00; 2,000,005.00 + 0.00 + 11,890.41 - 11,890.41 = 2,000,005.00 (off -5.00)
- **FAIL** `rf_continuity` @ `rollforward_schedule:ROLLFWD-2029/rows/NR-1401/2029-08-01/beginning_cents`  
  note NR-1401 ends period 2029-07-01 at 2,000,000.00 but opens 2029-08-01 at 2,000,005.00; the roll-forward is broken

### day_count_mismatch__Stonecrest_Communities

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `acc_day_count_ties` @ `rollforward_schedule:ROLLFWD-2029/rows/1/days`  
  row 1 (NR-1401) states 31 day(s) but 2029-07-01..2029-08-10 spans 40; the accrual day count does not tie the period

### duplicate_note_id__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `note_unique_ids` @ `note_register:NOTES-2029/notes/NR-1401`  
  note id NR-1401 appears 2 times; a schedule row that names it cannot be attributed to one note

### early_prepayment__Northmoor_Development_Group

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 2)

- **FAIL** `rf_ending_balance_rederives` @ `rollforward_schedule:ROLLFWD-2029/rows/4/ending_cents`  
  row 4 (NR-1403) ends 1,000,000.00; 1,000,000.00 + 0.00 + 6,575.34 - 56,575.34 = 950,000.00 (off 50,000.00)
- **FAIL** `gate_no_prepayment` @ `rollforward_schedule:ROLLFWD-2029/rows/4/payment_cents`  
  note NR-1403 bars prepayment, yet row 4 pays 56,575.34 against 6,575.34 accrued on 2029-07-01, before maturity 2029-09-01; 50,000.00 reduces principal

### ending_wrong__Halbrook_Residential

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 2)

- **FAIL** `rf_ending_balance_rederives` @ `rollforward_schedule:ROLLFWD-2029/rows/0/ending_cents`  
  row 0 (NR-1401) ends 2,000,005.00; 2,000,000.00 + 0.00 + 11,506.84 - 11,506.84 = 2,000,000.00 (off 5.00)
- **FAIL** `rf_continuity` @ `rollforward_schedule:ROLLFWD-2029/rows/NR-1401/2029-08-01/beginning_cents`  
  note NR-1401 ends period 2029-07-01 at 2,000,005.00 but opens 2029-08-01 at 2,000,000.00; the roll-forward is broken

### income_expense_break__Stonecrest_Communities

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `recip_income_expense_equal` @ `trial_balance:TB-2029/accounts/9-301-4402/balance_cents`  
  note NR-1402 books interest income 22,560.42 and expense 12,560.42 against 12,560.42 accrued; the reciprocal interest does not tie

### journal_off_accrual__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `gl_journal_ties_accrual` @ `interest_journal:JE-2029/lines`  
  the interest journal books 117,343.93 of interest; the schedules accrue 107,343.93 (off 10,000.00)

### journal_unbalanced__Northmoor_Development_Group

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `gl_journal_balances` @ `interest_journal:JE-2029/lines`  
  the interest journal debits 107,343.93 and credits 117,343.93; it is out of balance by -10,000.00

### maturity_approaching__Halbrook_Residential

**Verdict:** REVIEW (PASS 27, FLAG 1, FAIL 0)

- **FLAG** `gate_maturity_approaching` @ `note_register:NOTES-2029/notes/NR-1401/maturity_date`  
  note NR-1401 matures 2029-11-15, in 45 day(s); inside the 60-day window and due to be refinanced or repaid

### missing_document__Stonecrest_Communities

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `debt_service_report:-`  
  debt_service_report is missing; the controls that read it cannot run and must not be reported as having passed

### note_missing_field__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `note_required_fields` @ `note_register:NOTES-2029/notes/NR-1404`  
  note NR-1404 is missing lender_entity

### note_off_tb__Northmoor_Development_Group

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `gl_note_on_tb` @ `trial_balance:TB-2029/accounts/9-501-1402`  
  note NR-1404 maps np_account to 9-501-1402, which is not on the trial balance; the note cannot be tied out

### opening_mismatch__Halbrook_Residential

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `rf_opening_ties_principal` @ `rollforward_schedule:ROLLFWD-2029/rows/NR-1402/opening/beginning_cents`  
  note NR-1402 opens its schedule at 1,500,000.00; the register states principal 1,499,990.00

### orphan_row__Stonecrest_Communities

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `rf_row_note_exists` @ `rollforward_schedule:ROLLFWD-2029/rows/14/note_id`  
  schedule row 14 names note 'NR-9999', which is not in the note register

### orphan_tb_account__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `gl_tb_complete` @ `trial_balance:TB-2029/accounts/8-808-8888`  
  trial-balance account 8-808-8888 is claimed by no note; it is an orphan balance with no schedule behind it

### overpayment__Northmoor_Development_Group

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 2)

- **FAIL** `rf_ending_balance_rederives` @ `rollforward_schedule:ROLLFWD-2029/rows/1/ending_cents`  
  row 1 (NR-1401) ends 2,000,000.00; 2,000,000.00 + 0.00 + 11,890.41 - 10,011,890.41 = -8,000,000.00 (off 10,000,000.00)
- **FAIL** `wf_payment_within_balance` @ `rollforward_schedule:ROLLFWD-2029/rows/1/payment_cents`  
  row 1 (NR-1401) pays 10,011,890.41 against 2,011,890.41 owed (2,000,000.00 + 0.00 + 11,890.41); 8,000,000.00 overpays the balance

### payoff_residual__Halbrook_Residential

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `wf_final_settles_zero` @ `rollforward_schedule:ROLLFWD-2029/rows/NR-1403/final/ending_cents`  
  note NR-1403 is scheduled to pay off, yet its final period ends at 5,000.00 instead of settling to zero

### rate_step_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 2)

- **FAIL** `acc_interest_rederives` @ `rollforward_schedule:ROLLFWD-2029/rows/10/accrued_cents`  
  row 10 (NR-1405) books 6,904.10 accrued on 1,200,000.00 at 1200 bps for 30 day(s); re-deriving gives 11,835.61 (off -4,931.51)
- **FAIL** `gate_rate_step` @ `rollforward_schedule:ROLLFWD-2029/rows/10/rate_bps`  
  row 10 (NR-1405) starting 2029-06-01 accrues at 1200 bps; the note's terms call for 700 bps (default rate stepped in 2029-08-01)

### receivable_break__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `recip_nr_np_equal` @ `trial_balance:TB-2029/accounts/9-201-1402/balance_cents`  
  note NR-1401 carries receivable 2,000,000.00 and payable 2,010,000.00 against a schedule balance of 2,000,000.00; the two sides do not reconcile

### report_count_wrong__Northmoor_Development_Group

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `rpt_report_count_ties` @ `debt_service_report:REPORT-2029/settled_count`  
  the report states 2 settled / 4 outstanding; the interest summary recomputes 1 / 4

### row_missing_field__Halbrook_Residential

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `acc_row_fields_present` @ `rollforward_schedule:ROLLFWD-2029/rows/0`  
  schedule row 0 (NR-1401) is missing or malformed: days

### same_entity__Stonecrest_Communities

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `note_entities_distinct` @ `note_register:NOTES-2029/notes/NR-1403/borrower_entity`  
  note NR-1403 names 'Halbrook Residential' as both lender and borrower; a note has two sides

### settled_flag_wrong__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `rpt_note_settled_recomputes` @ `interest_summary:SUMMARY-2029/notes/NR-1403/settled`  
  note NR-1403 is summarised settled=False; recomputing from its schedule gives settled=True

### subordination_breach__Northmoor_Development_Group

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 2)

- **FAIL** `rf_ending_balance_rederives` @ `rollforward_schedule:ROLLFWD-2029/rows/10/ending_cents`  
  row 10 (NR-1405) ends 1,200,000.00; 1,200,000.00 + 0.00 + 6,904.10 - 56,904.10 = 1,150,000.00 (off 50,000.00)
- **FAIL** `wf_subordination_order` @ `rollforward_schedule:ROLLFWD-2029/rows/NR-1405/2029-07-01/payment_cents`  
  note NR-1405 is subordinated to NR-1401, which is not repaid, yet it pays 56,904.10 against 6,904.10 accrued on 2029-07-01; 50,000.00 reduces principal ahead of the senior

### watchlist_overstated__Halbrook_Residential

**Verdict:** REVIEW (PASS 27, FLAG 1, FAIL 0)

- **FLAG** `rpt_watchlist_ties` @ `maturity_watchlist:WATCHLIST-2029/entries/NR-1402`  
  the watchlist lists note NR-1402 as maturing soon, but it is not inside the lead-time window as of 2029-10-01
