# Subcontract SOV & change-order control report

**Overall verdict:** FAIL

- Billing files analyzed: 30
- Controls in registry: 29
- PASS / REVIEW / FAIL: 1 / 2 / 27

All data is fictional. The engine is read-only and never writes to a source
artifact. Every equality is exact integer-cent arithmetic with no tolerance,
and every derived figure is recomputed through the same kernel that produced
the baseline.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `cmt_ids_unique` | FAIL | 1 |
| 3 | `cmt_required_fields` | FAIL | 1 |
| 4 | `cmt_rollup_ties_register` | FAIL | 2 |
| 5 | `cmt_revised_rederives` | FAIL | 1 |
| 6 | `co_commitment_exists` | FAIL | 1 |
| 7 | `co_numbering_sequential` | FAIL | 1 |
| 8 | `co_status_valid` | FAIL | 1 |
| 9 | `co_not_split_to_new_commitment` | FAIL | 1 |
| 10 | `co_commitment_id_format` | FAIL | 2 |
| 11 | `sov_lines_wellformed` | FAIL | 1 |
| 12 | `sov_foots_to_original` | FAIL | 2 |
| 13 | `line_ref_valid` | FAIL | 1 |
| 14 | `line_completed_rederives` | FAIL | 1 |
| 15 | `line_percent_rederives` | FLAG | 2 |
| 16 | `line_header_foots` | FAIL | 2 |
| 17 | `line_current_request_rederives` | FAIL | 3 |
| 18 | `cap_not_overbilled` | FAIL | 1 |
| 19 | `cap_balance_rederives` | FAIL | 3 |
| 20 | `ret_rate_known` | FLAG | 1 |
| 21 | `ret_rederives` | FAIL | 2 |
| 22 | `tax_rederives` | FAIL | 2 |
| 23 | `tax_payment_due_rederives` | FAIL | 4 |
| 24 | `roll_previously_ties_prior` | FAIL | 2 |
| 25 | `roll_apps_sequential` | FAIL | 1 |
| 26 | `port_totals_foot` | FAIL | 5 |
| 27 | `port_revised_identity` | FAIL | 2 |
| 28 | `lien_release_per_app` | FAIL | 3 |
| 29 | `lien_amount_ties` | FAIL | 2 |

## Billing files

### amount_not_integer__Halbrook_Residential

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 2)

- **FAIL** `ret_rederives` @ `amount:pay_app[BWC-KETT00-1/app-2].totals.retention_cents`  
  AMOUNT_INVALID: pay_app[BWC-KETT00-1/app-2].totals.retention_cents must be integer cents, got 600000.5 -- amounts are integer cents and are never coerced
- **FAIL** `tax_payment_due_rederives` @ `amount:pay_app[BWC-KETT00-1/app-2].totals.retention_cents`  
  AMOUNT_INVALID: pay_app[BWC-KETT00-1/app-2].totals.retention_cents must be integer cents, got 600000.5 -- amounts are integer cents and are never coerced

### app_number_gap__Stonecrest_Communities

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 3)

- **FAIL** `roll_apps_sequential` @ `pay_application_register:PAYAPPS-2030/pay_applications/BWC-MARO00-1`  
  commitment BWC-MARO00-1 carries pay apps numbered [1, 4]; a continuous billing runs [1, 2] with no gap or repeat
- **FAIL** `lien_release_per_app` @ `lien_release_register:RELEASES-2030/releases/REL-BWC-MARO00-1-2`  
  release REL-BWC-MARO00-1-2 references pay app BWC-MARO00-1/app-2, which is not in the pay-application register; it waives lien rights against no billing
- **FAIL** `lien_release_per_app` @ `lien_release_register:RELEASES-2030/releases/BWC-MARO00-1/app-4`  
  pay app BWC-MARO00-1/app-4 carries 0 conditional release(s); each certified payment is exchanged for exactly one

### balance_misstated__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `cap_balance_rederives` @ `pay_application_register:PAYAPPS-2030/pay_applications/BWC-MARO00-1/app-1/lines/1/balance_to_finish_cents`  
  line 1 on pay app BWC-MARO00-1/app-1 states 119,900.00 to finish; scheduled 200,000.00 - completed 80,000.00 re-derives 120,000.00

### clean__Northmoor_Development_Group

**Verdict:** PASS (PASS 29, FLAG 0, FAIL 0)

All controls held.

### co_bad_status__Westmere

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `co_status_valid` @ `change_order_log:COLOG-2030/change_orders/CO-2002/status`  
  change order CO-2002 carries status 'maybe', which is not one of ('approved', 'pending', 'void'); whether it moves the revised contract cannot be decided

### co_booked_as_commitment__Northmoor_Development_Group

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 3)

- **FAIL** `cmt_rollup_ties_register` @ `commitment_rollup:ROLLUP-2030/rows/BWC-MARO00-2`  
  commitment BWC-MARO00-2 appears 0 time(s) on the committed-cost roster; each commitment carries exactly one row
- **FAIL** `co_not_split_to_new_commitment` @ `commitment_register:COMMITS-2030/commitments/BWC-MARO00-2/origin`  
  commitment BWC-MARO00-2 carries origin 'change_order'; change orders are applied to the original commitment as #-N and must never be booked as a commitment of their own
- **FAIL** `sov_foots_to_original` @ `sov_schedule:SOV-2030/lines/BWC-MARO00-2`  
  commitment BWC-MARO00-2 SOV lines foot to 0.00; the original contract amount is 4,200.00 (difference -4,200.00)

### co_number_gap__Halbrook_Residential

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `co_numbering_sequential` @ `change_order_log:COLOG-2030/change_orders/BWC-KETT00-1`  
  commitment BWC-KETT00-1 carries change orders numbered [1, 5]; the procedure numbers them sequentially [1, 2] against the original commitment

### co_unknown_commitment__Stonecrest_Communities

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `co_commitment_exists` @ `change_order_log:COLOG-2030/change_orders/CO-2099/commitment_id`  
  change order CO-2099 names commitment 'BWC-TALV00-1', which is not in the commitment register

### commitment_id_prefix_mismatch__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `co_commitment_id_format` @ `commitment_register:COMMITS-2030/commitments/BWC-CIND00-1/commitment_id`  
  commitment id BWC-CIND00-1 does not compose as CPY-CIND00-N from its own project code 'CPY' and vendor code 'CIND00'

### commitment_missing_field__Westmere

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `cmt_required_fields` @ `commitment_register:COMMITS-2030/commitments/BWC-MARO00-1`  
  commitment BWC-MARO00-1 is missing vendor

### duplicate_commitment_id__Northmoor_Development_Group

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 2)

- **FAIL** `cmt_ids_unique` @ `commitment_register:COMMITS-2030/commitments/BWC-KETT00-1`  
  commitment id BWC-KETT00-1 appears 2 times; a pay app that bills it cannot be attributed to one contract
- **FAIL** `co_commitment_id_format` @ `commitment_register:COMMITS-2030/commitments/BWC-KETT00`  
  vendor KETT00 on project BWC carries commitment counts [1, 1]; the procedure numbers them sequentially [1, 2]

### header_totals_wrong__Halbrook_Residential

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 3)

- **FAIL** `line_header_foots` @ `pay_application_register:PAYAPPS-2030/pay_applications/BWC-KETT00-1/app-1/totals/total_completed_cents`  
  pay app BWC-KETT00-1/app-1 header states total_completed_cents of 100,100.00; its own lines foot to 100,000.00
- **FAIL** `line_current_request_rederives` @ `pay_application_register:PAYAPPS-2030/pay_applications/BWC-KETT00-1/app-1/totals/current_request_cents`  
  pay app BWC-KETT00-1/app-1 requests 100,000.00; completed 100,100.00 - previously billed 0.00 re-derives 100,100.00
- **FAIL** `roll_previously_ties_prior` @ `pay_application_register:PAYAPPS-2030/pay_applications/BWC-KETT00-1/app-2/totals/total_previously_billed_cents`  
  pay app BWC-KETT00-1/app-2 opens with 100,000.00 previously billed; pay app BWC-KETT00-1/app-1 closed at 100,100.00 -- the roll-forward is broken by -100.00

### line_completed_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `line_completed_rederives` @ `pay_application_register:PAYAPPS-2030/pay_applications/BWC-KETT00-1/app-2/lines/1/total_completed_cents`  
  line 1 on pay app BWC-KETT00-1/app-2 states 105,000.00 completed; previously billed 60,000.00 + this period 44,900.00 re-derives 104,900.00

### line_overbilled__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `cap_not_overbilled` @ `pay_application_register:PAYAPPS-2030/pay_applications/BWC-CIND00-1/app-1/lines/1/total_completed_cents`  
  line 1 on pay app BWC-CIND00-1/app-1 is billed to 90,000.00 against a scheduled value of 86,750.00; the line is overbilled by 3,250.00

### missing_artifact__Westmere

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `lien_release_register:-`  
  lien_release_register is missing; the controls that read it cannot run and must not be reported as having passed

### net_changes_wrong__Northmoor_Development_Group

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 2)

- **FAIL** `cmt_revised_rederives` @ `commitment_rollup:ROLLUP-2030/rows/BWC-KETT00-1/net_changes_cents`  
  the roster states 20,500.00 of net changes on BWC-KETT00-1; the approved change orders re-derive 12,500.00 -- a pending or void order moves nothing until it is approved
- **FAIL** `port_totals_foot` @ `commitment_rollup:ROLLUP-2030/totals/changes_total_cents`  
  the roster states changes_total_cents of 8,300.00; its 3 commitment rows foot to 16,300.00

### payapp_line_unknown__Halbrook_Residential

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `line_ref_valid` @ `pay_application_register:PAYAPPS-2030/pay_applications/BWC-KETT00-1/app-1/lines/9`  
  pay app BWC-KETT00-1/app-1 bills line 9, which is not on commitment BWC-KETT00-1's schedule of values

### payment_due_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 2)

- **FAIL** `tax_payment_due_rederives` @ `pay_application_register:PAYAPPS-2030/pay_applications/BWC-KETT00-1/app-1/totals/payment_due_incl_tax_cents`  
  pay app BWC-KETT00-1/app-1 certifies 103,300.00 due; request 100,000.00 - retention 5,000.00 + tax 8,200.00 re-derives 103,200.00
- **FAIL** `lien_amount_ties` @ `lien_release_register:RELEASES-2030/releases/REL-BWC-KETT00-1-1/amount_cents`  
  release REL-BWC-KETT00-1-1 is signed for 103,200.00; pay app BWC-KETT00-1/app-1 certifies 103,300.00 due including tax (difference -100.00)

### percent_overstated__Ardenne_Field_Partners

**Verdict:** REVIEW (PASS 28, FLAG 1, FAIL 0)

- **FLAG** `line_percent_rederives` @ `pay_application_register:PAYAPPS-2030/pay_applications/BWC-KETT00-1/app-2/lines/2/percent_complete_bps`  
  line 2 on pay app BWC-KETT00-1/app-2 states 45.48% complete; 95,000.00 against 210,000.00 scheduled re-derives 45.23%

### previously_billed_break__Westmere

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 3)

- **FAIL** `line_header_foots` @ `pay_application_register:PAYAPPS-2030/pay_applications/BWC-KETT00-1/app-2/totals/total_previously_billed_cents`  
  pay app BWC-KETT00-1/app-2 header states total_previously_billed_cents of 99,500.00; its own lines foot to 100,000.00
- **FAIL** `line_current_request_rederives` @ `pay_application_register:PAYAPPS-2030/pay_applications/BWC-KETT00-1/app-2/totals/current_request_cents`  
  pay app BWC-KETT00-1/app-2 requests 120,000.00; completed 220,000.00 - previously billed 99,500.00 re-derives 120,500.00
- **FAIL** `roll_previously_ties_prior` @ `pay_application_register:PAYAPPS-2030/pay_applications/BWC-KETT00-1/app-2/totals/total_previously_billed_cents`  
  pay app BWC-KETT00-1/app-2 opens with 99,500.00 previously billed; pay app BWC-KETT00-1/app-1 closed at 100,000.00 -- the roll-forward is broken by -500.00

### release_amount_mismatch__Northmoor_Development_Group

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `lien_amount_ties` @ `lien_release_register:RELEASES-2030/releases/REL-BWC-KETT00-1-2/amount_cents`  
  release REL-BWC-KETT00-1-2 is signed for 123,740.00; pay app BWC-KETT00-1/app-2 certifies 123,840.00 due including tax (difference -100.00)

### release_missing__Halbrook_Residential

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `lien_release_per_app` @ `lien_release_register:RELEASES-2030/releases/BWC-CIND00-1/app-1`  
  pay app BWC-CIND00-1/app-1 carries 0 conditional release(s); each certified payment is exchanged for exactly one

### request_not_difference__Stonecrest_Communities

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 4)

- **FAIL** `line_current_request_rederives` @ `pay_application_register:PAYAPPS-2030/pay_applications/BWC-MARO00-1/app-2/totals/current_request_cents`  
  pay app BWC-MARO00-1/app-2 requests 80,100.00; completed 160,000.00 - previously billed 80,000.00 re-derives 80,000.00
- **FAIL** `ret_rederives` @ `pay_application_register:PAYAPPS-2030/pay_applications/BWC-MARO00-1/app-2/totals/retention_cents`  
  pay app BWC-MARO00-1/app-2 states retention of 8,000.00; 10.00% on the 80,100.00 request re-derives 8,010.00
- **FAIL** `tax_rederives` @ `pay_application_register:PAYAPPS-2030/pay_applications/BWC-MARO00-1/app-2/totals/taxable_request_cents`  
  pay app BWC-MARO00-1/app-2 states a taxable request of 80,000.00 against a current request of 80,100.00; these commitments bill fully-taxable work
- **FAIL** `tax_payment_due_rederives` @ `pay_application_register:PAYAPPS-2030/pay_applications/BWC-MARO00-1/app-2/totals/payment_due_incl_tax_cents`  
  pay app BWC-MARO00-1/app-2 certifies 78,560.00 due; request 80,100.00 - retention 8,000.00 + tax 6,560.00 re-derives 78,660.00

### retention_rate_nonstandard__Ardenne_Field_Partners

**Verdict:** REVIEW (PASS 28, FLAG 1, FAIL 0)

- **FLAG** `ret_rate_known` @ `commitment_register:COMMITS-2030/commitments/BWC-CIND00-1/retention_rate_bps`  
  commitment BWC-CIND00-1 carries retention at 7.50%; the standard all-lines menu is 5.00% / 10.00% -- confirm the contract actually says so

### revised_identity_broken__Westmere

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 2)

- **FAIL** `port_totals_foot` @ `commitment_rollup:ROLLUP-2030/totals/revised_total_cents`  
  the roster states revised_total_cents of 932,550.00; its 3 commitment rows foot to 932,450.00
- **FAIL** `port_revised_identity` @ `commitment_rollup:ROLLUP-2030/totals/revised_total_cents`  
  the roster's revised total is 932,550.00; original total 924,150.00 + changes total 8,300.00 re-derives 932,450.00

### rollup_row_missing__Northmoor_Development_Group

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 3)

- **FAIL** `cmt_rollup_ties_register` @ `commitment_rollup:ROLLUP-2030/rows/BWC-CIND00-1`  
  commitment BWC-CIND00-1 appears 0 time(s) on the committed-cost roster; each commitment carries exactly one row
- **FAIL** `port_totals_foot` @ `commitment_rollup:ROLLUP-2030/totals/original_total_cents`  
  the roster states original_total_cents of 924,150.00; its 2 commitment rows foot to 797,400.00
- **FAIL** `port_totals_foot` @ `commitment_rollup:ROLLUP-2030/totals/revised_total_cents`  
  the roster states revised_total_cents of 932,450.00; its 2 commitment rows foot to 805,700.00

### rollup_totals_wrong__Halbrook_Residential

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 2)

- **FAIL** `port_totals_foot` @ `commitment_rollup:ROLLUP-2030/totals/original_total_cents`  
  the roster states original_total_cents of 924,250.00; its 3 commitment rows foot to 924,150.00
- **FAIL** `port_revised_identity` @ `commitment_rollup:ROLLUP-2030/totals/revised_total_cents`  
  the roster's revised total is 932,450.00; original total 924,250.00 + changes total 8,300.00 re-derives 932,550.00

### sales_tax_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 2)

- **FAIL** `tax_rederives` @ `pay_application_register:PAYAPPS-2030/pay_applications/BWC-MARO00-1/app-1/totals/sales_tax_cents`  
  pay app BWC-MARO00-1/app-1 states sales tax of 6,560.10; 8.20% on the 80,000.00 taxable request re-derives 6,560.00
- **FAIL** `tax_payment_due_rederives` @ `pay_application_register:PAYAPPS-2030/pay_applications/BWC-MARO00-1/app-1/totals/payment_due_incl_tax_cents`  
  pay app BWC-MARO00-1/app-1 certifies 78,560.00 due; request 80,000.00 - retention 8,000.00 + tax 6,560.10 re-derives 78,560.10

### sov_does_not_foot__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 26, FLAG 1, FAIL 3)

- **FAIL** `sov_foots_to_original` @ `sov_schedule:SOV-2030/lines/BWC-KETT00-1`  
  commitment BWC-KETT00-1 SOV lines foot to 495,000.00; the original contract amount is 485,000.00 (difference 10,000.00)
- **FLAG** `line_percent_rederives` @ `pay_application_register:PAYAPPS-2030/pay_applications/BWC-KETT00-1/app-2/lines/3/percent_complete_bps`  
  line 3 on pay app BWC-KETT00-1/app-2 states 16.00% complete; 20,000.00 against 135,000.00 scheduled re-derives 14.81%
- **FAIL** `cap_balance_rederives` @ `pay_application_register:PAYAPPS-2030/pay_applications/BWC-KETT00-1/app-1/lines/3/balance_to_finish_cents`  
  line 3 on pay app BWC-KETT00-1/app-1 states 125,000.00 to finish; scheduled 135,000.00 - completed 0.00 re-derives 135,000.00
- **FAIL** `cap_balance_rederives` @ `pay_application_register:PAYAPPS-2030/pay_applications/BWC-KETT00-1/app-2/lines/3/balance_to_finish_cents`  
  line 3 on pay app BWC-KETT00-1/app-2 states 105,000.00 to finish; scheduled 135,000.00 - completed 20,000.00 re-derives 115,000.00

### sov_duplicate_line__Westmere

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `sov_lines_wellformed` @ `sov_schedule:SOV-2030/lines/BWC-KETT00-1/2`  
  SOV line 2 on commitment BWC-KETT00-1 appears 2 times; a pay-app line that bills it cannot be matched to one scheduled value
