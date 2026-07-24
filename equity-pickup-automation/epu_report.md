# Equity-method pickup & eliminations control report

**Overall verdict:** FAIL

- Consolidation files analyzed: 27
- Controls in registry: 25
- PASS / REVIEW / FAIL: 1 / 1 / 25

All data is fictional. The engine is read-only and never writes to a source
artifact. Every share, roll-forward, accrual and tie is re-derived in exact
integer cents against the figures carried in the file, never estimated.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `rf_identity` | FAIL | 2 |
| 3 | `rf_row_has_holding` | FAIL | 1 |
| 4 | `rf_coverage_complete` | FAIL | 1 |
| 5 | `rf_distributions_rederive` | FAIL | 1 |
| 6 | `epu_pickup_rederives` | FAIL | 2 |
| 7 | `epu_cost_no_pickup` | FAIL | 1 |
| 8 | `epu_ownership_bounds` | FAIL | 2 |
| 9 | `epu_refs_resolve` | FAIL | 1 |
| 10 | `elim_block_balances` | FAIL | 1 |
| 11 | `elim_pairing_complete` | FAIL | 1 |
| 12 | `elim_extinguishes_investment` | FAIL | 1 |
| 13 | `elim_refs_known` | FAIL | 1 |
| 14 | `elim_account_link_key` | FAIL | 1 |
| 15 | `pref_day_count` | FAIL | 1 |
| 16 | `pref_accrual_rederives` | FAIL | 1 |
| 17 | `pref_capital_chains` | FAIL | 2 |
| 18 | `pref_periods_contiguous` | FAIL | 1 |
| 19 | `alloc_foots` | FAIL | 1 |
| 20 | `alloc_ties_net_income` | FAIL | 1 |
| 21 | `alloc_member_is_holder` | FAIL | 1 |
| 22 | `alloc_tb_investment_ties` | FAIL | 1 |
| 23 | `alloc_tb_pickup_ties` | FAIL | 1 |
| 24 | `alloc_tb_adjustment_math` | FAIL | 1 |
| 25 | `alloc_tb_unposted_adjustment` | FLAG | 1 |

## Consolidation files

### account_convention_broken__Westmere_Combined_Reporting_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `elim_account_link_key` @ `holding_register:HOLDINGS-FY2030/holdings/HLD-03/investment_account`  
  holding HLD-03 books its investment at '100-1999'; the code link key derives 100-1322 from parent 100 and sub 322, and the pairing is only mechanical while it holds

### allocation_misfooted__Stonecrest_Reporting_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `alloc_foots` @ `allocation_summary:ALLOC-FY2030/entries/SUB-322/stated_total_cents`  
  the SUB-322 allocation states a total of 914,001.00; its member rows sum to 914,000.00 (off by 1.00)

### allocation_short_of_income__Ardenne_Field_Reporting_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `alloc_ties_net_income` @ `allocation_summary:ALLOC-FY2030/entries/SUB-285/members`  
  the SUB-285 member allocations sum to 482,451.37; the sub earned 482,501.37, leaving 50.00 of income belonging to nobody

### allocation_stranger_member__Northmoor_Consolidated_Reporting_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `alloc_member_is_holder` @ `allocation_summary:ALLOC-FY2030/entries/SUB-322/members/PAR-777`  
  the SUB-322 allocation includes member 'PAR-777', which holds no equity interest in SUB-322; income is landing in books with no ownership behind them

### amount_not_integer__Westmere_Combined_Reporting_Group

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 2)

- **FAIL** `rf_identity` @ `amount:rollforward[HLD-01].pickup_cents`  
  AMOUNT_INVALID: rollforward[HLD-01].pickup_cents must be integer cents, got 24125068.5 -- amounts are integer cents and are never coerced
- **FAIL** `epu_pickup_rederives` @ `amount:rollforward[HLD-01].pickup_cents`  
  AMOUNT_INVALID: rollforward[HLD-01].pickup_cents must be integer cents, got 24125068.5 -- amounts are integer cents and are never coerced

### clean__Northmoor_Consolidated_Reporting_Group

**Verdict:** PASS (PASS 25, FLAG 0, FAIL 0)

All controls held.

### cost_method_pickup_booked__Stonecrest_Reporting_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `epu_cost_no_pickup` @ `investment_rollforward:ROLLFWD-FY2030/rows/HLD-06/pickup_cents`  
  holding HLD-06 is carried at cost yet rolls pickup 4,800.00 and distributions 0.00 through the investment; a cost-method carrying value moves only by contributions

### distributions_share_wrong__Ardenne_Field_Reporting_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `rf_distributions_rederive` @ `investment_rollforward:ROLLFWD-FY2030/rows/HLD-01/distributions_cents`  
  holding HLD-01 states distributions 100,500.00; its ownership share of the 200,000.00 the sub declared re-derives 100,000.00 (off by 500.00)

### elimination_missing__Northmoor_Consolidated_Reporting_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `elim_pairing_complete` @ `elimination_schedule:ELIM-FY2030/blocks/HLD-02`  
  equity holding HLD-02 has no elimination block; its investment and the sub's equity both survive into consolidation, double-counting the same net assets

### elimination_unbalanced__Westmere_Combined_Reporting_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `elim_block_balances` @ `elimination_schedule:ELIM-FY2030/blocks/EB-03`  
  block EB-03 debits 3,014,250.00 against credits 3,014,000.00 (off by 250.00); an elimination that does not balance moves the consolidated totals

### elimination_understated__Stonecrest_Reporting_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `elim_extinguishes_investment` @ `elimination_schedule:ELIM-FY2030/blocks/EB-01/lines`  
  block EB-01 credits 100-1285 1,890,250.68; the roll-forward carries 1,891,250.68, leaving 1,000.00 of holding HLD-01 unextinguished on consolidation

### holding_parent_unknown__Ardenne_Field_Reporting_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `epu_refs_resolve` @ `holding_register:HOLDINGS-FY2030/holdings/HLD-01/parent_id`  
  holding HLD-01 names parent 'PAR-999', which is not a registered parent entity

### missing_artifact__Northmoor_Consolidated_Reporting_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `trial_balance:-`  
  trial_balance is missing; the controls that read it cannot run and must not be reported as having passed

### orphan_elimination_block__Westmere_Combined_Reporting_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `elim_refs_known` @ `elimination_schedule:ELIM-FY2030/blocks/EB-99/holding_id`  
  block EB-99 eliminates holding 'HLD-99', which is not in the holding register; it cancels an interest nobody holds

### orphan_rollforward_row__Stonecrest_Reporting_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `rf_row_has_holding` @ `investment_rollforward:ROLLFWD-FY2030/rows/HLD-99/holding_id`  
  roll-forward row names holding 'HLD-99', which is not in the holding register; its carrying value belongs to nobody

### ownership_over_allocated__Ardenne_Field_Reporting_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 2)

- **FAIL** `epu_ownership_bounds` @ `holding_register:HOLDINGS-FY2030/holdings/HLD-04/ownership_bps`  
  holding HLD-04 states ownership 10500 bps; a holding owns more than 0 and at most 10000 bps of its sub
- **FAIL** `epu_ownership_bounds` @ `holding_register:HOLDINGS-FY2030/holdings/SUB-160/ownership_bps`  
  the holders of SUB-160 claim 14500 bps between them; a sub has exactly 10000 bps to give

### pickup_not_rederived__Northmoor_Consolidated_Reporting_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `epu_pickup_rederives` @ `investment_rollforward:ROLLFWD-FY2030/rows/HLD-04/pickup_cents`  
  holding HLD-04 books pickup -50,561.00; ownership x sub net income re-derives -50,661.00 (off by 100.00)

### pref_accrual_overstated__Westmere_Combined_Reporting_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `pref_accrual_rederives` @ `preferred_return_schedule:PREF-FY2030/schedules/MBR-02/rows/2/accrued_cents`  
  schedule MBR-02 row 2 states accrued 31,858.90; 1,800,000.00 x 700 bps x 92/365 re-derives 31,758.90 (off by 100.00)

### pref_capital_chain_broken__Stonecrest_Reporting_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 2)

- **FAIL** `pref_capital_chains` @ `preferred_return_schedule:PREF-FY2030/schedules/MBR-01/rows/2/ending_capital_cents`  
  schedule MBR-01 row 2 ends at 3,001,000.00; opening 2,500,000.00 + contribution 500,000.00 re-derives 3,000,000.00 -- the return does not compound into capital
- **FAIL** `pref_capital_chains` @ `preferred_return_schedule:PREF-FY2030/schedules/MBR-01/rows/3/opening_capital_cents`  
  schedule MBR-01 row 3 opens at 3,000,000.00; the chain carries 3,001,000.00 forward from the prior period (off by -1,000.00)

### pref_days_misstated__Ardenne_Field_Reporting_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `pref_day_count` @ `preferred_return_schedule:PREF-FY2030/schedules/MBR-01/rows/3/days`  
  schedule MBR-01 row 3 states 91 day(s); 2030-01-01..2030-03-31 counted inclusively is 90

### pref_period_gap__Northmoor_Consolidated_Reporting_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `pref_periods_contiguous` @ `preferred_return_schedule:PREF-FY2030/schedules/MBR-02/rows/3/start_date`  
  schedule MBR-02 row 3 starts 2030-01-03 but the prior period ended 2029-12-31; the handover leaves 2 unaccrued day(s)

### rollforward_identity_broken__Westmere_Combined_Reporting_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `rf_identity` @ `investment_rollforward:ROLLFWD-FY2030/rows/HLD-03/end_cents`  
  holding HLD-03 states end 3,014,000.00; begin 2,400,000.00 + contributions 100.00 + pickup 914,000.00 - distributions 300,000.00 re-derives 3,014,100.00 (off by -100.00)

### rollforward_row_missing__Stonecrest_Reporting_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `rf_coverage_complete` @ `investment_rollforward:ROLLFWD-FY2030/rows/HLD-02`  
  holding HLD-02 has 0 roll-forward row(s); every holding carries exactly one, or its carrying value cannot be tied

### tb_adjustment_math_wrong__Ardenne_Field_Reporting_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `alloc_tb_adjustment_math` @ `trial_balance:TB-FY2030/rows/SUB-285/285-2999/adjustment_cents`  
  account 285-2999 on SUB-285 states adjustment 0.00; should-be -803,000.00 minus balance -800,000.00 re-derives -3,000.00

### tb_investment_break__Northmoor_Consolidated_Reporting_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `alloc_tb_investment_ties` @ `trial_balance:TB-FY2030/rows/PAR-100/100-1322/balance_cents`  
  account 100-1322 carries 3,016,000.00 on the trial balance; holding HLD-03's roll-forward ends at 3,014,000.00 (off by 2,000.00)

### tb_pickup_break__Westmere_Combined_Reporting_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `alloc_tb_pickup_ties` @ `trial_balance:TB-FY2030/rows/PAR-100/100-3285/balance_cents`  
  pickup account 100-3285 carries -241,249.68; ownership x sub net income re-derives a credit of -241,250.68 (off by 1.00)

### tb_unposted_adjustment__Stonecrest_Reporting_Group

**Verdict:** REVIEW (PASS 24, FLAG 1, FAIL 0)

- **FLAG** `alloc_tb_unposted_adjustment` @ `trial_balance:TB-FY2030/rows/SUB-322/322-2999/adjustment_cents`  
  account 322-2999 on SUB-322 carries an unposted adjustment of 1,500.00; the correction is derived but the books still show the old figure -- due for a human's entry
