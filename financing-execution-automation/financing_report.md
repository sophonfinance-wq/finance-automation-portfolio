# Financing execution & schedule-variance control report

**Overall verdict:** FAIL

- Financing reports analyzed: 23
- Controls in registry: 21
- PASS / REVIEW / FAIL: 1 / 1 / 21

All data is fictional. The engine is read-only and never writes to a source
artifact. Every overdue and period-end test is made against the `report_date`
carried in the file, never the system clock.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `mem_workstream_ids_unique` | FAIL | 1 |
| 3 | `mem_workstream_type_valid` | FAIL | 1 |
| 4 | `mem_workstream_status_valid` | FAIL | 1 |
| 5 | `mem_milestone_workstream_exists` | FAIL | 1 |
| 6 | `mem_playbook_defined` | FAIL | 2 |
| 7 | `mem_playbook_complete` | FAIL | 1 |
| 8 | `mem_portfolio_present` | FAIL | 1 |
| 9 | `mem_workstream_in_tracker` | FAIL | 1 |
| 10 | `var_dates_wellformed` | FAIL | 1 |
| 11 | `var_recomputes` | FAIL | 1 |
| 12 | `var_gantt_month_recomputes` | FAIL | 1 |
| 13 | `roll_prior_ties_current` | FAIL | 1 |
| 14 | `base_original_immutable` | FAIL | 1 |
| 15 | `date_report_is_period_end` | FAIL | 1 |
| 16 | `date_overdue_flag` | FLAG | 1 |
| 17 | `ord_sequence_unique` | FAIL | 1 |
| 18 | `ord_current_nondecreasing` | FAIL | 1 |
| 19 | `rpt_active_count_ties` | FAIL | 1 |
| 20 | `rpt_overdue_count_ties` | FAIL | 1 |
| 21 | `rpt_financing_total_ties` | FAIL | 2 |

## Financing reports

### active_count_wrong__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `rpt_active_count_ties` @ `financing_report:REPORT-2029-06/active_count`  
  the report states 5 active financing(s); the register recomputes 4

### amount_not_integer__Stonecrest_Communities

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `rpt_financing_total_ties` @ `amount:workstream[WS-01].financing_amount_cents`  
  AMOUNT_INVALID: workstream[WS-01].financing_amount_cents must be integer cents, got 4000000000.5 -- amounts are integer cents and are never coerced

### bad_financing_type__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `mem_workstream_type_valid` @ `workstream_register:WORKSTREAMS-2029-06/workstreams/WS-04/financing_type`  
  workstream WS-04 is typed 'mezzanine', which is not one of ('debt', 'equity', 'extension'); its playbook cannot be looked up

### bad_milestone_date__Westmere_Capital

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `var_dates_wellformed` @ `milestone_schedule:SCHEDULE-2029-06/milestones/WS-02-M1`  
  milestone WS-02-M1 has unreadable current_date; its variance and roll-forward cannot be re-derived

### bad_status__Northmoor_Development_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `mem_workstream_status_valid` @ `workstream_register:WORKSTREAMS-2029-06/workstreams/WS-05/status`  
  workstream WS-05 carries status 'WOUND_DOWN', which is not one of ('ACTIVE', 'CLOSED'); its overdue gate cannot be applied

### broken_rollforward__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `roll_prior_ties_current` @ `milestone_schedule:SCHEDULE-2029-06/milestones/WS-04-M2/prior_date`  
  milestone WS-04-M2 carries Prior 2029-08-03, but last month's Current was 2029-08-08; the roll-forward is broken

### clean__Northmoor_Development_Group

**Verdict:** PASS (PASS 21, FLAG 0, FAIL 0)

All controls held.

### duplicate_sequence__Stonecrest_Communities

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `ord_sequence_unique` @ `milestone_schedule:SCHEDULE-2029-06/milestones/WS-03/sequence/2`  
  workstream WS-03 has 2 milestones at sequence 2; their order is ambiguous

### duplicate_workstream_id__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `mem_workstream_ids_unique` @ `workstream_register:WORKSTREAMS-2029-06/workstreams/WS-01`  
  workstream id WS-01 appears 2 times; a milestone that names it cannot be attributed to one financing

### financing_total_wrong__Westmere_Capital

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `rpt_financing_total_ties` @ `financing_report:REPORT-2029-06/total_financing_cents`  
  the report states a financing total of 161,000,000.00; the active workstreams sum to 160,000,000.00 (off by 1,000,000.00)

### gantt_month_wrong__Northmoor_Development_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `var_gantt_month_recomputes` @ `gantt_summary:GANTT-2029-06/bars/WS-01/gantt_month`  
  Gantt bar WS-01 is placed in month 10; its target closing 2029-09-15 re-derives month 9

### missing_artifact__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 17, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `financing_report:-`  
  financing_report is missing; the controls that read it cannot run and must not be reported as having passed

### missing_playbook_milestone__Stonecrest_Communities

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `mem_playbook_complete` @ `milestone_schedule:SCHEDULE-2029-06/milestones/WS-01/Best & Final with Lenders`  
  active workstream WS-01 (debt) is missing playbook milestone 'Best & Final with Lenders'; its standard milestone set is incomplete

### missing_project__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `mem_portfolio_present` @ `master_tracker:TRACKER-2029-06/projects/WS-06`  
  active portfolio project 'Saltaire Wharf' (WS-06) has no workstream in the report; the financing is uncovered

### mutated_baseline__Westmere_Capital

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `base_original_immutable` @ `milestone_schedule:SCHEDULE-2029-06/milestones/WS-01-M1/original_date`  
  milestone WS-01-M1 carries Original 2029-06-10, but the frozen baseline was 2029-05-31; the baseline has been mutated

### orphan_milestone__Northmoor_Development_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `mem_milestone_workstream_exists` @ `milestone_schedule:SCHEDULE-2029-06/milestones/WS-999-M1/workstream_id`  
  milestone WS-999-M1 names workstream 'WS-999', which is not in the register

### out_of_order_milestone__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `ord_current_nondecreasing` @ `milestone_schedule:SCHEDULE-2029-06/milestones/WS-04-M4/current_date`  
  workstream WS-04 milestone WS-04-M4 (seq 4) is dated 2029-08-28, before its predecessor seq 3 at 2029-09-17; the schedule runs backwards

### overdue_count_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `rpt_overdue_count_ties` @ `financing_report:REPORT-2029-06/overdue_count`  
  the report states 1 overdue milestone(s); the schedule recomputes 0 against 2029-06-30

### overdue_flag_wrong__Ardenne_Field_Partners

**Verdict:** REVIEW (PASS 20, FLAG 1, FAIL 0)

- **FLAG** `date_overdue_flag` @ `milestone_schedule:SCHEDULE-2029-06/milestones/WS-02-M2/overdue`  
  milestone WS-02-M2 is flagged overdue=True; the date gate against 2029-06-30 re-derives overdue=False

### playbook_undefined__Westmere_Capital

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 2)

- **FAIL** `mem_playbook_defined` @ `playbook_catalog:PLAYBOOKS-2029/playbooks/debt`  
  the playbook catalog has no entry for 'debt', which workstream WS-01 is typed as; its milestone set cannot be enforced
- **FAIL** `mem_playbook_defined` @ `playbook_catalog:PLAYBOOKS-2029/playbooks/debt`  
  the playbook catalog has no entry for 'debt', which workstream WS-04 is typed as; its milestone set cannot be enforced

### untracked_workstream__Northmoor_Development_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `mem_workstream_in_tracker` @ `workstream_register:WORKSTREAMS-2029-06/workstreams/WS-07`  
  workstream WS-07 is not on the master tracker; it is being reported outside the portfolio of record

### variance_wrong__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `var_recomputes` @ `milestone_schedule:SCHEDULE-2029-06/milestones/WS-03-M2/variance_days`  
  milestone WS-03-M2 states variance 26 day(s); its Prior->Current dates re-derive 25

### wrong_report_date__Stonecrest_Communities

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `date_report_is_period_end` @ `-`  
  report_date 2029-06-29 is not the period-end for 2029-06; the last day of the period is 2029-06-30
