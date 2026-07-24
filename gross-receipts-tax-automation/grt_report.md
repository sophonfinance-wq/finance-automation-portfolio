# Gross-receipts & excise tax reconciliation report

**Overall verdict:** FAIL

- Reconciliation files analyzed: 29
- Controls in registry: 27
- PASS / REVIEW / FAIL: 1 / 2 / 26

All data is fictional. The engine is read-only and never writes to a source
artifact. Every due-date and renewal test is made against the `as_of` date carried
in the file, never the system clock.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `ent_unique_ids` | FAIL | 1 |
| 3 | `ent_jurisdictions_declared` | FAIL | 1 |
| 4 | `jur_cadence_valid` | FAIL | 1 |
| 5 | `jur_rate_windows_sound` | FAIL | 1 |
| 6 | `rev_required_fields` | FAIL | 1 |
| 7 | `rev_line_unique` | FAIL | 1 |
| 8 | `rev_entity_known` | FAIL | 1 |
| 9 | `rev_ledger_mapped` | FAIL | 2 |
| 10 | `rev_gross_ties_ledger` | FAIL | 3 |
| 11 | `fil_required_fields` | FAIL | 1 |
| 12 | `fil_unique` | FAIL | 2 |
| 13 | `fil_refs_exist` | FAIL | 1 |
| 14 | `eff_rate_matches_period` | FAIL | 2 |
| 15 | `rate_tax_before_credit_recomputes` | FAIL | 2 |
| 16 | `rate_tax_due_recomputes` | FAIL | 1 |
| 17 | `ded_base_recomputes` | FAIL | 3 |
| 18 | `ded_nontaxable_ties_ledger` | FAIL | 1 |
| 19 | `ded_credit_recomputes` | FAIL | 1 |
| 20 | `cal_completeness` | FAIL | 1 |
| 21 | `cal_due_date_gate` | FAIL | 1 |
| 22 | `cal_due_soon` | FLAG | 1 |
| 23 | `cal_approval_before_filing` | FAIL | 1 |
| 24 | `lic_status_active` | FAIL | 1 |
| 25 | `lic_renewal_current` | FLAG | 1 |
| 26 | `rpt_summary_recomputes` | FAIL | 2 |
| 27 | `rpt_report_totals_tie` | FAIL | 1 |

## Reconciliation files

### amount_not_integer__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 2)

- **FAIL** `rate_tax_before_credit_recomputes` @ `amount:filing[FIL-01].taxable_base_cents`  
  AMOUNT_INVALID: filing[FIL-01].taxable_base_cents must be integer cents, got 60000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `ded_base_recomputes` @ `amount:filing[FIL-01].taxable_base_cents`  
  AMOUNT_INVALID: filing[FIL-01].taxable_base_cents must be integer cents, got 60000000.5 -- amounts are integer cents and are never coerced

### bad_cadence__Stonecrest_Communities

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `jur_cadence_valid` @ `jurisdiction_register:JUR-2029/jurisdictions/OSTREND-CITY/cadence`  
  jurisdiction OSTREND-CITY files at cadence 'fortnightly', which is not one of ('monthly', 'quarterly', 'annual'); its expected-period set cannot be built

### base_wrong__Ardenne_Field_Group

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `ded_base_recomputes` @ `filing_register:FILINGS-2029/filings/FIL-02/taxable_base_cents`  
  worksheet FIL-02 states taxable base 600,000.01; 600,000.00 less back-out 0.00 less standard deduction 0.00 re-derives 600,000.00

### clean__Northmoor_Development_Group

**Verdict:** PASS (PASS 27, FLAG 0, FAIL 0)

All controls held.

### credit_wrong__Northmoor_Development_Group

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `ded_credit_recomputes` @ `filing_register:FILINGS-2029/filings/FIL-01/credit_cents`  
  worksheet FIL-01 claims credit 0.01; the MARRAN-STATE rules on gross 600,000.00 and pre-credit tax 10,500.00 allow 0.00

### due_soon_unfiled__Halbrook_Residential_Partners

**Verdict:** REVIEW (PASS 26, FLAG 1, FAIL 0)

- **FLAG** `cal_due_soon` @ `filing_register:FILINGS-2029/filings/FIL-09/due_date`  
  worksheet FIL-09 is unfiled and due 2030-03-20, in 19 day(s); inside the 60-day window and due to be filed

### duplicate_entity_id__Stonecrest_Communities

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `ent_unique_ids` @ `entity_register:ENTITIES-2029/entities/ENT-01`  
  entity id ENT-01 appears 2 times; a worksheet that names it cannot be attributed to one entity

### duplicate_filing__Ardenne_Field_Group

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 2)

- **FAIL** `fil_unique` @ `filing_register:FILINGS-2029/filings/FIL-05`  
  worksheet id FIL-05 appears 2 times
- **FAIL** `fil_unique` @ `filing_register:FILINGS-2029/filings/ENT-03/MARRAN-STATE/service_other/2029-09`  
  obligation ENT-03 / MARRAN-STATE / service_other / 2029-09 has 2 worksheets; exactly one governs

### duplicate_ledger_line__Northmoor_Development_Group

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `rev_line_unique` @ `revenue_ledger:GL-2029/lines/GL-01`  
  GL line id GL-01 appears 2 times; the same receipt cannot be counted twice into the taxable base

### filing_missing_field__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `fil_required_fields` @ `filing_register:FILINGS-2029/filings/FIL-04`  
  worksheet FIL-04 is missing worksheet_ref

### gross_tie_break__Stonecrest_Communities

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 3)

- **FAIL** `rev_gross_ties_ledger` @ `filing_register:FILINGS-2029/filings/FIL-01/gross_receipts_cents`  
  worksheet FIL-01 states gross 600,001.00; the GL lines under it sum to 600,000.00 (off by 1.00)
- **FAIL** `ded_base_recomputes` @ `filing_register:FILINGS-2029/filings/FIL-01/taxable_base_cents`  
  worksheet FIL-01 states taxable base 600,000.00; 600,001.00 less back-out 0.00 less standard deduction 0.00 re-derives 600,001.00
- **FAIL** `rpt_summary_recomputes` @ `tax_summary:SUMMARY-2029/filings/FIL-01/tax_due_cents`  
  worksheet FIL-01 is summarised at tax due 10,500.00; recomputing from its receipts gives 10,500.01

### inverted_rate_window__Ardenne_Field_Group

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 2)

- **FAIL** `jur_rate_windows_sound` @ `jurisdiction_register:JUR-2029/jurisdictions/HALZA-GET/rate_windows/0/effective_from`  
  jurisdiction HALZA-GET rate window 0 opens 2032-06-01 and closes 2031-12-31; the window does not run forwards
- **FAIL** `eff_rate_matches_period` @ `filing_register:FILINGS-2029/filings/FIL-09/period_start`  
  worksheet FIL-09 covers a period starting 2029-01-01, which no HALZA-GET rate window covers

### late_filing__Northmoor_Development_Group

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `cal_due_date_gate` @ `filing_register:FILINGS-2029/filings/FIL-09/filing_date`  
  worksheet FIL-09 was filed 2030-02-15, after its due date 2030-01-31 (15 day(s) late)

### ledger_missing_field__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 2)

- **FAIL** `rev_required_fields` @ `revenue_ledger:GL-2029/lines/GL-01`  
  ledger line GL-01 is missing gross_receipts_cents
- **FAIL** `rev_gross_ties_ledger` @ `amount:ledger[GL-01].gross_receipts_cents`  
  AMOUNT_INVALID: ledger[GL-01].gross_receipts_cents must be integer cents, got None -- amounts are integer cents and are never coerced

### license_cancelled__Stonecrest_Communities

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `lic_status_active` @ `license_register:LICENSES-2029/licenses/ENT-01/MARRAN-STATE/status`  
  entity ENT-01 files in MARRAN-STATE on a licence whose status is 'cancelled', not 'active'

### license_renewal_due__Ardenne_Field_Group

**Verdict:** REVIEW (PASS 26, FLAG 1, FAIL 0)

- **FLAG** `lic_renewal_current` @ `license_register:LICENSES-2029/licenses/ENT-02/OSTREND-CITY/renewal_date`  
  entity ENT-02 OSTREND-CITY licence renews 2030-04-01, in 31 day(s); inside the 60-day window and due to be renewed

### missing_artifact__Northmoor_Development_Group

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `excise_report:-`  
  excise_report is missing; the controls that read it cannot run and must not be reported as having passed

### missing_filing__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `cal_completeness` @ `filing_register:FILINGS-2029/filings/ENT-02/OSTREND-CITY/2029`  
  entity ENT-02 has no OSTREND-CITY worksheet for period 2029; the obligation is unfiled

### nontaxable_tie_break__Stonecrest_Communities

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `ded_nontaxable_ties_ledger` @ `filing_register:FILINGS-2029/filings/FIL-03/nontaxable_cents`  
  worksheet FIL-03 backs out 0.00 non-taxable; the GL lines under it sum to 0.01 (off by -0.01)

### orphan_ledger_line__Ardenne_Field_Group

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `rev_ledger_mapped` @ `revenue_ledger:GL-2029/lines/GL-90`  
  ledger line GL-90 (ENT-01 / HALZA-GET / get / 2029) has no worksheet; its receipts are taxed nowhere

### report_total_break__Northmoor_Development_Group

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `rpt_report_totals_tie` @ `excise_report:REPORT-2029/total_tax_due_cents`  
  the report states total 84,800.01 over 9 worksheet(s); the summary recomputes 84,800.00 over 9

### summary_recompute_break__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `rpt_summary_recomputes` @ `tax_summary:SUMMARY-2029/filings/FIL-07/tax_due_cents`  
  worksheet FIL-07 is summarised at tax due 4,500.01; recomputing from its receipts gives 4,500.00

### tax_before_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `rate_tax_before_credit_recomputes` @ `filing_register:FILINGS-2029/filings/FIL-01/tax_before_credit_cents`  
  worksheet FIL-01 states pre-credit tax 10,500.01; 600,000.00 at 175 bps re-derives 10,500.00

### tax_due_wrong__Ardenne_Field_Group

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `rate_tax_due_recomputes` @ `filing_register:FILINGS-2029/filings/FIL-02/tax_due_cents`  
  worksheet FIL-02 states tax due 12,600.01; 12,600.00 less credit 0.00 re-derives 12,600.00

### unapproved_filing__Northmoor_Development_Group

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `cal_approval_before_filing` @ `filing_register:FILINGS-2029/filings/FIL-06/approval_signed`  
  worksheet FIL-06 was filed with no approval signature

### undeclared_jurisdictions__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `ent_jurisdictions_declared` @ `entity_register:ENTITIES-2029/entities/ENT-03/required_jurisdictions`  
  active entity ENT-03 declares no filing jurisdiction; its calendar controls would pass on an empty obligation

### unknown_entity_filing__Stonecrest_Communities

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `fil_refs_exist` @ `filing_register:FILINGS-2029/filings/FIL-90/entity_id`  
  worksheet FIL-90 names entity 'ENT-999', which is not in the entity register

### unknown_entity_ledger__Ardenne_Field_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 3)

- **FAIL** `rev_entity_known` @ `revenue_ledger:GL-2029/lines/GL-13/entity_id`  
  ledger line GL-13 names entity 'ENT-999', which is not in the entity register
- **FAIL** `rev_ledger_mapped` @ `revenue_ledger:GL-2029/lines/GL-13`  
  ledger line GL-13 (ENT-999 / KELDER-CITY / service / 2029-Q3) has no worksheet; its receipts are taxed nowhere
- **FAIL** `rev_gross_ties_ledger` @ `filing_register:FILINGS-2029/filings/FIL-07/gross_receipts_cents`  
  worksheet FIL-07 states gross 3,000,000.00; the GL lines under it sum to 0.00 (off by 3,000,000.00)

### wrong_effective_rate__Northmoor_Development_Group

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `eff_rate_matches_period` @ `filing_register:FILINGS-2029/filings/FIL-01/period_start`  
  worksheet FIL-01 covers a period starting 2028-06-01, which no MARRAN-STATE rate window covers
