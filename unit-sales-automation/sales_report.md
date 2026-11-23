# Unit sales and commission tie-out control report

**Overall verdict:** FAIL

- Sales files analyzed: 23
- Controls in registry: 21
- PASS / REVIEW / FAIL: 1 / 2 / 20

All data is fictional. The engine is read-only and never writes to a source
artifact. Every closing test is made against the `as_of` date carried in the
file, never the system clock.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `plan_unique_codes` | FAIL | 1 |
| 3 | `plan_sqft_positive` | FAIL | 1 |
| 4 | `unit_required_fields` | FAIL | 1 |
| 5 | `unit_unique_ids` | FAIL | 1 |
| 6 | `unit_plan_defined` | FAIL | 1 |
| 7 | `unit_status_valid` | FAIL | 1 |
| 8 | `price_rev_per_sqft_recomputes` | FAIL | 1 |
| 9 | `price_concession_within_price` | FAIL | 1 |
| 10 | `price_net_proceeds_recomputes` | FAIL | 2 |
| 11 | `price_discount_to_list` | FLAG | 1 |
| 12 | `comm_rate_defined` | FAIL | 1 |
| 13 | `comm_total_recomputes` | FAIL | 2 |
| 14 | `comm_splits_tie` | FAIL | 1 |
| 15 | `comm_agent_known` | FAIL | 1 |
| 16 | `close_sold_reconciles` | FAIL | 1 |
| 17 | `close_date_order` | FAIL | 1 |
| 18 | `close_proof_received` | FLAG | 1 |
| 19 | `rpt_sold_count_ties` | FAIL | 1 |
| 20 | `rpt_revenue_ties` | FAIL | 2 |
| 21 | `rpt_commission_ties` | FAIL | 1 |

## Sales files

### agent_split_short__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `comm_splits_tie` @ `commission_log:COMMLOG-2031/splits/UNIT-105`  
  unit UNIT-105 splits 44,450.00 across 3 agent(s); the Matrix authorises 44,550.00 (off by -100.00)

### amount_not_integer__Stonecrest_Communities

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 2)

- **FAIL** `price_net_proceeds_recomputes` @ `amount:unit[UNIT-101].net_proceeds_cents`  
  AMOUNT_INVALID: unit[UNIT-101].net_proceeds_cents must be integer cents, got 58500000.5 -- amounts are integer cents and are never coerced
- **FAIL** `rpt_revenue_ties` @ `amount:unit[UNIT-101].net_proceeds_cents`  
  AMOUNT_INVALID: unit[UNIT-101].net_proceeds_cents must be integer cents, got 58500000.5 -- amounts are integer cents and are never coerced

### bad_unit_status__Ardenne_Field_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `unit_status_valid` @ `unit_matrix:MATRIX-2031/units/UNIT-106/status`  
  unit UNIT-106 is marked 'pending', which is not one of ('available', 'reserved', 'sold'); it is neither counted nor reconciled

### channel_rate_missing__Northmoor_Development_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `comm_rate_defined` @ `commission_schedule:COMMSCHED-2031/rates/referral`  
  the commission schedule has no rate for sale channel 'referral', which unit UNIT-104 was sold through; the known channels are ('in_house', 'co_broke', 'referral')

### clean__Northmoor_Development_Group

**Verdict:** PASS (PASS 21, FLAG 0, FAIL 0)

All controls held.

### close_row_missing__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `close_sold_reconciles` @ `sold_close_log:SOLDCLOSE-2031/closings/UNIT-104`  
  unit UNIT-104 is marked sold on the Matrix but has no row on the Sold/Close tab; the sale is claimed and not evidenced

### commission_rate_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 2)

- **FAIL** `comm_total_recomputes` @ `unit_matrix:MATRIX-2031/units/UNIT-102/total_commission_cents`  
  unit UNIT-102 states commission of 30,600.00; 5.50% on a sales price of 612,000.00 re-derives 33,660.00 (off by -3,060.00)
- **FAIL** `comm_total_recomputes` @ `unit_matrix:MATRIX-2031/units/UNIT-105/total_commission_cents`  
  unit UNIT-105 states commission of 44,550.00; 5.50% on a sales price of 891,000.00 re-derives 49,005.00 (off by -4,455.00)

### commission_total_overstated__Ardenne_Field_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `rpt_commission_ties` @ `sales_rollup:ROLLUP-2031/total_commission_cents`  
  the rollup states 165,950.00 of total commission; the Matrix commission column sums to 160,950.00 (off by 5,000.00)

### concession_exceeds_price__Northmoor_Development_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `price_concession_within_price` @ `unit_matrix:MATRIX-2031/units/UNIT-103/concession_cents`  
  unit UNIT-103 grants a concession of 735,000.01 against a sales price of 735,000.00; a concession sits inside the price it discounts

### dates_out_of_order__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `close_date_order` @ `sold_close_log:SOLDCLOSE-2031/closings/UNIT-103/actual_date_sold`  
  unit UNIT-103 was offered 2030-12-02, sold 2030-11-20 and closed 2031-02-11; the sequence does not run offer, sale, closing

### discount_over_band__Stonecrest_Communities

**Verdict:** REVIEW (PASS 20, FLAG 1, FAIL 0)

- **FLAG** `price_discount_to_list` @ `unit_matrix:MATRIX-2031/units/UNIT-102/sales_price_cents`  
  unit UNIT-102 sold at 612,000.00 against a list of 700,000.00, a discount of 12.57%; the approved band is 5.00%

### duplicate_plan_code__Ardenne_Field_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `plan_unique_codes` @ `plan_register:PLANS-2031/plans/PL-A1`  
  plan code PL-A1 appears 2 times; a unit that names it cannot be priced against one square footage

### duplicate_unit_id__Northmoor_Development_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `unit_unique_ids` @ `unit_matrix:MATRIX-2031/units/UNIT-107`  
  unit id UNIT-107 appears 2 times; a closing or a commission split that names it cannot be attributed to one unit

### missing_artifact__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 17, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `sales_rollup:-`  
  sales_rollup is missing; the controls that read it cannot run and must not be reported as having passed

### net_proceeds_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `price_net_proceeds_recomputes` @ `unit_matrix:MATRIX-2031/units/UNIT-105/net_proceeds_cents`  
  unit UNIT-105 states net proceeds of 868,135.00; 891,000.00 less 9,000.00 concession less 13,365.00 closing costs re-derives 868,635.00 (off by -500.00)

### plan_sqft_zero__Ardenne_Field_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `plan_sqft_positive` @ `plan_register:PLANS-2031/plans/PL-D4/plan_sqft`  
  plan PL-D4 states 0 square feet; revenue per square foot divides by this figure and cannot divide by it

### proof_not_received__Northmoor_Development_Group

**Verdict:** REVIEW (PASS 20, FLAG 1, FAIL 0)

- **FLAG** `close_proof_received` @ `sold_close_log:SOLDCLOSE-2031/closings/UNIT-105/proof_received`  
  unit UNIT-105 closed 2031-03-10, on or before the review date 2031-04-01, and its proof of closing has not been received; the sale is recorded on an unevidenced settlement

### rev_per_sqft_wrong__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `price_rev_per_sqft_recomputes` @ `unit_matrix:MATRIX-2031/units/UNIT-101/rev_per_sqft_cents`  
  unit UNIT-101 states 501.00 per square foot; 600,000.00 over 1200 square feet re-derives 500.00

### revenue_total_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `rpt_revenue_ties` @ `sales_rollup:ROLLUP-2031/total_sales_price_cents`  
  the rollup states 4,782,500.00 of sales price; the sold rows of the Matrix sum to 4,783,500.00 (off by -1,000.00)

### sold_count_wrong__Ardenne_Field_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `rpt_sold_count_ties` @ `sales_rollup:ROLLUP-2031/sold_unit_count`  
  the rollup states 7 sold unit(s); the Matrix recomputes 6

### unit_missing_field__Northmoor_Development_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `unit_required_fields` @ `unit_matrix:MATRIX-2031/units/UNIT-103`  
  unit UNIT-103 is missing building

### unknown_agent__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `comm_agent_known` @ `commission_log:COMMLOG-2031/splits/UNIT-104/AG-99`  
  unit UNIT-104 splits commission to agent 'AG-99', who is not in the agent register

### unknown_plan_code__Stonecrest_Communities

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `unit_plan_defined` @ `unit_matrix:MATRIX-2031/units/UNIT-107/plan_code`  
  unit UNIT-107 names plan 'PL-Z9', which is not in the plan register; its square footage is unknown
