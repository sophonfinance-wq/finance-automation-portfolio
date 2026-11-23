# Depreciation & prepaid amortization control report

**Overall verdict:** FAIL

- Close files analyzed: 32
- Controls in registry: 30
- PASS / REVIEW / FAIL: 1 / 2 / 29

All data is fictional. The engine is read-only and never writes to a source
artifact. Every derivation and date gate is measured to the `close_month`
carried in the file, never the system clock.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `cap_threshold_gate` | FAIL | 1 |
| 3 | `cap_register_meets_threshold` | FAIL | 1 |
| 4 | `life_class_known` | FAIL | 1 |
| 5 | `life_matches_class` | FAIL | 1 |
| 6 | `life_method_straight_line` | FAIL | 1 |
| 7 | `sl_monthly_dep_rederives` | FAIL | 1 |
| 8 | `sl_expense_rederives` | FAIL | 1 |
| 9 | `date_end_depr_rederives` | FAIL | 1 |
| 10 | `date_fully_depreciated_zero` | FAIL | 1 |
| 11 | `date_not_in_service_yet` | FAIL | 1 |
| 12 | `nbv_months_used_cap` | FAIL | 1 |
| 13 | `nbv_accum_rederives` | FAIL | 2 |
| 14 | `nbv_floor` | FAIL | 2 |
| 15 | `roll_accum_identity` | FAIL | 1 |
| 16 | `roll_closing_ties_register` | FAIL | 2 |
| 17 | `roll_prepaid_rollforward` | FAIL | 2 |
| 18 | `pre_window_valid` | FAIL | 1 |
| 19 | `pre_monthly_amort_rederives` | FAIL | 1 |
| 20 | `pre_expense_rederives` | FAIL | 1 |
| 21 | `pre_ending_balance_rederives` | FAIL | 1 |
| 22 | `pre_window_ending_watch` | FLAG | 1 |
| 23 | `disp_not_on_register` | FAIL | 1 |
| 24 | `disp_gain_loss_rederives` | FAIL | 1 |
| 25 | `disp_fully_depreciated_watch` | FLAG | 1 |
| 26 | `gl_cost_ties` | FAIL | 1 |
| 27 | `gl_accum_ties` | FAIL | 2 |
| 28 | `gl_prepaid_ties` | FAIL | 1 |
| 29 | `je_depreciation_ties` | FAIL | 1 |
| 30 | `je_prepaid_amort_ties` | FAIL | 1 |

## Close files

### accum_dep_misstated__Halbrook_Residential

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `nbv_accum_rederives` @ `fixed_asset_register:FAR-2029-06/assets/FA-102/accum_dep_cents`  
  asset FA-102 states accumulated depreciation of 11,525.07; 70 month(s) of the schedule re-derive 11,692.10

### accum_rollforward_broken__Stonecrest_Communities

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `roll_accum_identity` @ `rollforward_schedule:ROLL-2029-06/fixed_assets/closing_accum_cents`  
  the accumulated-depreciation roll-forward does not close: opening 44,305.07 + depreciation 1,757.03 - disposals 0.00 = 46,062.10, but closing is stated as 46,052.10

### amount_not_integer__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 4)

- **FAIL** `nbv_accum_rederives` @ `amount:asset[FA-102].accum_dep_cents`  
  AMOUNT_INVALID: asset[FA-102].accum_dep_cents must be integer cents, got 1169210.5 -- amounts are integer cents and are never coerced
- **FAIL** `nbv_floor` @ `amount:asset[FA-102].accum_dep_cents`  
  AMOUNT_INVALID: asset[FA-102].accum_dep_cents must be integer cents, got 1169210.5 -- amounts are integer cents and are never coerced
- **FAIL** `roll_closing_ties_register` @ `amount:asset[FA-102].accum_dep_cents`  
  AMOUNT_INVALID: asset[FA-102].accum_dep_cents must be integer cents, got 1169210.5 -- amounts are integer cents and are never coerced
- **FAIL** `gl_accum_ties` @ `amount:asset[FA-102].accum_dep_cents`  
  AMOUNT_INVALID: asset[FA-102].accum_dep_cents must be integer cents, got 1169210.5 -- amounts are integer cents and are never coerced

### clean__Northmoor_Development_Group

**Verdict:** PASS (PASS 30, FLAG 0, FAIL 0)

All controls held.

### depreciation_before_service__Westmere_Homes

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `date_not_in_service_yet` @ `fixed_asset_register:FAR-2029-06/assets/FA-106/in_service_month`  
  asset FA-106 enters service 2029-08, after the 2029-06 close, yet states months_used 0, accum 140.00, expense 0.00 and NBV 1,960.00; before service those must be zero and NBV must be cost

### disposal_writeoff_wrong__Northmoor_Development_Group

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `disp_gain_loss_rederives` @ `disposal_register:DISP-2029/disposals/FA-090/writeoff_cents`  
  disposal of asset FA-090 states a write-off of 9,281.00; cost 41,760.00 less accumulated 32,480.00 re-derives 9,280.00, and accumulation must stay within [0, cost]

### disposed_asset_still_depreciating__Halbrook_Residential

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `disp_not_on_register` @ `fixed_asset_register:FAR-2029-06/assets/FA-090`  
  asset FA-090 appears on the disposal register (disposed 2029-04) and is still on the fixed-asset register; depreciation must stop at disposal and the cost must roll off

### end_depr_date_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `date_end_depr_rederives` @ `fixed_asset_register:FAR-2029-06/assets/FA-105/end_depr_month`  
  asset FA-105 states end-of-depreciation '2035-07'; in service 2027-07 over 96 month(s) re-derives 2035-06

### expense_overstated__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `sl_expense_rederives` @ `fixed_asset_register:FAR-2029-06/assets/FA-103/depr_exp_cents`  
  asset FA-103 states 645.00 of depreciation for 2029-06; the schedule re-derives 640.00 for that month

### fully_depreciated_still_carrying__Westmere_Homes

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `date_fully_depreciated_zero` @ `fixed_asset_register:FAR-2029-06/assets/FA-104/accum_dep_cents`  
  asset FA-104 completed its schedule in 2029-03 yet states accum 4,140.00 against cost 5,040.00, expense 0.00 and NBV 900.00; past the end month those must be cost, zero and zero

### gl_accum_untied__Northmoor_Development_Group

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `gl_accum_ties` @ `gl_control_balances:GL-2029-06/accounts/1611/balance_cents`  
  GL account 1611 (accumulated depreciation) carries 46,102.10; the register foots to 46,052.10 (variance 50.00)

### gl_cost_untied__Halbrook_Residential

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `gl_cost_ties` @ `gl_control_balances:GL-2029-06/accounts/1610/balance_cents`  
  GL account 1610 (fixed assets at cost) carries 129,820.72; the register foots to 129,770.72 (variance 50.00)

### gl_prepaid_untied__Stonecrest_Communities

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `gl_prepaid_ties` @ `gl_control_balances:GL-2029-06/accounts/1420/balance_cents`  
  GL account 1420 (prepaid expenses) carries 59,600.50; the register foots to 59,550.50 (variance 50.00)

### je_amortization_untied__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `je_prepaid_amort_ties` @ `recurring_je:RJE-2029-06/lines/JE-AMORT/amount_cents`  
  recurring-JE line JE-AMORT (prepaid amortization) posted 4,582.35; the register foots to 4,581.35 (variance 1.00)

### je_depreciation_untied__Westmere_Homes

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `je_depreciation_ties` @ `recurring_je:RJE-2029-06/lines/JE-DEP/amount_cents`  
  recurring-JE line JE-DEP (monthly depreciation) posted 1,758.03; the register foots to 1,757.03 (variance 1.00)

### life_off_class_table__Northmoor_Development_Group

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `life_matches_class` @ `fixed_asset_register:FAR-2029-06/assets/FA-101/useful_life_months`  
  asset FA-101 is classed computer_equipment, whose table life is 36 month(s); the register carries 48 month(s), so every derived figure beneath it is off-convention

### missing_artifact__Halbrook_Residential

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `recurring_je:-`  
  recurring_je is missing; the controls that read it cannot run and must not be reported as having passed

### monthly_dep_overstated__Stonecrest_Communities

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `sl_monthly_dep_rederives` @ `fixed_asset_register:FAR-2029-06/assets/FA-101/monthly_dep_cents`  
  asset FA-101 states a monthly charge of 351.00; cost 12,600.00 over 36 month(s) re-derives 350.00

### months_used_overstated__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `nbv_months_used_cap` @ `fixed_asset_register:FAR-2029-06/assets/FA-101/months_used`  
  asset FA-101 states 29 month(s) used; in service 2027-03 through 2029-06 with a 36-month life re-derives min(elapsed, life) = 28

### nbv_identity_broken__Westmere_Homes

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `nbv_floor` @ `fixed_asset_register:FAR-2029-06/assets/FA-103/nbv_cents`  
  asset FA-103 states cost 38,400.00, accum 5,120.00 and NBV 33,280.01; NBV must equal cost less accumulated, and accumulated must stay within [0, cost]

### non_straight_line_method__Northmoor_Development_Group

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `life_method_straight_line` @ `fixed_asset_register:FAR-2029-06/assets/FA-102/method`  
  asset FA-102 states method 'declining_balance'; these books depreciate straight-line only, and a stated figure derived any other way cannot be re-derived by this engine's convention

### prepaid_ending_balance_wrong__Halbrook_Residential

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `pre_ending_balance_rederives` @ `prepaid_register:PPD-2029-06/items/PP-403/ending_balance_cents`  
  item PP-403 states balances 40,356.25 opening and 39,630.27 closing for 2029-06; the schedule re-derives 40,356.25 and 39,622.50

### prepaid_expense_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `pre_expense_rederives` @ `prepaid_register:PPD-2029-06/items/PP-403/amort_this_period_cents`  
  item PP-403 states 743.75 of amortization for 2029-06; the window 2029-01 to 2033-12 booked from 2029-01 re-derives 733.75

### prepaid_monthly_amort_wrong__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `pre_monthly_amort_rederives` @ `prepaid_register:PPD-2029-06/items/PP-401/monthly_amort_cents`  
  item PP-401 states monthly amortization of 750.10; additions 9,000.00 over the 12-period window re-derive 750.00

### prepaid_rollforward_broken__Westmere_Homes

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 2)

- **FAIL** `roll_prepaid_rollforward` @ `rollforward_schedule:ROLL-2029-06/prepaid/closing_cents`  
  the prepaid roll-forward does not close: opening 64,136.85 + additions 0.00 - amortization 4,581.35 = 59,555.50, but closing is stated as 59,550.50
- **FAIL** `roll_prepaid_rollforward` @ `rollforward_schedule:ROLL-2029-06/prepaid/opening_cents`  
  the prepaid roll-forward opens at 64,136.85; the register's beginning balances foot to 64,131.85

### prepaid_window_ending__Northmoor_Development_Group

**Verdict:** REVIEW (PASS 29, FLAG 1, FAIL 0)

- **FLAG** `pre_window_ending_watch` @ `prepaid_register:PPD-2029-06/items/PP-401/window_end`  
  item PP-401 amortizes through 2029-06, within 1 month(s) of the 2029-06 close; the underlying term is ending and its renewal needs a decision

### prepaid_window_inverted__Halbrook_Residential

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `pre_window_valid` @ `prepaid_register:PPD-2029-06/items/PP-401/window_end`  
  item PP-401 states an amortization window from 2028-11 to 2028-10; the window does not run forwards, so no schedule can be derived from it

### rollforward_untied_to_register__Stonecrest_Communities

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `roll_closing_ties_register` @ `rollforward_schedule:ROLL-2029-06/fixed_assets/closing_accum_cents`  
  the roll-forward closes accumulated depreciation at 46,062.10; the asset register foots to 46,052.10 (variance 10.00)

### stale_fully_depreciated_asset__Ardenne_Field_Partners

**Verdict:** REVIEW (PASS 29, FLAG 1, FAIL 0)

- **FLAG** `disp_fully_depreciated_watch` @ `fixed_asset_register:FAR-2029-06/assets/FA-104/end_depr_month`  
  asset FA-104 completed its schedule in 2027-12, more than 12 month(s) before the 2029-06 close, and is still on the register; it is due for disposal review

### subthreshold_asset_on_register__Westmere_Homes

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `cap_register_meets_threshold` @ `fixed_asset_register:FAR-2029-06/assets/FA-107/cost_cents`  
  asset FA-107 was capitalized at 420.00, below the 500.00 capitalization threshold; it belongs in expense, not on the register

### subthreshold_capitalized__Northmoor_Development_Group

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `cap_threshold_gate` @ `capitalization_policy:CAP-2029/items/EX-203/capitalized`  
  item EX-203 costs 460.00 (threshold 500.00, category 'furniture') and must be expensed under the policy; it is recorded capitalized=True

### unknown_asset_class__Halbrook_Residential

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `life_class_known` @ `fixed_asset_register:FAR-2029-06/assets/FA-103/asset_class`  
  asset FA-103 is classed 'artwork', which is not in the useful-life table; its required life cannot be looked up
