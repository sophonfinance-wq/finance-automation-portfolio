# Home-sale closing & settlement tie-out report

**Overall verdict:** FAIL

- Closing files analyzed: 27
- Controls in registry: 25
- PASS / REVIEW / FAIL: 1 / 2 / 24

All data is fictional. The engine is read-only and never writes to a source
artifact. Every figure is recomputed from the closing package underneath it,
never trusted as stated.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `unit_unique_ids` | FAIL | 1 |
| 3 | `unit_status_valid` | FAIL | 1 |
| 4 | `unit_required_fields` | FAIL | 1 |
| 5 | `unit_artifacts_complete` | FAIL | 1 |
| 6 | `je_unit_exists` | FAIL | 1 |
| 7 | `je_balances` | FAIL | 2 |
| 8 | `je_ar_plug_recomputes` | FAIL | 2 |
| 9 | `ss_total_charges_recompute` | FAIL | 2 |
| 10 | `ss_total_closing_costs_recompute` | FAIL | 2 |
| 11 | `ss_net_to_seller_recompute` | FAIL | 2 |
| 12 | `fee_listing_sales_rederives` | FAIL | 1 |
| 13 | `fee_warranty_reserve_rederives` | FAIL | 1 |
| 14 | `fee_broker_commission_variance` | FLAG | 2 |
| 15 | `fee_concessions_within_assumption` | FLAG | 1 |
| 16 | `rev_recognized_in_coe_month` | FAIL | 1 |
| 17 | `rev_deferred_upgrade_reversed` | FAIL | 1 |
| 18 | `loan_ending_recomputes` | FAIL | 1 |
| 19 | `loan_ties_lender_statement` | FAIL | 1 |
| 20 | `loan_release_price_covered` | FAIL | 1 |
| 21 | `cos_margin_recompute` | FAIL | 1 |
| 22 | `cos_prepaid_commission_relief_cap` | FAIL | 1 |
| 23 | `rpt_closed_count_ties` | FAIL | 2 |
| 24 | `rpt_net_to_seller_total_ties` | FAIL | 4 |
| 25 | `rpt_unit_tied_recomputes` | FAIL | 15 |

## Closing files

### amount_not_integer__Halbrook_Residential

**Verdict:** FAIL (PASS 19, FLAG 1, FAIL 5)

- **FAIL** `ss_total_charges_recompute` @ `amount:settlement.broker_commission_cents`  
  AMOUNT_INVALID: settlement.broker_commission_cents must be integer cents, got 2880000.5 -- amounts are integer cents and are never coerced
- **FAIL** `ss_total_closing_costs_recompute` @ `amount:settlement.broker_commission_cents`  
  AMOUNT_INVALID: settlement.broker_commission_cents must be integer cents, got 2880000.5 -- amounts are integer cents and are never coerced
- **FAIL** `ss_net_to_seller_recompute` @ `amount:settlement.broker_commission_cents`  
  AMOUNT_INVALID: settlement.broker_commission_cents must be integer cents, got 2880000.5 -- amounts are integer cents and are never coerced
- **FLAG** `fee_broker_commission_variance` @ `amount:settlement.broker_commission_cents`  
  AMOUNT_INVALID: settlement.broker_commission_cents must be integer cents, got 2880000.5 -- amounts are integer cents and are never coerced
- **FAIL** `rpt_net_to_seller_total_ties` @ `amount:settlement.broker_commission_cents`  
  AMOUNT_INVALID: settlement.broker_commission_cents must be integer cents, got 2880000.5 -- amounts are integer cents and are never coerced
- **FAIL** `rpt_unit_tied_recomputes` @ `amount:settlement.broker_commission_cents`  
  AMOUNT_INVALID: settlement.broker_commission_cents must be integer cents, got 2880000.5 -- amounts are integer cents and are never coerced

### ar_plug_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 3)

- **FAIL** `je_balances` @ `closing_je_register:CLOSING-JE-2029/entries/JE-U-102`  
  closing entry JE-U-102 for unit U-102 posts 669,000.00 debits against 659,000.00 credits; the entry does not foot (off 10,000.00)
- **FAIL** `je_ar_plug_recomputes` @ `closing_je_register:CLOSING-JE-2029/entries/JE-U-102/Accounts_Receivable`  
  closing entry JE-U-102 for unit U-102 states an Accounts Receivable of 610,800.00; the derived plug is 600,800.00 (off 10,000.00)
- **FAIL** `rpt_unit_tied_recomputes` @ `closing_summary:SUMMARY-2029/units/U-102/tied`  
  unit U-102 is summarised tied=True; recomputing from its closing package gives tied=False

### artifacts_incomplete__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 3)

- **FAIL** `unit_artifacts_complete` @ `unit_register:UNITS-2029/units/U-102`  
  closed unit U-102 has 0 settlement rows; a complete package carries exactly one
- **FAIL** `rpt_net_to_seller_total_ties` @ `closing_report:REPORT-2029/total_net_to_seller_cents`  
  the report states a total net to seller of 2,816,075.00; the settlements recompute 2,224,275.00 (off 591,800.00)
- **FAIL** `rpt_unit_tied_recomputes` @ `closing_summary:SUMMARY-2029/units/U-102/tied`  
  unit U-102 is summarised tied=True; recomputing from its closing package gives tied=False

### bad_unit_status__Northmoor_Development_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `unit_status_valid` @ `unit_register:UNITS-2029/units/U-105/status`  
  unit U-105 is status 'pending', which is not one of ('unsold', 'sold', 'closed')

### broker_commission_varies__Halbrook_Residential

**Verdict:** REVIEW (PASS 24, FLAG 1, FAIL 0)

- **FLAG** `fee_broker_commission_variance` @ `settlement_register:SETTLEMENT-2029/settlements/U-103/broker_commission_cents`  
  unit U-103 books a broker commission of 28,600.00; the proforma assumption of 3.60% is 26,100.00 (variance 2,500.00) -- confirm the negotiated rate

### clean__Northmoor_Development_Group

**Verdict:** PASS (PASS 25, FLAG 0, FAIL 0)

All controls held.

### closed_count_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `rpt_closed_count_ties` @ `closing_report:REPORT-2029/closed_count`  
  the report states 3 closed unit(s); the register has 4

### concessions_over_allowance__Ardenne_Field_Partners

**Verdict:** REVIEW (PASS 24, FLAG 1, FAIL 0)

- **FLAG** `fee_concessions_within_assumption` @ `settlement_register:SETTLEMENT-2029/settlements/U-104/concessions_cents`  
  unit U-104 grants concessions of 5,400.00; the proforma allowance of 0.50% is 4,500.00 (over by 900.00) -- confirm the concession

### cos_margin_wrong__Northmoor_Development_Group

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 2)

- **FAIL** `cos_margin_recompute` @ `cos_schedule:COS-2029/entries/U-101/revised_profit_cents`  
  unit U-101 states a revised project profit of 115,000.00; projected profit plus carry costs is 105,000.00 (off 10,000.00)
- **FAIL** `rpt_unit_tied_recomputes` @ `closing_summary:SUMMARY-2029/units/U-101/tied`  
  unit U-101 is summarised tied=True; recomputing from its closing package gives tied=False

### deferred_upgrade_wrong__Halbrook_Residential

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 2)

- **FAIL** `rev_deferred_upgrade_reversed` @ `revenue_schedule:REVREC-2029/entries/U-104/deferred_upgrade_reversed_cents`  
  unit U-104 reverses 20,500.00 of deferred upgrade revenue; the unit's deferred balance is 20,000.00 (off 500.00)
- **FAIL** `rpt_unit_tied_recomputes` @ `closing_summary:SUMMARY-2029/units/U-104/tied`  
  unit U-104 is summarised tied=True; recomputing from its closing package gives tied=False

### duplicate_unit_id__Stonecrest_Communities

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 3)

- **FAIL** `unit_unique_ids` @ `unit_register:UNITS-2029/units/U-101`  
  unit id U-101 appears 2 times; a settlement that names it cannot be attributed to one home
- **FAIL** `rpt_closed_count_ties` @ `closing_report:REPORT-2029/closed_count`  
  the report states 4 closed unit(s); the register has 5
- **FAIL** `rpt_net_to_seller_total_ties` @ `closing_report:REPORT-2029/total_net_to_seller_cents`  
  the report states a total net to seller of 2,816,075.00; the settlements recompute 3,549,625.00 (off -733,550.00)

### je_does_not_foot__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 3)

- **FAIL** `je_balances` @ `closing_je_register:CLOSING-JE-2029/entries/JE-U-101`  
  closing entry JE-U-101 for unit U-101 posts 825,000.00 debits against 815,000.00 credits; the entry does not foot (off 10,000.00)
- **FAIL** `je_ar_plug_recomputes` @ `closing_je_register:CLOSING-JE-2029/entries/JE-U-101/Accounts_Receivable`  
  closing entry JE-U-101 for unit U-101 states an Accounts Receivable of 748,550.00; the derived plug is 738,550.00 (off 10,000.00)
- **FAIL** `rpt_unit_tied_recomputes` @ `closing_summary:SUMMARY-2029/units/U-101/tied`  
  unit U-101 is summarised tied=True; recomputing from its closing package gives tied=False

### je_unknown_unit__Northmoor_Development_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `je_unit_exists` @ `closing_je_register:CLOSING-JE-2029/entries/JE-U-999/unit_id`  
  closing entry JE-U-999 names unit 'U-999', which is not in the unit register

### listing_off_rate__Halbrook_Residential

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `fee_listing_sales_rederives` @ `settlement_register:SETTLEMENT-2029/settlements/U-101/listing_sales_fee_cents`  
  unit U-101 states an LISTING sales fee of 5,000.00; 0.50% of gross is 4,000.00 (off 1,000.00)

### loan_does_not_tie__Stonecrest_Communities

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 2)

- **FAIL** `loan_ties_lender_statement` @ `loan_release_register:LOAN-2029/releases/U-102/lender_statement_ending_cents`  
  unit U-102 carries a loan ending balance of 508,000.00; the lender statement shows 518,000.00 (off -10,000.00)
- **FAIL** `rpt_unit_tied_recomputes` @ `closing_summary:SUMMARY-2029/units/U-102/tied`  
  unit U-102 is summarised tied=True; recomputing from its closing package gives tied=False

### loan_ending_wrong__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 2)

- **FAIL** `loan_ending_recomputes` @ `loan_release_register:LOAN-2029/releases/U-101/ending_balance_cents`  
  unit U-101 states a loan ending balance of 518,000.00; the roll-forward gives 508,000.00 (off 10,000.00)
- **FAIL** `rpt_unit_tied_recomputes` @ `closing_summary:SUMMARY-2029/units/U-101/tied`  
  unit U-101 is summarised tied=True; recomputing from its closing package gives tied=False

### missing_artifact__Northmoor_Development_Group

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `closing_report:-`  
  closing_report is missing; the controls that read it cannot run and must not be reported as having passed

### net_to_seller_wrong__Halbrook_Residential

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 2)

- **FAIL** `ss_net_to_seller_recompute` @ `settlement_register:SETTLEMENT-2029/settlements/U-103/net_to_seller_cents`  
  unit U-103 states net to seller of 672,675.00; gross less settlement charges is 662,675.00 (off 10,000.00)
- **FAIL** `rpt_unit_tied_recomputes` @ `closing_summary:SUMMARY-2029/units/U-103/tied`  
  unit U-103 is summarised tied=True; recomputing from its closing package gives tied=False

### net_total_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `rpt_net_to_seller_total_ties` @ `closing_report:REPORT-2029/total_net_to_seller_cents`  
  the report states a total net to seller of 2,826,075.00; the settlements recompute 2,816,075.00 (off 10,000.00)

### prepaid_relief_over_cap__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 2)

- **FAIL** `cos_prepaid_commission_relief_cap` @ `cos_schedule:COS-2029/entries/U-102/prepaid_relieved_cents`  
  unit U-102 relieves 21,000.00 of prepaid commission; MIN(earned 23,400.00, prepaid 20,000.00) is 20,000.00 (off 1,000.00)
- **FAIL** `rpt_unit_tied_recomputes` @ `closing_summary:SUMMARY-2029/units/U-102/tied`  
  unit U-102 is summarised tied=True; recomputing from its closing package gives tied=False

### release_price_short__Northmoor_Development_Group

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `loan_release_price_covered` @ `loan_release_register:LOAN-2029/releases/U-103/bank_remittance_cents`  
  unit U-103 remits 10,000.00 to the bank; the scheduled release price is 11,000.00 (short 1,000.00)

### revenue_wrong_month__Halbrook_Residential

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 2)

- **FAIL** `rev_recognized_in_coe_month` @ `revenue_schedule:REVREC-2029/entries/U-103/recognized_month`  
  unit U-103 recognises revenue in '2029-03'; close of escrow is 2029-02-05, so it must land in '2029-02'
- **FAIL** `rpt_unit_tied_recomputes` @ `closing_summary:SUMMARY-2029/units/U-103/tied`  
  unit U-103 is summarised tied=True; recomputing from its closing package gives tied=False

### tied_flag_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `rpt_unit_tied_recomputes` @ `closing_summary:SUMMARY-2029/units/U-101/tied`  
  unit U-101 is summarised tied=False; recomputing from its closing package gives tied=True

### total_charges_wrong__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 2)

- **FAIL** `ss_total_charges_recompute` @ `settlement_register:SETTLEMENT-2029/settlements/U-101/total_settlement_charges_cents`  
  unit U-101 states total settlement charges of 76,450.00; the components sum to 66,450.00 (off 10,000.00)
- **FAIL** `rpt_unit_tied_recomputes` @ `closing_summary:SUMMARY-2029/units/U-101/tied`  
  unit U-101 is summarised tied=True; recomputing from its closing package gives tied=False

### total_closing_costs_wrong__Northmoor_Development_Group

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 2)

- **FAIL** `ss_total_closing_costs_recompute` @ `settlement_register:SETTLEMENT-2029/settlements/U-102/total_closing_costs_cents`  
  unit U-102 states total closing costs of 44,800.00; charges less broker commission is 34,800.00 (off 10,000.00)
- **FAIL** `rpt_unit_tied_recomputes` @ `closing_summary:SUMMARY-2029/units/U-102/tied`  
  unit U-102 is summarised tied=True; recomputing from its closing package gives tied=False

### unit_missing_field__Halbrook_Residential

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 2)

- **FAIL** `unit_required_fields` @ `unit_register:UNITS-2029/units/U-103`  
  closed unit U-103 is missing coe_date; its closing cannot be recomputed
- **FAIL** `rpt_unit_tied_recomputes` @ `closing_summary:SUMMARY-2029/units/U-103/tied`  
  unit U-103 is summarised tied=True; recomputing from its closing package gives tied=False

### warranty_off_rate__Stonecrest_Communities

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `fee_warranty_reserve_rederives` @ `settlement_register:SETTLEMENT-2029/settlements/U-102/warranty_reserve_cents`  
  unit U-102 states a warranty reserve of 7,500.00; 1.00% of gross is 6,500.00 (off 1,000.00)
