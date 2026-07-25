# Contingency rollforward and adequacy control report

**Overall verdict:** FAIL

- Period files analyzed: 24
- Controls in registry: 22
- PASS / REVIEW / FAIL: 1 / 2 / 21

All data is fictional. The engine is read-only and never writes to a source
artifact. Every draw is tested against the reporting period carried in the file,
never the system clock.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `prj_unique_ids` | FAIL | 1 |
| 3 | `prj_status_valid` | FAIL | 1 |
| 4 | `prj_budget_defined` | FAIL | 1 |
| 5 | `alc_required_fields` | FAIL | 1 |
| 6 | `alc_unique_ids` | FAIL | 1 |
| 7 | `alc_project_exists` | FAIL | 1 |
| 8 | `alc_bucket_valid` | FAIL | 1 |
| 9 | `alc_within_period` | FAIL | 1 |
| 10 | `alc_amount_positive` | FAIL | 1 |
| 11 | `ctg_block_complete` | FAIL | 1 |
| 12 | `ctg_current_rolls_forward` | FAIL | 2 |
| 13 | `ctg_to_date_rolls_forward` | FAIL | 1 |
| 14 | `ctg_allocated_ties_line_items` | FAIL | 1 |
| 15 | `ctg_budget_reconciles` | FAIL | 2 |
| 16 | `ctg_no_overdraw` | FAIL | 1 |
| 17 | `adq_projection_nonnegative` | FAIL | 1 |
| 18 | `adq_flag_recomputes` | FAIL | 2 |
| 19 | `adq_headroom_watch` | FLAG | 1 |
| 20 | `rpt_portfolio_foots` | FAIL | 2 |
| 21 | `rpt_inadequate_count_ties` | FAIL | 1 |
| 22 | `rpt_watchlist_ties` | FLAG | 1 |

## Period files

### adequacy_flag_overridden__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `adq_flag_recomputes` @ `contingency_block:BLOCK-2031Q3/buckets/PRJ-401/construction/adequacy`  
  PRJ-401/construction is assessed 'inadequate'; recomputing from the row gives 'adequate' -- 3,105,000.00 remaining against 1,900,000.00 projected (1,205,000.00 of headroom)

### allocated_prior_restated__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `ctg_to_date_rolls_forward` @ `contingency_block:BLOCK-2031Q3/buckets/PRJ-403/construction/allocated_to_date_cents`  
  PRJ-403/construction states 1,565,000.00 allocated to date; prior periods 1,075,000.00 plus this period 465,000.00 is 1,540,000.00 (off by 25,000.00)

### allocation_bad_bucket__Ardenne_Field_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `alc_bucket_valid` @ `allocation_register:DRAWS-2031Q3/allocations/ALC-5091/bucket`  
  allocation ALC-5091 is filed to bucket 'soft_cost', which is not one of ('construction', 'project'); it reduces no stated balance

### allocation_missing_field__Northmoor_Development_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `alc_required_fields` @ `allocation_register:DRAWS-2031Q3/allocations/ALC-5002`  
  allocation ALC-5002 is missing description

### allocation_not_positive__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `alc_amount_positive` @ `allocation_register:DRAWS-2031Q3/allocations/ALC-5092/amount_cents`  
  allocation ALC-5092 draws 0.00 against contingency; a draw is a release out of the bucket and must be a positive amount

### allocation_outside_period__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `alc_within_period` @ `allocation_register:DRAWS-2031Q3/allocations/ALC-5003/allocation_date`  
  allocation ALC-5003 is dated 2031-06-15, outside the reporting period 2031-07-01 to 2031-09-30; it cannot be an allocation of this period

### allocation_unknown_project__Ardenne_Field_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `alc_project_exists` @ `allocation_register:DRAWS-2031Q3/allocations/ALC-5090/project_id`  
  allocation ALC-5090 draws on project 'PRJ-999', which is not in the project register

### amount_not_integer__Northmoor_Development_Group

**Verdict:** FAIL (PASS 18, FLAG 0, FAIL 4)

- **FAIL** `ctg_current_rolls_forward` @ `amount:block[PRJ-401/construction].current_balance_cents`  
  AMOUNT_INVALID: block[PRJ-401/construction].current_balance_cents must be integer cents, got 310500000.5 -- amounts are integer cents and are never coerced
- **FAIL** `ctg_budget_reconciles` @ `amount:block[PRJ-401/construction].current_balance_cents`  
  AMOUNT_INVALID: block[PRJ-401/construction].current_balance_cents must be integer cents, got 310500000.5 -- amounts are integer cents and are never coerced
- **FAIL** `adq_flag_recomputes` @ `amount:block[PRJ-401/construction].current_balance_cents`  
  AMOUNT_INVALID: block[PRJ-401/construction].current_balance_cents must be integer cents, got 310500000.5 -- amounts are integer cents and are never coerced
- **FAIL** `rpt_portfolio_foots` @ `amount:block[PRJ-401/construction].current_balance_cents`  
  AMOUNT_INVALID: block[PRJ-401/construction].current_balance_cents must be integer cents, got 310500000.5 -- amounts are integer cents and are never coerced

### block_row_missing__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `ctg_block_complete` @ `contingency_block:BLOCK-2031Q3/buckets/PRJ-402/project`  
  active project PRJ-402 restates no project contingency bucket this period; the balance is carried forward unreported

### budget_line_missing__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `prj_budget_defined` @ `budget_register:BUDGET-2031Q3/contingency_lines/PRJ-402/project`  
  the budget carries no project contingency line for active project PRJ-402; the bucket has nothing to reconcile to

### budget_line_restated__Ardenne_Field_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `ctg_budget_reconciles` @ `contingency_block:BLOCK-2031Q3/buckets/PRJ-402/construction/allocated_to_date_cents`  
  PRJ-402/construction carries 2,140,000.00 remaining plus 660,000.00 allocated to date, which is 2,800,000.00; the budget funds this bucket at 2,875,000.00 (off by -75,000.00)

### clean__Northmoor_Development_Group

**Verdict:** PASS (PASS 22, FLAG 0, FAIL 0)

All controls held.

### draw_exceeds_balance__Northmoor_Development_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `ctg_no_overdraw` @ `allocation_register:DRAWS-2031Q3/allocations/ALC-5005/amount_cents`  
  allocation ALC-5005 draws 900,000.00 against PRJ-402/project when only 780,000.00 remained; the draw exceeds the balance it is drawn against by 120,000.00

### duplicate_allocation_id__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `alc_unique_ids` @ `allocation_register:DRAWS-2031Q3/allocations/ALC-5006`  
  allocation id ALC-5006 appears 2 times; the register can no longer prove these are distinct draws

### duplicate_project_id__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `prj_unique_ids` @ `project_register:PROJECTS-2031Q3/projects/PRJ-401`  
  project id PRJ-401 appears 2 times; a draw that names it cannot be attributed to one project

### headroom_watch__Ardenne_Field_Group

**Verdict:** REVIEW (PASS 21, FLAG 1, FAIL 0)

- **FLAG** `adq_headroom_watch` @ `contingency_block:BLOCK-2031Q3/buckets/PRJ-402/project/projected_use_cents`  
  PRJ-402/project still covers its projection, with 45,000.00 of headroom on 745,000.00 remaining; projected use has reached the 80.00% watch band and the bucket is one revision from inadequate

### inadequate_count_wrong__Northmoor_Development_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `rpt_inadequate_count_ties` @ `portfolio_rollup:ROLLUP-2031Q3/inadequate_count`  
  the rollup states 1 inadequate bucket(s); the contingency block assesses 0 as inadequate

### line_item_dropped__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `ctg_allocated_ties_line_items` @ `contingency_block:BLOCK-2031Q3/buckets/PRJ-401/construction/allocated_period_cents`  
  PRJ-401/construction states 275,000.00 allocated this period; the 1 draw(s) in the register sum to 180,000.00 (off by 95,000.00)

### missing_artifact__Stonecrest_Communities

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `portfolio_rollup:-`  
  portfolio_rollup is missing; the controls that read it cannot run and must not be reported as having passed

### portfolio_total_wrong__Ardenne_Field_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `rpt_portfolio_foots` @ `portfolio_rollup:ROLLUP-2031Q3/total_current_balance_cents`  
  the rollup states 13,715,000.00 of current contingency; the 6 bucket(s) in the block foot to 13,615,000.00 (off by 100,000.00)

### prior_balance_restated__Northmoor_Development_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `ctg_current_rolls_forward` @ `contingency_block:BLOCK-2031Q3/buckets/PRJ-401/construction/current_balance_cents`  
  PRJ-401/construction states a current balance of 3,105,000.00; prior 3,430,000.00 less allocated 275,000.00 is 3,155,000.00 (off by -50,000.00)

### projection_negative__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `adq_projection_nonnegative` @ `contingency_block:BLOCK-2031Q3/buckets/PRJ-403/project/projected_use_cents`  
  PRJ-403/project projects -50,000.00 of potential use; a negative projection makes the adequacy test pass on any balance at all

### unknown_project_status__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `prj_status_valid` @ `project_register:PROJECTS-2031Q3/projects/PRJ-404/status`  
  project PRJ-404 is marked 'mothballed', which is not one of ('active', 'suspended', 'closed'); whether it owes a contingency block cannot be determined

### watchlist_overstated__Ardenne_Field_Group

**Verdict:** REVIEW (PASS 21, FLAG 1, FAIL 0)

- **FLAG** `rpt_watchlist_ties` @ `exposure_watchlist:WATCH-2031Q3/entries/PRJ-403/construction`  
  the watchlist carries PRJ-403/construction as thin on headroom, but the block does not put it inside the watch band
