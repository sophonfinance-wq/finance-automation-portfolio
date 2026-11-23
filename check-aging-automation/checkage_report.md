# Outstanding check aging and escheatment control report

**Overall verdict:** FAIL

- Aging files analyzed: 22
- Controls in registry: 20
- PASS / REVIEW / FAIL: 1 / 2 / 19

All data is fictional. The engine is read-only and never writes to a source
artifact; it never voids, re-issues, escheats or pays anything. Every age,
stale-dating and dormancy test is made against the `as_of` date carried in the
file, never the system clock.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `acct_unique_ids` | FAIL | 1 |
| 3 | `acct_jurisdiction_declared` | FAIL | 1 |
| 4 | `chk_required_fields` | FAIL | 1 |
| 5 | `chk_number_unique_per_account` | FAIL | 1 |
| 6 | `chk_account_exists` | FAIL | 1 |
| 7 | `chk_type_valid` | FAIL | 1 |
| 8 | `chk_date_not_future` | FAIL | 1 |
| 9 | `chk_cleared_pairing` | FAIL | 1 |
| 10 | `chk_cleared_ties_issued` | FAIL | 1 |
| 11 | `void_disposition_valid` | FAIL | 1 |
| 12 | `void_not_outstanding` | FAIL | 1 |
| 13 | `void_nets_to_zero` | FAIL | 1 |
| 14 | `age_outstanding_set_recomputes` | FAIL | 2 |
| 15 | `age_bucket_recomputes` | FAIL | 1 |
| 16 | `age_stale_dated_flagged` | FLAG | 1 |
| 17 | `esc_set_recomputes` | FAIL | 2 |
| 18 | `esc_jurisdiction_assigned` | FAIL | 1 |
| 19 | `rpt_outstanding_total_ties` | FAIL | 2 |
| 20 | `rpt_bucket_totals_tie` | FLAG | 2 |

## Aging files

### amount_not_integer__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 16, FLAG 1, FAIL 3)

- **FAIL** `age_outstanding_set_recomputes` @ `amount:check[BNK-100/CHK-4104].check_amount_cents`  
  AMOUNT_INVALID: check[BNK-100/CHK-4104].check_amount_cents must be integer cents, got 560000.5 -- amounts are integer cents and are never coerced
- **FAIL** `esc_set_recomputes` @ `amount:check[BNK-100/CHK-4104].check_amount_cents`  
  AMOUNT_INVALID: check[BNK-100/CHK-4104].check_amount_cents must be integer cents, got 560000.5 -- amounts are integer cents and are never coerced
- **FAIL** `rpt_outstanding_total_ties` @ `amount:check[BNK-100/CHK-4104].check_amount_cents`  
  AMOUNT_INVALID: check[BNK-100/CHK-4104].check_amount_cents must be integer cents, got 560000.5 -- amounts are integer cents and are never coerced
- **FLAG** `rpt_bucket_totals_tie` @ `amount:check[BNK-100/CHK-4104].check_amount_cents`  
  AMOUNT_INVALID: check[BNK-100/CHK-4104].check_amount_cents must be integer cents, got 560000.5 -- amounts are integer cents and are never coerced

### bad_check_type__Stonecrest_Communities

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `chk_type_valid` @ `check_register:CHECKS-2029/checks/BNK-100/CHK-4103/check_type`  
  check BNK-100/CHK-4103 is typed 'wire', which is not one of ('manual', 'system')

### bad_void_disposition__Ardenne_Field_Group

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `void_disposition_valid` @ `void_register:VOIDS-2029/entries/BNK-100/CHK-4109/disposition`  
  void entry BNK-100/CHK-4109 is dispositioned 'reissued', which is not one of ('voided', 'zero_dollar', 'stop_payment')

### bank_rec_total_wrong__Northmoor_Development_Group

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `rpt_outstanding_total_ties` @ `bank_reconciliation:BANKREC-2029/outstanding_checks_cents`  
  the reconciliation states 22,336.40 across 10 outstanding check(s); the register re-derives 21,336.40 across 10 (difference 1,000.00)

### bucket_total_overstated__Halbrook_Residential_Partners

**Verdict:** REVIEW (PASS 19, FLAG 1, FAIL 0)

- **FLAG** `rpt_bucket_totals_tie` @ `bank_reconciliation:BANKREC-2029/bucket_totals/31-60/amount_cents`  
  the 31-60 band states 2,200.25 across 1 item(s); the register re-derives 2,150.25 across 1

### check_dated_after_as_of__Stonecrest_Communities

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `chk_date_not_future` @ `check_register:CHECKS-2029/checks/BNK-100/CHK-4110/check_date`  
  check BNK-100/CHK-4110 is dated 2029-10-15, after the as-of date 2029-09-30; its age would be negative

### check_missing_field__Ardenne_Field_Group

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `chk_required_fields` @ `check_register:CHECKS-2029/checks/BNK-100/CHK-4105`  
  check BNK-100/CHK-4105 is missing payee

### clean__Northmoor_Development_Group

**Verdict:** PASS (PASS 20, FLAG 0, FAIL 0)

All controls held.

### cleared_amount_differs__Northmoor_Development_Group

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `chk_cleared_ties_issued` @ `check_register:CHECKS-2029/checks/BNK-100/CHK-4102/cleared_amount_cents`  
  check BNK-100/CHK-4102 was issued for 3,275.50 and cleared for 3,275.49; the 0.01 difference is an obligation that appears on no schedule

### cleared_without_date__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `chk_cleared_pairing` @ `check_register:CHECKS-2029/checks/BNK-100/CHK-4101/cleared_date`  
  check BNK-100/CHK-4101 carries a cleared amount of 12,450.00 and no cleared date; the two halves of the clearing must arrive together or the outstanding test is ambiguous

### duplicate_account_id__Stonecrest_Communities

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `acct_unique_ids` @ `bank_account_register:ACCOUNTS-2029/accounts/BNK-100`  
  bank account BNK-100 appears 2 times; a check drawn on it cannot be attributed to one account series

### duplicate_check_number__Ardenne_Field_Group

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `chk_number_unique_per_account` @ `check_register:CHECKS-2029/checks/BNK-100/CHK-4110`  
  check number CHK-4110 appears 2 times in bank account BNK-100; the register cannot say which row is the obligation

### escheatment_row_missing__Northmoor_Development_Group

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `esc_set_recomputes` @ `escheatment_schedule:ESCHEAT-2029/items/BNK-100/CHK-4111`  
  check BNK-100/CHK-4111 at 2,380.00 is 1349 day(s) old, past the 1095-day dormancy period, but is absent from the escheatment schedule

### follow_up_not_flagged__Halbrook_Residential_Partners

**Verdict:** REVIEW (PASS 19, FLAG 1, FAIL 0)

- **FLAG** `age_stale_dated_flagged` @ `outstanding_schedule:OUTSTANDING-2029/items/BNK-100/CHK-4107/follow_up_required`  
  check BNK-100/CHK-4107 is 228 day(s) old against a 180-day stale-dating threshold, so follow_up_required re-derives as True; the schedule states False

### missing_artifact__Stonecrest_Communities

**Verdict:** FAIL (PASS 17, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `bank_reconciliation:-`  
  bank_reconciliation is missing; the controls that read it cannot run and must not be reported as having passed

### missing_jurisdiction__Ardenne_Field_Group

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `acct_jurisdiction_declared` @ `bank_account_register:ACCOUNTS-2029/accounts/BNK-200/escheat_jurisdiction`  
  bank account BNK-200 declares no escheat jurisdiction; a dormant item drawn on it has nowhere to report

### outstanding_row_missing__Northmoor_Development_Group

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `age_outstanding_set_recomputes` @ `outstanding_schedule:OUTSTANDING-2029/items/BNK-100/CHK-4105`  
  check BNK-100/CHK-4105 at 2,150.25 has not cleared and is not withdrawn, but is absent from the outstanding schedule

### unknown_account_check__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `chk_account_exists` @ `check_register:CHECKS-2029/checks/BNK-900/CHK-4301/account_id`  
  check CHK-4301 is drawn on account 'BNK-900', which is not in the bank account register

### void_listed_outstanding__Stonecrest_Communities

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `void_not_outstanding` @ `outstanding_schedule:OUTSTANDING-2029/items/BNK-100/CHK-4109`  
  check BNK-100/CHK-4109 is on the outstanding schedule but the void register records it as withdrawn; a cancelled promise is not an outstanding obligation

### void_not_netted__Ardenne_Field_Group

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `void_nets_to_zero` @ `void_register:VOIDS-2029/entries/BNK-200/CHK-4107/void_amount_cents`  
  check BNK-200/CHK-4107 was issued for 7,300.00 and the stop_payment reverses -7,000.00, netting to 300.00 rather than zero

### wrong_aging_bucket__Northmoor_Development_Group

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `age_bucket_recomputes` @ `outstanding_schedule:OUTSTANDING-2029/items/BNK-100/CHK-4106/aging_bucket`  
  check BNK-100/CHK-4106 is bucketed '61-90' on the schedule; 94 day(s) falls in the 91-180 band

### wrong_escheat_jurisdiction__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `esc_jurisdiction_assigned` @ `escheatment_schedule:ESCHEAT-2029/items/BNK-200/CHK-4103/escheat_jurisdiction`  
  check BNK-200/CHK-4103 is scheduled to escheat to 'State of Marran'; bank account BNK-200 reports unclaimed property to 'City of Kelder'
