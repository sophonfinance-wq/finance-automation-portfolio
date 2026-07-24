# Property tax control report

**Overall verdict:** FAIL

- Roll files analyzed: 28
- Controls in registry: 26
- PASS / REVIEW / FAIL: 1 / 5 / 22

All data is fictional. The engine is read-only and never writes to a source
artifact. Every expiry and ageing test is made against the `as_of` date carried
in the file, never the system clock.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `par_parcel_unique` | FAIL | 1 |
| 3 | `par_required_fields` | FAIL | 1 |
| 4 | `par_project_mapped` | FAIL | 1 |
| 5 | `par_plat_completeness` | FAIL | 3 |
| 6 | `par_jurisdiction_known` | FAIL | 1 |
| 7 | `asmt_components_tie_total` | FAIL | 1 |
| 8 | `asmt_charge_follows_value` | FAIL | 1 |
| 9 | `asmt_variance_surfaced` | FLAG | 1 |
| 10 | `asmt_exemption_has_authority` | FLAG | 1 |
| 11 | `inst_shares_tie_annual` | FAIL | 1 |
| 12 | `inst_matches_regime_calendar` | FAIL | 1 |
| 13 | `inst_delinquency_recomputed` | FAIL | 1 |
| 14 | `inst_no_duplicate_payment` | FAIL | 1 |
| 15 | `inst_receipt_on_file` | FLAG | 1 |
| 16 | `own_sale_parcel_exists` | FAIL | 1 |
| 17 | `own_sold_parcel_flagged` | FAIL | 1 |
| 18 | `own_no_payment_after_escrow` | FAIL | 1 |
| 19 | `own_proration_sums_to_annual` | FAIL | 1 |
| 20 | `own_proration_by_days_held` | FAIL | 1 |
| 21 | `own_supplemental_on_transfer` | FLAG | 1 |
| 22 | `acr_periods_tie_annual` | FAIL | 3 |
| 23 | `acr_stops_at_escrow` | FAIL | 1 |
| 24 | `acr_ties_gl_liability` | FAIL | 3 |
| 25 | `acr_capitalisation_matches_stage` | FLAG | 1 |
| 26 | `pay_amount_ties_notice` | FAIL | 1 |

## Roll files

### accrual_after_escrow__Halbrook_Lot_Holdings

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `acr_stops_at_escrow` @ `accrual_ledger:ACCR-2029/accruals/P-2103/2029-08`  
  parcel P-2103 closed 2029-05-15 but still accrues 560.00 in 2029-08; the liability is for a house the developer no longer owns

### accrual_footing__Stonecrest_Land_Group

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `acr_periods_tie_annual` @ `accrual_ledger:ACCR-2029/accruals/P-2101`  
  parcel P-2101 accrues 6,510.00 across the year against an annual charge of 6,600.00 (difference -90.00)

### amount_not_integer__Ardenne_Field_Portfolio

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 4)

- **FAIL** `acr_periods_tie_annual` @ `amount:accrual[P-2102/2029-03].amount_cents`  
  AMOUNT_INVALID: accrual[P-2102/2029-03].amount_cents must be integer cents, got 53166.0 -- amounts are integer cents and are never coerced
- **FAIL** `acr_periods_tie_annual` @ `accrual_ledger:ACCR-2029/accruals/P-2102`  
  parcel P-2102 accrues 5,848.34 across the year against an annual charge of 6,380.00 (difference -531.66)
- **FAIL** `acr_ties_gl_liability` @ `amount:accrual[P-2102/2029-03].amount_cents`  
  AMOUNT_INVALID: accrual[P-2102/2029-03].amount_cents must be integer cents, got 53166.0 -- amounts are integer cents and are never coerced
- **FAIL** `acr_ties_gl_liability` @ `gl_positions:GL-2029/property_tax_accrued_cents`  
  the ledger carries 64,286.10 of accrued property tax; the accrual detail sums to 63,754.44 (difference 531.66)

### assessment_jump__Northmoor_Residential_Portfolio

**Verdict:** REVIEW (PASS 25, FLAG 1, FAIL 0)

- **FLAG** `asmt_variance_surfaced` @ `parcel_register:PARCEL-2029/parcels/P-2101/assessed_total_cents`  
  parcel P-2101 moved up 66.66% from 360,000.00 to 600,000.00; the protest window runs from the assessment, not the bill

### assessment_split_break__Halbrook_Lot_Holdings

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `asmt_components_tie_total` @ `parcel_register:PARCEL-2029/parcels/P-2102/assessed_total_cents`  
  parcel P-2102 assesses land 180,000.00 plus improvements 415,000.00 = 595,000.00, against a stated total of 580,000.00

### charge_off_rate__Stonecrest_Land_Group

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `asmt_charge_follows_value` @ `parcel_register:PARCEL-2029/parcels/P-2101/annual_tax_cents`  
  parcel P-2101 is charged 7,000.00; 1.10% of the 600,000.00 assessed value is 6,600.00 (difference 400.00)

### clean__Northmoor_Residential_Portfolio

**Verdict:** PASS (PASS 26, FLAG 0, FAIL 0)

All controls held.

### delinquency_math__Ardenne_Field_Portfolio

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `inst_delinquency_recomputed` @ `instalment_schedule:INST-2029/instalments/P-2312/1/penalty_cents`  
  parcel P-2312 instalment 1 is 48 day(s) late and carries penalty 404.80 and interest 100.80; the regime derives 604.80 and 100.80

### duplicate_instalment__Northmoor_Residential_Portfolio

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `inst_no_duplicate_payment` @ `instalment_schedule:INST-2029/instalments/P-2101/1`  
  parcel P-2101 carries 2 rows for instalment 1; the same charge is scheduled -- and payable -- more than once

### duplicate_parcel__Halbrook_Lot_Holdings

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 2)

- **FAIL** `par_parcel_unique` @ `parcel_register:PARCEL-2029/parcels/P-2102`  
  parcel P-2102 appears 2 times; it is the join key to the instalments, the closings and the accrual
- **FAIL** `par_plat_completeness` @ `parcel_register:PARCEL-2029/parcels/PRJ-210`  
  project PRJ-210 platted 4 lot(s) but the register carries 5 live parcel(s); the difference is being billed somewhere the register cannot see

### exemption_without_authority__Stonecrest_Land_Group

**Verdict:** REVIEW (PASS 25, FLAG 1, FAIL 0)

- **FLAG** `asmt_exemption_has_authority` @ `parcel_register:PARCEL-2029/parcels/P-2243/exemption_authority`  
  parcel P-2243 claims exemption 'MULTIFAMILY-DEFERRAL' with no authority cited; an exemption nobody can source is one the assessor can withdraw

### gl_break__Ardenne_Field_Portfolio

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `acr_ties_gl_liability` @ `gl_positions:GL-2029/property_tax_accrued_cents`  
  the ledger carries 65,536.10 of accrued property tax; the accrual detail sums to 64,286.10 (difference 1,250.00)

### instalment_split_break__Northmoor_Residential_Portfolio

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `inst_shares_tie_annual` @ `instalment_schedule:INST-2029/instalments/P-2241`  
  parcel P-2241 splits into instalments totalling 10,120.00 against an annual charge of 10,000.00 (difference 120.00)

### missing_artifact__Halbrook_Lot_Holdings

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `assessment_history:-`  
  assessment_history is missing; the controls that read it cannot run and must not be reported as having passed

### missing_receipt__Stonecrest_Land_Group

**Verdict:** REVIEW (PASS 25, FLAG 1, FAIL 0)

- **FLAG** `inst_receipt_on_file` @ `instalment_schedule:INST-2029/instalments/P-2102/2/receipt_reference`  
  parcel P-2102 instalment 2 is marked paid with no receipt; the payment is asserted, not evidenced

### missing_required_field__Ardenne_Field_Portfolio

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `par_required_fields` @ `parcel_register:PARCEL-2029/parcels/P-2311`  
  parcel P-2311 is missing lot_unit

### missing_supplemental__Northmoor_Residential_Portfolio

**Verdict:** REVIEW (PASS 25, FLAG 1, FAIL 0)

- **FLAG** `own_supplemental_on_transfer` @ `sale_register:SALE-2029/closings/P-2242/supplemental_recorded`  
  parcel P-2242 sits in Ardenne, which reassesses on change of ownership, and no supplemental is recorded against the closing

### paid_after_escrow__Halbrook_Lot_Holdings

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `own_no_payment_after_escrow` @ `instalment_schedule:INST-2029/instalments/P-2103/2/paid_amount_cents`  
  parcel P-2103 closed 2029-05-15 but 3,410.00 was paid on 2029-10-28 for an instalment due 2029-10-31; that period belongs to the buyer

### payment_mismatch__Stonecrest_Land_Group

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `pay_amount_ties_notice` @ `instalment_schedule:INST-2029/instalments/P-2311/1/paid_amount_cents`  
  parcel P-2311 instalment 1 paid 9,675.00 against 9,600.00 charged plus 0.00 penalty and 0.00 interest = 9,600.00

### plat_short__Ardenne_Field_Portfolio

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `par_plat_completeness` @ `parcel_register:PARCEL-2029/parcels/PRJ-210`  
  project PRJ-210 platted 5 lot(s) but the register carries 4 live parcel(s); the difference is being billed somewhere the register cannot see

### proration_days_wrong__Northmoor_Residential_Portfolio

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `own_proration_by_days_held` @ `sale_register:SALE-2029/closings/P-2242/seller_share_cents`  
  parcel P-2242 closed 2029-09-30, 91 day(s) into a fiscal year opening 2029-07-01; the seller's share of 9,375.00 derives to 2,337.32, not 6,986.30

### proration_gap__Halbrook_Lot_Holdings

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `own_proration_sums_to_annual` @ `sale_register:SALE-2029/closings/P-2103/seller_share_cents`  
  parcel P-2103 prorates 2,503.78 to the seller and 4,166.22 to the buyer = 6,670.00, against an annual charge of 6,820.00

### sale_unknown_parcel__Stonecrest_Land_Group

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `own_sale_parcel_exists` @ `sale_register:SALE-2029/closings/P-9999`  
  a closing names parcel 'P-9999', which is not on the register; the tax it prorates belongs to nothing

### status_mismatch__Ardenne_Field_Portfolio

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `own_sold_parcel_flagged` @ `parcel_register:PARCEL-2029/parcels/P-2104/status`  
  parcel P-2104 is carried sold with no closing on file; the tax has been handed to a buyer nobody can name

### unknown_jurisdiction__Northmoor_Residential_Portfolio

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `par_jurisdiction_known` @ `parcel_register:PARCEL-2029/parcels/P-2311/jurisdiction`  
  parcel P-2311 sits in 'Northmarch', which has no regime profile; it would skip every calendar control rather than fail one

### unmapped_project__Halbrook_Lot_Holdings

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 2)

- **FAIL** `par_project_mapped` @ `parcel_register:PARCEL-2029/parcels/P-2243/project_code`  
  parcel P-2243 names project 'PRJ-999', which is not in the project register; its tax cannot be costed
- **FAIL** `par_plat_completeness` @ `parcel_register:PARCEL-2029/parcels/PRJ-224`  
  project PRJ-224 platted 3 lot(s) but the register carries 2 live parcel(s); the difference is being billed somewhere the register cannot see

### wrong_capitalisation__Stonecrest_Land_Group

**Verdict:** REVIEW (PASS 25, FLAG 1, FAIL 0)

- **FLAG** `acr_capitalisation_matches_stage` @ `accrual_ledger:ACCR-2029/accruals/P-2241/2029-04/capitalised`  
  parcel P-2241 is capitalised in 2029-04 while its project is 'complete'; tax on a complete project is expensed

### wrong_due_date__Ardenne_Field_Portfolio

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `inst_matches_regime_calendar` @ `instalment_schedule:INST-2029/instalments/P-2241/1/due_date`  
  parcel P-2241 instalment 1 is dated 2029-12-20; Ardenne makes it due 2029-12-10
