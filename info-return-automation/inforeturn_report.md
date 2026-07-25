# Information-return issuance control report

**Overall verdict:** FAIL

- Reporting files analyzed: 24
- Controls in registry: 22
- PASS / REVIEW / FAIL: 1 / 2 / 21

All data is fictional. The engine is read-only and never writes to a source
artifact. Every payment line is tested against the reporting year carried in
the file, never the system clock.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `ent_unique_ids` | FAIL | 1 |
| 3 | `ent_payer_identity` | FAIL | 1 |
| 4 | `pye_unique_ids` | FAIL | 1 |
| 5 | `pye_type_valid` | FAIL | 1 |
| 6 | `pye_tin_wellformed` | FAIL | 1 |
| 7 | `box_catalog_defined` | FAIL | 1 |
| 8 | `box_catalog_unique` | FAIL | 1 |
| 9 | `led_rows_attributable` | FAIL | 1 |
| 10 | `led_amounts_valid` | FAIL | 1 |
| 11 | `led_payment_in_year` | FAIL | 1 |
| 12 | `frm_required_fields` | FAIL | 1 |
| 13 | `frm_payer_identity` | FAIL | 1 |
| 14 | `frm_no_duplicates` | FAIL | 1 |
| 15 | `frm_box_ties_ledger` | FAIL | 2 |
| 16 | `thr_required_form_issued` | FAIL | 1 |
| 17 | `thr_no_unrequired_form` | FAIL | 1 |
| 18 | `thr_near_threshold_review` | FLAG | 1 |
| 19 | `bwh_rate_recomputes` | FAIL | 2 |
| 20 | `rpt_transmittal_foots` | FAIL | 2 |
| 21 | `rpt_annual_rollup_ties` | FAIL | 1 |
| 22 | `rpt_watchlist_ties` | FLAG | 1 |

## Reporting files

### amount_not_integer__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 3)

- **FAIL** `frm_box_ties_ledger` @ `amount:form[FRM-401-02].box_amount_cents`  
  AMOUNT_INVALID: form[FRM-401-02].box_amount_cents must be integer cents, got 7500000.5 -- amounts are integer cents and are never coerced
- **FAIL** `bwh_rate_recomputes` @ `amount:form[FRM-401-02].box_amount_cents`  
  AMOUNT_INVALID: form[FRM-401-02].box_amount_cents must be integer cents, got 7500000.5 -- amounts are integer cents and are never coerced
- **FAIL** `rpt_transmittal_foots` @ `amount:form[FRM-401-02].box_amount_cents`  
  AMOUNT_INVALID: form[FRM-401-02].box_amount_cents must be integer cents, got 7500000.5 -- amounts are integer cents and are never coerced

### bad_payee_type__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `pye_type_valid` @ `payee_register:PAYEES-2029/payees/PYE-506/payee_type`  
  payee PYE-506 is classed 'contractor', which is not one of ('lender', 'affiliate', 'vendor', 'settlement_entity'); its reporting treatment was never decided

### clean__Northmoor_Development_Group

**Verdict:** PASS (PASS 22, FLAG 0, FAIL 0)

All controls held.

### duplicate_box_row__Ardenne_Field_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `box_catalog_unique` @ `box_catalog:BOXES-2029/boxes/interest_return/IB-1`  
  box interest_return/IB-1 is catalogued 2 times; the threshold applied to the population is whichever row is read first

### duplicate_entity_id__Westmere

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `ent_unique_ids` @ `entity_register:ENTITIES-2029/entities/ENT-402`  
  entity id ENT-402 appears 2 times; a form that names it cannot be attributed to one payer

### duplicate_form__Northmoor_Development_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `frm_no_duplicates` @ `form_register:FORMS-2029/forms/ENT-401/PYE-501/interest_return/IB-1`  
  forms FRM-401-01, FRM-401-04 all report entity ENT-401 payee PYE-501 box interest_return/IB-1; the same year total would be reported 2 times

### duplicate_payee_id__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `pye_unique_ids` @ `payee_register:PAYEES-2029/payees/PYE-506`  
  payee id PYE-506 appears 2 times; the year total for that payee can be split across the duplicates and understate every box

### entity_tin_malformed__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `ent_payer_identity` @ `entity_register:ENTITIES-2029/entities/ENT-403/payer_tin`  
  payer entity ENT-403 carries taxpayer number 'FTN-77', which is not a well-formed identifier; the returns it issues cannot be associated with a filer

### form_below_threshold__Ardenne_Field_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `thr_no_unrequired_form` @ `form_register:FORMS-2029/forms/FRM-401-04`  
  form FRM-401-04 reports payee PYE-506 for box nonemployee_compensation_return/NB-1, where entity ENT-401 paid 500.00 against a threshold of 750.00 and no backup withholding attaches; the payee was not reportable

### form_box_off_ledger__Westmere

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `frm_box_ties_ledger` @ `form_register:FORMS-2029/forms/FRM-401-02/box_amount_cents`  
  form FRM-401-02 reports 75,100.00 in box nonemployee_compensation_return/NB-1 for payee PYE-503; entity ENT-401 ledger lines for that box total 75,000.00 (difference 100.00)

### form_missing_field__Northmoor_Development_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `frm_required_fields` @ `form_register:FORMS-2029/forms/FRM-401-02`  
  form FRM-401-02 is missing issue_date

### ledger_orphan_payee__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `led_rows_attributable` @ `ledger_extract:LEDGER-2029/payments/PAY-9001/payee_id`  
  payment PAY-9001 is booked to payee 'PYE-999', which is not in the payee register; the amount joins no year total and the payee is under-reported by it

### missing_artifact__Stonecrest_Communities

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `issuance_report:-`  
  issuance_report is missing; the controls that read it cannot run and must not be reported as having passed

### missing_required_form__Ardenne_Field_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `thr_required_form_issued` @ `form_register:FORMS-2029/forms/ENT-402/PYE-503/nonemployee_compensation_return/NB-2`  
  entity ENT-402 paid payee PYE-503 60,000.00 in box nonemployee_compensation_return/NB-2, which obliges a return, and no form is on the register

### near_threshold_payee__Westmere

**Verdict:** REVIEW (PASS 21, FLAG 1, FAIL 0)

- **FLAG** `thr_near_threshold_review` @ `ledger_extract:LEDGER-2029/payments/ENT-401/PYE-506/NB-1`  
  entity ENT-401 paid payee PYE-506 720.00 in box nonemployee_compensation_return/NB-1, 30.00 under the threshold and inside the 50.00 review band; a late invoice posting to the year makes it reportable

### negative_payment__Northmoor_Development_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `led_amounts_valid` @ `ledger_extract:LEDGER-2029/payments/PAY-9002/amount_cents`  
  payment PAY-9002 carries -500.00; a reversal has to be netted against the payment it reverses before the population is assembled, not reported as a negative box

### payee_tin_malformed__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `pye_tin_wellformed` @ `payee_register:PAYEES-2029/payees/PYE-506/payee_tin`  
  payee PYE-506 carries taxpayer number 'FTN-77', which is not a well-formed identifier; it counts as on file, suppresses backup withholding, and prints on the form unusable

### payer_tin_mismatch__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `frm_payer_identity` @ `form_register:FORMS-2029/forms/FRM-403-01/payer_tin`  
  form FRM-403-01 prints payer taxpayer number 'FTN-400100011'; entity ENT-403 is registered as 'FTN-400100033', so the return would be filed under the wrong payer

### payment_outside_year__Ardenne_Field_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `led_payment_in_year` @ `ledger_extract:LEDGER-2029/payments/PAY-4103/paid_date`  
  payment PAY-4103 is dated 2030-01-05, outside the reporting year 2029-01-01 to 2029-12-31; it belongs to another year's population

### rollup_count_wrong__Westmere

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `rpt_annual_rollup_ties` @ `issuance_report:ISSUANCE-2029/form_count`  
  the annual rollup states 11 form(s) reporting 1,361,150.00 with 15,100.00 withheld; the transmittals sum to 10 form(s) reporting 1,361,150.00 with 15,100.00 withheld

### transmittal_total_wrong__Northmoor_Development_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `rpt_transmittal_foots` @ `transmittal_register:TRANSMITTALS-2029/transmittals/ENT-402`  
  entity ENT-402 transmits 4 form(s) reporting 790,401.00 with 100.00 withheld; the forms on the register foot to 4 form(s) reporting 790,400.00 with 100.00 withheld

### unknown_form_type__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `box_catalog_defined` @ `box_catalog:BOXES-2029/boxes/royalty_return/RB-1/form_type`  
  box RB-1 is catalogued under return series 'royalty_return', which is not one of ('interest_return', 'nonemployee_compensation_return', 'card_settlement_return'); no form of that series can be issued

### watchlist_overstated__Stonecrest_Communities

**Verdict:** REVIEW (PASS 21, FLAG 1, FAIL 0)

- **FLAG** `rpt_watchlist_ties` @ `threshold_watchlist:WATCHLIST-2029/entries/ENT-401/PYE-506`  
  the watchlist holds entity ENT-401 payee PYE-506 box nonemployee_compensation_return/NB-1 as near its threshold, and the ledger totals do not put it inside the review band

### withholding_wrong__Ardenne_Field_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `bwh_rate_recomputes` @ `form_register:FORMS-2029/forms/FRM-401-03/backup_withholding_cents`  
  form FRM-401-03 carries 4,000.00 of backup withholding on 20,000.00 reported; no taxpayer number is on file for the payee, so the statutory 25.00% rate recomputes 5,000.00
