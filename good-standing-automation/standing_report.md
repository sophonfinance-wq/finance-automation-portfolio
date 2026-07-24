# Entity good-standing control report

**Overall verdict:** FAIL

- Standing files analyzed: 28
- Controls in registry: 26
- PASS / REVIEW / FAIL: 1 / 2 / 25

All data is fictional. The engine is read-only and never writes to a source
artifact. Every currency and renewal test is made against the `as_of` date carried
in the file, never the system clock.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `ent_unique_ids` | FAIL | 1 |
| 3 | `ent_type_valid` | FAIL | 1 |
| 4 | `ent_status_valid` | FAIL | 1 |
| 5 | `ent_jurisdictions_declared` | FAIL | 1 |
| 6 | `jur_matrix_defined` | FAIL | 1 |
| 7 | `jur_record_present` | FAIL | 1 |
| 8 | `rec_required_fields` | FAIL | 1 |
| 9 | `rec_file_number_unique` | FAIL | 1 |
| 10 | `rec_entity_exists` | FAIL | 1 |
| 11 | `rec_state_required` | FAIL | 1 |
| 12 | `fil_due_date_recomputes` | FAIL | 1 |
| 13 | `fil_report_filed_on_time` | FAIL | 1 |
| 14 | `fil_report_fee_paid` | FAIL | 1 |
| 15 | `fil_renewal_lead_time` | FLAG | 1 |
| 16 | `tax_amount_meets` | FAIL | 2 |
| 17 | `tax_due_date_recomputes` | FAIL | 1 |
| 18 | `tax_paid_on_time` | FAIL | 1 |
| 19 | `agt_matches_sos` | FAIL | 1 |
| 20 | `agt_fee_current` | FAIL | 1 |
| 21 | `sts_sos_active` | FAIL | 1 |
| 22 | `lic_current` | FAIL | 1 |
| 23 | `dis_cancellation_complete` | FAIL | 1 |
| 24 | `roll_standing_recomputes` | FAIL | 13 |
| 25 | `roll_report_counts_tie` | FAIL | 1 |
| 26 | `roll_watchlist_ties` | FLAG | 1 |

## Standing files

### agent_fee_unpaid__Brightwater_Holdings

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 2)

- **FAIL** `agt_fee_current` @ `standing_record_register:RECORDS-2029/records/GS-1001/agent_fee_paid_date`  
  record GS-1001 (Marran) shows no paid date for the registered-agent fee; an unpaid agent resigns
- **FAIL** `roll_standing_recomputes` @ `standing_summary:SUMMARY-2029/entities/ENT-101/good_standing`  
  entity ENT-101 is summarised good_standing=True; recomputing from its records gives good_standing=False

### agent_mismatch__Copperfield_Holdings

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 2)

- **FAIL** `agt_matches_sos` @ `standing_record_register:RECORDS-2029/records/GS-1001/sos_agent_name`  
  record GS-1001 (Marran) names 'Vantage Corporate Agents' as agent of record; the contracted agent is 'Paravance Agent Services'
- **FAIL** `roll_standing_recomputes` @ `standing_summary:SUMMARY-2029/entities/ENT-101/good_standing`  
  entity ENT-101 is summarised good_standing=True; recomputing from its records gives good_standing=False

### amount_not_integer__Alderpoint_Holdings

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 2)

- **FAIL** `tax_amount_meets` @ `amount:record[GS-1001].franchise_tax_paid_cents`  
  AMOUNT_INVALID: record[GS-1001].franchise_tax_paid_cents must be integer cents, got 30000.5 -- amounts are integer cents and are never coerced
- **FAIL** `roll_standing_recomputes` @ `amount:record[GS-1001].franchise_tax_paid_cents`  
  AMOUNT_INVALID: record[GS-1001].franchise_tax_paid_cents must be integer cents, got 30000.5 -- amounts are integer cents and are never coerced

### bad_entity_status__Westmere_Holdings_Group

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `ent_status_valid` @ `entity_register:ENTITIES-2029/entities/ENT-103/status`  
  entity ENT-103 carries status 'pending', which is not one of ('active', 'inactive', 'dissolved'); whether it owes filings is undecided

### bad_entity_type__Brightwater_Holdings

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 2)

- **FAIL** `ent_type_valid` @ `entity_register:ENTITIES-2029/entities/ENT-102/entity_type`  
  entity ENT-102 is typed 'trust', which is not one of ('llc', 'corporation', 'lp'); its obligations cannot be looked up
- **FAIL** `roll_standing_recomputes` @ `standing_summary:SUMMARY-2029/entities/ENT-102/good_standing`  
  entity ENT-102 is summarised good_standing=True; recomputing from its records gives good_standing=False

### clean__Westmere_Holdings_Group

**Verdict:** PASS (PASS 26, FLAG 0, FAIL 0)

All controls held.

### duplicate_entity_id__Copperfield_Holdings

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `ent_unique_ids` @ `entity_register:ENTITIES-2029/entities/ENT-101`  
  entity id ENT-101 appears 2 times; a record that names it cannot be attributed to one entity

### duplicate_file_number__Alderpoint_Holdings

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `rec_file_number_unique` @ `standing_record_register:RECORDS-2029/records/sos_file_number/SOS-2029-1001`  
  SOS file number SOS-2029-1001 appears on 2 records; they cannot both be independent evidence of a registration

### franchise_due_date_wrong__Westmere_Holdings_Group

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `tax_due_date_recomputes` @ `standing_record_register:RECORDS-2029/records/GS-1001/franchise_tax_due_date`  
  record GS-1001 states a franchise-tax due date of '2029-06-10'; the Marran statute re-derives 2029-06-01 for 2029

### franchise_paid_late__Brightwater_Holdings

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 2)

- **FAIL** `tax_paid_on_time` @ `standing_record_register:RECORDS-2029/records/GS-1001/franchise_tax_paid_date`  
  record GS-1001 (Marran) paid its franchise tax 2029-06-02; the statutory due date is '2029-06-01' and it must be paid on-or-before it
- **FAIL** `roll_standing_recomputes` @ `standing_summary:SUMMARY-2029/entities/ENT-101/good_standing`  
  entity ENT-101 is summarised good_standing=True; recomputing from its records gives good_standing=False

### franchise_tax_short__Copperfield_Holdings

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 2)

- **FAIL** `tax_amount_meets` @ `standing_record_register:RECORDS-2029/records/GS-1001/franchise_tax_paid_cents`  
  record GS-1001 (Marran) paid 250.00 in franchise tax; the statute sets a flat 300.00 (short 50.00)
- **FAIL** `roll_standing_recomputes` @ `standing_summary:SUMMARY-2029/entities/ENT-101/good_standing`  
  entity ENT-101 is summarised good_standing=True; recomputing from its records gives good_standing=False

### incomplete_dissolution__Alderpoint_Holdings

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `dis_cancellation_complete` @ `standing_record_register:RECORDS-2029/records/GS-1007/cancellation_filed`  
  dissolved entity ENT-104 record GS-1007 shows no filed certificate of cancellation for Marran; the dissolution is incomplete there

### license_lapsed__Westmere_Holdings_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 2)

- **FAIL** `lic_current` @ `standing_record_register:RECORDS-2029/records/GS-1002/license_status`  
  record GS-1002 (Kelder) shows business licence 'lapsed' renewing 2030-06-01; it must read current and renew after the review date 2029-09-15
- **FAIL** `roll_standing_recomputes` @ `standing_summary:SUMMARY-2029/entities/ENT-101/good_standing`  
  entity ENT-101 is summarised good_standing=True; recomputing from its records gives good_standing=False

### matrix_row_missing__Brightwater_Holdings

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 2)

- **FAIL** `jur_matrix_defined` @ `jurisdiction_matrix:MATRIX-2029/requirements/Tolvane/corporation`  
  the jurisdiction matrix has no row for Tolvane/corporation, which entity ENT-102 is registered in; its obligations cannot be tested
- **FAIL** `roll_standing_recomputes` @ `standing_summary:SUMMARY-2029/entities/ENT-102/good_standing`  
  entity ENT-102 is summarised good_standing=True; recomputing from its records gives good_standing=False

### missing_artifact__Copperfield_Holdings

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `compliance_report:-`  
  compliance_report is missing; the controls that read it cannot run and must not be reported as having passed

### record_missing_field__Alderpoint_Holdings

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `rec_required_fields` @ `standing_record_register:RECORDS-2029/records/GS-1005`  
  record GS-1005 is missing sos_file_number

### record_present_missing__Westmere_Holdings_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 2)

- **FAIL** `jur_record_present` @ `standing_record_register:RECORDS-2029/records/ENT-102/Tolvane`  
  entity ENT-102 is registered in Tolvane but has no good-standing record on file for it
- **FAIL** `roll_standing_recomputes` @ `standing_summary:SUMMARY-2029/entities/ENT-102/good_standing`  
  entity ENT-102 is summarised good_standing=True; recomputing from its records gives good_standing=False

### renewal_due_soon__Brightwater_Holdings

**Verdict:** REVIEW (PASS 25, FLAG 1, FAIL 0)

- **FLAG** `fil_renewal_lead_time` @ `standing_record_register:RECORDS-2029/records/GS-1001/next_report_due_date`  
  record GS-1001 (Marran) has its next report due 2029-10-05, in 20 day(s); inside the 30-day renewal window and due to be filed

### report_count_wrong__Copperfield_Holdings

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `roll_report_counts_tie` @ `compliance_report:REPORT-2029/good_standing_count`  
  the report states 4 in good standing / 0 not; the summary recomputes 3 / 0

### report_due_date_wrong__Alderpoint_Holdings

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `fil_due_date_recomputes` @ `standing_record_register:RECORDS-2029/records/GS-1001/report_due_date`  
  record GS-1001 states a report due date of '2029-03-08'; the Marran statute re-derives 2029-03-01 for 2029

### report_fee_short__Westmere_Holdings_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 2)

- **FAIL** `fil_report_fee_paid` @ `standing_record_register:RECORDS-2029/records/GS-1001/report_fee_paid_cents`  
  record GS-1001 (Marran) paid 45.00 in report fees; the statute requires 50.00 (short 5.00)
- **FAIL** `roll_standing_recomputes` @ `standing_summary:SUMMARY-2029/entities/ENT-101/good_standing`  
  entity ENT-101 is summarised good_standing=True; recomputing from its records gives good_standing=False

### report_filed_late__Brightwater_Holdings

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 2)

- **FAIL** `fil_report_filed_on_time` @ `standing_record_register:RECORDS-2029/records/GS-1001/report_filed_date`  
  record GS-1001 (Marran) filed its report 2029-03-02; the statutory due date is '2029-03-01' and a report must be filed on-or-before it
- **FAIL** `roll_standing_recomputes` @ `standing_summary:SUMMARY-2029/entities/ENT-101/good_standing`  
  entity ENT-101 is summarised good_standing=True; recomputing from its records gives good_standing=False

### sos_suspended__Copperfield_Holdings

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 2)

- **FAIL** `sts_sos_active` @ `standing_record_register:RECORDS-2029/records/GS-1002/sos_status`  
  record GS-1002 (Kelder) reads SOS status 'SUSPENDED' for an entity the register calls 'active'; the two must reconcile
- **FAIL** `roll_standing_recomputes` @ `standing_summary:SUMMARY-2029/entities/ENT-101/good_standing`  
  entity ENT-101 is summarised good_standing=True; recomputing from its records gives good_standing=False

### standing_flag_wrong__Alderpoint_Holdings

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `roll_standing_recomputes` @ `standing_summary:SUMMARY-2029/entities/ENT-101/good_standing`  
  entity ENT-101 is summarised good_standing=False; recomputing from its records gives good_standing=True

### stray_state_record__Westmere_Holdings_Group

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `rec_state_required` @ `standing_record_register:RECORDS-2029/records/GS-2001/state`  
  record GS-2001 registers entity ENT-101 in Tolvane, which is not in its formation/qualified jurisdiction set

### undeclared_jurisdiction__Brightwater_Holdings

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `ent_jurisdictions_declared` @ `entity_register:ENTITIES-2029/entities/ENT-102/formation_state`  
  entity ENT-102 declares no known formation or qualified jurisdiction; its jurisdiction controls would pass on an empty requirement

### unknown_entity_record__Copperfield_Holdings

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `rec_entity_exists` @ `standing_record_register:RECORDS-2029/records/GS-2002/entity_id`  
  record GS-2002 names entity 'ENT-999', which is not in the entity register

### watchlist_overstated__Alderpoint_Holdings

**Verdict:** REVIEW (PASS 25, FLAG 1, FAIL 0)

- **FLAG** `roll_watchlist_ties` @ `renewal_watchlist:WATCHLIST-2029/entries/ENT-101/Marran`  
  the watchlist lists ENT-101 (Marran) as due for renewal, but it is not inside the lead-time window as of 2029-09-15
