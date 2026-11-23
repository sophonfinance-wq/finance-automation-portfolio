# Energy-Efficient Home Credit (§45L) control report

**Overall verdict:** FAIL

- Credit files analyzed: 28
- Controls in registry: 26
- PASS / REVIEW / FAIL: 1 / 2 / 25

All data is fictional. The engine is read-only and never writes to a source
artifact. Every close-of-escrow and sunset test is made against the period and
sunset dates carried in the file, never the system clock.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `unit_unique_ids` | FAIL | 1 |
| 3 | `unit_required_fields` | FAIL | 1 |
| 4 | `unit_project_known` | FAIL | 1 |
| 5 | `elig_close_in_period` | FAIL | 1 |
| 6 | `elig_within_sunset` | FAIL | 1 |
| 7 | `cert_present_for_credited` | FAIL | 1 |
| 8 | `cert_rater_id` | FAIL | 1 |
| 9 | `dup_no_double_count` | FAIL | 1 |
| 10 | `rate_per_unit` | FAIL | 1 |
| 11 | `rate_gross_credit` | FAIL | 2 |
| 12 | `rpt_units_times_rate` | FAIL | 1 |
| 13 | `roll_project_units` | FAIL | 3 |
| 14 | `roll_grand_total` | FAIL | 4 |
| 15 | `roll_region_subtotal` | FAIL | 3 |
| 16 | `fwd_total_identity` | FAIL | 1 |
| 17 | `fwd_period_bounds` | FAIL | 1 |
| 18 | `fwd_remaining_to_close` | FLAG | 1 |
| 19 | `net_addback` | FAIL | 3 |
| 20 | `net_tax_effect` | FAIL | 3 |
| 21 | `net_benefit` | FAIL | 4 |
| 22 | `alloc_shares_sum` | FAIL | 1 |
| 23 | `alloc_share_rederived` | FAIL | 3 |
| 24 | `recon_final_report_ties` | FAIL | 1 |
| 25 | `recon_closed_ge_credited` | FAIL | 1 |
| 26 | `recon_certification_gap` | FLAG | 1 |

## Credit files

### addback_wrong__Halbrook_Residential

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `net_addback` @ `credit_worksheet:WORKSHEET-2029/projects/PRJ-ALDR/addback_cents`  
  project PRJ-ALDR states a profit addback of 8,500.00; the gross credit added back is 8,000.00

### amount_not_integer__Stonecrest_Communities

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 6)

- **FAIL** `rate_gross_credit` @ `amount:project[PRJ-BRWT].gross_credit_cents`  
  AMOUNT_INVALID: project[PRJ-BRWT].gross_credit_cents must be integer cents, got 600000.5 -- amounts are integer cents and are never coerced
- **FAIL** `roll_grand_total` @ `amount:project[PRJ-BRWT].gross_credit_cents`  
  AMOUNT_INVALID: project[PRJ-BRWT].gross_credit_cents must be integer cents, got 600000.5 -- amounts are integer cents and are never coerced
- **FAIL** `roll_region_subtotal` @ `amount:project[PRJ-BRWT].gross_credit_cents`  
  AMOUNT_INVALID: project[PRJ-BRWT].gross_credit_cents must be integer cents, got 600000.5 -- amounts are integer cents and are never coerced
- **FAIL** `net_addback` @ `amount:project[PRJ-BRWT].gross_credit_cents`  
  AMOUNT_INVALID: project[PRJ-BRWT].gross_credit_cents must be integer cents, got 600000.5 -- amounts are integer cents and are never coerced
- **FAIL** `net_tax_effect` @ `amount:project[PRJ-BRWT].gross_credit_cents`  
  AMOUNT_INVALID: project[PRJ-BRWT].gross_credit_cents must be integer cents, got 600000.5 -- amounts are integer cents and are never coerced
- **FAIL** `net_benefit` @ `amount:project[PRJ-BRWT].gross_credit_cents`  
  AMOUNT_INVALID: project[PRJ-BRWT].gross_credit_cents must be integer cents, got 600000.5 -- amounts are integer cents and are never coerced

### certification_gap__Ardenne_Field_Partners

**Verdict:** REVIEW (PASS 25, FLAG 1, FAIL 0)

- **FLAG** `recon_certification_gap` @ `closings_schedule:CLOSINGS-2029/projects/PRJ-ALDR/closed_units`  
  project PRJ-ALDR closed 7 units but credited only 4; 3 closed unit(s) may be uncertified and worth chasing

### clean__Northmoor_Development_Group

**Verdict:** PASS (PASS 26, FLAG 0, FAIL 0)

All controls held.

### close_after_sunset__Westmere_Homebuilders

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `elig_within_sunset` @ `unit_register:UNITS-2029/units/UNIT-A04/coe_date`  
  claimed unit UNIT-A04 closed 2029-05-01, after the statutory sunset 2029-03-31; the credit had lapsed

### close_out_of_period__Northmoor_Development_Group

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `elig_close_in_period` @ `unit_register:UNITS-2029/units/UNIT-A03/coe_date`  
  claimed unit UNIT-A03 closed 2027-05-01, outside the fiscal-year window 2028-07-01..2029-06-30; it cannot be claimed here

### closed_lt_credited__Halbrook_Residential

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `recon_closed_ge_credited` @ `closings_schedule:CLOSINGS-2029/projects/PRJ-CPFD/closed_units`  
  project PRJ-CPFD credits 3 units but only 2 closed; a credited unit did not close

### double_count__Stonecrest_Communities

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `dup_no_double_count` @ `unit_register:UNITS-2029/units/UNIT-A01`  
  claimed unit UNIT-A01 was already claimed in a prior period filing; the §45L credit is taken once per dwelling

### duplicate_unit_id__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 2)

- **FAIL** `unit_unique_ids` @ `unit_register:UNITS-2029/units/UNIT-A01`  
  unit id UNIT-A01 appears 2 times; a credit that names it cannot be attributed to one dwelling
- **FAIL** `roll_project_units` @ `credit_worksheet:WORKSHEET-2029/projects/PRJ-ALDR/qualifying_units`  
  project PRJ-ALDR states 4 qualifying units; the register holds 5 claimed units for it

### final_report_units_wrong__Westmere_Homebuilders

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `recon_final_report_ties` @ `final_report:REPORT-2029/total_certified_units`  
  credited-unit counts disagree across artifacts: final report 11, worksheet 10, closings schedule 10

### grand_total_wrong__Northmoor_Development_Group

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `roll_grand_total` @ `credit_worksheet:WORKSHEET-2029/total_gross_credit_cents`  
  the worksheet totals gross credit 22,000.00; the project lines sum to 20,000.00

### gross_wrong__Halbrook_Residential

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 6)

- **FAIL** `rate_gross_credit` @ `credit_worksheet:WORKSHEET-2029/projects/PRJ-ALDR/gross_credit_cents`  
  project PRJ-ALDR states gross credit 10,000.00; 4 units x 2,000.00 re-derives 8,000.00
- **FAIL** `roll_grand_total` @ `credit_worksheet:WORKSHEET-2029/total_gross_credit_cents`  
  the worksheet totals gross credit 20,000.00; the project lines sum to 22,000.00
- **FAIL** `roll_region_subtotal` @ `credit_worksheet:WORKSHEET-2029/region_subtotals/Region of Marran/gross_credit_cents`  
  region 'Region of Marran' subtotal states 14,000.00; its projects sum to 16,000.00
- **FAIL** `net_addback` @ `credit_worksheet:WORKSHEET-2029/projects/PRJ-ALDR/addback_cents`  
  project PRJ-ALDR states a profit addback of 8,000.00; the gross credit added back is 10,000.00
- **FAIL** `net_tax_effect` @ `credit_worksheet:WORKSHEET-2029/projects/PRJ-ALDR/tax_effect_cents`  
  project PRJ-ALDR states a tax effect of -1,680.00; -(10,000.00 x 2100 bps) re-derives -2,100.00
- **FAIL** `net_benefit` @ `credit_worksheet:WORKSHEET-2029/projects/PRJ-ALDR/net_benefit_cents`  
  project PRJ-ALDR states a net benefit of 6,320.00; 10,000.00 + -1,680.00 re-derives 8,320.00

### missing_artifact__Stonecrest_Communities

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `final_report:-`  
  final_report is missing; the controls that read it cannot run and must not be reported as having passed

### missing_rater_id__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `cert_rater_id` @ `unit_register:UNITS-2029/units/UNIT-C01/rater_id`  
  unit UNIT-C01 carries a certificate with no rater id; the energy determination is unsigned

### net_benefit_wrong__Westmere_Homebuilders

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 2)

- **FAIL** `roll_grand_total` @ `credit_worksheet:WORKSHEET-2029/total_net_benefit_cents`  
  the worksheet totals net benefit 15,800.00; the project lines sum to 16,300.00
- **FAIL** `net_benefit` @ `credit_worksheet:WORKSHEET-2029/projects/PRJ-BRWT/net_benefit_cents`  
  project PRJ-BRWT states a net benefit of 5,240.00; 6,000.00 + -1,260.00 re-derives 4,740.00

### per_unit_wrong__Northmoor_Development_Group

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `rate_per_unit` @ `unit_register:UNITS-2029/units/UNIT-A02/credited_amount_cents`  
  unit UNIT-A02 is credited 1,500.00; the statutory amount for a claimed unit is 2,000.00

### period_overlap__Halbrook_Residential

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `fwd_period_bounds` @ `period_rollforward:ROLLFORWARD-2029/period_windows`  
  period windows overlap: one ends 2027-06-30 and the next starts 2027-01-01; a closing could fall in both

### project_units_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `roll_project_units` @ `credit_worksheet:WORKSHEET-2029/projects/PRJ-ALDR/qualifying_units`  
  project PRJ-ALDR states 4 qualifying units; the register holds 5 claimed units for it

### region_subtotal_wrong__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `roll_region_subtotal` @ `credit_worksheet:WORKSHEET-2029/region_subtotals/Region of Marran/gross_credit_cents`  
  region 'Region of Marran' subtotal states 15,000.00; its projects sum to 14,000.00

### remaining_open__Westmere_Homebuilders

**Verdict:** REVIEW (PASS 25, FLAG 1, FAIL 0)

- **FLAG** `fwd_remaining_to_close` @ `period_rollforward:ROLLFORWARD-2029/projects/PRJ-BRWT/remaining_units`  
  project PRJ-BRWT has 4 unit(s) still to close in a future period; the credit for them is not yet earned

### share_rederive_wrong__Northmoor_Development_Group

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 2)

- **FAIL** `alloc_share_rederived` @ `partner_allocation:ALLOCATION-2029/partners/PROG/allocated_cents`  
  partner PROG is allocated 6,952.00; its 5600 bps of 15,800.00 re-derives 8,848.00
- **FAIL** `alloc_share_rederived` @ `partner_allocation:ALLOCATION-2029/partners/NMSP/allocated_cents`  
  partner NMSP is allocated 8,848.00; its 4400 bps of 15,800.00 re-derives 6,952.00

### shares_sum_wrong__Halbrook_Residential

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 2)

- **FAIL** `alloc_shares_sum` @ `partner_allocation:ALLOCATION-2029/partners`  
  the partner shares sum to 15,900.00; the net benefit to allocate is 15,800.00
- **FAIL** `alloc_share_rederived` @ `partner_allocation:ALLOCATION-2029/partners/PROG/allocated_cents`  
  partner PROG is allocated 8,948.00; its 5600 bps of 15,800.00 re-derives 8,848.00

### tax_effect_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 2)

- **FAIL** `net_tax_effect` @ `credit_worksheet:WORKSHEET-2029/projects/PRJ-ALDR/tax_effect_cents`  
  project PRJ-ALDR states a tax effect of -1,180.00; -(8,000.00 x 2100 bps) re-derives -1,680.00
- **FAIL** `net_benefit` @ `credit_worksheet:WORKSHEET-2029/projects/PRJ-ALDR/net_benefit_cents`  
  project PRJ-ALDR states a net benefit of 6,320.00; 8,000.00 + -1,180.00 re-derives 6,820.00

### total_identity_wrong__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `fwd_total_identity` @ `period_rollforward:ROLLFORWARD-2029/projects/PRJ-CPFD/total_units`  
  project PRJ-CPFD states 9 total units; 7 closed across the periods plus 0 remaining re-derives 7

### uncertified_claim__Westmere_Homebuilders

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `cert_present_for_credited` @ `unit_register:UNITS-2029/units/UNIT-B02/certificate_ref`  
  claimed unit UNIT-B02 has no RESNET/HERS certificate on file; an uncertified closing cannot be claimed

### unit_missing_field__Northmoor_Development_Group

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `unit_required_fields` @ `unit_register:UNITS-2029/units/UNIT-A02`  
  unit UNIT-A02 is missing address

### unit_unknown_project__Halbrook_Residential

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 2)

- **FAIL** `unit_project_known` @ `unit_register:UNITS-2029/units/UNIT-B01/project_id`  
  unit UNIT-B01 names project 'PRJ-ZZZ', which the credit worksheet does not carry
- **FAIL** `roll_project_units` @ `credit_worksheet:WORKSHEET-2029/projects/PRJ-BRWT/qualifying_units`  
  project PRJ-BRWT states 3 qualifying units; the register holds 2 claimed units for it

### units_times_rate_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `rpt_units_times_rate` @ `final_report:REPORT-2029/total_credits_cents`  
  the report states 10 certified units and total credit 20,000.01; 10 x 2,000.00 re-derives 20,000.00
