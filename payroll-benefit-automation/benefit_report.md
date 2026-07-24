# Payroll & benefit reconciliation control report

**Overall verdict:** FAIL

- Reconciliation files analyzed: 31
- Controls in registry: 29
- PASS / REVIEW / FAIL: 1 / 2 / 28

All data is fictional. The engine is read-only and never writes to a source
artifact. Every date-gate is measured against the `as_of` and pay/remit dates
carried in the file, never the system clock.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `emp_unique_ids` | FAIL | 1 |
| 3 | `emp_entity_valid` | FAIL | 1 |
| 4 | `emp_fields_valid` | FAIL | 1 |
| 5 | `pln_unique_codes` | FAIL | 1 |
| 6 | `pln_type_valid` | FAIL | 1 |
| 7 | `ded_refs_valid` | FAIL | 1 |
| 8 | `ded_unique_pairs` | FAIL | 1 |
| 9 | `ded_matches_provider` | FAIL | 3 |
| 10 | `tie_provider_total` | FAIL | 3 |
| 11 | `tie_je_liability` | FAIL | 3 |
| 12 | `tie_cash_transfer` | FAIL | 3 |
| 13 | `ent_subtotal_recomputes` | FAIL | 9 |
| 14 | `ent_consolidated_ties` | FAIL | 4 |
| 15 | `mat_recomputes` | FAIL | 2 |
| 16 | `mat_comp_cap` | FAIL | 1 |
| 17 | `lim_402g_deferral` | FAIL | 3 |
| 18 | `lim_hsa_tier` | FAIL | 1 |
| 19 | `lim_fsa_cap` | FAIL | 1 |
| 20 | `lim_415c_additions` | FAIL | 2 |
| 21 | `lim_deferral_watch` | FLAG | 2 |
| 22 | `whh_per_period_recomputes` | FAIL | 3 |
| 23 | `whh_not_over_max` | FAIL | 2 |
| 24 | `dol_safe_harbor` | FAIL | 1 |
| 25 | `dol_remit_after_pay` | FAIL | 1 |
| 26 | `je_balances` | FAIL | 1 |
| 27 | `je_clearing_zeroes` | FAIL | 1 |
| 28 | `rpt_tie_status_recomputes` | FAIL | 6 |
| 29 | `rpt_exception_watchlist_ties` | FLAG | 2 |

## Reconciliation files

### amount_not_integer__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 18, FLAG 2, FAIL 9)

- **FAIL** `ded_matches_provider` @ `amount:deduction[EMP-01/P-401K].amount_cents`  
  AMOUNT_INVALID: deduction[EMP-01/P-401K].amount_cents must be integer cents, got 90000.5 -- amounts are integer cents and are never coerced
- **FAIL** `tie_provider_total` @ `amount:deduction[EMP-01/P-401K].amount_cents`  
  AMOUNT_INVALID: deduction[EMP-01/P-401K].amount_cents must be integer cents, got 90000.5 -- amounts are integer cents and are never coerced
- **FAIL** `tie_je_liability` @ `amount:deduction[EMP-01/P-401K].amount_cents`  
  AMOUNT_INVALID: deduction[EMP-01/P-401K].amount_cents must be integer cents, got 90000.5 -- amounts are integer cents and are never coerced
- **FAIL** `tie_cash_transfer` @ `amount:deduction[EMP-01/P-401K].amount_cents`  
  AMOUNT_INVALID: deduction[EMP-01/P-401K].amount_cents must be integer cents, got 90000.5 -- amounts are integer cents and are never coerced
- **FAIL** `ent_subtotal_recomputes` @ `amount:deduction[EMP-01/P-401K].amount_cents`  
  AMOUNT_INVALID: deduction[EMP-01/P-401K].amount_cents must be integer cents, got 90000.5 -- amounts are integer cents and are never coerced
- **FAIL** `ent_consolidated_ties` @ `amount:deduction[EMP-01/P-401K].amount_cents`  
  AMOUNT_INVALID: deduction[EMP-01/P-401K].amount_cents must be integer cents, got 90000.5 -- amounts are integer cents and are never coerced
- **FAIL** `lim_402g_deferral` @ `amount:deduction[EMP-01/P-401K].amount_cents`  
  AMOUNT_INVALID: deduction[EMP-01/P-401K].amount_cents must be integer cents, got 90000.5 -- amounts are integer cents and are never coerced
- **FAIL** `lim_415c_additions` @ `amount:deduction[EMP-01/P-401K].amount_cents`  
  AMOUNT_INVALID: deduction[EMP-01/P-401K].amount_cents must be integer cents, got 90000.5 -- amounts are integer cents and are never coerced
- **FLAG** `lim_deferral_watch` @ `amount:deduction[EMP-01/P-401K].amount_cents`  
  AMOUNT_INVALID: deduction[EMP-01/P-401K].amount_cents must be integer cents, got 90000.5 -- amounts are integer cents and are never coerced
- **FAIL** `rpt_tie_status_recomputes` @ `amount:deduction[EMP-01/P-401K].amount_cents`  
  AMOUNT_INVALID: deduction[EMP-01/P-401K].amount_cents must be integer cents, got 90000.5 -- amounts are integer cents and are never coerced
- **FLAG** `rpt_exception_watchlist_ties` @ `amount:deduction[EMP-01/P-401K].amount_cents`  
  AMOUNT_INVALID: deduction[EMP-01/P-401K].amount_cents must be integer cents, got 90000.5 -- amounts are integer cents and are never coerced

### bad_employee_field__Stonecrest_Communities

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `emp_fields_valid` @ `employee_register:EMPLOYEES-2031/employees/EMP-04/dob`  
  employee EMP-04 has DOB 'not-a-date', which is not a readable date; the age-50/55 catch-up gate cannot be measured

### bad_entity__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 6)

- **FAIL** `emp_entity_valid` @ `employee_register:EMPLOYEES-2031/employees/EMP-03/entity`  
  employee EMP-03 is assigned entity 'ENT-ZZ', not one of ('ENT-NW', 'ENT-SW', 'ENT-TX'); its deductions cannot be partitioned
- **FAIL** `ent_subtotal_recomputes` @ `entity_summary:ENTITY-2031/subtotals/ENT-SW/P-401K/subtotal_cents`  
  entity ENT-SW plan P-401K: subtotal 1,800.00 does not recompute to the register sum 1,200.00
- **FAIL** `ent_subtotal_recomputes` @ `entity_summary:ENTITY-2031/subtotals/ENT-SW/P-MATCH/subtotal_cents`  
  entity ENT-SW plan P-MATCH: subtotal 9,730.75 does not recompute to the register sum 6,730.75
- **FAIL** `ent_subtotal_recomputes` @ `entity_summary:ENTITY-2031/subtotals/ENT-ZZ/P-401K`  
  entity ENT-ZZ plan P-401K: register sums to 600.00 but the entity summary carries no subtotal for it
- **FAIL** `ent_subtotal_recomputes` @ `entity_summary:ENTITY-2031/subtotals/ENT-ZZ/P-FSA-MED`  
  entity ENT-ZZ plan P-FSA-MED: register sums to 100.00 but the entity summary carries no subtotal for it
- **FAIL** `ent_subtotal_recomputes` @ `entity_summary:ENTITY-2031/subtotals/ENT-ZZ/P-MATCH`  
  entity ENT-ZZ plan P-MATCH: register sums to 3,000.00 but the entity summary carries no subtotal for it

### bad_plan_type__Westmere_Holdings

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `pln_type_valid` @ `plan_catalog:PLANS-2031/plans/P-FSA-DEP/plan_type`  
  plan P-FSA-DEP is typed 'cafeteria', which is not one of ('deferral_pretax', 'employer_match', 'hsa', 'fsa_medical', 'fsa_dependent_care'); no control applies to it

### cash_transfer_off__Northmoor_Development_Group

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 2)

- **FAIL** `tie_cash_transfer` @ `remittance_schedule:REMIT-2031/remittances/P-FSA-DEP/cash_transfer_cents`  
  plan P-FSA-DEP: register total 300.00 but cash transfer 290.00 (off -10.00)
- **FAIL** `rpt_tie_status_recomputes` @ `reconciliation_report:RECON-2031/plans/P-FSA-DEP/tied`  
  plan P-FSA-DEP is reported tied=True; recomputing from its register, provider, ledger and cash legs gives tied=False

### clean__Northmoor_Development_Group

**Verdict:** PASS (PASS 29, FLAG 0, FAIL 0)

All controls held.

### clearing_not_zero__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `je_clearing_zeroes` @ `journal_entry:JE-2031/lines/2130-HSA`  
  clearing account 2130-HSA nets to -1.00 after remittance; the benefit payable did not zero out

### consolidated_off__Stonecrest_Communities

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 2)

- **FAIL** `ent_consolidated_ties` @ `entity_summary:ENTITY-2031/consolidated/P-FSA-MED/total_cents`  
  plan P-FSA-MED: consolidated total 225.00 does not tie the register total 220.00
- **FAIL** `ent_consolidated_ties` @ `entity_summary:ENTITY-2031/consolidated/P-FSA-MED/total_cents`  
  plan P-FSA-MED: entity subtotals sum to 220.00 but the consolidated total is 225.00

### deferral_watch__Ardenne_Field_Partners

**Verdict:** REVIEW (PASS 28, FLAG 1, FAIL 0)

- **FLAG** `lim_deferral_watch` @ `employee_register:EMPLOYEES-2031/employees/EMP-04/prior_ytd/P-401K`  
  employee EMP-04 P-401K: year-to-date deferral 29,400.00 is within 1,600.00 of the 402(g) limit 31,000.00; trim before it breaches

### duplicate_deduction_pair__Westmere_Holdings

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 7)

- **FAIL** `ded_unique_pairs` @ `deduction_register:DEDUCTIONS-2031/deductions/EMP-03/P-FSA-MED`  
  employee EMP-03 has 2 deduction rows for plan P-FSA-MED; the pair must be a single figure
- **FAIL** `tie_provider_total` @ `provider_file:UPLOADS-2031/uploads/Marran Flex Administrators/P-FSA-MED`  
  plan P-FSA-MED: register total 320.00 but Marran Flex Administrators upload total 220.00 (off -100.00)
- **FAIL** `tie_je_liability` @ `journal_entry:JE-2031/lines/P-FSA-MED/credit_cents`  
  plan P-FSA-MED: register total 320.00 but journal-entry liability credit 220.00 (off -100.00)
- **FAIL** `tie_cash_transfer` @ `remittance_schedule:REMIT-2031/remittances/P-FSA-MED/cash_transfer_cents`  
  plan P-FSA-MED: register total 320.00 but cash transfer 220.00 (off -100.00)
- **FAIL** `ent_subtotal_recomputes` @ `entity_summary:ENTITY-2031/subtotals/ENT-SW/P-FSA-MED/subtotal_cents`  
  entity ENT-SW plan P-FSA-MED: subtotal 100.00 does not recompute to the register sum 200.00
- **FAIL** `ent_consolidated_ties` @ `entity_summary:ENTITY-2031/consolidated/P-FSA-MED/total_cents`  
  plan P-FSA-MED: consolidated total 220.00 does not tie the register total 320.00
- **FAIL** `rpt_tie_status_recomputes` @ `reconciliation_report:RECON-2031/plans/P-FSA-MED/tied`  
  plan P-FSA-MED is reported tied=True; recomputing from its register, provider, ledger and cash legs gives tied=False

### duplicate_employee_id__Northmoor_Development_Group

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `emp_unique_ids` @ `employee_register:EMPLOYEES-2031/employees/EMP-01`  
  employee id EMP-01 appears 2 times; a deduction that names it cannot be attributed to one employee

### duplicate_plan_code__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `pln_unique_codes` @ `plan_catalog:PLANS-2031/plans/P-HSA`  
  plan code P-HSA appears 2 times; a deduction that names it cannot be attributed to one plan

### entity_subtotal_off__Stonecrest_Communities

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 2)

- **FAIL** `ent_subtotal_recomputes` @ `entity_summary:ENTITY-2031/subtotals/ENT-NW/P-HSA/subtotal_cents`  
  entity ENT-NW plan P-HSA: subtotal 1,229.99 does not recompute to the register sum 1,228.57
- **FAIL** `ent_subtotal_recomputes` @ `entity_summary:ENTITY-2031/subtotals/ENT-SW/P-HSA/subtotal_cents`  
  entity ENT-SW plan P-HSA: subtotal 570.00 does not recompute to the register sum 571.42

### hsa_over_max__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 2)

- **FAIL** `whh_per_period_recomputes` @ `deduction_register:DEDUCTIONS-2031/deductions/EMP-01/P-HSA/amount_cents`  
  employee EMP-01 P-HSA: per-period HSA 500.00 does not recompute to 400.00 = room 2,800.00 over 7 periods
- **FAIL** `whh_not_over_max` @ `deduction_register:DEDUCTIONS-2031/deductions/EMP-01/P-HSA/amount_cents`  
  employee EMP-01 P-HSA: per-period HSA 500.00 exceeds the pro-rated ceiling 400.00 (over 100.00)

### hsa_per_period_off__Westmere_Holdings

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `whh_per_period_recomputes` @ `deduction_register:DEDUCTIONS-2031/deductions/EMP-05/P-HSA/amount_cents`  
  employee EMP-05 P-HSA: per-period HSA 1,001.43 does not recompute to 1,001.42 = room 7,010.00 over 7 periods

### je_liability_off__Northmoor_Development_Group

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 2)

- **FAIL** `tie_je_liability` @ `journal_entry:JE-2031/lines/P-HSA/credit_cents`  
  plan P-HSA: register total 2,801.41 but journal-entry liability credit 0.00 (off -2,801.41)
- **FAIL** `rpt_tie_status_recomputes` @ `reconciliation_report:RECON-2031/plans/P-HSA/tied`  
  plan P-HSA is reported tied=True; recomputing from its register, provider, ledger and cash legs gives tied=False

### je_unbalanced__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `je_balances` @ `journal_entry:JE-2031/lines`  
  journal entry does not balance: debits 54,905.32 vs credits 54,904.32 (off 1.00)

### late_deposit__Stonecrest_Communities

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `dol_safe_harbor` @ `remittance_schedule:REMIT-2031/remittances/P-401K/remit_date`  
  plan P-401K: participant money paid 2031-08-29 was not deposited until 2031-09-15, 11 business days out, past the 7-day safe harbor

### match_miscomputed__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `mat_recomputes` @ `deduction_register:DEDUCTIONS-2031/deductions/EMP-01/P-MATCH/amount_cents`  
  employee EMP-01: booked match 3,900.00 but the formula on 8,000.00 eligible comp recomputes 4,000.00 (off -100.00)

### match_over_cap__Westmere_Holdings

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 2)

- **FAIL** `mat_recomputes` @ `deduction_register:DEDUCTIONS-2031/deductions/EMP-04/P-MATCH/amount_cents`  
  employee EMP-04: booked match 7,500.00 but the formula on 15,000.00 eligible comp recomputes 6,730.75 (off 769.25)
- **FAIL** `mat_comp_cap` @ `deduction_register:DEDUCTIONS-2031/deductions/EMP-04/P-MATCH/amount_cents`  
  employee EMP-04 earns 15,000.00, above the 13,461.50 comp cap; the booked match 7,500.00 exceeds the capped ceiling 6,730.75

### missing_artifact__Northmoor_Development_Group

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `reconciliation_report:-`  
  reconciliation_report is missing; the controls that read it cannot run and must not be reported as having passed

### over_402g__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `lim_402g_deferral` @ `employee_register:EMPLOYEES-2031/employees/EMP-03/prior_ytd/P-401K`  
  employee EMP-03 P-401K: year-to-date deferral 24,600.00 exceeds the 402(g) limit 23,500.00 (over 1,100.00)

### over_415c__Stonecrest_Communities

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 2)

- **FAIL** `lim_402g_deferral` @ `employee_register:EMPLOYEES-2031/employees/EMP-02/prior_ytd/P-401K`  
  employee EMP-02 P-401K: year-to-date deferral 66,000.00 exceeds the 402(g) limit 31,000.00 (over 35,000.00)
- **FAIL** `lim_415c_additions` @ `employee_register:EMPLOYEES-2031/employees/EMP-02/annual_additions`  
  employee EMP-02: annual additions 72,000.00 exceed the 415(c) limit 70,000.00 (over 2,000.00)

### over_fsa__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `lim_fsa_cap` @ `employee_register:EMPLOYEES-2031/employees/EMP-01/prior_ytd/P-FSA-MED`  
  employee EMP-01 P-FSA-MED: year-to-date FSA 3,370.00 exceeds the cap 3,300.00 (over 70.00)

### over_hsa__Westmere_Holdings

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 3)

- **FAIL** `lim_hsa_tier` @ `employee_register:EMPLOYEES-2031/employees/EMP-05/prior_ytd/P-HSA`  
  employee EMP-05 (family): year-to-date HSA 9,001.42 exceeds the tier limit 8,550.00 (over 451.42)
- **FAIL** `whh_per_period_recomputes` @ `deduction_register:DEDUCTIONS-2031/deductions/EMP-05/P-HSA/amount_cents`  
  employee EMP-05 P-HSA: per-period HSA 1,001.42 does not recompute to 44.28 = room 310.00 over 7 periods
- **FAIL** `whh_not_over_max` @ `deduction_register:DEDUCTIONS-2031/deductions/EMP-05/P-HSA/amount_cents`  
  employee EMP-05 P-HSA: per-period HSA 1,001.42 exceeds the pro-rated ceiling 44.32 (over 957.10)

### provider_per_employee_mismatch__Northmoor_Development_Group

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 2)

- **FAIL** `ded_matches_provider` @ `provider_file:UPLOADS-2031/uploads/Kelder Health Savings/P-HSA/EMP-01/amount_cents`  
  employee EMP-01 P-HSA: register deducted 400.00 but Kelder Health Savings received 1,001.42 (off 601.42)
- **FAIL** `ded_matches_provider` @ `provider_file:UPLOADS-2031/uploads/Kelder Health Savings/P-HSA/EMP-05/amount_cents`  
  employee EMP-05 P-HSA: register deducted 1,001.42 but Kelder Health Savings received 400.00 (off -601.42)

### provider_total_off__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 2)

- **FAIL** `tie_provider_total` @ `provider_file:UPLOADS-2031/uploads/Harborline Trust/P-401K`  
  plan P-401K: register total 4,400.00 but Harborline Trust upload total 4,410.00 (off 10.00)
- **FAIL** `rpt_tie_status_recomputes` @ `reconciliation_report:RECON-2031/plans/P-401K/tied`  
  plan P-401K is reported tied=True; recomputing from its register, provider, ledger and cash legs gives tied=False

### remit_before_pay__Stonecrest_Communities

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `dol_remit_after_pay` @ `remittance_schedule:REMIT-2031/remittances/P-HSA/remit_date`  
  plan P-HSA: remit date 2031-08-25 precedes the pay date 2031-08-29; the deposit cannot have settled before the payroll

### tie_flag_wrong__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `rpt_tie_status_recomputes` @ `reconciliation_report:RECON-2031/plans/P-HSA/tied`  
  plan P-HSA is reported tied=False; recomputing from its register, provider, ledger and cash legs gives tied=True

### unknown_reference__Westmere_Holdings

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `ded_refs_valid` @ `deduction_register:DEDUCTIONS-2031/deductions/EMP-01/P-UNKNOWN/plan_code`  
  deduction names plan 'P-UNKNOWN', which is not in the plan catalog

### watchlist_overstated__Northmoor_Development_Group

**Verdict:** REVIEW (PASS 28, FLAG 1, FAIL 0)

- **FLAG** `rpt_exception_watchlist_ties` @ `reconciliation_report:RECON-2031/exceptions/EMP-01/P-401K`  
  the watchlist lists deferral_over for employee EMP-01 plan P-401K, but the contributions do not support it
