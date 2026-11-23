# Project labor charge control report

**Overall verdict:** FAIL

- Charge-run files analyzed: 28
- Controls in registry: 26
- PASS / REVIEW / FAIL: 1 / 1 / 26

All data is fictional. The engine is read-only and never writes to a source
artifact. Every date test is made against the `as_of` date carried in the file,
never the system clock.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `emp_required_fields` | FAIL | 1 |
| 3 | `emp_id_unique` | FAIL | 1 |
| 4 | `emp_burdened_cost_positive` | FAIL | 1 |
| 5 | `prj_required_fields` | FAIL | 1 |
| 6 | `prj_code_unique` | FAIL | 1 |
| 7 | `prj_budget_positive` | FAIL | 1 |
| 8 | `auth_required_fields` | FAIL | 1 |
| 9 | `auth_employee_exists` | FAIL | 1 |
| 10 | `auth_project_exists` | FAIL | 1 |
| 11 | `auth_notice_before_start` | FAIL | 1 |
| 12 | `auth_cost_code_on_project` | FAIL | 1 |
| 13 | `auth_budget_confirmed` | FAIL | 1 |
| 14 | `auth_method_valid` | FAIL | 1 |
| 15 | `auth_charge_derives` | FAIL | 1 |
| 16 | `chg_authorized` | FAIL | 1 |
| 17 | `chg_not_before_start` | FAIL | 1 |
| 18 | `chg_amount_matches_auth` | FAIL | 4 |
| 19 | `chg_cost_code_matches_auth` | FAIL | 1 |
| 20 | `chg_period_valid` | FAIL | 1 |
| 21 | `bud_within_budget` | FAIL | 2 |
| 22 | `bud_near_budget` | FLAG | 3 |
| 23 | `inv_total_ties_charges` | FAIL | 4 |
| 24 | `inv_matches_charge_periods` | FAIL | 3 |
| 25 | `gl_total_ties_ledger` | FAIL | 3 |
| 26 | `gl_invoice_total_ties` | FAIL | 2 |

## Charge files

### amount_not_integer__Halbrook_Builders_Group

**Verdict:** FAIL (PASS 21, FLAG 1, FAIL 6)

- **FAIL** `chg_amount_matches_auth` @ `amount:charge[EMP-001/BW-100/2030-01].amount_cents`  
  AMOUNT_INVALID: charge[EMP-001/BW-100/2030-01].amount_cents must be integer cents, got 1200000.5 -- amounts are integer cents and are never coerced
- **FAIL** `bud_within_budget` @ `amount:charge[BW-100/2030-01].amount_cents`  
  AMOUNT_INVALID: charge[BW-100/2030-01].amount_cents must be integer cents, got 1200000.5 -- amounts are integer cents and are never coerced
- **FLAG** `bud_near_budget` @ `amount:charge[BW-100/2030-01].amount_cents`  
  AMOUNT_INVALID: charge[BW-100/2030-01].amount_cents must be integer cents, got 1200000.5 -- amounts are integer cents and are never coerced
- **FAIL** `inv_total_ties_charges` @ `amount:charge[BW-100/2030-01].amount_cents`  
  AMOUNT_INVALID: charge[BW-100/2030-01].amount_cents must be integer cents, got 1200000.5 -- amounts are integer cents and are never coerced
- **FAIL** `inv_total_ties_charges` @ `monthly_invoice:INVOICE-2030/invoices/BW-100/2030-01`  
  invoice for BW-100 in 2030-01 totals 16,500.00; the charges for that project-period sum to 4,500.00 (difference 12,000.00)
- **FAIL** `gl_total_ties_ledger` @ `amount:charge[BW-100/2030-01].amount_cents`  
  AMOUNT_INVALID: charge[BW-100/2030-01].amount_cents must be integer cents, got 1200000.5 -- amounts are integer cents and are never coerced
- **FAIL** `gl_total_ties_ledger` @ `gl_positions:GL-2030/total_labor_charge_cents`  
  the ledger carries 85,500.00 of labor charge; the charge lines sum to 73,500.00 (difference 12,000.00)

### auth_bad_method__Stonecrest_Development_Co

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `auth_method_valid` @ `charge_authorization:AUTH-REG-2030/authorizations/AUTH-3/method`  
  authorization AUTH-3 declares method 'hourly', which is not one of ('fixed', 'percent')

### auth_budget_unconfirmed__Ardenne_Contracting

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `auth_budget_confirmed` @ `charge_authorization:AUTH-REG-2030/authorizations/AUTH-2/budget_confirmed`  
  authorization AUTH-2 carries budget_confirmed=False; charging began without a confirmed budget

### auth_charge_mis_derived__Northmoor_Construction_Partners

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `auth_charge_derives` @ `charge_authorization:AUTH-REG-2030/authorizations/AUTH-2/monthly_charge_cents`  
  authorization AUTH-2 resolves to a monthly charge of 4,500.00; 60.00% of a burdened cost of 9,000.00 derives 5,400.00 (difference -900.00)

### auth_cost_code_off_project__Halbrook_Builders_Group

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `auth_cost_code_on_project` @ `charge_authorization:AUTH-REG-2030/authorizations/AUTH-X3/cost_code`  
  authorization AUTH-X3 charges AP-300 on cost code '99-999', which is not one of that project's cost codes ['03-100']

### auth_missing_field__Stonecrest_Development_Co

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `auth_required_fields` @ `charge_authorization:AUTH-REG-2030/authorizations/AUTH-1`  
  authorization AUTH-1 is missing notice_date

### auth_notice_after_start__Ardenne_Contracting

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `auth_notice_before_start` @ `charge_authorization:AUTH-REG-2030/authorizations/AUTH-1/notice_date`  
  authorization AUTH-1 gives notice 2029-12-16 for a start of 2029-12-15; the charge was authorized after it began, not in advance

### auth_unknown_employee__Northmoor_Construction_Partners

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `auth_employee_exists` @ `charge_authorization:AUTH-REG-2030/authorizations/AUTH-X1/employee_id`  
  authorization AUTH-X1 names employee 'EMP-999', which is not in the register

### auth_unknown_project__Halbrook_Builders_Group

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `auth_project_exists` @ `charge_authorization:AUTH-REG-2030/authorizations/AUTH-X2/project_code`  
  authorization AUTH-X2 names project 'ZZ-999', which is not in the register

### bud_near_warn__Stonecrest_Development_Co

**Verdict:** REVIEW (PASS 25, FLAG 1, FAIL 0)

- **FLAG** `bud_near_budget` @ `project_register:PRJ-REG-2030/projects/BW-100/labor_budget_cents`  
  project BW-100 has been charged 49,500.00 of labor, at or above the 90.00% warning band (49,500.00) of its 55,000.00 budget

### bud_over_budget__Ardenne_Contracting

**Verdict:** FAIL (PASS 24, FLAG 1, FAIL 1)

- **FAIL** `bud_within_budget` @ `project_register:PRJ-REG-2030/projects/BW-100/labor_budget_cents`  
  project BW-100 has been charged 49,500.00 of labor against a budget of 40,000.00 (over by 9,500.00)
- **FLAG** `bud_near_budget` @ `project_register:PRJ-REG-2030/projects/BW-100/labor_budget_cents`  
  project BW-100 has been charged 49,500.00 of labor, at or above the 90.00% warning band (36,000.00) of its 40,000.00 budget

### chg_amount_mismatch__Northmoor_Construction_Partners

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 3)

- **FAIL** `chg_amount_matches_auth` @ `labor_charge_ledger:LEDGER-2030/charges/EMP-003/CF-200/2030-01`  
  charge for EMP-003 on CF-200 in 2030-01 is 10,000.00; authorization AUTH-3 resolves to 11,000.00 (difference -1,000.00)
- **FAIL** `chg_amount_matches_auth` @ `labor_charge_ledger:LEDGER-2030/charges/EMP-003/CF-200/2030-02`  
  charge for EMP-003 on CF-200 in 2030-02 is 10,000.00; authorization AUTH-3 resolves to 11,000.00 (difference -1,000.00)
- **FAIL** `chg_amount_matches_auth` @ `labor_charge_ledger:LEDGER-2030/charges/EMP-003/CF-200/2030-03`  
  charge for EMP-003 on CF-200 in 2030-03 is 10,000.00; authorization AUTH-3 resolves to 11,000.00 (difference -1,000.00)

### chg_bad_period__Halbrook_Builders_Group

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 4)

- **FAIL** `chg_period_valid` @ `labor_charge_ledger:LEDGER-2030/charges/EMP-003/CF-200/period`  
  charge for EMP-003 on CF-200 carries period '2030-13', which is not a well-formed YYYY-MM month
- **FAIL** `inv_total_ties_charges` @ `monthly_invoice:INVOICE-2030/invoices/CF-200/2030-02`  
  invoice for CF-200 in 2030-02 totals 10,000.00; the charges for that project-period sum to 0.00 (difference 10,000.00)
- **FAIL** `inv_matches_charge_periods` @ `monthly_invoice:INVOICE-2030/invoices/CF-200/2030-13`  
  project CF-200 carries charges in 2030-13 but no invoice was raised; the labor cost was never billed
- **FAIL** `inv_matches_charge_periods` @ `monthly_invoice:INVOICE-2030/invoices/CF-200/2030-02`  
  an invoice was raised for CF-200 in 2030-02 with no charges beneath it; the project is billed for a month it did not work

### chg_before_start__Stonecrest_Development_Co

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `chg_not_before_start` @ `labor_charge_ledger:LEDGER-2030/charges/EMP-001/BW-100/2030-01`  
  charge for EMP-001 on BW-100 is dated 2030-01, before the authorized start month 2030-02

### chg_cost_code_mismatch__Ardenne_Contracting

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `chg_cost_code_matches_auth` @ `labor_charge_ledger:LEDGER-2030/charges/EMP-001/BW-100/2030-01/cost_code`  
  charge for EMP-001 on BW-100 in 2030-01 posts to cost code '01-200'; authorization AUTH-1 named '01-100'

### chg_unauthorized_pair__Northmoor_Construction_Partners

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `chg_authorized` @ `labor_charge_ledger:LEDGER-2030/charges/EMP-003/BW-100/2030-01`  
  charge for EMP-003 on BW-100 in 2030-01 has no authorization; the project never agreed to carry this employee

### clean__Northmoor_Construction_Partners

**Verdict:** PASS (PASS 26, FLAG 0, FAIL 0)

All controls held.

### emp_burden_nonpositive__Halbrook_Builders_Group

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `emp_burdened_cost_positive` @ `employee_register:EMP-REG-2030/employees/EMP-003/monthly_burdened_cost_cents`  
  employee EMP-003 carries a burdened cost of 0.00; it must be positive to charge over

### emp_duplicate_id__Stonecrest_Development_Co

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `emp_id_unique` @ `employee_register:EMP-REG-2030/employees/EMP-002`  
  employee id EMP-002 appears 2 times; its burdened cost is ambiguous

### emp_missing_name__Ardenne_Contracting

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `emp_required_fields` @ `employee_register:EMP-REG-2030/employees/EMP-001`  
  employee EMP-001 is missing name

### gl_charge_untied__Northmoor_Construction_Partners

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `gl_total_ties_ledger` @ `gl_positions:GL-2030/total_labor_charge_cents`  
  the ledger carries 85,510.00 of labor charge; the charge lines sum to 85,500.00 (difference 10.00)

### gl_invoice_untied__Halbrook_Builders_Group

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `gl_invoice_total_ties` @ `gl_positions:GL-2030/invoice_control_total_cents`  
  the invoice control account carries 85,510.00; the monthly invoices sum to 85,500.00 (difference 10.00)

### inv_orphan__Stonecrest_Development_Co

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `inv_matches_charge_periods` @ `monthly_invoice:INVOICE-2030/invoices/DP-400/2030-01`  
  an invoice was raised for DP-400 in 2030-01 with no charges beneath it; the project is billed for a month it did not work

### inv_total_off__Ardenne_Contracting

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 2)

- **FAIL** `inv_total_ties_charges` @ `monthly_invoice:INVOICE-2030/invoices/BW-100/2030-01`  
  invoice for BW-100 in 2030-01 totals 16,525.00; the charges for that project-period sum to 16,500.00 (difference 25.00)
- **FAIL** `gl_invoice_total_ties` @ `gl_positions:GL-2030/invoice_control_total_cents`  
  the invoice control account carries 85,500.00; the monthly invoices sum to 85,525.00 (difference -25.00)

### missing_artifact__Northmoor_Construction_Partners

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `gl_positions:-`  
  gl_positions is missing; the controls that read it cannot run and must not be reported as having passed

### prj_budget_nonpositive__Halbrook_Builders_Group

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `prj_budget_positive` @ `project_register:PRJ-REG-2030/projects/DP-400/labor_budget_cents`  
  project DP-400 carries a labor budget of 0.00; the overrun control needs a positive ceiling

### prj_duplicate_code__Stonecrest_Development_Co

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `prj_code_unique` @ `project_register:PRJ-REG-2030/projects/CF-200`  
  project code CF-200 appears 2 times; its labor budget is ambiguous

### prj_missing_name__Ardenne_Contracting

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 1)

- **FAIL** `prj_required_fields` @ `project_register:PRJ-REG-2030/projects/BW-100`  
  project BW-100 is missing name
