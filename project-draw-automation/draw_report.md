# Project draw control report

**Overall verdict:** FAIL

- Packages analyzed: 37
- Controls in registry: 34
- PASS / REVIEW / FAIL: 1 / 8 / 28

All data is fictional. The engine is read-only and never writes to a source
artifact.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `set_period_aligned` | FAIL | 1 |
| 3 | `recon_total_is_prior_plus_current` | FAIL | 1 |
| 4 | `recon_draws_tie_costs` | FAIL | 2 |
| 5 | `recon_categories_foot` | FAIL | 2 |
| 6 | `recon_retention_sign` | FAIL | 1 |
| 7 | `recon_retention_release_moved` | FAIL | 1 |
| 8 | `recon_funding_ties_ledger` | FAIL | 1 |
| 9 | `recon_funding_rows_foot` | FAIL | 1 |
| 10 | `recon_variance_explained` | FLAG | 1 |
| 11 | `form_lines_crossfoot` | FAIL | 2 |
| 12 | `form_remaining_is_budget_less_disbursed` | FAIL | 3 |
| 13 | `form_revised_budget_is_original_plus_adjustments` | FAIL | 1 |
| 14 | `form_columns_foot` | FAIL | 15 |
| 15 | `form_disbursed_ties_recon` | FAIL | 2 |
| 16 | `form_previous_ties_trial_balance` | FAIL | 1 |
| 17 | `form_request_ties_cost_detail` | FAIL | 2 |
| 18 | `form_no_negative_remaining` | FAIL | 1 |
| 19 | `cont_within_percent_complete` | FAIL | 1 |
| 20 | `cont_not_negative` | FLAG | 1 |
| 21 | `cut_costs_inside_period` | FAIL | 1 |
| 22 | `cut_posted_by_deadline` | FAIL | 1 |
| 23 | `cut_approvals_within_sla` | FLAG | 1 |
| 24 | `cut_cycle_milestones_ordered` | FAIL | 1 |
| 25 | `cut_submitted_by_target` | FLAG | 1 |
| 26 | `acc_only_material` | FLAG | 1 |
| 27 | `acc_prior_period_reversed` | FAIL | 1 |
| 28 | `doc_signed` | FAIL | 2 |
| 29 | `doc_backup_over_threshold` | FAIL | 1 |
| 30 | `doc_schedule_of_values` | FAIL | 1 |
| 31 | `doc_distribution_complete` | FLAG | 1 |
| 32 | `fund_within_agreement_days` | FLAG | 2 |
| 33 | `fund_overdue_followed_up` | FLAG | 1 |
| 34 | `fund_working_capital_floor` | FLAG | 1 |

## Packages

### accrual_not_reversed__Brightwater_Commons

**Verdict:** FAIL (PASS 33, FLAG 0, FAIL 1)

- **FAIL** `acc_prior_period_reversed` @ `draw_cycle_calendar:DCC-2027-04-0014/prior_period_accruals/T-9901/reversed`  
  prior-period accrual T-9901 of 48,000.00 has not been reversed; when the invoice posts the cost will be drawn twice

### amount_not_integer__Copperfield_Yards

**Verdict:** FAIL (PASS 31, FLAG 0, FAIL 3)

- **FAIL** `form_lines_crossfoot` @ `amount:form.lines[01-100].request_this_period_cents`  
  AMOUNT_INVALID: form.lines[01-100].request_this_period_cents must be integer cents, got 12000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `form_columns_foot` @ `amount:form.lines[01-100].request_this_period_cents`  
  AMOUNT_INVALID: form.lines[01-100].request_this_period_cents must be integer cents, got 12000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `form_request_ties_cost_detail` @ `amount:form.lines[01-100].request_this_period_cents`  
  AMOUNT_INVALID: form.lines[01-100].request_this_period_cents must be integer cents, got 12000000.5 -- amounts are integer cents and are never coerced

### approval_slow__Dunmore_Flats

**Verdict:** REVIEW (PASS 33, FLAG 1, FAIL 0)

- **FLAG** `cut_approvals_within_sla` @ `cost_transaction_detail:CTD-2027-04-0014/transactions/T-0002/approval_completed_date`  
  transaction T-0002 took 13 days to approve against a 2-day SLA (notice 2027-04-09, cleared 2027-04-22)

### backup_missing__Alderpoint_Terraces

**Verdict:** FAIL (PASS 33, FLAG 0, FAIL 1)

- **FAIL** `doc_backup_over_threshold` @ `supporting_documentation_index:SDI-2027-04-0014/backup_provided_txn_ids/T-0003`  
  transaction T-0003 of 200,000.00 is at or above the 5,000.00 backup threshold but no invoice copy is indexed in the package

### budget_not_derived__Brightwater_Commons

**Verdict:** FAIL (PASS 31, FLAG 0, FAIL 3)

- **FAIL** `form_remaining_is_budget_less_disbursed` @ `draw_request_form:DRF-2027-04-0014/lines/11-100/remaining_funds_cents`  
  line 11-100: revised budget 405,000.00 less disbursed 200,000.00 = 205,000.00, but remaining funds is stated as 200,000.00
- **FAIL** `form_revised_budget_is_original_plus_adjustments` @ `draw_request_form:DRF-2027-04-0014/lines/11-100/revised_budget_cents`  
  line 11-100: original 400,000.00 + adjustments 0.00 = 400,000.00, but the revised budget is 405,000.00
- **FAIL** `form_columns_foot` @ `draw_request_form:DRF-2027-04-0014/totals/revised_budget_cents`  
  revised budget: lines sum to 12,005,000.00 but the total row declares 12,000,000.00 (difference 5,000.00)

### category_no_foot__Copperfield_Yards

**Verdict:** FAIL (PASS 33, FLAG 0, FAIL 1)

- **FAIL** `recon_categories_foot` @ `job_cost_to_draw_reconciliation:JCR-2027-04-0014/totals/costs_to_date_cents`  
  costs to date: category rows sum to 5,359,000.00 but the total row declares 5,350,000.00 (difference 9,000.00)

### clean__Alderpoint_Terraces

**Verdict:** PASS (PASS 34, FLAG 0, FAIL 0)

All controls held.

### column_no_foot__Dunmore_Flats

**Verdict:** FAIL (PASS 33, FLAG 0, FAIL 1)

- **FAIL** `form_columns_foot` @ `draw_request_form:DRF-2027-04-0014/totals/request_this_period_cents`  
  request this period: lines sum to 570,000.00 but the total row declares 573,000.00 (difference -3,000.00)

### contingency_ahead__Alderpoint_Terraces

**Verdict:** FAIL (PASS 32, FLAG 0, FAIL 4)

- **FAIL** `form_columns_foot` @ `draw_request_form:DRF-2027-04-0014/totals/previous_applications_cents`  
  previous applications: lines sum to 4,690,000.00 but the total row declares 4,580,000.00 (difference 110,000.00)
- **FAIL** `form_columns_foot` @ `draw_request_form:DRF-2027-04-0014/totals/total_disbursed_to_date_cents`  
  total disbursed to date: lines sum to 5,260,000.00 but the total row declares 5,150,000.00 (difference 110,000.00)
- **FAIL** `form_columns_foot` @ `draw_request_form:DRF-2027-04-0014/totals/remaining_funds_cents`  
  remaining funds: lines sum to 6,740,000.00 but the total row declares 6,850,000.00 (difference -110,000.00)
- **FAIL** `cont_within_percent_complete` @ `draw_request_form:DRF-2027-04-0014/lines/03-900/total_disbursed_to_date_cents`  
  hard-cost contingency 03-900 has drawn 260,000.00 against a ceiling of 200,000.00 (40.00% complete of 500,000.00 original contingency); contingency may only be used on a percent-complete basis

### contingency_exhausted__Brightwater_Commons

**Verdict:** FAIL (PASS 32, FLAG 1, FAIL 3)

- **FAIL** `form_columns_foot` @ `draw_request_form:DRF-2027-04-0014/totals/previous_applications_cents`  
  previous applications: lines sum to 5,070,000.00 but the total row declares 4,580,000.00 (difference 490,000.00)
- **FAIL** `form_columns_foot` @ `draw_request_form:DRF-2027-04-0014/totals/total_disbursed_to_date_cents`  
  total disbursed to date: lines sum to 5,640,000.00 but the total row declares 5,150,000.00 (difference 490,000.00)
- **FAIL** `form_columns_foot` @ `draw_request_form:DRF-2027-04-0014/totals/remaining_funds_cents`  
  remaining funds: lines sum to 6,360,000.00 but the total row declares 6,850,000.00 (difference -490,000.00)
- **FLAG** `cont_not_negative` @ `draw_request_form:DRF-2027-04-0014/lines/19-900/total_disbursed_to_date_cents`  
  contingency 19-900 is 95.00% consumed (190,000.00 of 200,000.00); the project has little left to absorb a further overrun

### cost_outside_period__Copperfield_Yards

**Verdict:** FAIL (PASS 33, FLAG 0, FAIL 1)

- **FAIL** `cut_costs_inside_period` @ `cost_transaction_detail:CTD-2027-04-0014/transactions/T-0004/accounting_date`  
  transaction T-0004 is dated 2027-03-28, outside the draw period 2027-04 (2027-04-01..2027-04-30)

### distribution_gap__Dunmore_Flats

**Verdict:** REVIEW (PASS 33, FLAG 1, FAIL 0)

- **FLAG** `doc_distribution_complete` @ `supporting_documentation_index:SDI-2027-04-0014/actual_recipients`  
  1 required recipient(s) did not receive the submittal: controller@sandbox-developer.example

### form_vs_recon__Alderpoint_Terraces

**Verdict:** FAIL (PASS 32, FLAG 0, FAIL 2)

- **FAIL** `form_columns_foot` @ `draw_request_form:DRF-2027-04-0014/totals/total_disbursed_to_date_cents`  
  total disbursed to date: lines sum to 5,150,000.00 but the total row declares 5,156,000.00 (difference -6,000.00)
- **FAIL** `form_disbursed_ties_recon` @ `draw_request_form:DRF-2027-04-0014/totals/total_disbursed_to_date_cents`  
  form shows 5,156,000.00 disbursed to date; the reconciliation supporting it shows 5,150,000.00 (difference 6,000.00)

### funding_off_ledger__Brightwater_Commons

**Verdict:** FAIL (PASS 33, FLAG 0, FAIL 1)

- **FAIL** `recon_funding_ties_ledger` @ `job_cost_to_draw_reconciliation:JCR-2027-04-0014/ledger_debt_funding_cents`  
  debt funding per the reconciliation is 4,030,000.00 but the ledger balance is 4,000,000.00 (difference 30,000.00)

### funding_overdue__Copperfield_Yards

**Verdict:** REVIEW (PASS 33, FLAG 1, FAIL 0)

- **FLAG** `fund_within_agreement_days` @ `draw_cycle_calendar:DCC-2027-04-0014/funded`  
  funded in 24 days against a 14-day agreement window (2027-05-12 to 2027-06-05)

### funding_rows_off__Dunmore_Flats

**Verdict:** FAIL (PASS 33, FLAG 0, FAIL 1)

- **FAIL** `recon_funding_rows_foot` @ `funding_ledger:FDL-2027-04-0014/gl_debt_balance_cents`  
  debt funding events sum to 4,015,000.00 but the ledger balance is 4,000,000.00

### immaterial_accrual__Alderpoint_Terraces

**Verdict:** REVIEW (PASS 33, FLAG 1, FAIL 0)

- **FLAG** `acc_only_material` @ `cost_transaction_detail:CTD-2027-04-0014/transactions/T-0007/is_accrual`  
  transaction T-0007 is accrued at 10,000.00, below the 25,000.00 materiality threshold, and is not marked as requiring immediate payment

### line_no_crossfoot__Brightwater_Commons

**Verdict:** FAIL (PASS 31, FLAG 0, FAIL 3)

- **FAIL** `form_lines_crossfoot` @ `draw_request_form:DRF-2027-04-0014/lines/10-100/total_disbursed_to_date_cents`  
  line 10-100: previous 660,000.00 + this period 40,000.00 = 700,000.00, but disbursed to date is 702,000.00
- **FAIL** `form_remaining_is_budget_less_disbursed` @ `draw_request_form:DRF-2027-04-0014/lines/10-100/remaining_funds_cents`  
  line 10-100: revised budget 900,000.00 less disbursed 702,000.00 = 198,000.00, but remaining funds is stated as 200,000.00
- **FAIL** `form_columns_foot` @ `draw_request_form:DRF-2027-04-0014/totals/total_disbursed_to_date_cents`  
  total disbursed to date: lines sum to 5,152,000.00 but the total row declares 5,150,000.00 (difference 2,000.00)

### milestones_disordered__Copperfield_Yards

**Verdict:** FAIL (PASS 33, FLAG 0, FAIL 1)

- **FAIL** `cut_cycle_milestones_ordered` @ `draw_cycle_calendar:DCC-2027-04-0014/prep_start`  
  prep_start (2027-05-01) falls before posting_deadline (2027-05-03); the cycle cannot run in this order

### missing_artifact__Dunmore_Flats

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `package:missing_artifact__Dunmore_Flats/supporting_documentation_index`  
  package carries no supporting_documentation_index; absent evidence is not a passing control, so no downstream rule may read it

### negative_remaining__Alderpoint_Terraces

**Verdict:** FAIL (PASS 32, FLAG 0, FAIL 4)

- **FAIL** `form_columns_foot` @ `draw_request_form:DRF-2027-04-0014/totals/previous_applications_cents`  
  previous applications: lines sum to 4,800,000.00 but the total row declares 4,580,000.00 (difference 220,000.00)
- **FAIL** `form_columns_foot` @ `draw_request_form:DRF-2027-04-0014/totals/total_disbursed_to_date_cents`  
  total disbursed to date: lines sum to 5,370,000.00 but the total row declares 5,150,000.00 (difference 220,000.00)
- **FAIL** `form_columns_foot` @ `draw_request_form:DRF-2027-04-0014/totals/remaining_funds_cents`  
  remaining funds: lines sum to 6,630,000.00 but the total row declares 6,850,000.00 (difference -220,000.00)
- **FAIL** `form_no_negative_remaining` @ `draw_request_form:DRF-2027-04-0014/lines/11-100/remaining_funds_cents`  
  line 11-100 shows -20,000.00 remaining, i.e. it is over budget; no current-period budget adjustment has been made

### no_followup__Brightwater_Commons

**Verdict:** REVIEW (PASS 32, FLAG 2, FAIL 0)

- **FLAG** `fund_within_agreement_days` @ `draw_cycle_calendar:DCC-2027-04-0014/funded`  
  submitted 2027-05-12 and not yet funded; the agreement allows 14 days
- **FLAG** `fund_overdue_followed_up` @ `draw_cycle_calendar:DCC-2027-04-0014/followup_logged`  
  the draw is unfunded past the 14-day window and no follow-up with the lender is recorded

### period_drift__Copperfield_Yards

**Verdict:** FAIL (PASS 33, FLAG 0, FAIL 1)

- **FAIL** `set_period_aligned` @ `cost_transaction_detail:CTD-2027-04-0014/period`  
  document period '2027-03' does not match the package period '2027-04'

### posted_late__Dunmore_Flats

**Verdict:** FAIL (PASS 33, FLAG 0, FAIL 1)

- **FAIL** `cut_posted_by_deadline` @ `cost_transaction_detail:CTD-2027-04-0014/transactions/T-0006/posted_date`  
  transaction T-0006 posted 2027-05-09, after the 2027-05-03 posting deadline; it belongs to the following draw

### previous_vs_tb__Alderpoint_Terraces

**Verdict:** FAIL (PASS 33, FLAG 0, FAIL 1)

- **FAIL** `form_previous_ties_trial_balance` @ `draw_request_form:DRF-2027-04-0014/totals/previous_applications_cents`  
  previous applications on the form total 4,580,000.00 but the trial balance carries 4,591,000.00

### recon_break__Brightwater_Commons

**Verdict:** FAIL (PASS 33, FLAG 0, FAIL 1)

- **FAIL** `recon_draws_tie_costs` @ `job_cost_to_draw_reconciliation:JCR-2027-04-0014/totals`  
  total draws to date 5,150,000.00 less costs to date net of retention 5,162,500.00 = -12,500.00; this identity must be exactly zero for the draw to be supportable

### remaining_wrong__Copperfield_Yards

**Verdict:** FAIL (PASS 32, FLAG 0, FAIL 2)

- **FAIL** `form_remaining_is_budget_less_disbursed` @ `draw_request_form:DRF-2027-04-0014/lines/02-100/remaining_funds_cents`  
  line 02-100: revised budget 8,000,000.00 less disbursed 2,400,000.00 = 5,600,000.00, but remaining funds is stated as 5,592,500.00
- **FAIL** `form_columns_foot` @ `draw_request_form:DRF-2027-04-0014/totals/remaining_funds_cents`  
  remaining funds: lines sum to 6,842,500.00 but the total row declares 6,850,000.00 (difference -7,500.00)

### request_vs_detail__Dunmore_Flats

**Verdict:** FAIL (PASS 33, FLAG 0, FAIL 1)

- **FAIL** `form_request_ties_cost_detail` @ `draw_request_form:DRF-2027-04-0014/lines/02-100/request_this_period_cents`  
  line 02-100 requests 380,000.00 this period but the transaction detail subtotals 388,000.00 for that category

### retention_not_moved__Alderpoint_Terraces

**Verdict:** FAIL (PASS 33, FLAG 0, FAIL 1)

- **FAIL** `recon_retention_release_moved` @ `job_cost_to_draw_reconciliation:JCR-2027-04-0014/categories/01-100/retention_billed_current_cents`  
  25,000.00 of retention was released but the current period column does not carry it; the release must move, not merely disappear from retention

### retention_positive__Brightwater_Commons

**Verdict:** FAIL (PASS 32, FLAG 0, FAIL 2)

- **FAIL** `recon_categories_foot` @ `job_cost_to_draw_reconciliation:JCR-2027-04-0014/totals/retention_withheld_cents`  
  retention withheld: category rows sum to -140,000.00 but the total row declares -200,000.00 (difference 60,000.00)
- **FAIL** `recon_retention_sign` @ `job_cost_to_draw_reconciliation:JCR-2027-04-0014/categories/10-100/retention_withheld_cents`  
  retention withheld is 30,000.00, a positive amount; withheld retention reduces what may be drawn and is carried negative

### signer_unauthorized__Copperfield_Yards

**Verdict:** FAIL (PASS 33, FLAG 0, FAIL 1)

- **FAIL** `doc_signed` @ `draw_request_form:DRF-2027-04-0014/signed_by`  
  the draw request is signed by 'T. Aldington', who is not on the authorized signer list (A. Whitfield, R. Castellanos)

### sov_missing__Dunmore_Flats

**Verdict:** FAIL (PASS 33, FLAG 0, FAIL 1)

- **FAIL** `doc_schedule_of_values` @ `supporting_documentation_index:SDI-2027-04-0014/schedule_of_values_attached`  
  this lender requires a schedule of values of committed values by cost code and none is attached

### submitted_late__Alderpoint_Terraces

**Verdict:** REVIEW (PASS 33, FLAG 1, FAIL 0)

- **FLAG** `cut_submitted_by_target` @ `draw_cycle_calendar:DCC-2027-04-0014/submitted`  
  submitted 2027-05-19, 4 day(s) after the 2027-05-15 target; late submittal pushes funding past the point where subcontractors can be paid on time

### total_mismatch__Brightwater_Commons

**Verdict:** FAIL (PASS 31, FLAG 0, FAIL 3)

- **FAIL** `recon_total_is_prior_plus_current` @ `job_cost_to_draw_reconciliation:JCR-2027-04-0014/totals/total_draws_to_date_cents`  
  prior fundings 4,580,000.00 + current draw 570,000.00 = 5,150,000.00, but total draws to date is declared as 5,154,000.00 (difference -4,000.00)
- **FAIL** `recon_draws_tie_costs` @ `job_cost_to_draw_reconciliation:JCR-2027-04-0014/totals`  
  total draws to date 5,154,000.00 less costs to date net of retention 5,150,000.00 = 4,000.00; this identity must be exactly zero for the draw to be supportable
- **FAIL** `form_disbursed_ties_recon` @ `draw_request_form:DRF-2027-04-0014/totals/total_disbursed_to_date_cents`  
  form shows 5,150,000.00 disbursed to date; the reconciliation supporting it shows 5,154,000.00 (difference -4,000.00)

### unsigned__Copperfield_Yards

**Verdict:** FAIL (PASS 33, FLAG 0, FAIL 1)

- **FAIL** `doc_signed` @ `draw_request_form:DRF-2027-04-0014/signed_by`  
  the draw request carries no signature; almost every lender requires the form or its summary to be signed before funding

### variance_unexplained__Dunmore_Flats

**Verdict:** REVIEW (PASS 33, FLAG 1, FAIL 0)

- **FLAG** `recon_variance_explained` @ `job_cost_to_draw_reconciliation:JCR-2027-04-0014/variance_explanation`  
  a variance of 1,200.00 is declared with no explanation; the project accountant must be able to explain any variance

### working_capital_low__Alderpoint_Terraces

**Verdict:** REVIEW (PASS 33, FLAG 1, FAIL 0)

- **FLAG** `fund_working_capital_floor` @ `funding_ledger:FDL-2027-04-0014/working_capital_balance_cents`  
  working capital is 18,000.00 against a floor of 50,000.00; the project cannot fund costs that fall outside the draw cycle
