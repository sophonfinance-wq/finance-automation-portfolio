# Surety bond & collateral control report

**Overall verdict:** FAIL

- Programme files analyzed: 31
- Controls in registry: 29
- PASS / REVIEW / FAIL: 1 / 8 / 22

All data is fictional. The engine is read-only and never writes to a source
artifact. Every expiry and ageing test is made against the `as_of` date carried
in the file, never the system clock.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `reg_bond_number_unique` | FAIL | 1 |
| 3 | `reg_required_fields` | FAIL | 1 |
| 4 | `reg_status_domain` | FAIL | 1 |
| 5 | `reg_effective_before_expiration` | FAIL | 1 |
| 6 | `reg_project_mapped` | FAIL | 1 |
| 7 | `stat_licence_minimum` | FAIL | 1 |
| 8 | `stat_obligee_kind_matches_type` | FLAG | 1 |
| 9 | `stat_permit_reference_present` | FLAG | 1 |
| 10 | `life_active_not_expired` | FAIL | 2 |
| 11 | `life_expiry_horizon` | FLAG | 1 |
| 12 | `life_renewal_continuity` | FAIL | 1 |
| 13 | `life_released_has_evidence` | FAIL | 1 |
| 14 | `life_release_after_obligation` | FAIL | 1 |
| 15 | `life_maintenance_follows_acceptance` | FLAG | 1 |
| 16 | `life_no_release_while_collateral_outstanding` | FAIL | 2 |
| 17 | `coll_not_exceed_penal_sum` | FAIL | 2 |
| 18 | `coll_ledger_ties_register` | FAIL | 3 |
| 19 | `coll_refund_not_exceed_posted` | FAIL | 2 |
| 20 | `coll_refund_aging` | FLAG | 3 |
| 21 | `coll_location_recorded` | FLAG | 2 |
| 22 | `coll_ties_restricted_cash_gl` | FAIL | 3 |
| 23 | `prem_rate_within_schedule` | FLAG | 1 |
| 24 | `prem_no_premium_after_release` | FAIL | 1 |
| 25 | `prem_prepaid_amortisation_ties` | FAIL | 1 |
| 26 | `prem_return_has_rider` | FLAG | 1 |
| 27 | `prem_entry_type_domain` | FAIL | 1 |
| 28 | `expo_within_facility_limit` | FAIL | 1 |
| 29 | `expo_by_obligee_ties_total` | FAIL | 1 |

## Programme files

### amount_not_integer__Halbrook_Residential

**Verdict:** FAIL (PASS 22, FLAG 2, FAIL 7)

- **FAIL** `life_no_release_while_collateral_outstanding` @ `amount:collateral_ledger.entries[C-0018].amount_cents`  
  AMOUNT_INVALID: collateral_ledger.entries[C-0018].amount_cents must be integer cents, got 21000.0 -- amounts are integer cents and are never coerced
- **FAIL** `coll_not_exceed_penal_sum` @ `amount:collateral_ledger.entries[C-0018].amount_cents`  
  AMOUNT_INVALID: collateral_ledger.entries[C-0018].amount_cents must be integer cents, got 21000.0 -- amounts are integer cents and are never coerced
- **FAIL** `coll_ledger_ties_register` @ `amount:collateral_ledger.entries[C-0018].amount_cents`  
  AMOUNT_INVALID: collateral_ledger.entries[C-0018].amount_cents must be integer cents, got 21000.0 -- amounts are integer cents and are never coerced
- **FAIL** `coll_ledger_ties_register` @ `bond_register:BOND-2029Q1/bonds/B-4422/collateral_outstanding_cents`  
  bond B-4422 states 21,000.00 outstanding; the ledger shows 0.00 posted less 0.00 refunded = 0.00 (difference 21,000.00)
- **FAIL** `coll_refund_not_exceed_posted` @ `amount:collateral_ledger.entries[C-0018].amount_cents`  
  AMOUNT_INVALID: collateral_ledger.entries[C-0018].amount_cents must be integer cents, got 21000.0 -- amounts are integer cents and are never coerced
- **FLAG** `coll_refund_aging` @ `amount:collateral_ledger.entries[C-0018].amount_cents`  
  AMOUNT_INVALID: collateral_ledger.entries[C-0018].amount_cents must be integer cents, got 21000.0 -- amounts are integer cents and are never coerced
- **FLAG** `coll_location_recorded` @ `amount:collateral_ledger.entries[C-0018].amount_cents`  
  AMOUNT_INVALID: collateral_ledger.entries[C-0018].amount_cents must be integer cents, got 21000.0 -- amounts are integer cents and are never coerced
- **FAIL** `coll_ties_restricted_cash_gl` @ `amount:collateral_ledger.entries[C-0018].amount_cents`  
  AMOUNT_INVALID: collateral_ledger.entries[C-0018].amount_cents must be integer cents, got 21000.0 -- amounts are integer cents and are never coerced
- **FAIL** `coll_ties_restricted_cash_gl` @ `gl_positions:GL-2029Q1/restricted_cash_collateral_cents`  
  restricted cash carries 28,500.00; the collateral ledger nets to 7,500.00 (difference 21,000.00)

### bad_entry_type__Stonecrest_Communities

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `prem_entry_type_domain` @ `premium_ledger:PREM-2029Q1/entries/P-0104/entry_type`  
  premium entry P-0104 has type 'adjustment', outside ('initial', 'renewal', 'return'); it is excluded from every total built on type

### bad_status__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `reg_status_domain` @ `bond_register:BOND-2029Q1/bonds/B-4430/status`  
  bond B-4430 has status 'closed', which is outside ('pending', 'active', 'released', 'expired'); every lifecycle control keys off status

### clean__Northmoor_Development_Group

**Verdict:** PASS (PASS 29, FLAG 0, FAIL 0)

All controls held.

### collateral_ledger_break__Northmoor_Development_Group

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `coll_ledger_ties_register` @ `bond_register:BOND-2029Q1/bonds/B-4422/collateral_outstanding_cents`  
  bond B-4422 states 19,500.00 outstanding; the ledger shows 21,000.00 posted less 0.00 refunded = 21,000.00 (difference -1,500.00)

### collateral_over_penal_sum__Halbrook_Residential

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `coll_not_exceed_penal_sum` @ `bond_register:BOND-2029Q1/bonds/B-4440/penal_sum_cents`  
  bond B-4440 has 155,000.00 of collateral against a penal sum of 150,000.00; collateral cannot exceed the exposure it secures

### duplicate_bond_number__Stonecrest_Communities

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `reg_bond_number_unique` @ `bond_register:BOND-2029Q1/bonds/B-4440`  
  bond number B-4440 appears 2 times; it is the join key to the collateral and premium ledgers

### early_release__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `life_release_after_obligation` @ `bond_register:BOND-2029Q1/bonds/B-4431/release_date`  
  bond B-4431 was released 2028-04-20 but the warranty period ended 2028-05-20; cover was stood down while the obligation ran

### expired_but_active__Northmoor_Development_Group

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `life_active_not_expired` @ `bond_register:BOND-2029Q1/bonds/B-4416/expiration_date`  
  bond B-4416 is carried active but expired 2028-12-31, before the 2029-02-15 review date; the programme believes it holds cover it does not hold

### expiring_soon__Halbrook_Residential

**Verdict:** REVIEW (PASS 28, FLAG 1, FAIL 0)

- **FLAG** `life_expiry_horizon` @ `bond_register:BOND-2029Q1/bonds/B-4445/expiration_date`  
  bond B-4445 expires 2029-03-20, within 60 days of the review date; renew it or release it and recover the collateral

### inverted_term__Stonecrest_Communities

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 2)

- **FAIL** `reg_effective_before_expiration` @ `bond_register:BOND-2029Q1/bonds/B-4445/effective_date`  
  bond B-4445 is effective 2030-05-01 but expires 2028-05-01; the term does not run forwards
- **FAIL** `life_active_not_expired` @ `bond_register:BOND-2029Q1/bonds/B-4445/expiration_date`  
  bond B-4445 is carried active but expired 2028-05-01, before the 2029-02-15 review date; the programme believes it holds cover it does not hold

### licence_below_minimum__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `stat_licence_minimum` @ `bond_register:BOND-2029Q1/bonds/B-4402/penal_sum_cents`  
  bond B-4402 is written for 10,000.00 against a statutory minimum of 15,000.00 in Ardenne; the registration it supports is defective

### maintenance_before_acceptance__Northmoor_Development_Group

**Verdict:** REVIEW (PASS 28, FLAG 1, FAIL 0)

- **FLAG** `life_maintenance_follows_acceptance` @ `bond_register:BOND-2029Q1/bonds/B-4416/effective_date`  
  maintenance bond B-4416 incepts 2028-03-01 but the work was accepted 2028-06-15; it is carrying premium for a period in which it secures nothing

### missing_artifact__Halbrook_Residential

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `rate_schedule:-`  
  rate_schedule is missing; the controls that read it cannot run and must not be reported as having passed

### missing_collateral_location__Stonecrest_Communities

**Verdict:** REVIEW (PASS 28, FLAG 1, FAIL 0)

- **FLAG** `coll_location_recorded` @ `bond_register:BOND-2029Q1/bonds/B-4422/collateral_location`  
  bond B-4422 holds 21,000.00 of collateral with no recorded custodian; recovery starts with knowing who has it

### missing_permit_no__Ardenne_Field_Partners

**Verdict:** REVIEW (PASS 28, FLAG 1, FAIL 0)

- **FLAG** `stat_permit_reference_present` @ `bond_register:BOND-2029Q1/bonds/B-4422/permit_no`  
  bond B-4422 is a performance bond with no permit number; the release request has nothing to cite

### missing_required_field__Northmoor_Development_Group

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `reg_required_fields` @ `bond_register:BOND-2029Q1/bonds/B-4422`  
  bond B-4422 is missing obligee

### obligee_summary_break__Halbrook_Residential

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `expo_by_obligee_ties_total` @ `bond_register:BOND-2029Q1/exposure_by_obligee/City of Brightwater`  
  the summary shows 1,520,000.00 of active exposure with City of Brightwater; the register carries 1,588,500.00 (difference -68,500.00)

### over_facility_limit__Stonecrest_Communities

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `expo_within_facility_limit` @ `surety_facility:FAC-2029/aggregate_limit_cents`  
  active penal sums total 1,615,500.00 against an aggregate limit of 1,000,000.00; the programme is 615,500.00 over and the next bond will be declined for capacity

### over_refund__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `coll_refund_not_exceed_posted` @ `collateral_ledger:COLL-2029Q1/entries/B-4430`  
  bond B-4430 has 15,000.00 refunded against 12,500.00 posted; the excess 2,500.00 belongs to another bond

### premium_after_release__Northmoor_Development_Group

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `prem_no_premium_after_release` @ `premium_ledger:PREM-2029Q1/entries/P-0120/period_from`  
  bond B-4431 was released 2028-06-01 but is charged 350.00 for a period starting 2028-11-01; the surety was never told to stop

### premium_off_rate__Halbrook_Residential

**Verdict:** REVIEW (PASS 28, FLAG 1, FAIL 0)

- **FLAG** `prem_rate_within_schedule` @ `bond_register:BOND-2029Q1/bonds/B-4445/annual_premium_cents`  
  bond B-4445 carries premium 31,000.00; the card rates a performance bond of 950,000.00 at 17,100.00 (tolerance 2,565.00)

### prepaid_break__Stonecrest_Communities

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `prem_prepaid_amortisation_ties` @ `gl_positions:GL-2029Q1/prepaid_bond_premium_cents`  
  prepaid bond premium carries 14,914.81; straight-line amortisation of the premium ledger to 2029-02-15 gives 12,514.81 (difference 2,400.00)

### released_with_collateral__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 27, FLAG 1, FAIL 1)

- **FAIL** `life_no_release_while_collateral_outstanding` @ `bond_register:BOND-2029Q1/bonds/B-4415/collateral_refund_status`  
  bond B-4415 is released but 34,250.00 of collateral is still with the surety and no refund is recorded as in flight; the cash is sitting in restricted cash with nothing chasing it
- **FLAG** `coll_refund_aging` @ `bond_register:BOND-2029Q1/bonds/B-4415/collateral_outstanding_cents`  
  bond B-4415 was released 2028-08-01 and 34,250.00 of collateral is still outstanding 198 days later (>180-day band)

### released_without_evidence__Northmoor_Development_Group

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `life_released_has_evidence` @ `bond_register:BOND-2029Q1/bonds/B-4431/release_reference`  
  bond B-4431 is marked released with no obligee release document; the release is asserted, not evidenced

### renewal_gap__Halbrook_Residential

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `life_renewal_continuity` @ `bond_register:BOND-2029Q1/bonds/B-4401/effective_date`  
  bond B-4401 takes effect 2028-10-15 but B-4399 expired 2028-09-01, leaving 43 day(s) in which the obligation was unbonded

### restricted_cash_break__Stonecrest_Communities

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `coll_ties_restricted_cash_gl` @ `gl_positions:GL-2029Q1/restricted_cash_collateral_cents`  
  restricted cash carries 36,000.00; the collateral ledger nets to 28,500.00 (difference 7,500.00)

### return_without_rider__Ardenne_Field_Partners

**Verdict:** REVIEW (PASS 28, FLAG 1, FAIL 0)

- **FLAG** `prem_return_has_rider` @ `premium_ledger:PREM-2029Q1/entries/P-0108/rider_reference`  
  return premium entry P-0108 on bond B-4415 cites no rider; nothing ties the credit to a reduction in the penal sum

### stale_collateral__Northmoor_Development_Group

**Verdict:** REVIEW (PASS 28, FLAG 1, FAIL 0)

- **FLAG** `coll_refund_aging` @ `bond_register:BOND-2029Q1/bonds/B-4415/collateral_outstanding_cents`  
  bond B-4415 was released 2028-08-01 and 34,250.00 of collateral is still outstanding 198 days later (>180-day band)

### unmapped_project__Halbrook_Residential

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `reg_project_mapped` @ `bond_register:BOND-2029Q1/bonds/B-4416/project_code`  
  bond B-4416 names project 'PRJ-999', which is not in the project register; its obligation end cannot be derived

### wrong_obligee_kind__Stonecrest_Communities

**Verdict:** REVIEW (PASS 28, FLAG 1, FAIL 0)

- **FLAG** `stat_obligee_kind_matches_type` @ `bond_register:BOND-2029Q1/bonds/B-4401/obligee_kind`  
  bond B-4401 is a licence bond held by a municipality; a licence bond is held by a state_agency, so it may have been filed with the wrong body
