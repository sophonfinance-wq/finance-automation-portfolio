# Intercompany reciprocity control report

**Overall verdict:** FAIL

- Period files analyzed: 25
- Controls in registry: 23
- PASS / REVIEW / FAIL: 1 / 4 / 20

All data is fictional. The engine is read-only and never writes to a source
artifact.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `set_period_label` | FAIL | 1 |
| 3 | `set_entities_exist` | FAIL | 1 |
| 4 | `ent_codes_unique` | FAIL | 1 |
| 5 | `ent_parent_defined` | FAIL | 1 |
| 6 | `ent_tree_acyclic` | FAIL | 2 |
| 7 | `rec_pairs_symmetric` | FAIL | 1 |
| 8 | `rec_amounts_reciprocal` | FAIL | 1 |
| 9 | `rec_no_self_balance` | FAIL | 2 |
| 10 | `led_parties_distinct` | FAIL | 1 |
| 11 | `led_amounts_positive` | FAIL | 2 |
| 12 | `led_totals_foot` | FAIL | 3 |
| 13 | `led_rollforward_ties` | FAIL | 3 |
| 14 | `led_dates_inside_window` | FLAG | 1 |
| 15 | `fund_equity_from_capital` | FAIL | 1 |
| 16 | `fund_region_matches` | FAIL | 1 |
| 17 | `fund_services_from_holdings` | FAIL | 1 |
| 18 | `fund_advance_flows_down` | FLAG | 2 |
| 19 | `liq_guarantor_minimum` | FAIL | 1 |
| 20 | `liq_no_negative_cash` | FAIL | 1 |
| 21 | `liq_target_band` | FLAG | 2 |
| 22 | `appr_ledger_approved` | FAIL | 1 |
| 23 | `appr_large_advance_flagged` | FLAG | 2 |

## Period files

### advance_upstream__Calderwood_Holdings

**Verdict:** REVIEW (PASS 22, FLAG 1, FAIL 0)

- **FLAG** `fund_advance_flows_down` @ `intercompany_ledger:LDG-2028-Q2/transactions/13/to_entity`  
  advance 13 runs from NWCP to WCAP (up the chain); an advance that is not to a descendant is often a distribution or sweep and wants classifying

### amount_not_integer__Westmere_Development_Group

**Verdict:** FAIL (PASS 19, FLAG 1, FAIL 5)

- **FAIL** `led_amounts_positive` @ `amount:ledger.transactions[5].amount_cents`  
  AMOUNT_INVALID: ledger.transactions[5].amount_cents must be integer cents, got 10000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `led_totals_foot` @ `amount:ledger.transactions[5].amount_cents`  
  AMOUNT_INVALID: ledger.transactions[5].amount_cents must be integer cents, got 10000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `led_totals_foot` @ `intercompany_ledger:LDG-2028-Q2/totals/advance_cents`  
  advance lines sum to 435,000.00 but the ledger declares 535,000.00 (difference -100,000.00)
- **FAIL** `led_rollforward_ties` @ `amount:ledger.transactions[5].amount_cents`  
  AMOUNT_INVALID: ledger.transactions[5].amount_cents must be integer cents, got 10000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `led_rollforward_ties` @ `due_from_schedule:DF-2028-Q2/positions/WCAP->NWCP`  
  WCAP->NWCP: opening 180,000.00 plus advances 0.00 less repayments 0.00 = 120,000.00, but the closing balance is 220,000.00
- **FLAG** `appr_large_advance_flagged` @ `amount:ledger.transactions[5].amount_cents`  
  AMOUNT_INVALID: ledger.transactions[5].amount_cents must be integer cents, got 10000000.5 -- amounts are integer cents and are never coerced

### bad_period_label__Ashfield_US_Group

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `set_period_label` @ `file:bad_period_label__Ashfield_US_Group/period`  
  reporting period '2028-06' is not a YYYY-Qn label; every intercompany schedule is filed against a quarter and cannot be placed without one

### clean__Rivermont_US_Group

**Verdict:** PASS (PASS 23, FLAG 0, FAIL 0)

All controls held.

### dangling_parent__Rivermont_US_Group

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `ent_parent_defined` @ `entity_register:REG-2028/entities/WCAP/parent`  
  entity 'WCAP' names parent 'NOPE', which is not in the register

### duplicate_entity_code__Calderwood_Holdings

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `ent_codes_unique` @ `entity_register:REG-2028/entities/NWCP`  
  entity code 'NWCP' appears 2 times in the register; codes must be unique or a balance keyed on it is ambiguous

### equity_from_services__Westmere_Development_Group

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `fund_equity_from_capital` @ `intercompany_ledger:LDG-2028-Q2/transactions/11/from_entity`  
  equity funding 11 for 'Ballard Yard' comes from NWSV (Services), but project equity must be funded from the Capital group

### guarantor_short__Ashfield_US_Group

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `liq_guarantor_minimum` @ `liquidity_positions:LIQ-2028-Q2/positions/WCAP`  
  the guarantor WCAP holds 8,000,000.00, below its 10,000,000.00 minimum liquidity covenant (short 2,000,000.00)

### large_advance__Rivermont_US_Group

**Verdict:** REVIEW (PASS 22, FLAG 1, FAIL 0)

- **FLAG** `appr_large_advance_flagged` @ `intercompany_ledger:LDG-2028-Q2/transactions/13/amount_cents`  
  advance 13 of 600,000.00 meets the 500,000.00 second-signature threshold and should be reviewed before funding

### missing_artifact__Calderwood_Holdings

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `file:missing_artifact__Calderwood_Holdings/liquidity_positions`  
  period file carries no liquidity_positions; absent evidence is not a passing control, so no downstream rule may read it

### negative_amount__Westmere_Development_Group

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `led_amounts_positive` @ `intercompany_ledger:LDG-2028-Q2/transactions/13/amount_cents`  
  transaction 13 carries a non-positive amount -1.00; direction is carried by the type and the parties, not the sign

### negative_cash__Ashfield_US_Group

**Verdict:** FAIL (PASS 21, FLAG 1, FAIL 1)

- **FAIL** `liq_no_negative_cash` @ `liquidity_positions:LIQ-2028-Q2/positions/NWSV`  
  entity NWSV reports negative cash -5,000.00; a bank balance cannot be overdrawn on the books
- **FLAG** `liq_target_band` @ `liquidity_positions:LIQ-2028-Q2/positions/NWSV`  
  NWSV holds -5,000.00, below its target band floor of 200,000.00; it is undercapitalised for the cash it should carry

### orphan_due_to__Rivermont_US_Group

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `rec_pairs_symmetric` @ `due_to_schedule:DT-2028-Q2/positions/NWCP->PRED`  
  NWCP books a due-to against PRED, but PRED books no due-from against NWCP; the receivable side is missing

### parent_cycle__Calderwood_Holdings

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 2)

- **FAIL** `ent_tree_acyclic` @ `entity_register:REG-2028/entities/AAAA/parent`  
  the ownership chain from 'AAAA' cycles through 'AAAA' and never reaches the top parent; the group has no root
- **FAIL** `ent_tree_acyclic` @ `entity_register:REG-2028/entities/BBBB/parent`  
  the ownership chain from 'BBBB' cycles through 'BBBB' and never reaches the top parent; the group has no root

### reciprocity_off__Westmere_Development_Group

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `rec_amounts_reciprocal` @ `due_from_schedule:DF-2028-Q2/positions/HOLD->PRED`  
  HOLD books a due-from of 450,000.00 against PRED, but PRED books a due-to of 450,500.00 against HOLD (difference -500.00); the balance will not eliminate on consolidation

### region_mismatch__Ashfield_US_Group

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `fund_region_matches` @ `intercompany_ledger:LDG-2028-Q2/transactions/11/from_entity`  
  equity funding 11 for a Seattle project comes from SWCP (region 'SoCal'); the funding entity's region must match the project's

### rollforward_off__Rivermont_US_Group

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `led_rollforward_ties` @ `due_from_schedule:DF-2028-Q2/positions/WCAP->NWCP`  
  WCAP->NWCP: opening 180,000.00 plus advances 100,000.00 less repayments 0.00 = 220,000.00, but the closing balance is 221,000.00

### same_party__Calderwood_Holdings

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `led_parties_distinct` @ `intercompany_ledger:LDG-2028-Q2/transactions/13/to_entity`  
  repayment 13 moves cash from HOLD to itself; an entity cannot advance to or repay itself

### self_balance__Westmere_Development_Group

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 2)

- **FAIL** `rec_no_self_balance` @ `due_from_schedule:DF-2028-Q2/positions/SWCP`  
  entity 'SWCP' books a due-from against itself; a counterparty has been mis-keyed
- **FAIL** `rec_no_self_balance` @ `due_to_schedule:DT-2028-Q2/positions/SWCP`  
  entity 'SWCP' books a due-to against itself; a counterparty has been mis-keyed

### services_from_capital__Ashfield_US_Group

**Verdict:** FAIL (PASS 21, FLAG 1, FAIL 1)

- **FAIL** `fund_services_from_holdings` @ `intercompany_ledger:LDG-2028-Q2/transactions/13/from_entity`  
  advance 13 funds NWSV (Services) from WCAP, but Services and predevelopment funding must come from the top parent 'HOLD'
- **FLAG** `fund_advance_flows_down` @ `intercompany_ledger:LDG-2028-Q2/transactions/13/to_entity`  
  advance 13 runs from WCAP to NWSV (across the tree); an advance that is not to a descendant is often a distribution or sweep and wants classifying

### target_breach__Rivermont_US_Group

**Verdict:** REVIEW (PASS 22, FLAG 1, FAIL 0)

- **FLAG** `liq_target_band` @ `liquidity_positions:LIQ-2028-Q2/positions/NWCP`  
  NWCP holds 50,000.00, below its target band floor of 200,000.00; it is undercapitalised for the cash it should carry

### totals_off__Calderwood_Holdings

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `led_totals_foot` @ `intercompany_ledger:LDG-2028-Q2/totals/advance_cents`  
  advance lines sum to 535,000.00 but the ledger declares 536,000.00 (difference -1,000.00)

### txn_outside_window__Westmere_Development_Group

**Verdict:** REVIEW (PASS 22, FLAG 1, FAIL 0)

- **FLAG** `led_dates_inside_window` @ `intercompany_ledger:LDG-2028-Q2/transactions/1/txn_date`  
  transaction 1 is dated 2028-08-15, outside the 2028-04-01..2028-06-30 window

### unapproved__Ashfield_US_Group

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `appr_ledger_approved` @ `intercompany_ledger:LDG-2028-Q2/approved_by`  
  the intercompany ledger carries no approver; cash moved between entities without a sign-off

### unknown_entity__Rivermont_US_Group

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `set_entities_exist` @ `entity_register/ZZZZ`  
  code 'ZZZZ' is used at liquidity.entity but is not in the entity register; a position on an unregistered entity cannot be reconciled or eliminated
