# G&A expense allocation control report

**Overall verdict:** FAIL

- Allocation files analyzed: 24
- Controls in registry: 22
- PASS / REVIEW / FAIL: 1 / 1 / 22

All data is fictional. The engine is read-only and never writes to a source
artifact; it re-derives the allocation journal entry and compares it, and never
posts, files or pays. Every accounting-date test is made against the period
stamped in the file, never the system clock.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `per_months_consecutive` | FAIL | 1 |
| 3 | `per_tab_continuity` | FAIL | 1 |
| 4 | `rcp_unique_ids` | FAIL | 1 |
| 5 | `rcp_rows_wellformed` | FAIL | 1 |
| 6 | `rcp_holding_not_recipient` | FAIL | 1 |
| 7 | `drv_counts_whole` | FAIL | 1 |
| 8 | `drv_coverage_complete` | FAIL | 1 |
| 9 | `pol_components_sum` | FAIL | 1 |
| 10 | `pol_month_over_month_variance` | FLAG | 2 |
| 11 | `alc_recipient_coverage` | FAIL | 1 |
| 12 | `alc_shares_sum_to_full` | FAIL | 1 |
| 13 | `alc_shares_rederive` | FAIL | 2 |
| 14 | `alc_amounts_tie_pool` | FAIL | 2 |
| 15 | `alc_amounts_rederive` | FAIL | 3 |
| 16 | `je_balanced` | FAIL | 2 |
| 17 | `je_ties_allocation` | FAIL | 1 |
| 18 | `je_consolidation_nets_zero` | FAIL | 1 |
| 19 | `pst_meter_rolls_forward` | FAIL | 2 |
| 20 | `pst_allocations_tie_meter_delta` | FAIL | 1 |
| 21 | `pst_pool_component_ties` | FAIL | 1 |
| 22 | `rpt_rollup_ties` | FAIL | 1 |

## Allocation files

### allocation_over_pool__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `alc_amounts_tie_pool` @ `allocation_schedule:SCHEDULE-2031/allocations/2031-05/allocated_cents`  
  the 2031-05 allocation sums to 294,552.15 against a pool of 289,552.15 (out by 5,000.00); the difference stays in, or is over-relieved from, the holding entity

### allocation_row_missing__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `alc_recipient_coverage` @ `allocation_schedule:SCHEDULE-2031/allocations/2031-02/PRJ-302`  
  recipient PRJ-302 has 0 allocation rows in 2031-02; the month's pool cannot be pushed out across a tab that is missing a recipient or carries one twice

### allocation_swapped__Ardenne_Field_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 2)

- **FAIL** `alc_amounts_rederive` @ `allocation_schedule:SCHEDULE-2031/allocations/2031-01/ENT-201/allocated_cents`  
  recipient ENT-201 is allocated 65,555.76 of the 2031-01 pool; its driver share re-derives 88,813.85 (out by -23,258.09)
- **FAIL** `alc_amounts_rederive` @ `allocation_schedule:SCHEDULE-2031/allocations/2031-01/ENT-202/allocated_cents`  
  recipient ENT-202 is allocated 88,813.85 of the 2031-01 pool; its driver share re-derives 65,555.76 (out by 23,258.09)

### amount_not_integer__Northmoor_Development_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 2)

- **FAIL** `alc_amounts_tie_pool` @ `amount:allocation[2031-01/ENT-203].allocated_cents`  
  AMOUNT_INVALID: allocation[2031-01/ENT-203].allocated_cents must be integer cents, got 5709060.5 -- amounts are integer cents and are never coerced
- **FAIL** `alc_amounts_rederive` @ `amount:allocation[2031-01/ENT-203].allocated_cents`  
  AMOUNT_INVALID: allocation[2031-01/ENT-203].allocated_cents must be integer cents, got 5709060.5 -- amounts are integer cents and are never coerced

### bad_recipient_kind__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `rcp_rows_wellformed` @ `recipient_register:LOOKUP-2031/recipients/PRJ-302/kind`  
  recipient PRJ-302 is typed 'department', which is not one of ('operating_entity', 'project'); the allocation policy has no rule for it

### clean__Northmoor_Development_Group

**Verdict:** PASS (PASS 22, FLAG 0, FAIL 0)

All controls held.

### driver_row_missing__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `drv_coverage_complete` @ `driver_table:DRIVERS-2031/drivers/2031-02/PRJ-301`  
  recipient PRJ-301 has 0 driver rows in 2031-02; its share of that month's pool cannot be derived from exactly one basis

### duplicate_recipient_id__Ardenne_Field_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `rcp_unique_ids` @ `recipient_register:LOOKUP-2031/recipients/ENT-203`  
  recipient id ENT-203 appears 2 times; a driver count that names it cannot be attributed to one recipient

### holding_as_recipient__Northmoor_Development_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `rcp_holding_not_recipient` @ `recipient_register:LOOKUP-2031/recipients/HOLD-1`  
  the holding entity HOLD-1 is listed as a recipient; it cannot allocate its own G&A to itself, and the slice it took would never leave the group's overhead

### journal_off_schedule__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `je_ties_allocation` @ `allocation_journal:JOURNAL-2031/entries/2031-03/lines/ENT-203`  
  the 2031-03 entry charges ENT-203 a net 51,045.97; the allocation re-derives 54,045.97 (out by -3,000.00)

### journal_self_wash__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `je_consolidation_nets_zero` @ `allocation_journal:JOURNAL-2031/entries/2031-04/lines/ENT-202`  
  the 2031-04 entry both charges ENT-202 107,617.95 and relieves it 40,000.00; the pair nets to nothing at that entity while inflating both sides of the entry

### journal_unbalanced__Ardenne_Field_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 2)

- **FAIL** `je_balanced` @ `allocation_journal:JOURNAL-2031/entries/2031-02/lines`  
  the 2031-02 allocation entry debits 282,812.75 against credits of 287,812.75 (out by -5,000.00); it does not balance and cannot be posted as written
- **FAIL** `je_balanced` @ `allocation_journal:JOURNAL-2031/entries/2031-05/lines`  
  the 2031-05 allocation entry debits 289,552.15 against credits of 284,552.15 (out by 5,000.00); it does not balance and cannot be posted as written

### meter_runs_backward__Northmoor_Development_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 2)

- **FAIL** `pst_meter_rolls_forward` @ `postage_log:POSTAGE-2031/meters/2031-03/end_meter_cents`  
  the 2031-03 meter opens at 13,497.25 and closes at 13,200.00; a cumulative meter cannot run backwards, so the period's spend cannot be taken as the difference
- **FAIL** `pst_meter_rolls_forward` @ `postage_log:POSTAGE-2031/meters/2031-04/begin_meter_cents`  
  the 2031-04 meter opens at 13,965.45 while 2031-03 closed at 13,200.00; the roll-forward is broken and 765.45 of metered spend is unaccounted for

### missing_artifact__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `allocation_report:-`  
  allocation_report is missing; the controls that read it cannot run and must not be reported as having passed

### missing_period_tab__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `per_tab_continuity` @ `period_calendar:CALENDAR-2031/periods/2031-05`  
  period 2031-05 carries 0 postage meter reading rows; the tab is complete only with exactly one

### negative_driver_count__Ardenne_Field_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `drv_counts_whole` @ `driver_table:DRIVERS-2031/drivers/2031-03/ENT-204/driver_count`  
  recipient ENT-204 carries a driver count of -19 in 2031-03; a negative basis would allocate cost away from a recipient rather than to it

### period_gap__Northmoor_Development_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `per_months_consecutive` @ `period_calendar:CALENDAR-2031/periods/2031-07`  
  the tab after 2031-05 is 2031-07; the calendar skips 2031-06, so that month's G&A was never allocated

### pool_components_drift__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `pol_components_sum` @ `cost_pool_ledger:POOL-2031/pools/2031-04/pool_total_cents`  
  the 2031-04 pool states a total of 286,881.40; its components add to 287,181.40 (out by -300.00), so the figure being allocated is not the figure being reviewed

### pool_step_change__Stonecrest_Communities

**Verdict:** REVIEW (PASS 21, FLAG 2, FAIL 0)

- **FLAG** `pol_month_over_month_variance` @ `cost_pool_ledger:POOL-2031/pools/2031-04/pool_total_cents`  
  the pool moved from 286,868.20 in 2031-03 to 326,881.40 in 2031-04, a step of 13.94% against a 5.00% band; a recurring pool that steps this far has changed in substance
- **FLAG** `pol_month_over_month_variance` @ `cost_pool_ledger:POOL-2031/pools/2031-05/pool_total_cents`  
  the pool moved from 326,881.40 in 2031-04 to 289,552.15 in 2031-05, a step of 11.41% against a 5.00% band; a recurring pool that steps this far has changed in substance

### postage_code_overstated__Ardenne_Field_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `pst_allocations_tie_meter_delta` @ `postage_log:POSTAGE-2031/meters/2031-02/allocations`  
  the 2031-02 postage split sums to 527.75 against a meter delta of 512.75 (out by 15.00); the physical counter and the workbook disagree

### postage_component_drift__Northmoor_Development_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `pst_pool_component_ties` @ `cost_pool_ledger:POOL-2031/pools/2031-06/postage_cents`  
  the 2031-06 pool carries postage of 719.80; the meter read 519.80 of spend (out by 200.00), so the pool being allocated is not the postage that was bought

### report_total_wrong__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `rpt_rollup_ties` @ `allocation_report:ROLLUP-2031/pool_total_cents`  
  the rollup states pool_total_cents of 1,721,768.80; the tabs beneath it recompute 1,720,768.80

### share_drift__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 2)

- **FAIL** `alc_shares_rederive` @ `allocation_schedule:SCHEDULE-2031/allocations/2031-01/ENT-201/share_bps`  
  recipient ENT-201 is given 31.83% of the 2031-01 pool; its driver count re-derives 31.58% (out by 0.25%)
- **FAIL** `alc_shares_rederive` @ `allocation_schedule:SCHEDULE-2031/allocations/2031-01/ENT-202/share_bps`  
  recipient ENT-202 is given 23.06% of the 2031-01 pool; its driver count re-derives 23.31% (out by -0.25%)

### shares_overstated__Ardenne_Field_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `alc_shares_sum_to_full` @ `allocation_schedule:SCHEDULE-2031/allocations/2031-01/share_bps`  
  the 2031-01 shares sum to 100.25%, not 100.00% (out by 0.25%); the month's pool is not fully pushed out of the holding entity
