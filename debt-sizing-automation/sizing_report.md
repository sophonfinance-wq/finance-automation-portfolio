# Debt term-sheet sizing control report

**Overall verdict:** FAIL

- Sizing files analyzed: 23
- Controls in registry: 21
- PASS / REVIEW / FAIL: 1 / 2 / 20

All data is fictional. The engine is read-only and never writes to a source
artifact. Every term-sheet expiry test is made against the `as_of` pricing date
carried in the file, never the system clock.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `deal_unique_ids` | FAIL | 1 |
| 3 | `deal_loan_type_valid` | FAIL | 1 |
| 4 | `deal_index_valid` | FAIL | 1 |
| 5 | `deal_recourse_valid` | FAIL | 1 |
| 6 | `deal_basis_declared` | FAIL | 1 |
| 7 | `size_ltc_not_exceeded` | FAIL | 2 |
| 8 | `size_drawn_within_commitment` | FAIL | 2 |
| 9 | `size_maturity_reconciles` | FAIL | 1 |
| 10 | `rate_buildup_present` | FAIL | 1 |
| 11 | `rate_all_in_recomputes` | FAIL | 1 |
| 12 | `fee_type_valid` | FAIL | 1 |
| 13 | `fee_base_type_valid` | FAIL | 1 |
| 14 | `fee_deal_exists` | FAIL | 1 |
| 15 | `fee_amount_recomputes` | FAIL | 5 |
| 16 | `exp_termsheet_not_expired` | FAIL | 1 |
| 17 | `exp_termsheet_lead_time` | FLAG | 1 |
| 18 | `rpt_deal_count_ties` | FAIL | 1 |
| 19 | `rpt_commitment_total_ties` | FAIL | 2 |
| 20 | `rpt_fee_total_ties` | FAIL | 2 |
| 21 | `rpt_expiry_watchlist_ties` | FLAG | 1 |

## Sizing files

### all_in_wrong__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `rate_all_in_recomputes` @ `rate_summary:RATES-2029/rates/DL-201/all_in_rate_bps`  
  deal DL-201 states an all-in rate of 9.99%; the build-up recomputes to 7.00%

### amount_not_integer__Stonecrest_Communities

**Verdict:** FAIL (PASS 16, FLAG 0, FAIL 8)

- **FAIL** `size_ltc_not_exceeded` @ `amount:deal[DL-201].max_loan_amount_cents`  
  AMOUNT_INVALID: deal[DL-201].max_loan_amount_cents must be integer cents, got 6000000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `size_drawn_within_commitment` @ `amount:deal[DL-201].max_loan_amount_cents`  
  AMOUNT_INVALID: deal[DL-201].max_loan_amount_cents must be integer cents, got 6000000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `fee_amount_recomputes` @ `amount:deal[DL-201].max_loan_amount_cents`  
  AMOUNT_INVALID: deal[DL-201].max_loan_amount_cents must be integer cents, got 6000000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `fee_amount_recomputes` @ `amount:deal[DL-201].max_loan_amount_cents`  
  AMOUNT_INVALID: deal[DL-201].max_loan_amount_cents must be integer cents, got 6000000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `fee_amount_recomputes` @ `amount:deal[DL-201].max_loan_amount_cents`  
  AMOUNT_INVALID: deal[DL-201].max_loan_amount_cents must be integer cents, got 6000000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `fee_amount_recomputes` @ `amount:deal[DL-201].max_loan_amount_cents`  
  AMOUNT_INVALID: deal[DL-201].max_loan_amount_cents must be integer cents, got 6000000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `rpt_commitment_total_ties` @ `amount:deal[DL-201].max_loan_amount_cents`  
  AMOUNT_INVALID: deal[DL-201].max_loan_amount_cents must be integer cents, got 6000000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `rpt_fee_total_ties` @ `amount:deal[DL-201].max_loan_amount_cents`  
  AMOUNT_INVALID: deal[DL-201].max_loan_amount_cents must be integer cents, got 6000000000.5 -- amounts are integer cents and are never coerced

### bad_base_type__Ardenne_Field_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `fee_base_type_valid` @ `fee_schedule:FEES-2029/fees/FEE-203C/base_type`  
  fee FEE-203C is struck on base 'gross', which is not one of ('commitment', 'drawn', 'undrawn', 'facility')

### bad_fee_type__Westmere

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `fee_type_valid` @ `fee_schedule:FEES-2029/fees/FEE-201A/fee_type`  
  fee FEE-201A is typed 'exit', which is not one of ('origination', 'commitment', 'unused', 'admin')

### bad_index__Northmoor_Development_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `deal_index_valid` @ `deal_register:DEALS-2029/deals/DL-203/index_name`  
  deal DL-203 names index 'unlisted_index', which is not one of ('term_reference_index', 'overnight_index', 'prime_reference', 'fixed_swap_index')

### bad_loan_type__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `deal_loan_type_valid` @ `deal_register:DEALS-2029/deals/DL-204/loan_type`  
  deal DL-204 is typed 'revolver', which is not one of ('construction', 'permanent', 'bridge', 'mini_perm')

### bad_recourse__Stonecrest_Communities

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `deal_recourse_valid` @ `deal_register:DEALS-2029/deals/DL-202/recourse_type`  
  deal DL-202 carries recourse 'limited_recourse', which is not one of ('full_recourse', 'partial_recourse', 'non_recourse')

### basis_undeclared__Ardenne_Field_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `deal_basis_declared` @ `deal_register:DEALS-2029/deals/DL-203/cost_basis_cents`  
  deal DL-203 declares no positive cost basis; the advance-rate control would have no base to size the loan against

### clean__Northmoor_Development_Group

**Verdict:** PASS (PASS 21, FLAG 0, FAIL 0)

All controls held.

### commitment_total_wrong__Westmere

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `rpt_commitment_total_ties` @ `term_sheet_rollup:ROLLUP-2029/total_commitment_cents`  
  the rollup states 170,000,000.00 total commitment; the deals foot to 169,000,000.00

### deal_count_wrong__Northmoor_Development_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `rpt_deal_count_ties` @ `term_sheet_rollup:ROLLUP-2029/deal_count`  
  the rollup states 5 active deals; the register carries 4

### drawn_over_commitment__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `size_drawn_within_commitment` @ `deal_register:DEALS-2029/deals/DL-202/drawn_amount_cents`  
  deal DL-202 is drawn 50,000,000.01 against a commitment of 50,000,000.00 (over by 0.01)

### duplicate_deal_id__Stonecrest_Communities

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `deal_unique_ids` @ `deal_register:DEALS-2029/deals/DL-201`  
  deal id DL-201 appears 2 times; it would be double-counted in the portfolio total and its fees could not be attributed

### fee_amount_wrong__Ardenne_Field_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `fee_amount_recomputes` @ `fee_summary:FEEAMT-2029/amounts/FEE-201A/fee_amount_cents`  
  fee FEE-201A states 601,000.00; its rate on the commitment base recomputes to 600,000.00

### fee_orphan_deal__Westmere

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `fee_deal_exists` @ `fee_schedule:FEES-2029/fees/FEE-901/deal_id`  
  fee FEE-901 names deal 'DL-999', which is not in the deal register

### fee_total_wrong__Northmoor_Development_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `rpt_fee_total_ties` @ `term_sheet_rollup:ROLLUP-2029/total_fees_cents`  
  the rollup states 2,356,600.00 total fees; the fee lines foot to 2,356,500.00

### loan_over_advance__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `size_ltc_not_exceeded` @ `deal_register:DEALS-2029/deals/DL-204/max_loan_amount_cents`  
  deal DL-204 is sized to 37,400,000.01; max loan-to-cost 68.00% of cost basis 55,000,000.00 caps the loan at 37,400,000.00 (over by 0.01)

### maturity_mismatch__Stonecrest_Communities

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `size_maturity_reconciles` @ `deal_register:DEALS-2029/deals/DL-203/stated_maturity_months`  
  deal DL-203 states a 31-month maturity; base term 24 plus extensions [6] reconciles to 30

### missing_artifact__Ardenne_Field_Group

**Verdict:** FAIL (PASS 17, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `term_sheet_rollup:-`  
  term_sheet_rollup is missing; the controls that read it cannot run and must not be reported as having passed

### rate_buildup_missing__Westmere

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `rate_buildup_present` @ `rate_buildup:BUILDUP-2029/buildups/DL-204`  
  deal DL-204 has no rate build-up row; its all-in rate cannot be recomputed from an index, spread and floor

### termsheet_due_soon__Northmoor_Development_Group

**Verdict:** REVIEW (PASS 20, FLAG 1, FAIL 0)

- **FLAG** `exp_termsheet_lead_time` @ `deal_register:DEALS-2029/deals/DL-201/termsheet_expiration_date`  
  deal DL-201 term sheet expires 2029-10-20, in 19 day(s); inside the 45-day window and due to close

### termsheet_expired__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `exp_termsheet_not_expired` @ `deal_register:DEALS-2029/deals/DL-202/termsheet_expiration_date`  
  deal DL-202 term sheet expired 2029-09-01, on or before the pricing date 2029-10-01; its terms cannot close

### watchlist_overstated__Stonecrest_Communities

**Verdict:** REVIEW (PASS 20, FLAG 1, FAIL 0)

- **FLAG** `rpt_expiry_watchlist_ties` @ `expiry_watchlist:WATCH-2029/entries/DL-203`  
  the watchlist lists deal DL-203 as expiring, but its term sheet is not inside the lead-time window as of 2029-10-01
