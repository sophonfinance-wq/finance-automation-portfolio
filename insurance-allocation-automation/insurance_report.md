# Insurance cost allocation control report

**Overall verdict:** FAIL

- Programme files analyzed: 26
- Controls in registry: 24
- PASS / REVIEW / FAIL: 1 / 2 / 23

All data is fictional. The engine is read-only and never writes to a source
artifact. Every expiry and ageing test is made against the `as_of` date carried
in the file, never the system clock.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `pol_required_fields` | FAIL | 1 |
| 3 | `pol_no_duplicate` | FAIL | 1 |
| 4 | `pol_term_runs_forwards` | FAIL | 1 |
| 5 | `pol_no_coverage_gap` | FAIL | 1 |
| 6 | `pol_tower_has_no_gap` | FAIL | 1 |
| 7 | `alloc_basis_declared` | FAIL | 1 |
| 8 | `alloc_project_exists` | FAIL | 1 |
| 9 | `alloc_only_covered_projects` | FAIL | 2 |
| 10 | `alloc_basis_data_complete` | FAIL | 3 |
| 11 | `alloc_sums_to_premium` | FAIL | 2 |
| 12 | `alloc_shares_recompute` | FAIL | 9 |
| 13 | `alloc_no_negative` | FAIL | 2 |
| 14 | `br_value_ties_budget` | FLAG | 1 |
| 15 | `br_term_covers_construction` | FAIL | 1 |
| 16 | `br_completed_project_removed` | FAIL | 1 |
| 17 | `aud_true_up_sums` | FAIL | 1 |
| 18 | `aud_credits_deposit_bearers` | FAIL | 1 |
| 19 | `aud_uses_deposit_basis` | FAIL | 3 |
| 20 | `aud_basis_restated` | FLAG | 1 |
| 21 | `gl_allocation_ties_job_cost` | FAIL | 8 |
| 22 | `gl_prepaid_amortisation_ties` | FAIL | 4 |
| 23 | `gl_total_ties_programme` | FAIL | 2 |
| 24 | `rpt_per_unit_recomputes` | FLAG | 8 |

## Programme files

### allocation_short__Halbrook_Residential

**Verdict:** FAIL (PASS 20, FLAG 1, FAIL 3)

- **FAIL** `alloc_sums_to_premium` @ `allocation_schedule:ALLOC-2029/allocations/GL-2029`  
  policy GL-2029 allocates 233,500.00 against a premium of 234,000.00 (difference -500.00); the residual is on no project at all
- **FAIL** `alloc_shares_recompute` @ `allocation_schedule:ALLOC-2029/allocations/GL-2029/PRJ-101`  
  policy GL-2029 allocates 88,630.60 to PRJ-101; 234,000.00 weighted by hard_cost_cents derives 89,130.60 (difference -500.00)
- **FAIL** `gl_allocation_ties_job_cost` @ `job_cost_ledger:JOBCOST-2029/postings/PRJ-101`  
  project PRJ-101 carries 237,690.00 of insurance in job cost; the allocation schedule gives it 237,190.00 (difference 500.00)
- **FLAG** `rpt_per_unit_recomputes` @ `allocation_summary:SUMMARY-2029/projects/PRJ-101/per_unit_cents`  
  project PRJ-101 reports 5,942.25 per unit; 237,190.00 across 40 units is 5,929.75

### amount_not_integer__Stonecrest_Communities

**Verdict:** FAIL (PASS 19, FLAG 2, FAIL 5)

- **FAIL** `alloc_sums_to_premium` @ `amount:allocation[GL-2029/PRJ-102].allocated_cents`  
  AMOUNT_INVALID: allocation[GL-2029/PRJ-102].allocated_cents must be integer cents, got 6685380.5 -- amounts are integer cents and are never coerced
- **FAIL** `alloc_shares_recompute` @ `amount:allocation[GL-2029/PRJ-102].allocated_cents`  
  AMOUNT_INVALID: allocation[GL-2029/PRJ-102].allocated_cents must be integer cents, got 6685380.5 -- amounts are integer cents and are never coerced
- **FAIL** `alloc_no_negative` @ `amount:allocation[GL-2029/PRJ-102].allocated_cents`  
  AMOUNT_INVALID: allocation[GL-2029/PRJ-102].allocated_cents must be integer cents, got 6685380.5 -- amounts are integer cents and are never coerced
- **FAIL** `gl_allocation_ties_job_cost` @ `amount:allocation[GL-2029/PRJ-102].allocated_cents`  
  AMOUNT_INVALID: allocation[GL-2029/PRJ-102].allocated_cents must be integer cents, got 6685380.5 -- amounts are integer cents and are never coerced
- **FAIL** `gl_allocation_ties_job_cost` @ `job_cost_ledger:JOBCOST-2029/postings/PRJ-102`  
  project PRJ-102 carries 178,275.60 of insurance in job cost; the allocation schedule gives it 111,421.80 (difference 66,853.80)
- **FLAG** `rpt_per_unit_recomputes` @ `amount:allocation[GL-2029/PRJ-102].allocated_cents`  
  AMOUNT_INVALID: allocation[GL-2029/PRJ-102].allocated_cents must be integer cents, got 6685380.5 -- amounts are integer cents and are never coerced
- **FLAG** `rpt_per_unit_recomputes` @ `allocation_summary:SUMMARY-2029/projects/PRJ-102/per_unit_cents`  
  project PRJ-102 reports 5,942.52 per unit; 111,421.80 across 30 units is 3,714.06

### audit_no_final_basis__Ardenne_Field_Partners

**Verdict:** REVIEW (PASS 23, FLAG 1, FAIL 0)

- **FLAG** `aud_basis_restated` @ `audit_register:AUDIT-2029/audits/AUD-2028/reallocation/PRJ-101/final_basis_cents`  
  audit AUD-2028 records no final exposure for PRJ-101; next year's deposit will be estimated from the figure this audit just corrected

### audit_true_up_short__Northmoor_Development_Group

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 2)

- **FAIL** `aud_true_up_sums` @ `audit_register:AUDIT-2029/audits/AUD-2028/reallocation`  
  audit AUD-2028 reallocates 17,900.00 of a 18,000.00 true-up (difference -100.00)
- **FAIL** `aud_uses_deposit_basis` @ `audit_register:AUDIT-2029/audits/AUD-2028/reallocation/PRJ-101`  
  audit AUD-2028 credits 6,756.20 to PRJ-101; the deposit basis derives 6,856.20 (difference -100.00)

### audit_wrong_basis__Halbrook_Residential

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 2)

- **FAIL** `aud_uses_deposit_basis` @ `audit_register:AUDIT-2029/audits/AUD-2028/reallocation/PRJ-101`  
  audit AUD-2028 credits 6,806.20 to PRJ-101; the deposit basis derives 6,856.20 (difference -50.00)
- **FAIL** `aud_uses_deposit_basis` @ `audit_register:AUDIT-2029/audits/AUD-2028/reallocation/PRJ-102`  
  audit AUD-2028 credits 5,192.60 to PRJ-102; the deposit basis derives 5,142.60 (difference 50.00)

### audit_wrong_bearers__Stonecrest_Communities

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `aud_credits_deposit_bearers` @ `audit_register:AUDIT-2029/audits/AUD-2028/reallocation/PRJ-777`  
  audit AUD-2028 on policy GL-2028 credits PRJ-777, which never bore the deposit premium on that policy

### br_term_short__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `br_term_covers_construction` @ `policy_register:POL-2029/policies/BR-2029/inception_date`  
  policy BR-2029 runs 2029-07-01 to 2030-07-01 while PRJ-101 builds 2029-08-01 to 2030-08-01; the construction is not fully bracketed

### builders_value_adrift__Northmoor_Development_Group

**Verdict:** FAIL (PASS 22, FLAG 1, FAIL 3)

- **FAIL** `alloc_shares_recompute` @ `allocation_schedule:ALLOC-2029/allocations/BR-2029/PRJ-101`  
  policy BR-2029 allocates 32,004.00 to PRJ-101; 72,000.00 weighted by insured_value_cents derives 27,000.00 (difference 5,004.00)
- **FAIL** `alloc_shares_recompute` @ `allocation_schedule:ALLOC-2029/allocations/BR-2029/PRJ-102`  
  policy BR-2029 allocates 23,997.60 to PRJ-102; 72,000.00 weighted by insured_value_cents derives 31,500.00 (difference -7,502.40)
- **FAIL** `alloc_shares_recompute` @ `allocation_schedule:ALLOC-2029/allocations/BR-2029/PRJ-103`  
  policy BR-2029 allocates 15,998.40 to PRJ-103; 72,000.00 weighted by insured_value_cents derives 13,500.00 (difference 2,498.40)
- **FLAG** `br_value_ties_budget` @ `project_register:PROJ-2029/projects/PRJ-102/insured_value_cents`  
  project PRJ-102 is insured for 5,600,000.00 against a hard-cost budget of 3,600,000.00 (tolerance 360,000.00)

### clean__Northmoor_Development_Group

**Verdict:** PASS (PASS 24, FLAG 0, FAIL 0)

All controls held.

### completed_still_scheduled__Halbrook_Residential

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `br_completed_project_removed` @ `policy_register:POL-2029/policies/BR-2029/covered_projects`  
  policy BR-2029 still schedules PRJ-101, which is complete; it is taking a share of a builder's risk premium for cover that no longer applies

### coverage_gap__Stonecrest_Communities

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 2)

- **FAIL** `pol_no_coverage_gap` @ `policy_register:POL-2029/policies/GL-2029/inception_date`  
  general_liability (primary) expires 2029-07-01 on GL-2028 and does not resume until 2029-09-01 on GL-2029, leaving 62 uninsured day(s)
- **FAIL** `gl_prepaid_amortisation_ties` @ `gl_positions:GL-2029/prepaid_insurance_cents`  
  prepaid insurance carries 300,673.95; straight-line amortisation of the policy register to 2029-10-01 gives 336,486.46 (difference -35,812.51)

### duplicate_policy__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 3)

- **FAIL** `pol_no_duplicate` @ `policy_register:POL-2029/policies/GL-2029`  
  policy GL-2029 appears 2 times; its premium is counted 2 times in the programme total
- **FAIL** `gl_prepaid_amortisation_ties` @ `gl_positions:GL-2029/prepaid_insurance_cents`  
  prepaid insurance carries 300,673.95; straight-line amortisation of the policy register to 2029-10-01 gives 475,693.12 (difference -175,019.17)
- **FAIL** `gl_total_ties_programme` @ `gl_positions:GL-2029/total_insurance_cost_cents`  
  the ledger carries 612,000.00 of programme cost; the policy register sums to 846,000.00 (difference -234,000.00)

### inverted_term__Northmoor_Development_Group

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 2)

- **FAIL** `pol_term_runs_forwards` @ `policy_register:POL-2029/policies/XS-2029/inception_date`  
  policy XS-2029 incepts 2029-07-01 and expires 2029-06-01; the term does not run forwards
- **FAIL** `gl_prepaid_amortisation_ties` @ `gl_positions:GL-2029/prepaid_insurance_cents`  
  prepaid insurance carries 300,673.95; straight-line amortisation of the policy register to 2029-10-01 gives 228,871.22 (difference 71,802.73)

### jobcost_untied__Halbrook_Residential

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `gl_allocation_ties_job_cost` @ `job_cost_ledger:JOBCOST-2029/postings/PRJ-101`  
  project PRJ-101 carries 237,940.00 of insurance in job cost; the allocation schedule gives it 237,690.00 (difference 250.00)

### missing_artifact__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `gl_positions:-`  
  gl_positions is missing; the controls that read it cannot run and must not be reported as having passed

### missing_basis_value__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 3)

- **FAIL** `alloc_basis_data_complete` @ `project_register:PROJ-2029/projects/PRJ-104/hard_cost_cents`  
  project PRJ-104 is covered by policy GL-2028 on a hard_cost_cents basis but carries 0; it would drop out of the weighting and move every other project's share
- **FAIL** `alloc_basis_data_complete` @ `project_register:PROJ-2029/projects/PRJ-104/hard_cost_cents`  
  project PRJ-104 is covered by policy GL-2029 on a hard_cost_cents basis but carries 0; it would drop out of the weighting and move every other project's share
- **FAIL** `alloc_basis_data_complete` @ `project_register:PROJ-2029/projects/PRJ-104/hard_cost_cents`  
  project PRJ-104 is covered by policy XS-2029 on a hard_cost_cents basis but carries 0; it would drop out of the weighting and move every other project's share

### missing_required_field__Northmoor_Development_Group

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `pol_required_fields` @ `policy_register:POL-2029/policies/GL-2029`  
  policy GL-2029 is missing carrier

### negative_share__Halbrook_Residential

**Verdict:** FAIL (PASS 20, FLAG 2, FAIL 5)

- **FAIL** `alloc_shares_recompute` @ `allocation_schedule:ALLOC-2029/allocations/GL-2029/PRJ-101`  
  policy GL-2029 allocates 156,007.80 to PRJ-101; 234,000.00 weighted by hard_cost_cents derives 89,130.60 (difference 66,877.20)
- **FAIL** `alloc_shares_recompute` @ `allocation_schedule:ALLOC-2029/allocations/GL-2029/PRJ-104`  
  policy GL-2029 allocates -33,438.60 to PRJ-104; 234,000.00 weighted by hard_cost_cents derives 33,438.60 (difference -66,877.20)
- **FAIL** `alloc_no_negative` @ `allocation_schedule:ALLOC-2029/allocations/GL-2029/PRJ-104`  
  policy GL-2029 allocates -33,438.60 to PRJ-104; a negative share nets to the right total and leaves two wrong numbers behind it
- **FAIL** `gl_allocation_ties_job_cost` @ `job_cost_ledger:JOBCOST-2029/postings/PRJ-101`  
  project PRJ-101 carries 237,690.00 of insurance in job cost; the allocation schedule gives it 304,567.20 (difference -66,877.20)
- **FAIL** `gl_allocation_ties_job_cost` @ `job_cost_ledger:JOBCOST-2029/postings/PRJ-104`  
  project PRJ-104 carries 77,166.00 of insurance in job cost; the allocation schedule gives it 10,288.80 (difference 66,877.20)
- **FLAG** `rpt_per_unit_recomputes` @ `allocation_summary:SUMMARY-2029/projects/PRJ-101/per_unit_cents`  
  project PRJ-101 reports 5,942.25 per unit; 304,567.20 across 40 units is 7,614.18
- **FLAG** `rpt_per_unit_recomputes` @ `allocation_summary:SUMMARY-2029/projects/PRJ-104/per_unit_cents`  
  project PRJ-104 reports 4,287.00 per unit; 10,288.80 across 18 units is 571.60

### per_unit_wrong__Stonecrest_Communities

**Verdict:** REVIEW (PASS 23, FLAG 1, FAIL 0)

- **FLAG** `rpt_per_unit_recomputes` @ `allocation_summary:SUMMARY-2029/projects/PRJ-101/per_unit_cents`  
  project PRJ-101 reports 5,952.25 per unit; 237,690.00 across 40 units is 5,942.25

### prepaid_untied__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `gl_prepaid_amortisation_ties` @ `gl_positions:GL-2029/prepaid_insurance_cents`  
  prepaid insurance carries 301,173.95; straight-line amortisation of the policy register to 2029-10-01 gives 300,673.95 (difference 500.00)

### programme_total_untied__Northmoor_Development_Group

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `gl_total_ties_programme` @ `gl_positions:GL-2029/total_insurance_cost_cents`  
  the ledger carries 613,000.00 of programme cost; the policy register sums to 612,000.00 (difference 1,000.00)

### share_misallocated__Halbrook_Residential

**Verdict:** FAIL (PASS 21, FLAG 2, FAIL 4)

- **FAIL** `alloc_shares_recompute` @ `allocation_schedule:ALLOC-2029/allocations/GL-2029/PRJ-101`  
  policy GL-2029 allocates 88,830.60 to PRJ-101; 234,000.00 weighted by hard_cost_cents derives 89,130.60 (difference -300.00)
- **FAIL** `alloc_shares_recompute` @ `allocation_schedule:ALLOC-2029/allocations/GL-2029/PRJ-102`  
  policy GL-2029 allocates 67,153.80 to PRJ-102; 234,000.00 weighted by hard_cost_cents derives 66,853.80 (difference 300.00)
- **FAIL** `gl_allocation_ties_job_cost` @ `job_cost_ledger:JOBCOST-2029/postings/PRJ-101`  
  project PRJ-101 carries 237,690.00 of insurance in job cost; the allocation schedule gives it 237,390.00 (difference 300.00)
- **FAIL** `gl_allocation_ties_job_cost` @ `job_cost_ledger:JOBCOST-2029/postings/PRJ-102`  
  project PRJ-102 carries 178,275.60 of insurance in job cost; the allocation schedule gives it 178,575.60 (difference -300.00)
- **FLAG** `rpt_per_unit_recomputes` @ `allocation_summary:SUMMARY-2029/projects/PRJ-101/per_unit_cents`  
  project PRJ-101 reports 5,942.25 per unit; 237,390.00 across 40 units is 5,934.75
- **FLAG** `rpt_per_unit_recomputes` @ `allocation_summary:SUMMARY-2029/projects/PRJ-102/per_unit_cents`  
  project PRJ-102 reports 5,942.52 per unit; 178,575.60 across 30 units is 5,952.52

### tower_gap__Stonecrest_Communities

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `pol_tower_has_no_gap` @ `policy_register:POL-2029/policies/XS-2029/attachment_point_cents`  
  excess policy XS-2029 attaches at 6,000,000.00 over a primary limit of 5,000,000.00; 1,000,000.00 of the tower is uninsured

### uncovered_project__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `alloc_only_covered_projects` @ `allocation_schedule:ALLOC-2029/allocations/BR-2029/PRJ-104`  
  policy BR-2029 allocates cost to PRJ-104, which is not on its covered schedule; that project is carrying cover it does not have

### undeclared_basis__Northmoor_Development_Group

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `alloc_basis_declared` @ `policy_register:POL-2029/policies/BR-2029/allocation_basis`  
  policy BR-2029 declares allocation basis 'square_feet', which is not one of ('hard_cost_cents', 'insured_value_cents', 'unit_count')

### unknown_project__Halbrook_Residential

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 2)

- **FAIL** `alloc_project_exists` @ `allocation_schedule:ALLOC-2029/allocations/GL-2029/PRJ-777`  
  policy GL-2029 allocates to project 'PRJ-777', which is not in the register
- **FAIL** `alloc_only_covered_projects` @ `allocation_schedule:ALLOC-2029/allocations/GL-2029/PRJ-777`  
  policy GL-2029 allocates cost to PRJ-777, which is not on its covered schedule; that project is carrying cover it does not have
