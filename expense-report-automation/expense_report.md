# Expense & P-Card control report

**Overall verdict:** FAIL

- Cycle files analyzed: 24
- Controls in registry: 23
- PASS / REVIEW / FAIL: 1 / 2 / 21

All data is fictional. The engine is read-only and never writes to a source
artifact. Every window and ageing test is made against the `as_of` date carried
in the file, never the system clock.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `card_required_fields` | FAIL | 1 |
| 3 | `card_id_unique` | FAIL | 1 |
| 4 | `card_last4_valid` | FAIL | 1 |
| 5 | `card_home_entity_known` | FAIL | 1 |
| 6 | `stmt_required_fields` | FAIL | 1 |
| 7 | `stmt_line_unique` | FAIL | 1 |
| 8 | `stmt_amounts_integer` | FAIL | 1 |
| 9 | `stmt_last4_matches_card` | FAIL | 4 |
| 10 | `rpt_required_fields` | FAIL | 1 |
| 11 | `rpt_receipt_on_file` | FAIL | 1 |
| 12 | `rpt_purpose_present` | FAIL | 1 |
| 13 | `rec_every_charge_reported` | FAIL | 5 |
| 14 | `rec_no_orphan_report_line` | FAIL | 2 |
| 15 | `rec_report_total_ties` | FAIL | 3 |
| 16 | `rec_gl_ties_reports` | FAIL | 3 |
| 17 | `cod_gl_valid` | FAIL | 1 |
| 18 | `cod_project_exists` | FAIL | 1 |
| 19 | `cod_disallowed_category` | FLAG | 1 |
| 20 | `pol_submitted_within_window` | FLAG | 1 |
| 21 | `pol_per_charge_limit` | FAIL | 2 |
| 22 | `pol_approver_distinct` | FAIL | 1 |
| 23 | `dup_no_duplicate_charge` | FAIL | 1 |

## Expense files

### amount_not_integer__Halbrook_Residential

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 4)

- **FAIL** `stmt_amounts_integer` @ `amount:statement[STMT-2909-01/L-0101].amount_cents`  
  AMOUNT_INVALID: statement[STMT-2909-01/L-0101].amount_cents must be integer cents, got 84250.5 -- amounts are integer cents and are never coerced
- **FAIL** `rec_every_charge_reported` @ `amount:statement[L-0101].amount_cents`  
  AMOUNT_INVALID: statement[L-0101].amount_cents must be integer cents, got 84250.5 -- amounts are integer cents and are never coerced
- **FAIL** `rec_report_total_ties` @ `amount:statement[CH-01].amount_cents`  
  AMOUNT_INVALID: statement[CH-01].amount_cents must be integer cents, got 84250.5 -- amounts are integer cents and are never coerced
- **FAIL** `pol_per_charge_limit` @ `amount:statement[L-0101].amount_cents`  
  AMOUNT_INVALID: statement[L-0101].amount_cents must be integer cents, got 84250.5 -- amounts are integer cents and are never coerced

### card_bad_last4__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 4)

- **FAIL** `card_last4_valid` @ `cardholder_register:CARD-2909/cardholders/CH-03/card_last4`  
  cardholder CH-03 has card last four '619', which is not four digits
- **FAIL** `stmt_last4_matches_card` @ `statement_register:STMT-2909/statements/STMT-2909-03/L-0301/last4`  
  charge L-0301 carries last four '6190'; cardholder CH-03's card ends '619'
- **FAIL** `stmt_last4_matches_card` @ `statement_register:STMT-2909/statements/STMT-2909-03/L-0302/last4`  
  charge L-0302 carries last four '6190'; cardholder CH-03's card ends '619'
- **FAIL** `stmt_last4_matches_card` @ `statement_register:STMT-2909/statements/STMT-2909-03/L-0303/last4`  
  charge L-0303 carries last four '6190'; cardholder CH-03's card ends '619'

### card_duplicate_id__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `card_id_unique` @ `cardholder_register:CARD-2909/cardholders/CH-01`  
  cardholder CH-01 appears 2 times; a charge's ownership is ambiguous

### card_missing_field__Northmoor_Development_Group

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `card_required_fields` @ `cardholder_register:CARD-2909/cardholders/CH-02`  
  cardholder CH-02 is missing home_entity

### card_unknown_entity__Halbrook_Residential

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `card_home_entity_known` @ `cardholder_register:CARD-2909/cardholders/CH-01/home_entity`  
  cardholder CH-01 has home entity 'Westmere Group', which is not one of ('Northmoor Construction LLC', 'Halbrook Builders', 'Stonecrest Holdings', 'Ardenne Field Partners')

### clean__Northmoor_Development_Group

**Verdict:** PASS (PASS 23, FLAG 0, FAIL 0)

All controls held.

### cod_bad_gl__Stonecrest_Communities

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `cod_gl_valid` @ `expense_report_register:EXP-2909/reports/EXP-2909-01/R-L-0101/gl_code`  
  report EXP-2909-01 line R-L-0101 is coded to GL '9999', which is not in the policy's valid set

### cod_bad_project__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `cod_project_exists` @ `expense_report_register:EXP-2909/reports/EXP-2909-02/R-L-0201/project_code`  
  report EXP-2909-02 line R-L-0201 is coded to project 'PRJ-999', which is not in the register

### cod_disallowed__Northmoor_Development_Group

**Verdict:** REVIEW (PASS 22, FLAG 1, FAIL 0)

- **FLAG** `cod_disallowed_category` @ `statement_register:STMT-2909/statements/STMT-2909-03/L-0303/category`  
  charge L-0303 at Harbor Fuel Stop is category 'gambling', which the policy disallows; a reviewer must clear it by hand

### dup_charge__Halbrook_Residential

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `dup_no_duplicate_charge` @ `statement_register:STMT-2909/statements/*/L-0101`  
  charges L-0101, L-0105 are duplicates: Cascadia Air Charter on 2029-09-03 for 842.50 on card ending 4417; one should be disputed or removed

### gl_total_untied__Stonecrest_Communities

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `rec_gl_ties_reports` @ `gl_positions:GL-2909/total_pcard_expense_cents`  
  the ledger carries 7,533.94 of P-Card expense; the report lines sum to 7,433.94 (difference 100.00)

### missing_artifact__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `gl_positions:-`  
  gl_positions is missing; the controls that read it cannot run and must not be reported as having passed

### pol_late_submission__Northmoor_Development_Group

**Verdict:** REVIEW (PASS 22, FLAG 1, FAIL 0)

- **FLAG** `pol_submitted_within_window` @ `expense_report_register:EXP-2909/reports/EXP-2909-02/submitted_date`  
  report EXP-2909-02 was filed 46 days after the statement dated 2029-09-30; the window is 14 days

### pol_over_limit__Halbrook_Residential

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `pol_per_charge_limit` @ `statement_register:STMT-2909/statements/STMT-2909-02/L-0203/amount_cents`  
  charge L-0203 at Pinehill Software is 5,001.00, over the per-charge limit of 5,000.00

### pol_self_approved__Stonecrest_Communities

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `pol_approver_distinct` @ `expense_report_register:EXP-2909/reports/EXP-2909-03/approver`  
  report EXP-2909-03 was approved by 'Rupert Vance', the cardholder themself; approval requires a second person

### rec_orphan_report_line__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 2)

- **FAIL** `rec_every_charge_reported` @ `statement_register:STMT-2909/statements/STMT-2909-02/L-0203/-`  
  charge L-0203 on statement STMT-2909-02 has no report line; it is an uncoded, unreceipted company expense
- **FAIL** `rec_no_orphan_report_line` @ `expense_report_register:EXP-2909/reports/EXP-2909-02/R-L-0203/statement_line_id`  
  report EXP-2909-02 line R-L-0203 claims charge 'L-9999', which is on no statement in the cycle

### rec_total_untied__Northmoor_Development_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 3)

- **FAIL** `rec_every_charge_reported` @ `expense_report_register:EXP-2909/reports/EXP-2909-03/R-L-0302/amount_cents`  
  charge L-0302 is 742.88 on the statement but 743.88 on the report (difference 1.00); it does not reconcile to the cent
- **FAIL** `rec_report_total_ties` @ `expense_report_register:EXP-2909/reports/CH-03`  
  cardholder CH-03 reports 2,174.13 against a statement of 2,173.13 (difference 1.00)
- **FAIL** `rec_gl_ties_reports` @ `gl_positions:GL-2909/total_pcard_expense_cents`  
  the ledger carries 7,433.94 of P-Card expense; the report lines sum to 7,434.94 (difference -1.00)

### rec_unreported_charge__Halbrook_Residential

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 3)

- **FAIL** `rec_every_charge_reported` @ `statement_register:STMT-2909/statements/STMT-2909-01/L-0104/-`  
  charge L-0104 on statement STMT-2909-01 has no report line; it is an uncoded, unreceipted company expense
- **FAIL** `rec_report_total_ties` @ `expense_report_register:EXP-2909/reports/CH-01`  
  cardholder CH-01 reports 2,376.26 against a statement of 2,472.66 (difference -96.40)
- **FAIL** `rec_gl_ties_reports` @ `gl_positions:GL-2909/total_pcard_expense_cents`  
  the ledger carries 7,433.94 of P-Card expense; the report lines sum to 7,337.54 (difference 96.40)

### rpt_blank_purpose__Stonecrest_Communities

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `rpt_purpose_present` @ `expense_report_register:EXP-2909/reports/EXP-2909-03/R-L-0301/purpose`  
  report EXP-2909-03 line R-L-0301 states no business purpose

### rpt_missing_field__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `rpt_required_fields` @ `expense_report_register:EXP-2909/reports/EXP-2909-02/R-L-0202/-`  
  report EXP-2909-02 line R-L-0202 is missing gl_code

### rpt_no_receipt__Northmoor_Development_Group

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `rpt_receipt_on_file` @ `expense_report_register:EXP-2909/reports/EXP-2909-01/R-L-0103/receipt_on_file`  
  report EXP-2909-01 line R-L-0103 has no receipt on file; the charge is unsupported

### stmt_duplicate_line_id__Halbrook_Residential

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 3)

- **FAIL** `stmt_line_unique` @ `statement_register:STMT-2909/statements/*/L-0201`  
  statement line id L-0201 appears 2 times; a report line cannot reconcile against it unambiguously
- **FAIL** `rec_every_charge_reported` @ `expense_report_register:EXP-2909/reports/EXP-2909-02/R-L-0201/amount_cents`  
  charge L-0201 is 1,499.00 on the statement but 1,005.00 on the report (difference -494.00); it does not reconcile to the cent
- **FAIL** `rec_no_orphan_report_line` @ `expense_report_register:EXP-2909/reports/EXP-2909-02/R-L-0203/statement_line_id`  
  report EXP-2909-02 line R-L-0203 claims charge 'L-0203', which is on no statement in the cycle

### stmt_missing_field__Stonecrest_Communities

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `stmt_required_fields` @ `statement_register:STMT-2909/statements/STMT-2909-02/L-0202/-`  
  statement STMT-2909-02 line L-0202 is missing merchant

### stmt_wrong_last4__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `stmt_last4_matches_card` @ `statement_register:STMT-2909/statements/STMT-2909-01/L-0102/last4`  
  charge L-0102 carries last four '0000'; cardholder CH-01's card ends '4417'
