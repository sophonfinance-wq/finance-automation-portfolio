# Combined-group franchise-tax control report

**Overall verdict:** FAIL

- Combined-return files analyzed: 23
- Controls in registry: 21
- PASS / REVIEW / FAIL: 1 / 1 / 21

All data is fictional. The engine is read-only and never writes to a source
artifact. Every registration-renewal test is made against the `as_of` date carried
in the file, never the system clock.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `aff_unique_ids` | FAIL | 1 |
| 3 | `aff_address_valid` | FAIL | 1 |
| 4 | `aff_status_valid` | FAIL | 1 |
| 5 | `aff_registration_renewal` | FLAG | 1 |
| 6 | `grp_roster_continuity` | FAIL | 1 |
| 7 | `grp_members_registered` | FAIL | 1 |
| 8 | `grp_excluded_reconciled` | FAIL | 1 |
| 9 | `tb_required_fields` | FAIL | 1 |
| 10 | `tb_line_unique` | FAIL | 1 |
| 11 | `tb_member_known` | FAIL | 1 |
| 12 | `apt_receipts_sound` | FAIL | 1 |
| 13 | `apt_totals_tie_receipts` | FAIL | 1 |
| 14 | `apt_factor_recomputes` | FAIL | 1 |
| 15 | `apt_worksheet_factor_recomputes` | FAIL | 1 |
| 16 | `mgn_revenue_ties_tb` | FAIL | 2 |
| 17 | `mgn_margin_recomputes` | FAIL | 2 |
| 18 | `mgn_apportioned_recomputes` | FAIL | 1 |
| 19 | `mgn_tax_recomputes` | FAIL | 1 |
| 20 | `rpt_summary_recomputes` | FAIL | 1 |
| 21 | `rpt_report_totals_tie` | FAIL | 1 |

## Combined-return files

### amount_not_integer__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 2)

- **FAIL** `mgn_revenue_ties_tb` @ `amount:margin_worksheet.group_revenue_cents`  
  AMOUNT_INVALID: margin_worksheet.group_revenue_cents must be integer cents, got 20000000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `mgn_margin_recomputes` @ `amount:margin_worksheet.group_revenue_cents`  
  AMOUNT_INVALID: margin_worksheet.group_revenue_cents must be integer cents, got 20000000000.5 -- amounts are integer cents and are never coerced

### apportioned_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `mgn_apportioned_recomputes` @ `margin_worksheet:MARGIN-2029/apportioned_margin_cents`  
  the margin worksheet states apportioned margin 48,750,000.01; 130,000,000.00 at 37.50% re-derives 48,750,000.00

### bad_address__Ardenne_Field_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `aff_address_valid` @ `affiliate_register:AFFILIATES-2029/affiliates/AFF-02`  
  affiliate AFF-02 is missing postal_code on the address tab; it cannot be placed or registered

### bad_affiliate_status__Northmoor_Development_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `aff_status_valid` @ `affiliate_register:AFFILIATES-2029/affiliates/AFF-03/status`  
  affiliate AFF-03 carries status 'pending', which is not one of ('active', 'inactive')

### clean__Northmoor_Development_Group

**Verdict:** PASS (PASS 21, FLAG 0, FAIL 0)

All controls held.

### duplicate_affiliate_id__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `aff_unique_ids` @ `affiliate_register:AFFILIATES-2029/affiliates/AFF-01`  
  affiliate id AFF-01 appears 2 times; a revenue line that names it cannot be attributed to one affiliate

### excluded_unreconciled__Stonecrest_Communities

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `grp_excluded_reconciled` @ `combined_group:GROUP-2029/excluded/AFF-04`  
  affiliate AFF-04 was removed from the combined group but is not enumerated on the excluded list; the exclusion is unreconciled

### factor_wrong__Ardenne_Field_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `apt_factor_recomputes` @ `receipts_factor:RECEIPTS-2029/factor_bps`  
  the receipts workpaper states an apportionment factor of 38.00%; in-state over everywhere recomputes 37.50%

### margin_wrong__Northmoor_Development_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `mgn_margin_recomputes` @ `margin_worksheet:MARGIN-2029/taxable_margin_cents`  
  the margin worksheet states taxable margin 130,000,000.01; revenue 200,000,000.00 less elected deduction 70,000,000.00 re-derives 130,000,000.00

### member_unregistered__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `grp_members_registered` @ `affiliate_register:AFFILIATES-2029/affiliates/AFF-02`  
  combined member AFF-02 is not on the affiliate register; it has no address or registration to be admitted on

### missing_artifact__Stonecrest_Communities

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `franchise_report:-`  
  franchise_report is missing; the controls that read it cannot run and must not be reported as having passed

### receipts_unsound__Ardenne_Field_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `apt_receipts_sound` @ `receipts_factor:RECEIPTS-2029/receipts/AFF-02/in_state_receipts_cents`  
  affiliate AFF-02 reports in-state receipts 60,000,000.00 above its everywhere receipts 50,000,000.00; in-state is a subset of everywhere

### registration_renewal_due__Northmoor_Development_Group

**Verdict:** REVIEW (PASS 20, FLAG 1, FAIL 0)

- **FLAG** `aff_registration_renewal` @ `affiliate_register:AFFILIATES-2029/affiliates/AFF-01/registration_renewal_date`  
  affiliate AFF-01 registration renews 2030-05-21, in 20 day(s); inside the 60-day window and due to be renewed

### report_total_break__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `rpt_report_totals_tie` @ `franchise_report:REPORT-2029/total_tax_due_cents`  
  the report states total 365,625.01 over 4 combined member(s); the summary and roster give 365,625.00 over 4

### revenue_tie_break__Stonecrest_Communities

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `mgn_revenue_ties_tb` @ `margin_worksheet:MARGIN-2029/group_revenue_cents`  
  the margin worksheet states group revenue 200,000,000.01; the consolidated trial-balance lines sum to 200,000,000.00 (off by 0.01)

### roster_discontinuity__Ardenne_Field_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `grp_roster_continuity` @ `combined_group:GROUP-2029/members`  
  the combined roster states members ['AFF-01', 'AFF-02', 'AFF-03', 'AFF-05']; rebuilding from prior ['AFF-01', 'AFF-02', 'AFF-03', 'AFF-04', 'AFF-06'] plus additions ['AFF-05'] less removals ['AFF-04'] gives ['AFF-01', 'AFF-02', 'AFF-03', 'AFF-05', 'AFF-06']

### summary_recompute_break__Northmoor_Development_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `rpt_summary_recomputes` @ `tax_summary:SUMMARY-2029/tax_cents`  
  the tax summary states franchise tax 365,625.01; recomputing from the workpapers gives 365,625.00

### tax_wrong__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `mgn_tax_recomputes` @ `margin_worksheet:MARGIN-2029/tax_cents`  
  the margin worksheet states tax 365,625.01; 48,750,000.00 at 0.75% re-derives 365,625.00

### tb_duplicate_line__Stonecrest_Communities

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `tb_line_unique` @ `trial_balance:TB-2029/lines/TB-01`  
  trial-balance line id TB-01 appears 2 times; the same revenue cannot be counted twice into the consolidated base

### tb_missing_field__Ardenne_Field_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `tb_required_fields` @ `trial_balance:TB-2029/lines/TB-03`  
  trial-balance line TB-03 is missing account

### tb_unknown_member__Northmoor_Development_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `tb_member_known` @ `trial_balance:TB-2029/lines/TB-05/affiliate_id`  
  trial-balance line TB-05 is attributed to 'AFF-77', which is not a current combined member

### totals_tie_break__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `apt_totals_tie_receipts` @ `receipts_factor:RECEIPTS-2029/in_state_total_cents`  
  the receipts workpaper states totals in-state 75,000,001.00 / everywhere 200,000,000.00; the rows sum to 75,000,000.00 / 200,000,000.00

### worksheet_factor_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `apt_worksheet_factor_recomputes` @ `margin_worksheet:MARGIN-2029/apportionment_factor_bps`  
  the margin worksheet applied an apportionment factor of 38.00%; the receipts workpaper recomputes 37.50%
