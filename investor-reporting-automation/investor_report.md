# JV investor reporting package control report

**Overall verdict:** FAIL

- Package files analyzed: 27
- Controls in registry: 25
- PASS / REVIEW / FAIL: 1 / 1 / 25

All data is fictional. The engine is read-only, never writes to a source artifact
and never posts an entry. Every executed draw is tested against the reporting period
carried in the file, never the system clock.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `tb_nets_zero` | FAIL | 2 |
| 2 | `tb_completeness` | FAIL | 1 |
| 3 | `tb_agrees_ledger` | FAIL | 3 |
| 4 | `bs_balances` | FAIL | 1 |
| 5 | `interco_classified` | FAIL | 1 |
| 6 | `capital_agrees_ledger` | FAIL | 1 |
| 7 | `contributions_foot` | FAIL | 1 |
| 8 | `total_cross_foots` | FAIL | 1 |
| 9 | `capital_rollforward` | FAIL | 1 |
| 10 | `net_income_agrees` | FAIL | 1 |
| 11 | `devcost_agrees_wip` | FAIL | 1 |
| 12 | `jobcost_bridge` | FAIL | 1 |
| 13 | `division_coverage` | FAIL | 1 |
| 14 | `draw_schedule_agrees` | FAIL | 1 |
| 15 | `reciprocal_investment` | FAIL | 1 |
| 16 | `nil_is_genuine` | FAIL | 2 |
| 17 | `cash_supported` | FLAG | 1 |
| 18 | `footnote_figures` | FAIL | 1 |
| 19 | `caption_matches_type` | FAIL | 1 |
| 20 | `cover_consistent` | FAIL | 1 |
| 21 | `checkrows_excluded` | FAIL | 1 |
| 22 | `no_preparer_artifacts` | FAIL | 1 |
| 23 | `prior_period_continuity` | FAIL | 1 |
| 24 | `package_complete` | FAIL | 2 |
| 25 | `release_gate` | FAIL | 1 |

## Package files

### amount_not_integer__Copperfield_Yards

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 2)

- **FAIL** `tb_nets_zero` @ `amount:trial_balance[1310].debit_cents`  
  AMOUNT_INVALID: trial_balance[1310].debit_cents must be integer cents, got 3840000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `tb_agrees_ledger` @ `amount:trial_balance[1310].debit_cents`  
  AMOUNT_INVALID: trial_balance[1310].debit_cents must be integer cents, got 3840000000.5 -- amounts are integer cents and are never coerced

### balance_taken_by_position__Alderpoint_Terraces

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 2)

- **FAIL** `tb_agrees_ledger` @ `trial_balance:TB-2032M04/rows/2010`  
  account 2010 Accounts payable is stated at -985,000.00 in the package trial balance; the ledger carries -1,120,000.00 (off by 135,000.00)
- **FAIL** `tb_agrees_ledger` @ `trial_balance:TB-2032M04/rows/2020`  
  account 2020 Retainage payable is stated at -1,120,000.00 in the package trial balance; the ledger carries -985,000.00 (off by -135,000.00)

### bridge_difference_undisclosed__Dunmore_Flats

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `jobcost_bridge` @ `jobcost_report:JCB-2032M04/reconciling_items`  
  the job cost report of 37,710,000.00 plus 0 reconciling item(s) totalling 0.00 reaches 37,710,000.00 against work in process of 38,400,000.00; 690,000.00 of the difference is neither itemized nor disclosed

### bs_equity_transposed__Brightwater_Commons

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `bs_balances` @ `balance_sheet:BS-2032M04/total_assets_cents`  
  total assets of 40,688,000.00 does not equal total liabilities of 24,959,000.00 plus members' equity of 15,684,000.00 (40,643,000.00); the statement is out by 45,000.00

### capital_ending_off_ledger__Copperfield_Yards

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `capital_agrees_ledger` @ `capital_statement:CAP-2032M04/columns/MEM-01/ending_cents`  
  member MEM-01 (Northmoor Development Group) ends at 3,115,800.00 on the capital statement; its ledger capital account carries 3,145,800.00 (off by -30,000.00)

### caption_implies_period_cost__Alderpoint_Terraces

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `caption_matches_type` @ `devcost_schedule:DEV-2032M04/caption`  
  devcost_schedule is a cost_to_date schedule captioned 'Development cost incurred during the period', which says 'during the period'; the figures on it are cumulative and the caption presents them as one period's activity

### cash_support_absent__Dunmore_Flats

**Verdict:** REVIEW (PASS 24, FLAG 1, FAIL 0)

- **FLAG** `cash_supported` @ `cash_support:CASH-2032M04/reconciliations/1020`  
  cash account 1020 Cash - restricted reserve is reported at 350,000.00 with no bank reconciliation attached; the support is a document the engine cannot produce, so the balance goes to a person

### check_row_in_print_area__Brightwater_Commons

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `checkrows_excluded` @ `release_log:REL-2032M04/check_rows/CHK-02`  
  tie-out row CHK-02 (Check: assets less liabilities and capital) on balance_sheet is inside the released print area; the reviewer's arithmetic ships to the partner as though it were a line of the statement

### clean__Brightwater_Commons

**Verdict:** PASS (PASS 25, FLAG 0, FAIL 0)

All controls held.

### contribution_line_omitted__Copperfield_Yards

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `contributions_foot` @ `capital_statement:CAP-2032M04/columns/MEM-02/contributions_cents`  
  member MEM-02 (Halbrook Residential Partners) is shown contributing 1,600,000.00 in the period; the 2 contribution line(s) listed for it foot to 1,200,000.00 (off by 400,000.00)

### cover_asserts_no_exceptions__Alderpoint_Terraces

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `cover_consistent` @ `package_cover:COVER-2032M04/asserts_no_exceptions`  
  the basis of presentation asserts the package is free of exceptions while the notes disclose 1 (EXC-01); the cover is the page the partner reads closest

### devcost_row_understated__Dunmore_Flats

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `devcost_agrees_wip` @ `devcost_schedule:DEV-2032M04/rows`  
  the development cost schedule analyses 38,373,000.00 of cost; work in process in the ledger carries 38,400,000.00 (off by -27,000.00)

### distribution_dropped_from_rollforward__Brightwater_Commons

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `capital_rollforward` @ `capital_statement:CAP-2032M04/columns/MEM-01/ending_cents`  
  member MEM-01 (Northmoor Development Group) ends at 3,145,800.00; beginning 2,795,800.00 plus contributions 400,000.00 plus result 0.00 less distributions 20,000.00 is 3,175,800.00 (off by -30,000.00)

### division_renumbered__Copperfield_Yards

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `division_coverage` @ `devcost_schedule:DEV-2032M04/rows/DIV-09`  
  job cost division DIV-09 (Finishes) carries 3,020,000.00 of cost and appears in neither the development cost schedule nor a disclosed reconciling item

### draw_schedule_variance__Alderpoint_Terraces

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `draw_schedule_agrees` @ `capital_statement:CAP-2032M04/columns/MEM-02/contributions_cents`  
  member MEM-02 (Halbrook Residential Partners) is shown contributing 1,600,000.00; the 3 draw(s) executed between 2032-04-01 and 2032-04-30 fund 1,645,000.00, a variance of -45,000.00 that the package does not quantify

### footnote_quotes_stale_figure__Dunmore_Flats

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `footnote_figures` @ `footnotes:NOTES-2032M04/notes/NOTE-01/quoted_cents`  
  note NOTE-01 quotes 21,400,000.00 for balance_sheet/row/2100; that cell prints 22,000,000.00 (off by -600,000.00)

### interco_netted_in_assets__Brightwater_Commons

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `interco_classified` @ `balance_sheet:BS-2032M04/rows/1500`  
  intercompany account 1500 Intercompany - managing member advances is in credit at -640,000.00 and is presented in assets; a credit intercompany balance is a liability and belongs in liabilities, not netted against assets

### ledger_account_omitted__Copperfield_Yards

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `tb_completeness` @ `trial_balance:TB-2032M04/rows/1290`  
  ledger account 1290 Construction cost clearing moved 45,000.00 of debits and 45,000.00 of credits in the period and does not appear in the package trial balance; its net balance of 0.00 is why nobody missed it

### net_income_off_statement__Alderpoint_Terraces

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `net_income_agrees` @ `capital_statement:CAP-2032M04/columns/total/net_income_cents`  
  the capital statement allocates 0.00 of result to the members; the statement of operations reports 45,000.00 (off by -45,000.00)

### nil_masks_activity__Dunmore_Flats

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 2)

- **FAIL** `nil_is_genuine` @ `income_statement:IS-2032M04/presented_nil`  
  the statement of operations is presented nil while ledger account 4100 Other income carries 0.00 of debits and 65,000.00 of credits; a bottom line of nil is not the same thing as no activity, and the omission is silent
- **FAIL** `nil_is_genuine` @ `income_statement:IS-2032M04/presented_nil`  
  the statement of operations is presented nil while ledger account 6100 Marketing and promotion carries 65,000.00 of debits and 0.00 of credits; a bottom line of nil is not the same thing as no activity, and the omission is silent

### one_sided_entry__Brightwater_Commons

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `tb_nets_zero` @ `trial_balance:TB-2032M04/rows`  
  the trial balance carries 40,733,000.00 of debits against 40,734,000.00 of credits, out by -1,000.00; every statement built on it inherits a difference that has to land somewhere

### preparer_artifact_released__Copperfield_Yards

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `no_preparer_artifacts` @ `release_log:REL-2032M04/artifacts/ART-10`  
  Reviewer comment log (ART-10) is a preparer-only artifact and is marked released; it is part of how the package was built and not part of the package

### prior_closing_restated__Alderpoint_Terraces

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `prior_period_continuity` @ `capital_statement:CAP-2032M04/columns/MEM-01/beginning_cents`  
  member MEM-01 (Northmoor Development Group) opens at 2,795,800.00; the FY2032-M03 package closed it at 2,745,800.00 (off by 50,000.00), and the partner holds that package

### reciprocal_investment_stale__Dunmore_Flats

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `reciprocal_investment` @ `parent_ledger:PGL-2032M04/accounts`  
  the parent carries 2,795,800.00 of investment in the project entity across 1 account(s); member MEM-01 ends at 3,145,800.00 in the package (off by -350,000.00)

### released_uncleared__Brightwater_Commons

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `release_gate` @ `release_log:REL-2032M04/controls_cleared`  
  the release record itself says the controls were not cleared, and the package is marked released; the exception was known before it was sent

### statement_missing__Copperfield_Yards

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 2)

- **FAIL** `package_complete` @ `income_statement:-`  
  income_statement is missing; the controls that read it cannot run and must not be reported as having passed
- **FAIL** `package_complete` @ `package_cover:COVER-2032M04/contents/income_statement`  
  the contents page names income_statement and the package does not carry it; a contents page is a promise

### total_row_links_elsewhere__Alderpoint_Terraces

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `total_cross_foots` @ `capital_statement:CAP-2032M04/columns/total/contributions_cents`  
  the Total column states 2,060,000.00 on the contributions_cents row; the 2 member column(s) on that row add to 2,000,000.00 (off by 60,000.00); a Total cell that does not sum its own row is linked to something else
