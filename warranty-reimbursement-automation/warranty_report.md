# Warranty reimbursement control report

**Overall verdict:** FAIL

- Claim files analyzed: 25
- Controls in registry: 22
- PASS / REVIEW / FAIL: 1 / 2 / 22

All data is fictional. The engine is read-only and never writes to a source
artifact.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `set_period_label` | FAIL | 1 |
| 3 | `pol_premium_derived_from_cost` | FAIL | 1 |
| 4 | `pol_coverage_derived_from_premium` | FAIL | 2 |
| 5 | `pol_period_length` | FAIL | 1 |
| 6 | `pol_cumulative_within_limit` | FAIL | 1 |
| 7 | `pol_remaining_is_limit_less_cumulative` | FAIL | 3 |
| 8 | `pol_coverage_not_nearly_exhausted` | FLAG | 1 |
| 9 | `clm_period_subtotals_foot` | FAIL | 2 |
| 10 | `clm_cumulative_is_sum_of_periods` | FAIL | 3 |
| 11 | `clm_request_matches_current_period` | FAIL | 2 |
| 12 | `clm_claim_inside_its_period` | FAIL | 1 |
| 13 | `clm_claim_inside_policy_period` | FAIL | 1 |
| 14 | `clm_no_duplicate_invoice` | FAIL | 1 |
| 15 | `cost_claim_traces_to_ledger` | FAIL | 3 |
| 16 | `cost_uses_warranty_cost_code` | FAIL | 1 |
| 17 | `cost_accounting_date_inside_period` | FLAG | 1 |
| 18 | `unit_claim_unit_has_closed` | FAIL | 1 |
| 19 | `unit_claim_after_close` | FAIL | 1 |
| 20 | `rem_insured_entity_matches` | FAIL | 1 |
| 21 | `rem_bank_details_present` | FLAG | 1 |
| 22 | `rem_submission_approved` | FAIL | 1 |

## Claim files

### accounting_outside_window__Brightwater_Commons

**Verdict:** REVIEW (PASS 21, FLAG 1, FAIL 0)

- **FLAG** `cost_accounting_date_inside_period` @ `warranty_cost_ledger:LDG-2028-Q2/transactions/HE-2210/accounting_date`  
  transaction on invoice HE-2210 is accounted 2029-01-10, outside the ledger's 2027-07-01..2028-06-30 window

### amount_not_integer__Copperfield_Yards

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 2)

- **FAIL** `clm_period_subtotals_foot` @ `amount:history.2027-Q3.claims[1].amount_cents`  
  AMOUNT_INVALID: history.2027-Q3.claims[1].amount_cents must be integer cents, got 124000.5 -- amounts are integer cents and are never coerced
- **FAIL** `cost_claim_traces_to_ledger` @ `amount:history.claims[1].amount_cents`  
  AMOUNT_INVALID: history.claims[1].amount_cents must be integer cents, got 124000.5 -- amounts are integer cents and are never coerced

### bad_period_label__Dunmore_Flats

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 2)

- **FAIL** `set_period_label` @ `file:bad_period_label__Dunmore_Flats/period`  
  reporting period '2028-06' is not a YYYY-Qn label; every claim is filed against a quarter and cannot be placed without one
- **FAIL** `clm_request_matches_current_period` @ `claims_history:HIS-2028-Q2/periods`  
  the claims history carries no period 2028-06, which is the period this submission is filed for

### bank_details_missing__Alderpoint_Terraces

**Verdict:** REVIEW (PASS 21, FLAG 1, FAIL 0)

- **FLAG** `rem_bank_details_present` @ `claim_submission:CLM-2028-Q2/remit_bank_name`  
  wire instructions are incomplete: remit_routing_reference is missing, so the claim cannot be paid as submitted

### claim_amount_mismatch__Brightwater_Commons

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `cost_claim_traces_to_ledger` @ `claims_history:HIS-2028-Q2/periods/2028-Q2/claims/2/amount_cents`  
  claim 2 requests 640.00 but the ledger carries 550.00 for invoice CM-1180

### claim_before_close__Copperfield_Yards

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `unit_claim_after_close` @ `claims_history:HIS-2028-Q2/periods/2028-Q2/claims/1/claim_date`  
  claim 1 is dated 2028-04-22, before unit U-18 closed on 2028-05-01; the defect predates the coverage

### claim_outside_policy__Dunmore_Flats

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `clm_claim_inside_policy_period` @ `claims_history:HIS-2028-Q2/periods/2028-Q2/claims/1/claim_date`  
  claim 1 is dated 2029-02-11, outside the policy period (2027-06-01..2028-12-01); it is not covered

### claim_outside_quarter__Alderpoint_Terraces

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `clm_claim_inside_its_period` @ `claims_history:HIS-2028-Q2/periods/2028-Q1/claims/1/claim_date`  
  claim 1 is dated 2028-04-09, outside its 2028-Q1 window (2028-01-01..2028-03-31)

### claim_without_cost__Brightwater_Commons

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `cost_claim_traces_to_ledger` @ `claims_history:HIS-2028-Q2/periods/2028-Q2/claims/1`  
  claim 1 for 3,180.00 cites invoice RP-9999 from Rosewater Plumbing, which has no matching warranty cost in the job-cost ledger

### clean__Alderpoint_Terraces

**Verdict:** PASS (PASS 22, FLAG 0, FAIL 0)

All controls held.

### coverage_off__Copperfield_Yards

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 2)

- **FAIL** `pol_coverage_derived_from_premium` @ `policy_declaration:POL-2027-0001/coverage_limit_cents`  
  premium 104,365.48 at 130.00% derives a coverage limit of 135,675.12, but 144,675.12 is recorded
- **FAIL** `pol_remaining_is_limit_less_cumulative` @ `claim_submission:CLM-2028-Q2/coverage_remaining_cents`  
  limit 144,675.12 less cumulative 10,300.00 = 134,375.12, but coverage remaining is stated as 125,375.12

### cumulative_off__Dunmore_Flats

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 2)

- **FAIL** `pol_remaining_is_limit_less_cumulative` @ `claim_submission:CLM-2028-Q2/coverage_remaining_cents`  
  limit 135,675.12 less cumulative 11,400.00 = 124,275.12, but coverage remaining is stated as 125,375.12
- **FAIL** `clm_cumulative_is_sum_of_periods` @ `claim_submission:CLM-2028-Q2/cumulative_reimbursement_cents`  
  period subtotals sum to 10,300.00 but cumulative reimbursement is stated as 11,400.00 (difference -1,100.00)

### duplicate_invoice__Alderpoint_Terraces

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `clm_no_duplicate_invoice` @ `claims_history:HIS-2028-Q2/claims/Rosewater Plumbing/RP-4412`  
  invoice RP-4412 from Rosewater Plumbing is claimed in 2 periods (2027-Q3, 2028-Q2); the same repair is being reimbursed more than once

### missing_artifact__Brightwater_Commons

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `file:missing_artifact__Brightwater_Commons/closed_units`  
  claim file carries no closed_units; absent evidence is not a passing control, so no downstream rule may read it

### nearly_exhausted__Copperfield_Yards

**Verdict:** FAIL (PASS 20, FLAG 1, FAIL 1)

- **FLAG** `pol_coverage_not_nearly_exhausted` @ `claim_submission:CLM-2028-Q2/coverage_remaining_cents`  
  only 4,000.00 of the 135,675.12 pool remains (2.94%); further defects on this project will not be recoverable once it is gone
- **FAIL** `clm_cumulative_is_sum_of_periods` @ `claim_submission:CLM-2028-Q2/cumulative_reimbursement_cents`  
  period subtotals sum to 10,300.00 but cumulative reimbursement is stated as 131,675.12 (difference -121,375.12)

### over_limit__Dunmore_Flats

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `pol_cumulative_within_limit` @ `claim_submission:CLM-2028-Q2/cumulative_reimbursement_cents`  
  cumulative reimbursement of 150,300.00 exceeds the 135,675.12 coverage limit by 14,624.88; the pool is finite and the excess is not recoverable

### policy_end_off__Alderpoint_Terraces

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `pol_period_length` @ `policy_declaration:POL-2027-0001/policy_end`  
  a 18-month policy starting 2027-06-01 ends 2028-12-01, but 2028-11-01 is recorded

### premium_off__Brightwater_Commons

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 2)

- **FAIL** `pol_premium_derived_from_cost` @ `policy_declaration:POL-2027-0001/premium_cents`  
  construction cost 6,957,699.00 at 1.50% derives a premium of 104,365.48, but 105,865.48 is recorded
- **FAIL** `pol_coverage_derived_from_premium` @ `policy_declaration:POL-2027-0001/coverage_limit_cents`  
  premium 105,865.48 at 130.00% derives a coverage limit of 137,625.12, but 135,675.12 is recorded

### remaining_off__Copperfield_Yards

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `pol_remaining_is_limit_less_cumulative` @ `claim_submission:CLM-2028-Q2/coverage_remaining_cents`  
  limit 135,675.12 less cumulative 10,300.00 = 125,375.12, but coverage remaining is stated as 124,625.12

### request_off__Dunmore_Flats

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `clm_request_matches_current_period` @ `claim_submission:CLM-2028-Q2/reimbursement_requested_cents`  
  the submission requests 4,040.00 but the claims filed for 2028-Q2 total 3,820.00

### subtotal_off__Alderpoint_Terraces

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 2)

- **FAIL** `clm_period_subtotals_foot` @ `claims_history:HIS-2028-Q2/periods/2028-Q1/subtotal_cents`  
  2028-Q1: claim lines sum to 2,805.00 but the subtotal declares 3,105.00 (difference -300.00)
- **FAIL** `clm_cumulative_is_sum_of_periods` @ `claim_submission:CLM-2028-Q2/cumulative_reimbursement_cents`  
  period subtotals sum to 10,600.00 but cumulative reimbursement is stated as 10,300.00 (difference 300.00)

### unapproved__Brightwater_Commons

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `rem_submission_approved` @ `claim_submission:CLM-2028-Q2/approved_by`  
  the claim submission carries no approver; a request for money leaves the business unapproved

### unit_not_closed__Copperfield_Yards

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `unit_claim_unit_has_closed` @ `claims_history:HIS-2028-Q2/periods/2028-Q2/claims/1/unit`  
  claim 1 is for unit U-18, which has no recorded close of escrow; warranty coverage does not begin until the home is sold

### wrong_cost_code__Dunmore_Flats

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `cost_uses_warranty_cost_code` @ `warranty_cost_ledger:LDG-2028-Q2/transactions/RP-4630/cost_code`  
  transaction on invoice RP-4630 is coded 12-400, which is not a warranty cost code (86-103, 86-104)

### wrong_remittee__Alderpoint_Terraces

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `rem_insured_entity_matches` @ `claim_submission:CLM-2028-Q2/remit_to_entity`  
  reimbursement is directed to 'Alderpoint Services LLC' but the policy insures 'Alderpoint Terraces Holdings LLC'
