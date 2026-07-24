# Non-resident withholding & 1042-S control report

**Overall verdict:** FAIL

- Withholding files analyzed: 30
- Controls in registry: 28
- PASS / REVIEW / FAIL: 1 / 2 / 27

All data is fictional. The engine is read-only and never writes to a source
artifact. Every expiry and renewal test is made against the `as_of` date carried
in the file, never the system clock.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `payee_unique_ids` | FAIL | 1 |
| 3 | `payee_country_known` | FAIL | 1 |
| 4 | `payee_ch3_status_valid` | FAIL | 1 |
| 5 | `payee_ch4_status_valid` | FAIL | 1 |
| 6 | `payee_lob_code_valid` | FAIL | 1 |
| 7 | `rate_table_defined` | FAIL | 1 |
| 8 | `rate_within_bounds` | FAIL | 1 |
| 9 | `pay_required_fields` | FAIL | 1 |
| 10 | `pay_income_code_known` | FAIL | 2 |
| 11 | `pay_payee_exists` | FAIL | 1 |
| 12 | `pay_status_valid` | FAIL | 1 |
| 13 | `wh_us_payee_excluded` | FAIL | 1 |
| 14 | `wh_accrued_not_withheld` | FAIL | 1 |
| 15 | `wh_rate_recomputes` | FAIL | 4 |
| 16 | `wh_tax_recomputes` | FAIL | 4 |
| 17 | `exm_w8_present_for_treaty` | FAIL | 2 |
| 18 | `exm_w8_not_expired` | FAIL | 1 |
| 19 | `exm_w8_renewal_window` | FLAG | 1 |
| 20 | `exm_portfolio_interest_eligible` | FAIL | 1 |
| 21 | `exm_fatca_override` | FAIL | 1 |
| 22 | `dep_total_ties_withheld` | FAIL | 2 |
| 23 | `dep_1042_filed_on_time` | FAIL | 1 |
| 24 | `rec_slip_per_payee` | FAIL | 1 |
| 25 | `rec_gross_ties` | FAIL | 2 |
| 26 | `rec_withheld_ties` | FAIL | 2 |
| 27 | `rec_slip_count_ties_1042t` | FAIL | 2 |
| 28 | `rec_w8_watchlist_ties` | FLAG | 1 |

## Withholding files

### accrued_withheld__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `wh_accrued_not_withheld` @ `payment_register:PAYMENTS-2029/payments/PMT-06/tax_withheld_cents`  
  payment PMT-06 is accrued-only but shows 90,000.00 withheld; only a paid amount is subject to withholding

### amount_not_integer__Stonecrest_Communities

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `wh_tax_recomputes` @ `amount:payment[PMT-03].gross_cents`  
  AMOUNT_INVALID: payment[PMT-03].gross_cents must be integer cents, got 80000000.5 -- amounts are integer cents and are never coerced

### bad_ch3_status__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `payee_ch3_status_valid` @ `payee_register:PAYEES-2029/payees/PAYEE-03/chapter_3_status_code`  
  payee PAYEE-03 carries Chapter 3 status 'ZZ', which is not one of ('15', '16', 'US')

### bad_ch4_status__Northmoor_Development_Group

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `payee_ch4_status_valid` @ `payee_register:PAYEES-2029/payees/PAYEE-03/chapter_4_status_code`  
  payee PAYEE-03 carries Chapter 4 status '88', which is not one of ('01', '09', '19', '22')

### bad_lob_code__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `payee_lob_code_valid` @ `payee_register:PAYEES-2029/payees/PAYEE-01/lob_code`  
  payee PAYEE-01 claims a treaty benefit but carries LOB code '99', which is not one of ('01', '02', '03', '04', '05')

### bad_payment_status__Stonecrest_Communities

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `pay_status_valid` @ `payment_register:PAYMENTS-2029/payments/PMT-06/payment_status`  
  payment PMT-06 carries status 'pending', which is not one of ('paid', 'accrued')

### clean__Northmoor_Development_Group

**Verdict:** PASS (PASS 28, FLAG 0, FAIL 0)

All controls held.

### deposits_short__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `dep_total_ties_withheld` @ `deposit_register:DEPOSITS-2029/deposits`  
  deposits total 520,000.00; tax withheld across reportable payments is 570,000.00 (difference -50,000.00)

### duplicate_payee_id__Northmoor_Development_Group

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `payee_unique_ids` @ `payee_register:PAYEES-2029/payees/PAYEE-01`  
  payee id PAYEE-01 appears 2 times; a payment that names it cannot be attributed to one payee

### fatca_override_ignored__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 3)

- **FAIL** `wh_rate_recomputes` @ `payment_register:PAYMENTS-2029/payments/PMT-04/rate_applied_bps`  
  payment PMT-04 applied 15.00%; recomputing from payee PAYEE-04's status gives 30.00%
- **FAIL** `wh_tax_recomputes` @ `payment_register:PAYMENTS-2029/payments/PMT-04/tax_withheld_cents`  
  payment PMT-04 shows 180,000.00 withheld; 15.00% of 600,000.00 is 90,000.00
- **FAIL** `exm_fatca_override` @ `payment_register:PAYMENTS-2029/payments/PMT-04/rate_applied_bps`  
  payment PMT-04 to non-participating FFI PAYEE-04 applied 15.00%; the FATCA override requires the statutory 30.00%

### filed_late__Stonecrest_Communities

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `dep_1042_filed_on_time` @ `form_1042:FORM1042-2029/filed_date`  
  Form 1042 was filed 2030-03-20, after its due date 2030-03-15; the return is late

### gross_untied__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `rec_gross_ties` @ `form_1042:FORM1042-2029/total_gross_cents`  
  Form 1042 states total gross 5,000,000.00; the 1042-S slips sum to 4,900,000.00 (difference 100,000.00)

### missing_artifact__Northmoor_Development_Group

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `form_1042:-`  
  form_1042 is missing; the controls that read it cannot run and must not be reported as having passed

### payment_missing_field__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 2)

- **FAIL** `pay_required_fields` @ `payment_register:PAYMENTS-2029/payments/PMT-03`  
  payment PMT-03 is missing income_code
- **FAIL** `pay_income_code_known` @ `payment_register:PAYMENTS-2029/payments/PMT-03/income_code`  
  payment PMT-03 carries income code None, which the income-code table does not define

### portfolio_contingent__Stonecrest_Communities

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `exm_portfolio_interest_eligible` @ `payment_register:PAYMENTS-2029/payments/PMT-02/interest_subcharacter`  
  payment PMT-02 is coded portfolio interest but is contingent interest, which is ineligible for the portfolio-interest exemption

### rate_applied_wrong__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 2)

- **FAIL** `wh_rate_recomputes` @ `payment_register:PAYMENTS-2029/payments/PMT-01/rate_applied_bps`  
  payment PMT-01 applied 10.00%; recomputing from payee PAYEE-01's status gives 15.00%
- **FAIL** `wh_tax_recomputes` @ `payment_register:PAYMENTS-2029/payments/PMT-01/tax_withheld_cents`  
  payment PMT-01 shows 150,000.00 withheld; 10.00% of 1,000,000.00 is 100,000.00

### rate_out_of_bounds__Northmoor_Development_Group

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `rate_within_bounds` @ `treaty_rate_table:TREATY-2029/rates/Marran/rent/rate_bps`  
  treaty rate for Marran/rent is 31.00%; it must be between 0.00% and the statutory 30.00%

### rate_row_missing__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `rate_table_defined` @ `treaty_rate_table:TREATY-2029/rates/Marran/dividend`  
  the treaty table has no row for Marran/dividend, which payment PMT-01 needs; its treaty rate cannot be looked up

### slip_count_untied__Stonecrest_Communities

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `rec_slip_count_ties_1042t` @ `form_1042:FORM1042-2029/transmitted_count`  
  Form 1042 states slip_count 4 and 1042-T transmitted_count 5; 4 1042-S slip(s) are on file

### slip_missing__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 4)

- **FAIL** `rec_slip_per_payee` @ `slip_register:SLIPS-2029/slips/PAYEE-03`  
  reportable payee PAYEE-03 has 0 1042-S slip(s); exactly one is filed per reportable payee
- **FAIL** `rec_gross_ties` @ `form_1042:FORM1042-2029/total_gross_cents`  
  Form 1042 states total gross 4,900,000.00; the 1042-S slips sum to 4,100,000.00 (difference 800,000.00)
- **FAIL** `rec_withheld_ties` @ `form_1042:FORM1042-2029/total_withheld_cents`  
  Form 1042 states total tax 570,000.00; the 1042-S slips sum to 330,000.00 (difference 240,000.00)
- **FAIL** `rec_slip_count_ties_1042t` @ `form_1042:FORM1042-2029/transmitted_count`  
  Form 1042 states slip_count 4 and 1042-T transmitted_count 4; 3 1042-S slip(s) are on file

### tax_withheld_wrong__Northmoor_Development_Group

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 2)

- **FAIL** `wh_tax_recomputes` @ `payment_register:PAYMENTS-2029/payments/PMT-03/tax_withheld_cents`  
  payment PMT-03 shows 241,000.00 withheld; 30.00% of 800,000.00 is 240,000.00
- **FAIL** `dep_total_ties_withheld` @ `deposit_register:DEPOSITS-2029/deposits`  
  deposits total 570,000.00; tax withheld across reportable payments is 571,000.00 (difference -1,000.00)

### treaty_without_w8__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 4)

- **FAIL** `wh_rate_recomputes` @ `payment_register:PAYMENTS-2029/payments/PMT-01/rate_applied_bps`  
  payment PMT-01 applied 15.00%; recomputing from payee PAYEE-01's status gives 30.00%
- **FAIL** `wh_rate_recomputes` @ `payment_register:PAYMENTS-2029/payments/PMT-05/rate_applied_bps`  
  payment PMT-05 applied 0.00%; recomputing from payee PAYEE-01's status gives 30.00%
- **FAIL** `exm_w8_present_for_treaty` @ `payment_register:PAYMENTS-2029/payments/PMT-01/rate_applied_bps`  
  payment PMT-01 applied a treaty-reduced 15.00% but payee PAYEE-01 has no valid Form W-8 on file
- **FAIL** `exm_w8_present_for_treaty` @ `payment_register:PAYMENTS-2029/payments/PMT-05/rate_applied_bps`  
  payment PMT-05 applied a treaty-reduced 0.00% but payee PAYEE-01 has no valid Form W-8 on file

### unknown_country__Stonecrest_Communities

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `payee_country_known` @ `payee_register:PAYEES-2029/payees/PAYEE-02/country`  
  payee PAYEE-02 resides in 'Ostreach', which the treaty rate table does not carry; no rate could be looked up for it

### unknown_income_code__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `pay_income_code_known` @ `payment_register:PAYMENTS-2029/payments/PMT-01/income_code`  
  payment PMT-01 carries income code '77', which the income-code table does not define

### unknown_payment_payee__Northmoor_Development_Group

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `pay_payee_exists` @ `payment_register:PAYMENTS-2029/payments/PMT-99/payee_id`  
  payment PMT-99 names payee 'PAYEE-999', which is not in the payee register

### us_payee_withheld__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `wh_us_payee_excluded` @ `payment_register:PAYMENTS-2029/payments/PMT-07/tax_withheld_cents`  
  payment PMT-07 to US payee PAYEE-05 shows 120,000.00 withheld; a US person is not subject to Chapter 3 withholding

### w8_expired__Stonecrest_Communities

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `exm_w8_not_expired` @ `payee_register:PAYEES-2029/payees/PAYEE-03/w8_expiration`  
  payee PAYEE-03 holds a W-8 expiring 2029-06-30, on or before the review date 2029-12-31; the treaty claim is unsupported

### w8_renewal_due__Ardenne_Field_Partners

**Verdict:** REVIEW (PASS 27, FLAG 1, FAIL 0)

- **FLAG** `exm_w8_renewal_window` @ `payee_register:PAYEES-2029/payees/PAYEE-04/w8_expiration`  
  payee PAYEE-04 holds a W-8 expiring 2030-02-09, in 40 day(s); inside the 60-day renewal window and due to be refreshed

### watchlist_overstated__Northmoor_Development_Group

**Verdict:** REVIEW (PASS 27, FLAG 1, FAIL 0)

- **FLAG** `rec_w8_watchlist_ties` @ `w8_watchlist:WATCHLIST-2029/entries/PAYEE-01`  
  the watchlist lists payee PAYEE-01 as due for W-8 renewal, but its W-8 is not inside the lead-time window as of 2029-12-31

### withheld_untied__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `rec_withheld_ties` @ `form_1042:FORM1042-2029/total_withheld_cents`  
  Form 1042 states total tax 571,000.00; the 1042-S slips sum to 570,000.00 (difference 1,000.00)
