# Tax workpaper build & carry-down control report

**Overall verdict:** FAIL

- Build files analyzed: 27
- Controls in registry: 24
- PASS / REVIEW / FAIL: 1 / 1 / 25

The engine builds the package; these controls prove what it built. All data is
fictional. The controls never write to a source artifact, the builder never writes
to its inputs, and every fiscal year is read from the file, never the system clock.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `frozen_layers_byte_equal` | FAIL | 2 |
| 2 | `captions_advance_one_year` | FAIL | 2 |
| 3 | `capital_flow_equals_delta` | FAIL | 2 |
| 4 | `split_pairs_sum_to_one` | FAIL | 1 |
| 5 | `income_split_rows_exact` | FAIL | 1 |
| 6 | `equity_total_rolls` | FAIL | 1 |
| 7 | `equity_ties_balance_sheet` | FAIL | 2 |
| 8 | `member_capital_chain` | FAIL | 1 |
| 9 | `member_closing_ties_equity` | FAIL | 1 |
| 10 | `tax_basis_is_capital_plus_liability` | FAIL | 1 |
| 11 | `ep_chain_rolls` | FAIL | 1 |
| 12 | `retained_earnings_beginning_rolls` | FAIL | 1 |
| 13 | `row_form_classified_from_balances` | FAIL | 1 |
| 14 | `evidence_ties_locked_source` | FAIL | 1 |
| 15 | `evidence_subtotal_foots` | FAIL | 2 |
| 16 | `citation_block_correct` | FAIL | 1 |
| 17 | `locked_source_digest_matches` | FAIL | 1 |
| 18 | `prebuild_image_digest_matches` | FAIL | 1 |
| 19 | `edit_scope_matches_register` | FAIL | 1 |
| 20 | `cross_schedule_reciprocity` | FAIL | 1 |
| 21 | `source_completeness` | FAIL | 1 |
| 22 | `exception_register_honored` | FAIL | 1 |
| 23 | `render_hygiene` | FAIL | 1 |
| 24 | `history_labels_survive` | FAIL | 1 |

## Build files

### amount_not_integer__Ashfield_Holdings

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `capital_flow_equals_delta` @ `amount:equity[EQ-2029-3010]/amount_cents`  
  AMOUNT_INVALID: equity[EQ-2029-3010]/amount_cents must be integer cents, got 60000000.5 -- amounts are integer cents and are never coerced

### cell_edited_outside_register__Copperfield_Yards_Group

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `edit_scope_matches_register` @ `built_package:WP-RIVERMONT-01-FY2029/notes/N-02/text`  
  cell 'notes/N-02/text' changed from 'The note payable to a member is unsecured and bears interest at a fixed annual rate.' to 'The note payable to a member is unsecured and bears interest at a fixed annual rate, payable at maturity.' and the build register does not name it -- an edit nobody declared is an edit nobody reviewed

### citation_names_wrong_tab__Alderpoint_Terraces_Partners

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `citation_block_correct` @ `built_package:WP-RIVERMONT-01-FY2029/evidence/citation/tab`  
  the citation names tab as 'Monthly activity'; the locked source declares 'TB by entity block' -- a citation a reviewer cannot follow back is not evidence

### clean__Rivermont_Holdings

**Verdict:** PASS (PASS 24, FLAG 0, FAIL 0)

All controls held.

### ep_accumulated_typed_over__Rivermont_Holdings

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `ep_chain_rolls` @ `built_package:WP-RIVERMONT-01-FY2029/earnings_and_profits/blocks[EP-2029]`  
  block 'EP-2029' ends at 1,093,888.89; 610,000.00 accumulated plus 482,888.89 taxable is 1,092,888.89

### equity_total_typed_over__Ashfield_Holdings

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `equity_total_rolls` @ `built_package:WP-RIVERMONT-01-FY2029/equity/total_cents`  
  the equity schedule closes at 6,453,388.89; the prior-year total of 4,935,000.00 plus the current-year flows and the result derives 6,452,888.89, a difference of 500.00

### equity_vs_bs_disclosed__Copperfield_Yards_Group

**Verdict:** REVIEW (PASS 23, FLAG 1, FAIL 0)

- **FLAG** `equity_ties_balance_sheet` @ `built_package:WP-RIVERMONT-01-FY2029/balance_sheet/rows[equity]`  
  the balance sheet presents equity of 6,452,388.89 against a derived 6,452,888.89; the difference of 500.00 is disclosed in the exception register ('Contribution received after the extract was locked; presented on the balance sheet and carried to the equity schedule next year.') -- confirm the disclosure still describes this year before the package is issued

### equity_vs_bs_undisclosed__Alderpoint_Terraces_Partners

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `equity_ties_balance_sheet` @ `built_package:WP-RIVERMONT-01-FY2029/balance_sheet/rows[equity]`  
  the balance sheet presents equity of 6,452,388.89 against a derived 6,452,888.89, a difference of 500.00 that no entry in the disclosed-exception register accounts for

### evidence_subtotal_typed_over__Rivermont_Holdings

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 2)

- **FAIL** `evidence_subtotal_foots` @ `built_package:WP-RIVERMONT-01-FY2029/evidence/subtotal_cents`  
  the evidence subtotal reads 120.00 against 0.00 footed from its own 23 rows -- a subtotal that is not the sum of the rows above it has been typed over
- **FAIL** `evidence_subtotal_foots` @ `built_package:WP-RIVERMONT-01-FY2029/evidence/subtotal_cents`  
  the evidence subtotal is 120.00; a harvested ledger foots to zero, and a non-zero support tab means an account was left behind or counted twice

### evidence_title_off_source__Ashfield_Holdings

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `evidence_ties_locked_source` @ `built_package:WP-RIVERMONT-01-FY2029/evidence/rows[1010]`  
  evidence row '1010' is titled 'Cash - reserve account'; the locked source titles it 'Cash - reserve'

### flow_off_source_delta__Copperfield_Yards_Group

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `capital_flow_equals_delta` @ `built_package:WP-RIVERMONT-01-FY2029/equity/rows[EQ-2029-3000]/amount_cents`  
  account 3000 carries 400,250.00 on the current-year row; the source balance less the prior-year balance is 400,000.00 (source -2,150,000.00, prior -1,750,000.00) -- a flow row is a movement, never a balance

### formula_error_rendered__Alderpoint_Terraces_Partners

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `render_hygiene` @ `built_package:WP-RIVERMONT-01-FY2029/trial_balance/rows[4]/display`  
  the package renders '#REF!' at trial_balance/rows[4]/display -- an error marker where a figure belongs is a cell that never computed, delivered as if it had

### frozen_layer_reordered__Rivermont_Holdings

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 2)

- **FAIL** `frozen_layers_byte_equal` @ `built_package:WP-RIVERMONT-01-FY2029/equity/rows[1]`  
  frozen layer at position 1 is not the prior-year row: the package carries 'EQ-2028-3010' (800,000.00) where the prior package has 'EQ-2028-3000' (450,000.00) -- a prior layer that moves is a signed figure being restated a year later
- **FAIL** `frozen_layers_byte_equal` @ `built_package:WP-RIVERMONT-01-FY2029/equity/rows[2]`  
  frozen layer at position 2 is not the prior-year row: the package carries 'EQ-2028-3000' (450,000.00) where the prior package has 'EQ-2028-3010' (800,000.00) -- a prior layer that moves is a signed figure being restated a year later

### funded_account_left_off__Ashfield_Holdings

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `source_completeness` @ `built_package:WP-RIVERMONT-01-FY2029/trial_balance/rows`  
  account '1010' ('Cash - reserve') carries 140,000.00 in the locked source and appears nowhere on the built trial balance

### history_label_dropped__Copperfield_Yards_Group

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `history_labels_survive` @ `built_package:WP-RIVERMONT-01-FY2029/captions`  
  the prior package labelled a row 'Calderwood Group - Fiscal year ended June 30, 2028' and the built package carries no such label; the figure survived the roll and the thing that said what it was did not

### income_split_off_ratio__Alderpoint_Terraces_Partners

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `income_split_rows_exact` @ `built_package:WP-RIVERMONT-01-FY2029/equity/rows[income/M-CALDERWOOD]/amount_cents`  
  member 'M-CALDERWOOD' is allocated 262,444.44; 524,888.89 at 3500 basis points is 183,711.11 -- the income rows have to sum back to the statement of operations to the cent

### investment_stub_drifts__Rivermont_Holdings

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `cross_schedule_reciprocity` @ `built_package:WP-RIVERMONT-01-FY2029/trial_balance/rows[1300]/balance_cents`  
  the investment in Brightwater Commons JV is carried at 465,000.00 and the counterpart stub reports 463,500.00, a difference of 1,500.00

### liability_split_does_not_sum__Ashfield_Holdings

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `split_pairs_sum_to_one` @ `allocation_register:AR-RIVERMONT-01-FY2029/splits/liability_share`  
  the 'liability_share' split sums to 10100 basis points, not 10000; a pair that is not exactly one allocates a whole the entity never had

### member_closing_off_equity__Copperfield_Yards_Group

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `member_closing_ties_equity` @ `built_package:WP-RIVERMONT-01-FY2029/member_capital/blocks`  
  the members' closing book capital sums to 6,453,488.89 against an equity schedule of 6,452,888.89, a difference of 600.00 across 2 members

### member_contribution_column_typed__Alderpoint_Terraces_Partners

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `member_capital_chain` @ `built_package:WP-RIVERMONT-01-FY2029/member_capital/blocks[MC-2029-M-CALDERWOOD]`  
  book column of block 'MC-2029-M-CALDERWOOD' closes at 2,225,961.11; 1,732,250.00 opening plus 400,400.00 contributions plus 183,711.11 allocated result less 90,000.00 distributions is 2,226,361.11

### placeholder_deregistered__Rivermont_Holdings

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `exception_register_honored` @ `built_package:WP-RIVERMONT-01-FY2029/trial_balance/rows[9990]`  
  account '9990' is a suspense-range or unmapped placeholder and carries no registered exception; a placeholder nobody accepted has been built into the package

### prebuild_image_retaken__Ashfield_Holdings

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `prebuild_image_digest_matches` @ `manifest:MF-RIVERMONT-01-FY2029/prebuild_image_digest`  
  the pre-build image hashes to 236a534a4524e9e9... and the manifest records c620a705ad966309... -- the custody backup on file is not the one the build took, so the edit-scope diff proves nothing

### retained_earnings_not_rolled__Copperfield_Yards_Group

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `retained_earnings_beginning_rolls` @ `built_package:WP-RIVERMONT-01-FY2029/trial_balance/rows[3900]/balance_cents`  
  account 3900 opens the year at 300,000.00; last year's opening of 300,000.00 plus last year's result of 235,000.00 is 535,000.00, a difference of -235,000.00

### row_form_read_from_formula__Alderpoint_Terraces_Partners

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `row_form_classified_from_balances` @ `built_package:WP-RIVERMONT-01-FY2029/equity/rows[EQ-2029-3020]/row_form`  
  account 3020 is classified 'year_delta'; its balances (0.00 at the prior year-end, -250,000.00 at this one) make it 'cumulative_residual' -- the row carries a live formula, which is what the form appears to have been read from

### source_moved_after_build__Rivermont_Holdings

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `locked_source_digest_matches` @ `manifest:MF-RIVERMONT-01-FY2029/locked_source_digest`  
  the locked source hashes to 75c096050fb0a110... and the manifest records 8f109c3f757f64f3... -- the extract the package cites is not the extract it was built from, so every harvested figure is unproved

### stale_prior_year_caption__Ashfield_Holdings

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 2)

- **FAIL** `captions_advance_one_year` @ `built_package:WP-RIVERMONT-01-FY2029/captions/equity_title`  
  caption 'equity_title' reads "Statement of members' equity - fiscal year ended June 30, 2028"; rolling the prior-year caption forward 1 year(s) gives "Statement of members' equity - fiscal year ended June 30, 2029" -- the label has to move with the figures underneath it
- **FAIL** `captions_advance_one_year` @ `built_package:WP-RIVERMONT-01-FY2029/captions/equity_title`  
  caption 'equity_title' still names 2028 after the roll; a stale year on a rolled row sends the reader to the wrong column of the wrong package

### tax_basis_omits_liability__Copperfield_Yards_Group

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `tax_basis_is_capital_plus_liability` @ `built_package:WP-RIVERMONT-01-FY2029/member_capital/blocks[MC-2029-M-CALDERWOOD]/tax_basis_cents`  
  block 'MC-2029-M-CALDERWOOD' reports basis of 2,119,011.11; 2,119,011.11 tax capital plus 917,700.00 liability share is 3,036,711.11, a difference of -917,700.00
