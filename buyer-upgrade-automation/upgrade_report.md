# Buyer upgrade control report

**Overall verdict:** FAIL

- Books analyzed: 22
- Controls in registry: 20
- PASS / REVIEW / FAIL: 1 / 3 / 18

All data is fictional. The engine is read-only and never writes to a source
artifact.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `set_period_aligned` | FAIL | 1 |
| 3 | `unit_upgrade_maps_to_a_unit` | FAIL | 1 |
| 4 | `unit_no_duplicate_orders` | FAIL | 1 |
| 5 | `unit_closed_has_close_date` | FAIL | 1 |
| 6 | `def_released_only_on_close` | FAIL | 1 |
| 7 | `def_unit_total_is_deposit` | FAIL | 5 |
| 8 | `def_schedule_ties_ledger` | FAIL | 3 |
| 9 | `def_revenue_ties_ledger` | FAIL | 2 |
| 10 | `cos_entry_balances` | FAIL | 1 |
| 11 | `cos_only_closed_units_costed` | FAIL | 1 |
| 12 | `cos_costs_within_committed` | FLAG | 1 |
| 13 | `cos_change_order_referenced` | FLAG | 1 |
| 14 | `tax_derived_from_rate` | FAIL | 2 |
| 15 | `tax_not_recognised_as_revenue` | FAIL | 3 |
| 16 | `tie_ctc_revenue_to_proforma` | FAIL | 1 |
| 17 | `tie_ctc_costs_to_proforma` | FAIL | 1 |
| 18 | `tie_proforma_to_variance` | FAIL | 1 |
| 19 | `tie_ctc_units_foot` | FAIL | 1 |
| 20 | `flag_actual_on_closed_units` | FLAG | 1 |

## Books

### amount_not_integer__Brightwater_Commons

**Verdict:** FAIL (PASS 18, FLAG 0, FAIL 3)

- **FAIL** `def_unit_total_is_deposit` @ `amount:register.orders[O-1001].price_cents`  
  AMOUNT_INVALID: register.orders[O-1001].price_cents must be integer cents, got 2800000.5 -- amounts are integer cents and are never coerced
- **FAIL** `def_unit_total_is_deposit` @ `closings_schedule:CLS-2027-04/units/U-01`  
  unit U-01: recognised 28,000.00 + deferred 0.00 = 28,000.00, but the register contracts 0.00 of upgrades
- **FAIL** `tax_derived_from_rate` @ `amount:register.orders[O-1001].price_cents`  
  AMOUNT_INVALID: register.orders[O-1001].price_cents must be integer cents, got 2800000.5 -- amounts are integer cents and are never coerced

### clean__Alderpoint_Terraces

**Verdict:** PASS (PASS 20, FLAG 0, FAIL 0)

All controls held.

### closed_no_date__Copperfield_Yards

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `unit_closed_has_close_date` @ `closings_schedule:CLS-2027-04/units/U-02/close_date`  
  unit U-02 is marked closed but carries no readable close-of-escrow date

### cost_before_close__Dunmore_Flats

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `cos_only_closed_units_costed` @ `cost_to_complete_upgrades:CTC-2027-04/units/U-03/cost_of_sales_cents`  
  unit U-03 has 5,940.00 relieved to cost of sales but has not closed; cost follows revenue

### cost_overrun__Alderpoint_Terraces

**Verdict:** REVIEW (PASS 19, FLAG 1, FAIL 0)

- **FLAG** `cos_costs_within_committed` @ `cost_to_complete_upgrades:CTC-2027-04/units/U-04/costs_to_date_cents`  
  unit U-04 has incurred 9,450.00 against a committed cost of 7,650.00 (123.52%); an executed change order should raise the commitment before the cost lands

### ctc_no_foot__Brightwater_Commons

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `tie_ctc_units_foot` @ `cost_to_complete_upgrades:CTC-2027-04/totals/committed_cost_cents`  
  committed cost: unit rows sum to 73,710.00 but the total declares 74,360.00 (difference -650.00)

### ctc_vs_proforma_cost__Copperfield_Yards

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `tie_ctc_costs_to_proforma` @ `proforma_upgrade_lines:PFA-2027-04/upgrade_costs_to_date_cents`  
  the cost-to-complete reports 62,242.50 of costs to date; the proforma's upgrade job-cost line carries -61,542.50, which negates to 61,542.50 (difference 700.00)

### ctc_vs_proforma_rev__Dunmore_Flats

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `tie_ctc_revenue_to_proforma` @ `proforma_upgrade_lines:PFA-2027-04/upgrade_income_cents`  
  the cost-to-complete reports 122,850.00 of net upgrade revenue; the proforma carries 124,350.00 (difference -1,500.00)

### deferred_vs_ledger__Alderpoint_Terraces

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `def_schedule_ties_ledger` @ `ledger:unearned_revenue_upgrades`  
  the closings schedule carries 34,750.00 of deferred upgrade revenue but the ledger balance is 36,000.00 (difference -1,250.00)

### duplicate_order__Brightwater_Commons

**Verdict:** FAIL (PASS 17, FLAG 0, FAIL 3)

- **FAIL** `unit_no_duplicate_orders` @ `upgrade_order_register:UPR-2027-04/orders/O-1001`  
  upgrade order O-1001 appears 2 times; a duplicate double-counts both the liability and the revenue it becomes
- **FAIL** `def_unit_total_is_deposit` @ `closings_schedule:CLS-2027-04/units/U-01`  
  unit U-01: recognised 28,000.00 + deferred 0.00 = 28,000.00, but the register contracts 56,000.00 of upgrades
- **FAIL** `tax_not_recognised_as_revenue` @ `ledger:sales_tax_payable`  
  orders carry 14,330.75 of sales tax but the liability account holds 11,670.75; tax collected is owed onward, not earned

### early_recognition__Copperfield_Yards

**Verdict:** FAIL (PASS 17, FLAG 0, FAIL 3)

- **FAIL** `def_released_only_on_close` @ `closings_schedule:CLS-2027-04/units/U-03/revenue_recognised_cents`  
  unit U-03 has not closed but 22,000.00 of upgrade revenue is already recognised; the money is a liability until close of escrow
- **FAIL** `def_schedule_ties_ledger` @ `ledger:unearned_revenue_upgrades`  
  the closings schedule carries 12,750.00 of deferred upgrade revenue but the ledger balance is 34,750.00 (difference -22,000.00)
- **FAIL** `def_revenue_ties_ledger` @ `ledger:revenue_upgrades`  
  the schedule recognises 110,100.00 of upgrade revenue but the ledger carries 88,100.00 (difference 22,000.00)

### entry_unbalanced__Dunmore_Flats

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `cos_entry_balances` @ `ledger:contra_wip_upgrades`  
  cost of sales 52,860.00 and contra work-in-progress -50,860.00 do not offset (net 2,000.00); the closing entry reclassifies cost, it does not create it

### missing_artifact__Alderpoint_Terraces

**Verdict:** FAIL (PASS 16, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `book:missing_artifact__Alderpoint_Terraces/proforma_upgrade_lines`  
  book carries no proforma_upgrade_lines; absent evidence is not a passing control, so no downstream rule may read it

### no_change_order__Brightwater_Commons

**Verdict:** REVIEW (PASS 19, FLAG 1, FAIL 0)

- **FLAG** `cos_change_order_referenced` @ `cost_to_complete_upgrades:CTC-2027-04/units/U-05/change_order_ref`  
  unit U-05 is committed at 23,040.00 against a budget of 20,640.00 with no change order referenced

### orphan_unit__Copperfield_Yards

**Verdict:** FAIL (PASS 18, FLAG 0, FAIL 2)

- **FAIL** `unit_upgrade_maps_to_a_unit` @ `upgrade_order_register:UPR-2027-04/orders/O-1004/unit`  
  upgrade order O-1004 references unit 'U-99', which is not on the closings schedule
- **FAIL** `def_unit_total_is_deposit` @ `closings_schedule:CLS-2027-04/units/U-03`  
  unit U-03: recognised 0.00 + deferred 22,000.00 = 22,000.00, but the register contracts 0.00 of upgrades

### period_drift__Dunmore_Flats

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `set_period_aligned` @ `cost_to_complete_upgrades:CTC-2027-04/period`  
  document period '2027-03' does not match the book period '2027-04'

### proforma_vs_variance__Alderpoint_Terraces

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `tie_proforma_to_variance` @ `proforma_upgrade_lines:PFA-2027-04/variance_tab_net_cents`  
  upgrade income 122,850.00 plus the job-cost line -62,242.50 = 60,607.50, but the variance tab shows 60,932.50

### revenue_vs_ledger__Brightwater_Commons

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `def_revenue_ties_ledger` @ `ledger:revenue_upgrades`  
  the schedule recognises 88,100.00 of upgrade revenue but the ledger carries 87,200.00 (difference 900.00)

### stale_basis__Copperfield_Yards

**Verdict:** REVIEW (PASS 19, FLAG 1, FAIL 0)

- **FLAG** `flag_actual_on_closed_units` @ `cost_to_complete_upgrades:CTC-2027-04/units/U-01/revenue_basis`  
  unit U-01 has closed but its revenue is still marked 'budgeted'; a closed unit's figure is a fact, not a forecast

### tax_in_revenue__Dunmore_Flats

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `tax_not_recognised_as_revenue` @ `ledger:sales_tax_payable`  
  orders carry 11,670.75 of sales tax but the liability account holds 11,370.75; tax collected is owed onward, not earned

### tax_wrong__Alderpoint_Terraces

**Verdict:** FAIL (PASS 18, FLAG 0, FAIL 2)

- **FAIL** `tax_derived_from_rate` @ `upgrade_order_register:UPR-2027-04/orders/O-1003/sales_tax_cents`  
  order O-1003: 9,200.00 at 9.50% derives 874.00 of sales tax, but 914.00 is recorded
- **FAIL** `tax_not_recognised_as_revenue` @ `ledger:sales_tax_payable`  
  orders carry 11,710.75 of sales tax but the liability account holds 11,670.75; tax collected is owed onward, not earned

### unit_total_off__Brightwater_Commons

**Verdict:** FAIL (PASS 18, FLAG 0, FAIL 2)

- **FAIL** `def_unit_total_is_deposit` @ `closings_schedule:CLS-2027-04/units/U-04`  
  unit U-04: recognised 0.00 + deferred 13,250.00 = 13,250.00, but the register contracts 12,750.00 of upgrades
- **FAIL** `def_schedule_ties_ledger` @ `ledger:unearned_revenue_upgrades`  
  the closings schedule carries 35,250.00 of deferred upgrade revenue but the ledger balance is 34,750.00 (difference 500.00)
