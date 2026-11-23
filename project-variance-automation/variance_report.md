# Project variance and business-plan compare control report

**Overall verdict:** FAIL

- Project reports analyzed: 24
- Controls in registry: 22
- PASS / REVIEW / FAIL: 1 / 2 / 21

All data is fictional. The engine is read-only and never writes to a source
artifact. Every milestone is tested against the reporting period carried in
the file, never the system clock.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `prj_unique_ids` | FAIL | 1 |
| 3 | `prj_type_valid` | FAIL | 1 |
| 4 | `prj_comparatives_present` | FAIL | 1 |
| 5 | `bud_line_required_fields` | FAIL | 1 |
| 6 | `bud_category_valid` | FAIL | 1 |
| 7 | `bud_project_exists` | FAIL | 1 |
| 8 | `bud_cost_to_complete_foots` | FAIL | 2 |
| 9 | `eco_net_revenue_foots` | FAIL | 1 |
| 10 | `eco_expense_foots_budget` | FAIL | 2 |
| 11 | `eco_profit_foots` | FAIL | 1 |
| 12 | `eco_margin_on_cost_recomputes` | FAIL | 1 |
| 13 | `var_comparative_columns_foot` | FAIL | 1 |
| 14 | `var_prior_column_ties` | FAIL | 1 |
| 15 | `var_plan_column_ties` | FAIL | 2 |
| 16 | `var_plan_version_frozen` | FAIL | 1 |
| 17 | `mst_required_fields` | FAIL | 1 |
| 18 | `mst_variance_sign_convention` | FAIL | 1 |
| 19 | `mst_baseline_variance_foots` | FAIL | 1 |
| 20 | `mst_slippage_lead_time` | FLAG | 1 |
| 21 | `rpt_rollup_foots` | FAIL | 1 |
| 22 | `rpt_slippage_watchlist_ties` | FLAG | 1 |

## Project reports

### amount_not_integer__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 2)

- **FAIL** `bud_cost_to_complete_foots` @ `amount:cost_line[CL-3012].total_budget_cents`  
  AMOUNT_INVALID: cost_line[CL-3012].total_budget_cents must be integer cents, got 6200000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `eco_expense_foots_budget` @ `amount:cost_line[CL-3012].total_budget_cents`  
  AMOUNT_INVALID: cost_line[CL-3012].total_budget_cents must be integer cents, got 6200000000.5 -- amounts are integer cents and are never coerced

### bad_cost_category__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `bud_category_valid` @ `budget_variance:BUDGET-2029Q3/cost_lines/CL-3022/cost_category`  
  cost line CL-3022 sits in category 'marketing_reserve', which is not one of ('land', 'hard_cost', 'soft_cost', 'financing_cost', 'contingency')

### bad_project_type__Ardenne_Field_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `prj_type_valid` @ `project_register:PROJECTS-2029Q3/projects/PRJ-303/project_type`  
  project PRJ-303 is typed 'industrial_flex', which is not one of ('for_sale_residential', 'rental_residential', 'mixed_use', 'land_development'); the reporting convention does not describe it

### baseline_variance_wrong__Westmere

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `mst_baseline_variance_foots` @ `milestone_schedule:SCHEDULE-2029Q3/milestones/MS-3033/variance_baseline_days`  
  milestone MS-3033 states a baseline variance of +15 day(s); baseline date less current date is +5 day(s)

### clean__Northmoor_Development_Group

**Verdict:** PASS (PASS 22, FLAG 0, FAIL 0)

All controls held.

### cost_to_complete_wrong__Northmoor_Development_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `bud_cost_to_complete_foots` @ `budget_variance:BUDGET-2029Q3/cost_lines/CL-3032/cost_to_complete_cents`  
  cost line CL-3032 states cost to complete 22,250,000.00; total budget less cost to date is 22,000,000.00 (out by 250,000.00)

### duplicate_project_id__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `prj_unique_ids` @ `project_register:PROJECTS-2029Q3/projects/PRJ-301`  
  project id PRJ-301 appears 2 times in the register; a cost line or milestone that names it cannot be attributed to one project

### expense_off_budget__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `eco_expense_foots_budget` @ `current_period_economics:CURRENT-2029Q3/projects/PRJ-304/total_project_expense_cents`  
  project PRJ-304 states total project expense 32,000,000.00; its 3 budget lines total 32,500,000.00 (out by -500,000.00)

### line_missing_field__Ardenne_Field_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `bud_line_required_fields` @ `budget_variance:BUDGET-2029Q3/cost_lines/CL-3013`  
  cost line CL-3013 is missing cost_category; the budget tab cannot place it on a project

### margin_overstated__Westmere

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `eco_margin_on_cost_recomputes` @ `current_period_economics:CURRENT-2029Q3/projects/PRJ-301/margin_on_cost_bps`  
  project PRJ-301 states margin on cost 26.00%; profit over total project expense recomputes 25.00%

### milestone_sign_flipped__Northmoor_Development_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `mst_variance_sign_convention` @ `milestone_schedule:SCHEDULE-2029Q3/milestones/MS-3012/variance_prior_days`  
  milestone MS-3012 states a prior variance of -3 day(s); prior date less current date is +3 day(s) under the convention that + is ahead

### milestone_slipped__Halbrook_Residential_Partners

**Verdict:** REVIEW (PASS 21, FLAG 1, FAIL 0)

- **FLAG** `mst_slippage_lead_time` @ `milestone_schedule:SCHEDULE-2029Q3/milestones/MS-3043/current_date`  
  milestone MS-3043 on project PRJ-304 now dates 2031-03-06 against a frozen baseline of 2031-02-28, 6 day(s) behind and past the 5-day tolerance

### milestone_unnamed__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `mst_required_fields` @ `milestone_schedule:SCHEDULE-2029Q3/milestones/MS-3022/milestone_name`  
  milestone MS-3022 is named 'site_mobilization', which the frozen baseline schedule does not define

### missing_artifact__Ardenne_Field_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `report_rollup:-`  
  report_rollup is missing; the controls that read it cannot run and must not be reported as having passed

### net_revenue_off__Westmere

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `eco_net_revenue_foots` @ `current_period_economics:CURRENT-2029Q3/projects/PRJ-302/net_project_revenue_cents`  
  project PRJ-302 states net project revenue 100,000,000.00; gross revenue less deductions is 99,750,000.00 (out by 250,000.00)

### orphan_cost_line__Northmoor_Development_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `bud_project_exists` @ `budget_variance:BUDGET-2029Q3/cost_lines/CL-3099/project_id`  
  cost line CL-3099 names project 'PRJ-999', which is not in the project register

### plan_column_broken__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `var_comparative_columns_foot` @ `business_plan_baseline:PLAN-2028R2/projects/PRJ-303/project_profit_cents`  
  the business plan column for project PRJ-303 states profit 13,900,000.00; its own net revenue less expense is 13,500,000.00

### plan_variance_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 2)

- **FAIL** `var_plan_column_ties` @ `variance_summary:VARIANCE-2029Q3/rows/PRJ-302/net_project_revenue/plan_value`  
  project PRJ-302 net_project_revenue shows a business-plan figure of 95,900,000.00; the approved baseline carries 96,000,000.00
- **FAIL** `var_plan_column_ties` @ `variance_summary:VARIANCE-2029Q3/rows/PRJ-302/net_project_revenue/variance_vs_plan`  
  project PRJ-302 net_project_revenue states a business-plan variance of 4,000,000.00; current less plan is 4,100,000.00

### plan_version_rebased__Ardenne_Field_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `var_plan_version_frozen` @ `variance_summary:VARIANCE-2029Q3/basis_plan_version`  
  the variance tab is headed business plan BP-2029-R1 but the baseline document is version BP-2028-R2; the plan column is not the plan named

### prior_column_missing__Westmere

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `prj_comparatives_present` @ `project_register:PROJECTS-2029Q3/projects/PRJ-304`  
  project PRJ-304 has no prior period column; there is nothing for the variance tab to restate it against

### prior_variance_wrong__Northmoor_Development_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `var_prior_column_ties` @ `variance_summary:VARIANCE-2029Q3/rows/PRJ-301/gross_revenue/variance_vs_prior`  
  project PRJ-301 gross_revenue states a prior-period variance of 2,100,000.00; current less prior is 2,000,000.00

### profit_off__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `eco_profit_foots` @ `current_period_economics:CURRENT-2029Q3/projects/PRJ-302/project_profit_cents`  
  project PRJ-302 states profit 20,500,000.00; net project revenue less total project expense is 20,000,000.00 (out by 500,000.00)

### rollup_total_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `rpt_rollup_foots` @ `report_rollup:ROLLUP-2029Q3/total_project_profit_cents`  
  the rollup states a total project profit of 68,000,000.00; footing the 4 current-period rows gives 67,000,000.00

### watchlist_overstated__Ardenne_Field_Group

**Verdict:** REVIEW (PASS 21, FLAG 1, FAIL 0)

- **FLAG** `rpt_slippage_watchlist_ties` @ `slippage_watchlist:SLIPPAGE-2029Q3/entries/MS-3013`  
  the watchlist lists milestone MS-3013 as behind the frozen baseline, but the schedule does not put it past tolerance as of 2029-10-01
