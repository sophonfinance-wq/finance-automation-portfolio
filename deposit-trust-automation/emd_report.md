# Earnest-money deposit trust control report

**Overall verdict:** FAIL

- Deposit files analyzed: 29
- Controls in registry: 27
- PASS / REVIEW / FAIL: 1 / 2 / 26

All data is fictional. The engine is read-only and never writes to a source
artifact. Every equality is exact to the cent; a variance of one cent is a
variance, and the only passing value on any reconciliation leg is zero.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `led_unique_ids` | FAIL | 1 |
| 3 | `led_required_fields` | FAIL | 1 |
| 4 | `seg_amount_splits` | FAIL | 1 |
| 5 | `seg_components_nonnegative` | FAIL | 1 |
| 6 | `tie_agent_variance_zero` | FAIL | 2 |
| 7 | `tie_agent_completeness` | FAIL | 1 |
| 8 | `tie_ledger_completeness` | FAIL | 1 |
| 9 | `tie_loan_leg_zero` | FAIL | 1 |
| 10 | `swp_posted_has_paydown` | FAIL | 1 |
| 11 | `swp_paydown_has_deposit` | FAIL | 1 |
| 12 | `swp_need_to_post_not_swept` | FAIL | 1 |
| 13 | `cxl_row_joins` | FAIL | 1 |
| 14 | `cxl_split_sums` | FAIL | 1 |
| 15 | `cxl_reversal_matches_sweep` | FAIL | 1 |
| 16 | `cxl_fee_account` | FAIL | 1 |
| 17 | `sts_valid_bucket` | FAIL | 1 |
| 18 | `sts_closed_excluded_from_agent` | FLAG | 1 |
| 19 | `bnk_upgrade_bank_ties` | FAIL | 1 |
| 20 | `bnk_forfeiture_income_ties` | FAIL | 1 |
| 21 | `net_sale_recomputes` | FAIL | 1 |
| 22 | `net_concession_sign` | FAIL | 1 |
| 23 | `net_concession_account` | FAIL | 1 |
| 24 | `rpt_unit_variance_recomputes` | FAIL | 2 |
| 25 | `rpt_exception_flags_tie` | FLAG | 2 |
| 26 | `rpt_total_variance_ties` | FAIL | 2 |
| 27 | `rpt_bucket_totals_tie` | FAIL | 1 |

## Deposit files

### agent_ledger_variance__Halbrook_Residential

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `tie_agent_variance_zero` @ `escrow_agent_statement:AGENT-2030/entries/UNIT-105/agent_deposit_cents`  
  unit UNIT-105: the escrow agent records 19,000.00 of earnest money; the deposit ledger supports 20,000.00 (variance -1,000.00); zero is the only passing value

### agent_missing_unit__Stonecrest_Communities

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `tie_ledger_completeness` @ `escrow_agent_statement:AGENT-2030/entries/UNIT-102`  
  the ledger carries 15,000.00 of pre-close earnest money for unit UNIT-102, but the escrow agent's statement does not list the unit; the funds have left escrow on paper only

### agent_unknown_unit__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `tie_agent_completeness` @ `escrow_agent_statement:AGENT-2030/entries/UNIT-999`  
  the escrow agent holds earnest money for unit UNIT-999, which has no deposit on the ledger at all; the receipt was never booked

### amount_not_integer__Westmere

**Verdict:** FAIL (PASS 23, FLAG 1, FAIL 3)

- **FAIL** `tie_agent_variance_zero` @ `amount:escrow_entry[UNIT-101].agent_deposit_cents`  
  AMOUNT_INVALID: escrow_entry[UNIT-101].agent_deposit_cents must be integer cents, got 3000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `rpt_unit_variance_recomputes` @ `amount:escrow_entry[UNIT-101].agent_deposit_cents`  
  AMOUNT_INVALID: escrow_entry[UNIT-101].agent_deposit_cents must be integer cents, got 3000000.5 -- amounts are integer cents and are never coerced
- **FLAG** `rpt_exception_flags_tie` @ `amount:escrow_entry[UNIT-101].agent_deposit_cents`  
  AMOUNT_INVALID: escrow_entry[UNIT-101].agent_deposit_cents must be integer cents, got 3000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `rpt_total_variance_ties` @ `amount:escrow_entry[UNIT-101].agent_deposit_cents`  
  AMOUNT_INVALID: escrow_entry[UNIT-101].agent_deposit_cents must be integer cents, got 3000000.5 -- amounts are integer cents and are never coerced

### amount_split_broken__Northmoor_Development_Group

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `seg_amount_splits` @ `deposit_ledger:LEDGER-2030/deposits/DEP-1001/amount_cents`  
  deposit DEP-1001 moved 26,000.00 of cash but splits into 5,000.00 upgrade + 20,000.00 earnest money = 25,000.00; the segregation identity does not hold

### bad_status_bucket__Halbrook_Residential

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `sts_valid_bucket` @ `deposit_ledger:LEDGER-2030/deposits/DEP-1002/status`  
  deposit DEP-1002 carries status 'pending', which is not one of ('need_to_post', 'already_posted', 'unit_closed'); it cannot be placed in any reconciliation bucket

### bucket_totals_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `rpt_bucket_totals_tie` @ `reconciliation_summary:RECON-2030/bucket_totals/need_to_post_cents`  
  the summary states 26,000.00 of earnest money in the need_to_post bucket; the ledger recomputes 25,000.00

### cancellation_orphan__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `cxl_row_joins` @ `cancellation_register:CXL-2030/cancellations/CXL-3999/deposit_id`  
  cancellation CXL-3999 names deposit 'DEP-8888', which is not on the ledger; it splits money that was never receipted

### clean__Northmoor_Development_Group

**Verdict:** PASS (PASS 27, FLAG 0, FAIL 0)

All controls held.

### closed_unit_on_agent__Westmere

**Verdict:** REVIEW (PASS 26, FLAG 1, FAIL 0)

- **FLAG** `sts_closed_excluded_from_agent` @ `escrow_agent_statement:AGENT-2030/entries/UNIT-103`  
  unit UNIT-103 still appears on the agent's open-escrow statement, but every deposit the ledger carries for it has closed or cancelled; the escrow is stale and belongs to the close-of-escrow handoff

### concession_misbooked__Northmoor_Development_Group

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `net_concession_account` @ `sales_matrix:SALES-2030/units/UNIT-101/concession_account`  
  unit UNIT-101 books its concession to '5010 Construction Cost of Sales'; a concession is a reduction of revenue and belongs in '3900 Sales Revenue - Concessions', never a construction cost code

### concession_positive__Halbrook_Residential

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `net_concession_sign` @ `sales_matrix:SALES-2030/units/UNIT-102/concession_cents`  
  unit UNIT-102 carries a concession of 2,000.00; a concession reduces revenue and is stored as a non-positive amount, so a positive one inflates the net sale price

### deposit_missing_field__Stonecrest_Communities

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `led_required_fields` @ `deposit_ledger:LEDGER-2030/deposits/DEP-1002`  
  deposit DEP-1002 is missing receipt_date

### duplicate_deposit_id__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `led_unique_ids` @ `deposit_ledger:LEDGER-2030/deposits/DEP-1001`  
  deposit id DEP-1001 appears 2 times; a paydown or cancellation that names it cannot be attributed to one receipt

### exception_flag_wrong__Westmere

**Verdict:** REVIEW (PASS 26, FLAG 1, FAIL 0)

- **FLAG** `rpt_exception_flags_tie` @ `reconciliation_summary:RECON-2030/units/UNIT-101/exception_flag`  
  unit UNIT-101 is flagged True but its recomputed variance of 0.00 says False; the reviewer's work queue does not match the evidence

### fee_account_wrong__Northmoor_Development_Group

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `cxl_fee_account` @ `cancellation_register:CXL-2030/cancellations/CXL-3001/fee_account`  
  cancellation CXL-3001 books its retained fee to '5010 Construction Cost of Sales'; a termination fee is forfeiture income and belongs in '4910 Forfeited Deposits', never a cost code

### forfeiture_income_wrong__Halbrook_Residential

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `bnk_forfeiture_income_ties` @ `trust_account_balances:TRUST-2030/forfeiture_income_cents`  
  forfeiture income is stated as 8,000.00; the cancellation register's retained fees sum to 7,500.00 (variance 500.00)

### forfeiture_split_broken__Stonecrest_Communities

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `cxl_split_sums` @ `cancellation_register:CXL-2030/cancellations/CXL-3001/termination_fee_cents`  
  cancellation CXL-3001: retained fee 6,000.00 + refund 10,000.00 = 16,000.00 does not account for the 15,000.00 earnest money of deposit DEP-1004 (difference 1,000.00)

### missing_artifact__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `reconciliation_summary:-`  
  reconciliation_summary is missing; the controls that read it cannot run and must not be reported as having passed

### negative_component__Westmere

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `seg_components_nonnegative` @ `deposit_ledger:LEDGER-2030/deposits/DEP-1006/upgrade_cents`  
  deposit DEP-1006 carries upgrade_cents of -2,000.00; a negative component fakes the segregation identity by moving money between the two deposit streams

### net_sale_wrong__Northmoor_Development_Group

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `net_sale_recomputes` @ `sales_matrix:SALES-2030/units/UNIT-105/net_sale_cents`  
  unit UNIT-105 states a net sale of 596,000.00; sales price 605,000.00 plus concession -10,000.00 recomputes to 595,000.00 (variance 1,000.00)

### orphan_paydown__Halbrook_Residential

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `swp_paydown_has_deposit` @ `loan_paydown_register:LOAN-2030/movements/PDN-2999/deposit_id`  
  movement PDN-2999 names deposit 'DEP-9999', which is not on the ledger; principal moved with no receipt behind it

### paydown_leg_short__Stonecrest_Communities

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `tie_loan_leg_zero` @ `loan_paydown_register:LOAN-2030/movements/UNIT-105`  
  unit UNIT-105: the loan register nets 19,000.00 of principal paydown; the ledger's swept earnest money supports 20,000.00 (variance -1,000.00)

### premature_sweep__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `swp_need_to_post_not_swept` @ `loan_paydown_register:LOAN-2030/movements/DEP-1002`  
  deposit DEP-1002 (unit UNIT-102) is still marked need_to_post yet the loan register already carries 1 paydown row(s) for it; the next posting run would sweep the same money twice

### reversal_missing__Westmere

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `cxl_reversal_matches_sweep` @ `loan_paydown_register:LOAN-2030/movements/DEP-1004`  
  cancelled deposit DEP-1004 (unit UNIT-104) was swept to the loan but the register carries 0 reversal row(s); its 15,000.00 paydown must be reversed exactly once

### summary_variance_wrong__Northmoor_Development_Group

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `rpt_unit_variance_recomputes` @ `reconciliation_summary:RECON-2030/units/UNIT-105/variance_cents`  
  unit UNIT-105 is summarised at a variance of 1,000.00; recomputing agent-minus-books gives 0.00

### sweep_missing__Halbrook_Residential

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `swp_posted_has_paydown` @ `loan_paydown_register:LOAN-2030/movements/DEP-1001`  
  deposit DEP-1001 (unit UNIT-101) is marked already_posted but the loan register carries 0 paydown row(s) for it; a swept deposit has exactly one

### total_variance_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `rpt_total_variance_ties` @ `reconciliation_summary:RECON-2030/total_variance_cents`  
  the summary states a total variance of 4,200.00; the recomputed unit variances foot to 0.00

### upgrade_bank_short__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `bnk_upgrade_bank_ties` @ `trust_account_balances:TRUST-2030/upgrade_bank_balance_cents`  
  the segregated upgrade-deposit bank states 6,500.00; the ledger's active pre-close upgrade deposits support 7,500.00 (variance -1,000.00)
