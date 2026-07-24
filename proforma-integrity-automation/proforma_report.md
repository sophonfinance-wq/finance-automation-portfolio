# Project-proforma integrity control report

**Overall verdict:** FAIL

- Proforma files analyzed: 28
- Controls in registry: 26
- PASS / REVIEW / FAIL: 1 / 1 / 26

All data is fictional. The engine is read-only and never writes to a source
artifact. Every filing due-date gate is made against the `as_of` date carried
in the file, never the system clock.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `src_sources_total_ties` | FAIL | 1 |
| 3 | `src_uses_total_ties` | FAIL | 1 |
| 4 | `src_source_use_balance` | FAIL | 1 |
| 5 | `cost_hard_soft_total` | FAIL | 2 |
| 6 | `cost_unlevered_ties_devbudget` | FAIL | 2 |
| 7 | `cost_contingency_rollup` | FAIL | 1 |
| 8 | `int_reserve_adequate` | FAIL | 1 |
| 9 | `int_equity_funded_before_construction` | FAIL | 1 |
| 10 | `prof_net_profit_derivation` | FAIL | 2 |
| 11 | `prof_unlevered_profit_derivation` | FAIL | 2 |
| 12 | `wfl_waterfall_ties_net` | FAIL | 2 |
| 13 | `wfl_budgeted_ties_net` | FAIL | 2 |
| 14 | `wfl_distributed_ties_net` | FAIL | 2 |
| 15 | `wfl_sponsor_share_derivation` | FAIL | 2 |
| 16 | `wfl_split_completeness` | FAIL | 3 |
| 17 | `mgn_margin_on_cost` | FAIL | 2 |
| 18 | `mgn_margin_on_revenue` | FAIL | 2 |
| 19 | `mgn_cost_per_nsf` | FAIL | 2 |
| 20 | `var_metric_delta` | FAIL | 3 |
| 21 | `var_schedule_days` | FAIL | 1 |
| 22 | `var_materiality_flag` | FLAG | 2 |
| 23 | `rpt_project_qpr_filed` | FAIL | 1 |
| 24 | `rpt_qpr_due_date_gate` | FAIL | 1 |
| 25 | `rpt_regional_deliverables_present` | FAIL | 1 |
| 26 | `rpt_cycle_count_ties` | FAIL | 1 |

## Proforma files

### amount_not_integer__Halbrook_Residential

**Verdict:** FAIL (PASS 12, FLAG 1, FAIL 14)

- **FAIL** `cost_hard_soft_total` @ `amount:ledger[PRJ-01].hard_cost_cents`  
  AMOUNT_INVALID: ledger[PRJ-01].hard_cost_cents must be integer cents, got 3000000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `cost_unlevered_ties_devbudget` @ `amount:ledger[PRJ-01].hard_cost_cents`  
  AMOUNT_INVALID: ledger[PRJ-01].hard_cost_cents must be integer cents, got 3000000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `prof_net_profit_derivation` @ `amount:ledger[PRJ-01].hard_cost_cents`  
  AMOUNT_INVALID: ledger[PRJ-01].hard_cost_cents must be integer cents, got 3000000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `prof_unlevered_profit_derivation` @ `amount:ledger[PRJ-01].hard_cost_cents`  
  AMOUNT_INVALID: ledger[PRJ-01].hard_cost_cents must be integer cents, got 3000000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `wfl_waterfall_ties_net` @ `amount:ledger[PRJ-01].hard_cost_cents`  
  AMOUNT_INVALID: ledger[PRJ-01].hard_cost_cents must be integer cents, got 3000000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `wfl_budgeted_ties_net` @ `amount:ledger[PRJ-01].hard_cost_cents`  
  AMOUNT_INVALID: ledger[PRJ-01].hard_cost_cents must be integer cents, got 3000000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `wfl_distributed_ties_net` @ `amount:ledger[PRJ-01].hard_cost_cents`  
  AMOUNT_INVALID: ledger[PRJ-01].hard_cost_cents must be integer cents, got 3000000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `wfl_sponsor_share_derivation` @ `amount:ledger[PRJ-01].hard_cost_cents`  
  AMOUNT_INVALID: ledger[PRJ-01].hard_cost_cents must be integer cents, got 3000000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `wfl_split_completeness` @ `amount:ledger[PRJ-01].hard_cost_cents`  
  AMOUNT_INVALID: ledger[PRJ-01].hard_cost_cents must be integer cents, got 3000000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `mgn_margin_on_cost` @ `amount:ledger[PRJ-01].hard_cost_cents`  
  AMOUNT_INVALID: ledger[PRJ-01].hard_cost_cents must be integer cents, got 3000000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `mgn_margin_on_revenue` @ `amount:ledger[PRJ-01].hard_cost_cents`  
  AMOUNT_INVALID: ledger[PRJ-01].hard_cost_cents must be integer cents, got 3000000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `mgn_cost_per_nsf` @ `amount:ledger[PRJ-01].hard_cost_cents`  
  AMOUNT_INVALID: ledger[PRJ-01].hard_cost_cents must be integer cents, got 3000000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `var_metric_delta` @ `amount:ledger[PRJ-01].hard_cost_cents`  
  AMOUNT_INVALID: ledger[PRJ-01].hard_cost_cents must be integer cents, got 3000000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `var_metric_delta` @ `amount:ledger[PRJ-01].hard_cost_cents`  
  AMOUNT_INVALID: ledger[PRJ-01].hard_cost_cents must be integer cents, got 3000000000.5 -- amounts are integer cents and are never coerced
- **FLAG** `var_materiality_flag` @ `amount:ledger[PRJ-01].hard_cost_cents`  
  AMOUNT_INVALID: ledger[PRJ-01].hard_cost_cents must be integer cents, got 3000000000.5 -- amounts are integer cents and are never coerced

### budgeted_profit_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `wfl_budgeted_ties_net` @ `tieout_summary:SUMMARY-2031Q1/projects/PRJ-01/budgeted_profit_cents`  
  project PRJ-01 states budgeted profit 10,000,000.01; net profit re-derives to 10,000,000.00 (off 0.01)

### clean__Northmoor_Development_Group

**Verdict:** PASS (PASS 26, FLAG 0, FAIL 0)

All controls held.

### contingency_rollup_wrong__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `cost_contingency_rollup` @ `proforma_ledger:LEDGER-2031Q1/projects/PRJ-01/contingency_total_cents`  
  project PRJ-01 states a contingency total of 1,500,000.01; its lines sum to 1,500,000.00 (off 0.01)

### cost_per_nsf_wrong__Westmere_Urban_Partners

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `mgn_cost_per_nsf` @ `tieout_summary:SUMMARY-2031Q1/projects/PRJ-01/cost_per_nsf_cents`  
  project PRJ-01 states 210.01 per NSF; cost over 200000 NSF re-derives to 210.00

### cycle_count_wrong__Northmoor_Development_Group

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `rpt_cycle_count_ties` @ `cycle_report:CYCLE-2031Q1/filed_qpr_count`  
  the cycle report states 4 filed QPR(s); the filing register recomputes 3 for the active projects

### devbudget_wrong__Halbrook_Residential

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `cost_unlevered_ties_devbudget` @ `proforma_ledger:LEDGER-2031Q1/projects/PRJ-01/dev_cost_budget_cents`  
  project PRJ-01 carries a dev-cost budget of 40,000,000.01; the proforma's unlevered cost is 40,000,000.00 (unlevered-cost error 0.01)

### distributed_profit_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `wfl_distributed_ties_net` @ `tieout_summary:SUMMARY-2031Q1/projects/PRJ-01/distributed_profit_cents`  
  project PRJ-01 states distributed profit 10,000,000.01; net profit re-derives to 10,000,000.00 (off 0.01)

### equity_not_funded_first__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `int_equity_funded_before_construction` @ `proforma_ledger:LEDGER-2031Q1/projects/PRJ-01/equity_funded_before_construction`  
  project PRJ-01 does not fund its equity before construction; the loan was sized on the assumption that it does

### hard_soft_total_wrong__Westmere_Urban_Partners

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `cost_hard_soft_total` @ `tieout_summary:SUMMARY-2031Q1/projects/PRJ-01/total_project_cost_cents`  
  project PRJ-01 states total project cost 42,000,000.01; hard 30,000,000.00 plus soft 12,000,000.00 is 42,000,000.00 (off 0.01)

### interest_reserve_short__Northmoor_Development_Group

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `int_reserve_adequate` @ `proforma_ledger:LEDGER-2031Q1/projects/PRJ-01/interest_reserve_cents`  
  project PRJ-01 budgets 2,000,000.00 of interest against a reserve of 1,999,999.99; the reserve is short 0.01

### margin_on_cost_wrong__Halbrook_Residential

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `mgn_margin_on_cost` @ `tieout_summary:SUMMARY-2031Q1/projects/PRJ-01/margin_on_cost_bps`  
  project PRJ-01 quotes a margin on cost of 23.81%; net profit over cost re-derives to 23.80%

### margin_on_revenue_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `mgn_margin_on_revenue` @ `tieout_summary:SUMMARY-2031Q1/projects/PRJ-01/margin_on_revenue_bps`  
  project PRJ-01 quotes a margin on revenue of 19.24%; net profit over revenue re-derives to 19.23%

### missing_artifact__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `cycle_report:-`  
  cycle_report is missing; the controls that read it cannot run and must not be reported as having passed

### net_profit_wrong__Westmere_Urban_Partners

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `prof_net_profit_derivation` @ `tieout_summary:SUMMARY-2031Q1/projects/PRJ-01/net_profit_cents`  
  project PRJ-01 states net profit 10,000,000.01; revenue 52,000,000.00 less cost is 10,000,000.00 (off 0.01)

### profit_swing_material__Northmoor_Development_Group

**Verdict:** REVIEW (PASS 25, FLAG 1, FAIL 0)

- **FLAG** `var_materiality_flag` @ `tieout_summary:SUMMARY-2031Q1/projects/PRJ-01/variance/net_profit_cents`  
  project PRJ-01 swings net profit 3,000,000.00 against prior, beyond the 1,000,000.00 materiality band; the move is real and wants a reviewer

### qpr_late__Halbrook_Residential

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `rpt_qpr_due_date_gate` @ `filing_register:FILINGS-2031Q1/qpr_filings/PRJ-01/filed_date`  
  project PRJ-01 filed its QPR 2031-02-01, after the Marran due date 2031-01-22 (10 day(s) late)

### qpr_missing__Stonecrest_Communities

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `rpt_project_qpr_filed` @ `filing_register:FILINGS-2031Q1/qpr_filings/PRJ-02`  
  active project PRJ-02 has no QPR on file this cycle; the deck is incomplete without it

### regional_deliverable_missing__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `rpt_regional_deliverables_present` @ `filing_register:FILINGS-2031Q1/regional_filings/Marran/market_update`  
  region Marran did not file its market_update this cycle; the deck is incomplete without it

### schedule_variance_wrong__Westmere_Urban_Partners

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `var_schedule_days` @ `tieout_summary:SUMMARY-2031Q1/projects/PRJ-01/schedule_variance_days/construction_start`  
  project PRJ-01 milestone construction_start states a schedule variance of 15 day(s); current less baseline is 14 day(s)

### source_use_imbalance__Northmoor_Development_Group

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `src_source_use_balance` @ `proforma_ledger:LEDGER-2031Q1/projects/PRJ-01/uses`  
  project PRJ-01 funds 42,000,000.00 of sources against 42,250,000.00 of uses; the source-and-use error is -250,000.00, not zero

### sources_total_wrong__Halbrook_Residential

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `src_sources_total_ties` @ `tieout_summary:SUMMARY-2031Q1/projects/PRJ-01/total_sources_cents`  
  project PRJ-01 states total sources 42,000,000.01; its source lines sum to 42,000,000.00 (off 0.01)

### split_leaks__Stonecrest_Communities

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `wfl_split_completeness` @ `tieout_summary:SUMMARY-2031Q1/projects/PRJ-01/investor_profit_cents`  
  project PRJ-01 splits net profit into sponsor 3,000,000.00 plus investor 7,000,000.01 = 10,000,000.01; net profit is 10,000,000.00 (leakage 0.01)

### sponsor_share_wrong__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 2)

- **FAIL** `wfl_sponsor_share_derivation` @ `tieout_summary:SUMMARY-2031Q1/projects/PRJ-01/sponsor_profit_cents`  
  project PRJ-01 states a sponsor profit of 3,000,000.01; the equity split gives 3,000,000.00 (off 0.01)
- **FAIL** `wfl_split_completeness` @ `tieout_summary:SUMMARY-2031Q1/projects/PRJ-01/investor_profit_cents`  
  project PRJ-01 splits net profit into sponsor 3,000,000.01 plus investor 7,000,000.00 = 10,000,000.01; net profit is 10,000,000.00 (leakage 0.01)

### unlevered_profit_wrong__Westmere_Urban_Partners

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `prof_unlevered_profit_derivation` @ `tieout_summary:SUMMARY-2031Q1/projects/PRJ-01/unlevered_profit_cents`  
  project PRJ-01 states unlevered profit 12,000,000.01; revenue less unlevered cost is 12,000,000.00 (off 0.01)

### uses_total_wrong__Northmoor_Development_Group

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `src_uses_total_ties` @ `tieout_summary:SUMMARY-2031Q1/projects/PRJ-01/total_uses_cents`  
  project PRJ-01 states total uses 42,000,000.01; its use lines sum to 42,000,000.00 (off 0.01)

### variance_typed__Halbrook_Residential

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `var_metric_delta` @ `tieout_summary:SUMMARY-2031Q1/projects/PRJ-01/variance/net_profit_cents`  
  project PRJ-01 states a net_profit_cents variance of 500,000.01; current less prior is 500,000.00 (off 0.01)

### waterfall_profit_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `wfl_waterfall_ties_net` @ `tieout_summary:SUMMARY-2031Q1/projects/PRJ-01/waterfall_profit_cents`  
  project PRJ-01 states waterfall profit 10,000,000.01; net profit re-derives to 10,000,000.00 (off 0.01)
