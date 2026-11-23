# Filing-obligation calendar control report

**Overall verdict:** FAIL

- Calendar files analyzed: 24
- Controls in registry: 22
- PASS / REVIEW / FAIL: 1 / 3 / 20

All data is fictional. The engine is read-only and never writes to a source
artifact. Every due-date and overdue test is made against the `as_of` date carried
in the file, never the system clock.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `due_year_end_valid` | FAIL | 1 |
| 3 | `due_table_defined` | FAIL | 1 |
| 4 | `due_original_matches` | FAIL | 1 |
| 5 | `due_extended_matches` | FAIL | 1 |
| 6 | `ext_flag_valid` | FAIL | 1 |
| 7 | `ext_applicable_overdue` | FAIL | 1 |
| 8 | `ext_filed_on_time` | FAIL | 1 |
| 9 | `ext_due_soon` | FLAG | 1 |
| 10 | `pay_fixed_amount` | FAIL | 2 |
| 11 | `evd_filed_has_evidence` | FAIL | 1 |
| 12 | `evd_extension_evidence` | FAIL | 1 |
| 13 | `evd_no_orphan_evidence` | FAIL | 1 |
| 14 | `ros_entity_has_row` | FAIL | 1 |
| 15 | `ros_row_entity_known` | FAIL | 1 |
| 16 | `ros_unique_obligation_ids` | FAIL | 1 |
| 17 | `wfl_goal_monotonic` | FAIL | 1 |
| 18 | `wfl_actual_slippage` | FLAG | 1 |
| 19 | `cnt_final_not_recurring` | FAIL | 1 |
| 20 | `rpt_status_recomputes` | FAIL | 1 |
| 21 | `rpt_counts_tie` | FAIL | 1 |
| 22 | `rpt_watchlist_ties` | FLAG | 1 |

## Calendar files

### amount_not_integer__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `pay_fixed_amount` @ `amount:obligation[OB-1003].amount_required_cents`  
  AMOUNT_INVALID: obligation[OB-1003].amount_required_cents must be integer cents, got 80000.5 -- amounts are integer cents and are never coerced

### bad_year_end__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `due_year_end_valid` @ `obligation_register:REGISTER-2028/obligations/OB-1004/year_end`  
  obligation OB-1004 carries year-end '2028-13-40', which is not a readable date; its statutory due dates cannot be looked up

### clean__Northmoor_Development_Group

**Verdict:** PASS (PASS 22, FLAG 0, FAIL 0)

All controls held.

### count_wrong__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `rpt_counts_tie` @ `status_summary:SUMMARY-2028/overdue_count`  
  the summary states 1 overdue / 6 filed; the register recomputes 0 / 6

### duplicate_obligation_id__Northmoor_Development_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `ros_unique_obligation_ids` @ `obligation_register:REGISTER-2028/obligations/OB-1009`  
  obligation id OB-1009 appears 2 times; a voucher or status that names it cannot be attributed to one obligation

### entity_missing_obligation__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `ros_entity_has_row` @ `entity_roster:ROSTER-2028/entities/ENT-106`  
  active entity ENT-106 carries no obligation row; its filings are untracked

### extension_date_without_flag__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `ext_flag_valid` @ `obligation_register:REGISTER-2028/obligations/OB-1004/extension_filed`  
  obligation OB-1004 carries an extended due date but is not marked extension-filed; the deferral has no basis

### filed_after_due__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `ext_filed_on_time` @ `obligation_register:REGISTER-2028/obligations/OB-1004/return_filed`  
  obligation OB-1004 was filed '2028-10-01', after its applicable deadline 2028-09-15; the filing is late

### final_entity_recurring__Northmoor_Development_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `cnt_final_not_recurring` @ `obligation_register:REGISTER-2028/obligations/ENT-101`  
  entity ENT-101 was marked FINAL in the prior fiscal year but carries live obligations this year: OB-1001, OB-1002, OB-1003

### form_not_in_table__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `due_table_defined` @ `due_dates_table:DUEDATES-2028/rules/ZZZ-999/06-30`  
  the due-dates table has no row for form 'ZZZ-999' at year-end 06-30, which obligation OB-1006 requires; its due date cannot be re-derived

### goal_out_of_order__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `wfl_goal_monotonic` @ `obligation_register:REGISTER-2028/obligations/OB-1001/review_goal`  
  obligation OB-1001 workflow goals are out of order: prep 2028-08-20, review 2028-08-15, sent 2028-09-01, due 2029-03-15

### missing_artifact__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `status_summary:-`  
  status_summary is missing; the controls that read it cannot run and must not be reported as having passed

### missing_extension_evidence__Northmoor_Development_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `evd_extension_evidence` @ `evidence_index:EVIDENCE-2028/evidence/OB-1002`  
  obligation OB-1002 is marked extension-filed but no extension acceptance is on file for it

### missing_filed_evidence__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `evd_filed_has_evidence` @ `evidence_index:EVIDENCE-2028/evidence/OB-1003`  
  obligation OB-1003 is marked filed but no filed-return or payment voucher is on file for it

### obligation_due_soon__Stonecrest_Communities

**Verdict:** REVIEW (PASS 21, FLAG 1, FAIL 0)

- **FLAG** `ext_due_soon` @ `obligation_register:REGISTER-2028/obligations/OB-1012/original_due`  
  obligation OB-1012 falls due 2028-12-15, in 14 day(s); inside the 30-day window and due to be chased

### orphan_evidence__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `evd_no_orphan_evidence` @ `evidence_index:EVIDENCE-2028/evidence/EV-99/obligation_id`  
  evidence EV-99 points at obligation 'OB-9999', which is not in the register; it is an orphan with no row to claim it

### status_wrong__Northmoor_Development_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `rpt_status_recomputes` @ `status_summary:SUMMARY-2028/obligations/OB-1001/status`  
  obligation OB-1001 is summarised status='filed'; recomputing from its register dates gives status='open'

### unfiled_overdue__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `ext_applicable_overdue` @ `obligation_register:REGISTER-2028/obligations/OB-1004/return_filed`  
  obligation OB-1004 is unfiled and its applicable deadline 2028-09-15 is on or before the review date 2028-12-01; the obligation is overdue

### unknown_entity__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `ros_row_entity_known` @ `obligation_register:REGISTER-2028/obligations/OB-2001/entity_id`  
  obligation OB-2001 names entity 'ENT-777', which is not in the roster

### watchlist_overstated__Ardenne_Field_Partners

**Verdict:** REVIEW (PASS 21, FLAG 1, FAIL 0)

- **FLAG** `rpt_watchlist_ties` @ `due_watchlist:WATCHLIST-2028/entries/OB-1001`  
  the watchlist lists obligation OB-1001 as due soon, but it is not inside the lead-time window as of 2028-12-01

### workflow_slippage__Northmoor_Development_Group

**Verdict:** REVIEW (PASS 21, FLAG 1, FAIL 0)

- **FLAG** `wfl_actual_slippage` @ `obligation_register:REGISTER-2028/obligations/OB-1002/review_actual`  
  obligation OB-1002 review completed 2028-09-05, after its goal 2028-08-15; the schedule is slipping

### wrong_extended_due__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `due_extended_matches` @ `obligation_register:REGISTER-2028/obligations/OB-1001/extended_due`  
  obligation OB-1001 stores extended due '2029-04-15'; re-deriving the original plus the statutory offset gives 2029-03-15

### wrong_fixed_amount__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `pay_fixed_amount` @ `obligation_register:REGISTER-2028/obligations/OB-1003/amount_required_cents`  
  obligation OB-1003 states amount 799.00; the statutory fixed amount for form MAR-3522 is 800.00

### wrong_original_due__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `due_original_matches` @ `obligation_register:REGISTER-2028/obligations/OB-1004/original_due`  
  obligation OB-1004 stores original due '2028-09-16'; re-deriving from the table gives 2028-09-15
