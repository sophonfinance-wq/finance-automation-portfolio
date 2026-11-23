# Lien waiver coverage control report

**Overall verdict:** FAIL

- Portfolio files analyzed: 27
- Controls in registry: 25
- PASS / REVIEW / FAIL: 1 / 2 / 24

All data is fictional. The engine is read-only and never writes to a source
artifact. Every coverage and ageing test is made against the `as_of` date
carried in the file, never the system clock.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `party_required_fields` | FAIL | 1 |
| 3 | `party_unique_ids` | FAIL | 1 |
| 4 | `party_tier_valid` | FAIL | 1 |
| 5 | `party_lower_tier_parent` | FAIL | 1 |
| 6 | `party_project_exists` | FAIL | 1 |
| 7 | `pay_required_fields` | FAIL | 1 |
| 8 | `pay_sub_exists` | FAIL | 1 |
| 9 | `pay_amount_positive` | FAIL | 2 |
| 10 | `pay_dates_sensible` | FAIL | 1 |
| 11 | `wvr_required_fields` | FAIL | 1 |
| 12 | `wvr_unique_ids` | FAIL | 1 |
| 13 | `wvr_type_valid` | FAIL | 1 |
| 14 | `wvr_references_payment` | FAIL | 1 |
| 15 | `wvr_amount_ties_payment` | FAIL | 5 |
| 16 | `cov_payment_covered` | FAIL | 1 |
| 17 | `cov_cleared_unconditional` | FAIL | 1 |
| 18 | `cov_stale_conditional` | FLAG | 1 |
| 19 | `tier_party_has_waiver` | FAIL | 1 |
| 20 | `tier_waiver_covers` | FAIL | 1 |
| 21 | `tier_required_recomputes` | FAIL | 1 |
| 22 | `exp_recomputes` | FAIL | 1 |
| 23 | `exp_all_projects_present` | FAIL | 1 |
| 24 | `rpt_waiver_counts_tie` | FAIL | 1 |
| 25 | `rpt_covered_count_ties` | FLAG | 1 |

## Portfolio files

### amount_not_integer__Halbrook_Residential

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 3)

- **FAIL** `pay_amount_positive` @ `amount:payment[PAY-3].amount_cents`  
  AMOUNT_INVALID: payment[PAY-3].amount_cents must be integer cents, got 8000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `wvr_amount_ties_payment` @ `amount:payment[PAY-3].amount_cents`  
  AMOUNT_INVALID: payment[PAY-3].amount_cents must be integer cents, got 8000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `wvr_amount_ties_payment` @ `amount:payment[PAY-3].amount_cents`  
  AMOUNT_INVALID: payment[PAY-3].amount_cents must be integer cents, got 8000000.5 -- amounts are integer cents and are never coerced

### clean__Northmoor_Development_Group

**Verdict:** PASS (PASS 25, FLAG 0, FAIL 0)

All controls held.

### cov_cleared_conditional_only__Stonecrest_Communities

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `cov_cleared_unconditional` @ `payment_register:PAYMENT-2031/payments/PAY-1/cleared`  
  payment PAY-1 cleared and is paid through 2031-01-31, but no unconditional waiver releases through that date; a conditional release does not survive the cheque clearing

### cov_conditional_stale__Ardenne_Field_Partners

**Verdict:** REVIEW (PASS 24, FLAG 1, FAIL 0)

- **FLAG** `cov_stale_conditional` @ `payment_register:PAYMENT-2031/payments/PAY-6/paid_through_date`  
  payment PAY-6 is paid through 2030-11-01 and still uncleared 134 days later (band 60); its conditional waiver should have been upgraded by now

### cov_payment_uncovered__Northmoor_Development_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `cov_payment_covered` @ `payment_register:PAYMENT-2031/payments/PAY-2/paid_through_date`  
  payment PAY-2 is paid through 2031-02-28 but no waiver releases at least that far; the lien right is still live

### exp_missing_project__Halbrook_Residential

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `exp_all_projects_present` @ `exposure_summary:EXPOSURE-2031/projects/Copperfield Yards`  
  project Copperfield Yards carries payments but is absent from the exposure summary; its unwaived exposure is reported as nothing

### exp_wrong_figure__Stonecrest_Communities

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `exp_recomputes` @ `exposure_summary:EXPOSURE-2031/projects/Brightwater Commons/unwaived_exposure_cents`  
  project Brightwater Commons reports 95,500.00 of unwaived exposure; payments not yet released unconditionally sum to 95,000.00 (difference 500.00)

### missing_artifact__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `waiver_log:-`  
  waiver_log is missing; the controls that read it cannot run and must not be reported as having passed

### party_bad_project__Northmoor_Development_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `party_project_exists` @ `contract_register:CONTRACT-2031/subcontracts/SUB-200/project`  
  subcontract SUB-200 names project 'Elsewhere Point', which is not one of ('Brightwater Commons', 'Copperfield Yards', 'Alderpoint Terraces', 'Dunmore Flats')

### party_bad_tier__Halbrook_Residential

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `party_tier_valid` @ `contract_register:CONTRACT-2031/subcontracts/SUB-200/tier`  
  subcontract SUB-200 has tier 0; a tier is a whole number 1 or greater

### party_duplicate_id__Stonecrest_Communities

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `party_unique_ids` @ `contract_register:CONTRACT-2031/subcontracts/SUB-100`  
  sub id SUB-100 appears 2 times; the joins to payments and waivers become ambiguous

### party_missing_field__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `party_required_fields` @ `contract_register:CONTRACT-2031/subcontracts/SUB-200`  
  subcontract SUB-200 is missing name

### party_orphan_lower_tier__Northmoor_Development_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `party_lower_tier_parent` @ `contract_register:CONTRACT-2031/subcontracts/SUB-110/parent_sub`  
  subcontract SUB-110 is tier 2 but names parent 'SUB-909', which is not in the register; its release cannot be tied to a payment

### pay_bad_paid_through__Halbrook_Residential

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `pay_dates_sensible` @ `payment_register:PAYMENT-2031/payments/PAY-3/paid_through_date`  
  payment PAY-3 has paid-through date '2031-02-30', which is not a readable date

### pay_missing_field__Stonecrest_Communities

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `pay_required_fields` @ `payment_register:PAYMENT-2031/payments/PAY-3`  
  payment PAY-3 is missing period

### pay_negative_amount__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 3)

- **FAIL** `pay_amount_positive` @ `payment_register:PAYMENT-2031/payments/PAY-1/amount_cents`  
  payment PAY-1 is -120,000.00; a progress payment must be a positive amount
- **FAIL** `wvr_amount_ties_payment` @ `waiver_register:WAIVER-2031/waivers/WV-C-PAY-1/amount_cents`  
  waiver WV-C-PAY-1 releases 120,000.00 against a payment of -120,000.00 (difference 240,000.00)
- **FAIL** `wvr_amount_ties_payment` @ `waiver_register:WAIVER-2031/waivers/WV-U-PAY-1/amount_cents`  
  waiver WV-U-PAY-1 releases 120,000.00 against a payment of -120,000.00 (difference 240,000.00)

### pay_unknown_sub__Northmoor_Development_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `pay_sub_exists` @ `payment_register:PAYMENT-2031/payments/PAY-4/sub_id`  
  payment PAY-4 pays sub 'SUB-909', which is not in the contract register

### rpt_wrong_count__Halbrook_Residential

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `rpt_waiver_counts_tie` @ `waiver_log:WAIVERLOG-2031/waiver_count`  
  waiver_count in the waiver log is 10; the register holds 9

### rpt_wrong_covered__Stonecrest_Communities

**Verdict:** REVIEW (PASS 24, FLAG 1, FAIL 0)

- **FLAG** `rpt_covered_count_ties` @ `waiver_log:WAIVERLOG-2031/covered_payment_count`  
  covered_payment_count in the waiver log is 4; 3 payments carry an unconditional release

### tier_no_waiver__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `tier_party_has_waiver` @ `lower_tier_register:LOWERTIER-2031/parties/LTP-1/waiver_through_date`  
  lower-tier party LTP-1 has no readable waiver-through date; it has not released, and its lien survives the payment it was funded from

### tier_short_waiver__Northmoor_Development_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `tier_waiver_covers` @ `lower_tier_register:LOWERTIER-2031/parties/LTP-1/waiver_through_date`  
  lower-tier party LTP-1 releases through 2031-01-15 but its parent was paid through 2031-02-28; the gap is unwaived downstream work

### tier_wrong_required__Halbrook_Residential

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `tier_required_recomputes` @ `lower_tier_register:LOWERTIER-2031/parties/LTP-1/required_through_date`  
  lower-tier party LTP-1 records a required-through date of 2031-01-10; its parent SUB-100 was last paid through 2031-02-28

### wvr_amount_mismatch__Stonecrest_Communities

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `wvr_amount_ties_payment` @ `waiver_register:WAIVER-2031/waivers/WV-U-PAY-4/amount_cents`  
  waiver WV-U-PAY-4 releases 61,000.00 against a payment of 60,000.00 (difference 1,000.00)

### wvr_bad_reference__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `wvr_references_payment` @ `waiver_register:WAIVER-2031/waivers/WV-C-PAY-1/payment_id`  
  waiver WV-C-PAY-1 references payment 'PAY-909', which is not in the payment register

### wvr_bad_type__Northmoor_Development_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `wvr_type_valid` @ `waiver_register:WAIVER-2031/waivers/WV-C-PAY-1/waiver_type`  
  waiver WV-C-PAY-1 is type 'partial', which is not one of ('conditional', 'unconditional')

### wvr_duplicate_id__Halbrook_Residential

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `wvr_unique_ids` @ `waiver_register:WAIVER-2031/waivers/WV-C-PAY-1`  
  waiver id WV-C-PAY-1 appears 2 times; a waiver must be uniquely identifiable to be tracked

### wvr_missing_field__Stonecrest_Communities

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `wvr_required_fields` @ `waiver_register:WAIVER-2031/waivers/WV-C-PAY-1`  
  waiver WV-C-PAY-1 is missing through_date
