# Section 263A interest-capitalization control report

**Overall verdict:** FAIL

- Capitalization files analyzed: 21
- Controls in registry: 19
- PASS / REVIEW / FAIL: 1 / 1 / 19

All data is fictional. The engine is read-only and never writes to a source
artifact. Every capitalized figure is re-derived from the accumulated production
expenditures and the period rate carried in the file, never asserted.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `prj_unique_keys` | FAIL | 1 |
| 3 | `prj_name_present` | FAIL | 1 |
| 4 | `prj_status_valid` | FAIL | 1 |
| 5 | `prj_tb_complete` | FAIL | 1 |
| 6 | `data_project_coverage` | FAIL | 1 |
| 7 | `data_ape_nonneg` | FAIL | 2 |
| 8 | `data_ape_nondecreasing` | FAIL | 2 |
| 9 | `data_rate_valid` | FAIL | 1 |
| 10 | `cap_rate_consistent` | FAIL | 1 |
| 11 | `cap_rederives` | FAIL | 2 |
| 12 | `cap_no_leakage` | FAIL | 1 |
| 13 | `cap_within_interest` | FAIL | 1 |
| 14 | `cap_annual_total_foots` | FAIL | 1 |
| 15 | `cap_ceased_on_completion` | FLAG | 1 |
| 16 | `cmp_current_ties_schedule` | FAIL | 1 |
| 17 | `cmp_prior_year_ties` | FAIL | 1 |
| 18 | `rpt_total_capitalized_ties` | FAIL | 1 |
| 19 | `rpt_project_count_ties` | FAIL | 1 |

## Capitalization files

### amount_not_integer__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 16, FLAG 0, FAIL 3)

- **FAIL** `data_ape_nonneg` @ `amount:project_data[100/J-4101].accumulated_production_expenditures_cents`  
  AMOUNT_INVALID: project_data[100/J-4101].accumulated_production_expenditures_cents must be integer cents, got 4000000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `data_ape_nondecreasing` @ `amount:project_data[100/J-4101].accumulated_production_expenditures_cents`  
  AMOUNT_INVALID: project_data[100/J-4101].accumulated_production_expenditures_cents must be integer cents, got 4000000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `cap_rederives` @ `amount:project_data[100/J-4101].accumulated_production_expenditures_cents`  
  AMOUNT_INVALID: project_data[100/J-4101].accumulated_production_expenditures_cents must be integer cents, got 4000000000.5 -- amounts are integer cents and are never coerced

### annual_total_miscast__Stonecrest_Communities

**Verdict:** FAIL (PASS 18, FLAG 0, FAIL 1)

- **FAIL** `cap_annual_total_foots` @ `interest_by_year:INTEREST-2029/projects/100/J-4101/annual_interest_cents`  
  project 100/J-4101 states annual interest of 4,100,000.00, but its quarters foot to 4,000,000.00 (off 100,000.00)

### ape_decreases__Ardenne_Field_Group

**Verdict:** FAIL (PASS 18, FLAG 0, FAIL 1)

- **FAIL** `data_ape_nondecreasing` @ `project_data:DATA-2029/projects/100/J-4101/2029-09-30/accumulated_production_expenditures_cents`  
  project 100/J-4101 accumulated expenditures fall from 55,000,000.00 at 2029-06-30 to 40,000,000.00 at 2029-09-30; the accumulation cannot decrease

### bad_project_status__Westmere

**Verdict:** FAIL (PASS 18, FLAG 0, FAIL 1)

- **FAIL** `prj_status_valid` @ `project_status:STATUS-2029/projects/100/J-4101/status`  
  project 100/J-4101 is in status 'suspended', which is not one of ('active', 'complete', 'on_hold')

### blank_project_name__Northmoor_Development_Group

**Verdict:** FAIL (PASS 18, FLAG 0, FAIL 1)

- **FAIL** `prj_name_present` @ `project_status:STATUS-2029/projects/100/J-4101/project_name`  
  project 100/J-4101 carries no project name

### capitalized_exceeds_interest__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 18, FLAG 0, FAIL 1)

- **FAIL** `cap_within_interest` @ `interest_by_year:INTEREST-2029/projects/100/J-4101/2029-03-31/capitalized_cents`  
  project 100/J-4101 at 2029-03-31 capitalizes 600,000.00 against 500,000.00 of interest incurred (excess 100,000.00)

### capitalized_misderived__Stonecrest_Communities

**Verdict:** FAIL (PASS 18, FLAG 0, FAIL 1)

- **FAIL** `cap_rederives` @ `interest_by_year:INTEREST-2029/projects/100/J-4101/2029-12-31/capitalized_cents`  
  project 100/J-4101 capitalizes 1,200,000.00 at 2029-12-31; 90,000,000.00 of expenditures at 1.50% re-derives 1,350,000.00

### capitalizing_after_completion__Ardenne_Field_Group

**Verdict:** REVIEW (PASS 18, FLAG 1, FAIL 0)

- **FLAG** `cap_ceased_on_completion` @ `interest_by_year:INTEREST-2029/projects/100/J-4101/annual_capitalized_cents`  
  project 100/J-4101 is placed in service but still capitalizes 3,645,000.00 this year; capitalization should cease at the in-service date

### clean__Northmoor_Development_Group

**Verdict:** PASS (PASS 19, FLAG 0, FAIL 0)

All controls held.

### comparison_current_off__Westmere

**Verdict:** FAIL (PASS 18, FLAG 0, FAIL 1)

- **FAIL** `cmp_current_ties_schedule` @ `comparison:COMPARISON-2029/projects/100/J-4101/current_year_capitalized_cents`  
  project 100/J-4101 shows 3,655,000.00 current-year capitalized on the comparison; the schedule foots 3,645,000.00

### data_quarter_missing__Northmoor_Development_Group

**Verdict:** FAIL (PASS 18, FLAG 0, FAIL 1)

- **FAIL** `data_project_coverage` @ `project_data:DATA-2029/projects/100/J-4101/quarters`  
  project 100/J-4101 Project Data is missing quarter(s) ['2029-09-30']; its capitalized interest cannot be re-derived

### duplicate_project_key__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 18, FLAG 0, FAIL 1)

- **FAIL** `prj_unique_keys` @ `project_status:STATUS-2029/projects/100/J-4101`  
  project 100/J-4101 appears 2 times; a quarter of interest that names it cannot be attributed to one project

### interest_leaks__Stonecrest_Communities

**Verdict:** FAIL (PASS 18, FLAG 0, FAIL 1)

- **FAIL** `cap_no_leakage` @ `interest_by_year:INTEREST-2029/projects/100/J-4101/2029-06-30`  
  project 100/J-4101 at 2029-06-30 incurs 950,000.00 interest but capitalizes 825,000.00 and deducts 75,000.00 (50,000.00 leaked)

### invalid_rate__Ardenne_Field_Group

**Verdict:** FAIL (PASS 18, FLAG 0, FAIL 1)

- **FAIL** `data_rate_valid` @ `project_data:DATA-2029/projects/100/J-4101/capitalization_rate_bps`  
  project 100/J-4101 carries capitalization rate 15000, which is not a basis-point rate in 0..10000

### missing_artifact__Westmere

**Verdict:** FAIL (PASS 15, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `comparison:-`  
  comparison is missing; the controls that read it cannot run and must not be reported as having passed

### negative_ape__Northmoor_Development_Group

**Verdict:** FAIL (PASS 18, FLAG 0, FAIL 1)

- **FAIL** `data_ape_nonneg` @ `project_data:DATA-2029/projects/100/J-4101/2029-03-31/accumulated_production_expenditures_cents`  
  project 100/J-4101 shows -5,000,000.00 accumulated production expenditures at 2029-03-31; the balance cannot be negative

### prior_year_untied__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 18, FLAG 0, FAIL 1)

- **FAIL** `cmp_prior_year_ties` @ `comparison:COMPARISON-2029/projects/100/J-4101/ending_capitalized_cents`  
  project 100/J-4101 ends at 6,145,000.01 capitalized; 2,500,000.00 prior plus 3,645,000.00 current rolls forward to 6,145,000.00

### project_count_off__Stonecrest_Communities

**Verdict:** FAIL (PASS 18, FLAG 0, FAIL 1)

- **FAIL** `rpt_project_count_ties` @ `interest_by_year:INTEREST-2029/project_count`  
  the schedule states 5 project(s); the roster carries 4

### rate_inconsistent__Ardenne_Field_Group

**Verdict:** FAIL (PASS 18, FLAG 0, FAIL 1)

- **FAIL** `cap_rate_consistent` @ `project_data:DATA-2029/projects/100/J-4101/capitalization_rate_bps`  
  project 100/J-4101 is rolled at 1.20%, but the period rate elsewhere on the schedule is 1.50%; the rate must be applied consistently

### tb_project_missing__Westmere

**Verdict:** FAIL (PASS 18, FLAG 0, FAIL 1)

- **FAIL** `prj_tb_complete` @ `project_status:STATUS-2029/projects/300/J-9001`  
  project 300/J-9001 carries an interest balance on the trial balance but is absent from the schedule; its interest would be deducted in full with none capitalized

### total_capitalized_off__Northmoor_Development_Group

**Verdict:** FAIL (PASS 18, FLAG 0, FAIL 1)

- **FAIL** `rpt_total_capitalized_ties` @ `interest_by_year:INTEREST-2029/total_capitalized_cents`  
  the schedule states 7,050,000.01 total capitalized; the project annuals sum to 7,050,000.00 (off 0.01)
