# Trial-balance roll-forward control report

**Overall verdict:** FAIL

- Workpaper files analyzed: 27
- Controls in registry: 24
- PASS / REVIEW / FAIL: 1 / 2 / 24

All data is fictional. The engine is read-only and never writes to a source
artifact. Every registration date is tested against the fiscal window carried
in the file, never the system clock. Balance columns and title columns are
located by their declared role, never by position.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `reg_entities_valid` | FAIL | 2 |
| 3 | `src_code_rows_only` | FAIL | 1 |
| 4 | `src_books_self_balance` | FAIL | 1 |
| 5 | `src_balance_basis` | FAIL | 2 |
| 6 | `scope_final_year_removed` | FAIL | 1 |
| 7 | `scope_renamed_once` | FAIL | 1 |
| 8 | `scope_first_year_registered` | FAIL | 1 |
| 9 | `scope_register_matches_columns` | FAIL | 4 |
| 10 | `map_forward_complete` | FAIL | 4 |
| 11 | `map_reverse_traces` | FAIL | 12 |
| 12 | `map_values_exact` | FAIL | 23 |
| 13 | `map_dual_codes_sum` | FAIL | 4 |
| 14 | `map_duplicate_row_zero` | FAIL | 2 |
| 15 | `col_self_balance` | FAIL | 7 |
| 16 | `elim_covers_all_columns` | FAIL | 4 |
| 17 | `combined_foots` | FAIL | 8 |
| 18 | `bak_backup_complete` | FAIL | 34 |
| 19 | `bak_titles_from_title_column` | FAIL | 26 |
| 20 | `lnk_links_resolve` | FAIL | 41 |
| 21 | `twin_exports_match` | FAIL | 8 |
| 22 | `fee_final_year_suppressed` | FAIL | 1 |
| 23 | `dormant_entity_review` | FLAG | 2 |
| 24 | `reg_short_period_review` | FLAG | 1 |

## Workpaper files

### activity_column_used__Calderwood_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 24)

- **FAIL** `src_balance_basis` @ `workpaper:E-PARENT/column`  
  column 'E-PARENT' matches the book's monthly-activity column on every differing row (11 of them) -- it was populated from the activity column, not the balance column. Activity foots to zero too, so the column self-balances while carrying movement instead of balances
- **FAIL** `map_values_exact` @ `workpaper:E-PARENT/row 0 (0106)`  
  cell carries 2,100.00; the balance column derives 41,500.00 -- the difference of -39,400.00 is a figure the extract does not support
- **FAIL** `map_values_exact` @ `workpaper:E-PARENT/row 1 (0126)`  
  cell carries 900.00; the balance column derives 18,250.00 -- the difference of -17,350.00 is a figure the extract does not support
- **FAIL** `map_values_exact` @ `workpaper:E-PARENT/row 2 (1206)`  
  cell carries 15,000.00; the balance column derives 2,450,000.00 -- the difference of -2,435,000.00 is a figure the extract does not support
- **FAIL** `map_values_exact` @ `workpaper:E-PARENT/row 3 (1222)`  
  cell carries -4,000.00; the balance column derives 610,000.00 -- the difference of -614,000.00 is a figure the extract does not support
- **FAIL** `map_values_exact` @ `workpaper:E-PARENT/row 4 (2001/1601)`  
  cell carries -3,100.00; the balance column derives -96,750.00 -- the difference of 93,650.00 is a figure the extract does not support
- **FAIL** `map_values_exact` @ `workpaper:E-PARENT/row 5 (2936)`  
  cell carries -23,600.00; the balance column derives -3,180,000.00 -- the difference of 3,156,400.00 is a figure the extract does not support
- **FAIL** `map_values_exact` @ `workpaper:E-PARENT/row 6 (2973)`  
  cell carries 11,000.00; the balance column derives 240,000.00 -- the difference of -229,000.00 is a figure the extract does not support
- **FAIL** `map_values_exact` @ `workpaper:E-PARENT/row 7 (3999)`  
  cell carries 0.00; the balance column derives -96,500.00 -- the difference of 96,500.00 is a figure the extract does not support
- **FAIL** `map_values_exact` @ `workpaper:E-PARENT/row 8 (3300)`  
  cell carries -1,500.00; the balance column derives -18,000.00 -- the difference of 16,500.00 is a figure the extract does not support
- **FAIL** `map_values_exact` @ `workpaper:E-PARENT/row 10 (7829)`  
  cell carries 2,400.00; the balance column derives 29,700.00 -- the difference of -27,300.00 is a figure the extract does not support
- **FAIL** `map_values_exact` @ `workpaper:E-PARENT/row 11 (7901)`  
  cell carries 800.00; the balance column derives 1,800.00 -- the difference of -1,000.00 is a figure the extract does not support
- **FAIL** `map_dual_codes_sum` @ `workpaper:E-PARENT/row 4 (2001/1601)`  
  dual-code row collects ['2001', '1601'] and is owed -96,750.00, but carries -3,100.00 -- part of the balance is stranded on a code the sum ignored
- **FAIL** `map_dual_codes_sum` @ `workpaper:E-PARENT/row 7 (3999)`  
  dual-code row collects ['3999', '2999'] and is owed -96,500.00, but carries 0.00 -- part of the balance is stranded on a code the sum ignored
- **FAIL** `lnk_links_resolve` @ `workpaper:E-PARENT/row 0 (0106)`  
  cell carries 2,100.00 but its backup row 'BKP-0106' carries 41,500.00 -- a link that disagrees with its cell looks reviewed and is not
- **FAIL** `lnk_links_resolve` @ `workpaper:E-PARENT/row 1 (0126)`  
  cell carries 900.00 but its backup row 'BKP-0126' carries 18,250.00 -- a link that disagrees with its cell looks reviewed and is not
- **FAIL** `lnk_links_resolve` @ `workpaper:E-PARENT/row 2 (1206)`  
  cell carries 15,000.00 but its backup row 'BKP-1206' carries 2,450,000.00 -- a link that disagrees with its cell looks reviewed and is not
- **FAIL** `lnk_links_resolve` @ `workpaper:E-PARENT/row 3 (1222)`  
  cell carries -4,000.00 but its backup row 'BKP-1222' carries 610,000.00 -- a link that disagrees with its cell looks reviewed and is not
- **FAIL** `lnk_links_resolve` @ `workpaper:E-PARENT/row 4 (2001/1601)`  
  cell carries -3,100.00 but its backup row 'BKP-1601' carries -96,750.00 -- a link that disagrees with its cell looks reviewed and is not
- **FAIL** `lnk_links_resolve` @ `workpaper:E-PARENT/row 5 (2936)`  
  cell carries -23,600.00 but its backup row 'BKP-2936' carries -3,180,000.00 -- a link that disagrees with its cell looks reviewed and is not
- **FAIL** `lnk_links_resolve` @ `workpaper:E-PARENT/row 6 (2973)`  
  cell carries 11,000.00 but its backup row 'BKP-2973' carries 240,000.00 -- a link that disagrees with its cell looks reviewed and is not
- **FAIL** `lnk_links_resolve` @ `workpaper:E-PARENT/row 8 (3300)`  
  cell carries -1,500.00 but its backup row 'BKP-3300' carries -18,000.00 -- a link that disagrees with its cell looks reviewed and is not
- **FAIL** `lnk_links_resolve` @ `workpaper:E-PARENT/row 10 (7829)`  
  cell carries 2,400.00 but its backup row 'BKP-7829' carries 29,700.00 -- a link that disagrees with its cell looks reviewed and is not
- **FAIL** `lnk_links_resolve` @ `workpaper:E-PARENT/row 11 (7901)`  
  cell carries 800.00 but its backup row 'BKP-7901' carries 1,800.00 -- a link that disagrees with its cell looks reviewed and is not

### amount_not_integer__Westmere_Partners

**Verdict:** FAIL (PASS 14, FLAG 1, FAIL 13)

- **FAIL** `src_balance_basis` @ `amount:workpaper[E-PARENT/row 1]/value_cents`  
  AMOUNT_INVALID: workpaper[E-PARENT/row 1]/value_cents must be integer cents, got 1825000.5 -- amounts are integer cents and are never coerced
- **FAIL** `map_reverse_traces` @ `amount:workpaper[E-PARENT/row 1]/value_cents`  
  AMOUNT_INVALID: workpaper[E-PARENT/row 1]/value_cents must be integer cents, got 1825000.5 -- amounts are integer cents and are never coerced
- **FAIL** `map_values_exact` @ `amount:workpaper[E-PARENT/row 1]/value_cents`  
  AMOUNT_INVALID: workpaper[E-PARENT/row 1]/value_cents must be integer cents, got 1825000.5 -- amounts are integer cents and are never coerced
- **FAIL** `map_values_exact` @ `workpaper:E-PARENT/row 1 (0126)`  
  cell carries 0.00; the balance column derives 18,250.00 -- the difference of -18,250.00 is a figure the extract does not support
- **FAIL** `map_dual_codes_sum` @ `amount:workpaper[E-PARENT/row 1]/value_cents`  
  AMOUNT_INVALID: workpaper[E-PARENT/row 1]/value_cents must be integer cents, got 1825000.5 -- amounts are integer cents and are never coerced
- **FAIL** `map_duplicate_row_zero` @ `amount:workpaper[E-PARENT/row 1]/value_cents`  
  AMOUNT_INVALID: workpaper[E-PARENT/row 1]/value_cents must be integer cents, got 1825000.5 -- amounts are integer cents and are never coerced
- **FAIL** `col_self_balance` @ `amount:workpaper[E-PARENT/row 1]/value_cents`  
  AMOUNT_INVALID: workpaper[E-PARENT/row 1]/value_cents must be integer cents, got 1825000.5 -- amounts are integer cents and are never coerced
- **FAIL** `col_self_balance` @ `workpaper:E-PARENT/column`  
  column sums to -18,250.00, not zero -- something is unmapped, dropped or half-posted in this column
- **FAIL** `combined_foots` @ `amount:workpaper[E-PARENT/row 1]/value_cents`  
  AMOUNT_INVALID: workpaper[E-PARENT/row 1]/value_cents must be integer cents, got 1825000.5 -- amounts are integer cents and are never coerced
- **FAIL** `combined_foots` @ `workpaper:-/combined[row 1 (0126)]`  
  combined carries 18,250.00; the cells and eliminations foot to 0.00 -- a combined column maintained beside the grid rather than struck from it
- **FAIL** `lnk_links_resolve` @ `amount:workpaper[E-PARENT/row 1]/value_cents`  
  AMOUNT_INVALID: workpaper[E-PARENT/row 1]/value_cents must be integer cents, got 1825000.5 -- amounts are integer cents and are never coerced
- **FAIL** `twin_exports_match` @ `amount:workpaper[E-PARENT/row 1]/value_cents`  
  AMOUNT_INVALID: workpaper[E-PARENT/row 1]/value_cents must be integer cents, got 1825000.5 -- amounts are integer cents and are never coerced
- **FAIL** `twin_exports_match` @ `twin_export:E-PARENT/row 1 (0126)`  
  the twin carries 18,250.00 where the workpaper carries 0.00 -- two formats, two truths, and the reviewer always finds the stale one
- **FLAG** `dormant_entity_review` @ `amount:workpaper[E-PARENT/row 1]/value_cents`  
  AMOUNT_INVALID: workpaper[E-PARENT/row 1]/value_cents must be integer cents, got 1825000.5 -- amounts are integer cents and are never coerced

### backup_row_missing__Ashfield_Holdings

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 2)

- **FAIL** `bak_backup_complete` @ `backup_tab:-/BK2-1206`  
  mapped account 'BK2-1206' is missing from the backup tab -- a figure with no backup row cannot be reviewed
- **FAIL** `lnk_links_resolve` @ `workpaper:E-COPPERFIELD/row 2 (1206)`  
  link points at 'BK2-1206', which the backup tab does not carry -- a dead link fails exactly when a reviewer follows it

### backup_title_from_category__Rivermont_Holdings

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 26)

- **FAIL** `bak_titles_from_title_column` @ `backup_tab:-/BK1-0106/title`  
  backup titles 'BK1-0106' as 'Cash'; the source's title column says 'Cash - operating' -- this is the source's CATEGORY column, the text neighbour of the title column: the harvest read text by position, not by role
- **FAIL** `bak_titles_from_title_column` @ `backup_tab:-/BK1-1206/title`  
  backup titles 'BK1-1206' as 'Investments'; the source's title column says 'Investment in project' -- this is the source's CATEGORY column, the text neighbour of the title column: the harvest read text by position, not by role
- **FAIL** `bak_titles_from_title_column` @ `backup_tab:-/BK1-2001/title`  
  backup titles 'BK1-2001' as 'Payables'; the source's title column says 'Accounts payable' -- this is the source's CATEGORY column, the text neighbour of the title column: the harvest read text by position, not by role
- **FAIL** `bak_titles_from_title_column` @ `backup_tab:-/BK1-2936/title`  
  backup titles 'BK1-2936' as 'Equity'; the source's title column says 'Equity - parent' -- this is the source's CATEGORY column, the text neighbour of the title column: the harvest read text by position, not by role
- **FAIL** `bak_titles_from_title_column` @ `backup_tab:-/BK1-2999/title`  
  backup titles 'BK1-2999' as 'Equity'; the source's title column says 'Retained earnings - beginning' -- this is the source's CATEGORY column, the text neighbour of the title column: the harvest read text by position, not by role
- **FAIL** `bak_titles_from_title_column` @ `backup_tab:-/BK2-0106/title`  
  backup titles 'BK2-0106' as 'Cash'; the source's title column says 'Cash - operating' -- this is the source's CATEGORY column, the text neighbour of the title column: the harvest read text by position, not by role
- **FAIL** `bak_titles_from_title_column` @ `backup_tab:-/BK2-1206/title`  
  backup titles 'BK2-1206' as 'Investments'; the source's title column says 'Investment in project' -- this is the source's CATEGORY column, the text neighbour of the title column: the harvest read text by position, not by role
- **FAIL** `bak_titles_from_title_column` @ `backup_tab:-/BK2-2001/title`  
  backup titles 'BK2-2001' as 'Payables'; the source's title column says 'Accounts payable' -- this is the source's CATEGORY column, the text neighbour of the title column: the harvest read text by position, not by role
- **FAIL** `bak_titles_from_title_column` @ `backup_tab:-/BK2-2936/title`  
  backup titles 'BK2-2936' as 'Equity'; the source's title column says 'Equity - parent' -- this is the source's CATEGORY column, the text neighbour of the title column: the harvest read text by position, not by role
- **FAIL** `bak_titles_from_title_column` @ `backup_tab:-/BK2-2999/title`  
  backup titles 'BK2-2999' as 'Equity'; the source's title column says 'Retained earnings - beginning' -- this is the source's CATEGORY column, the text neighbour of the title column: the harvest read text by position, not by role
- **FAIL** `bak_titles_from_title_column` @ `backup_tab:-/BK3-0106/title`  
  backup titles 'BK3-0106' as 'Cash'; the source's title column says 'Cash - operating' -- this is the source's CATEGORY column, the text neighbour of the title column: the harvest read text by position, not by role
- **FAIL** `bak_titles_from_title_column` @ `backup_tab:-/BK3-1206/title`  
  backup titles 'BK3-1206' as 'Investments'; the source's title column says 'Investment in project' -- this is the source's CATEGORY column, the text neighbour of the title column: the harvest read text by position, not by role
- **FAIL** `bak_titles_from_title_column` @ `backup_tab:-/BK3-2001/title`  
  backup titles 'BK3-2001' as 'Payables'; the source's title column says 'Accounts payable' -- this is the source's CATEGORY column, the text neighbour of the title column: the harvest read text by position, not by role
- **FAIL** `bak_titles_from_title_column` @ `backup_tab:-/BK3-2936/title`  
  backup titles 'BK3-2936' as 'Equity'; the source's title column says 'Equity - parent' -- this is the source's CATEGORY column, the text neighbour of the title column: the harvest read text by position, not by role
- **FAIL** `bak_titles_from_title_column` @ `backup_tab:-/BK3-2999/title`  
  backup titles 'BK3-2999' as 'Equity'; the source's title column says 'Retained earnings - beginning' -- this is the source's CATEGORY column, the text neighbour of the title column: the harvest read text by position, not by role
- **FAIL** `bak_titles_from_title_column` @ `backup_tab:-/BKP-0106/title`  
  backup titles 'BKP-0106' as 'Cash'; the source's title column says 'Cash - operating' -- this is the source's CATEGORY column, the text neighbour of the title column: the harvest read text by position, not by role
- **FAIL** `bak_titles_from_title_column` @ `backup_tab:-/BKP-0126/title`  
  backup titles 'BKP-0126' as 'Cash'; the source's title column says 'Cash - reserve' -- this is the source's CATEGORY column, the text neighbour of the title column: the harvest read text by position, not by role
- **FAIL** `bak_titles_from_title_column` @ `backup_tab:-/BKP-1206/title`  
  backup titles 'BKP-1206' as 'Investments'; the source's title column says 'Investment in project' -- this is the source's CATEGORY column, the text neighbour of the title column: the harvest read text by position, not by role
- **FAIL** `bak_titles_from_title_column` @ `backup_tab:-/BKP-1222/title`  
  backup titles 'BKP-1222' as 'Investments'; the source's title column says 'Investment in joint venture' -- this is the source's CATEGORY column, the text neighbour of the title column: the harvest read text by position, not by role
- **FAIL** `bak_titles_from_title_column` @ `backup_tab:-/BKP-1601/title`  
  backup titles 'BKP-1601' as 'Payables'; the source's title column says 'Accounts payable' -- this is the source's CATEGORY column, the text neighbour of the title column: the harvest read text by position, not by role
- **FAIL** `bak_titles_from_title_column` @ `backup_tab:-/BKP-2936/title`  
  backup titles 'BKP-2936' as 'Equity'; the source's title column says 'Equity - parent' -- this is the source's CATEGORY column, the text neighbour of the title column: the harvest read text by position, not by role
- **FAIL** `bak_titles_from_title_column` @ `backup_tab:-/BKP-2973/title`  
  backup titles 'BKP-2973' as 'Equity'; the source's title column says 'Distributions - parent' -- this is the source's CATEGORY column, the text neighbour of the title column: the harvest read text by position, not by role
- **FAIL** `bak_titles_from_title_column` @ `backup_tab:-/BKP-2999/title`  
  backup titles 'BKP-2999' as 'Equity'; the source's title column says 'Retained earnings - beginning' -- this is the source's CATEGORY column, the text neighbour of the title column: the harvest read text by position, not by role
- **FAIL** `bak_titles_from_title_column` @ `backup_tab:-/BKP-3300/title`  
  backup titles 'BKP-3300' as 'Income'; the source's title column says 'Management fees' -- this is the source's CATEGORY column, the text neighbour of the title column: the harvest read text by position, not by role
- **FAIL** `bak_titles_from_title_column` @ `backup_tab:-/BKP-7829/title`  
  backup titles 'BKP-7829' as 'Expense'; the source's title column says 'Permits and fees' -- this is the source's CATEGORY column, the text neighbour of the title column: the harvest read text by position, not by role
- **FAIL** `bak_titles_from_title_column` @ `backup_tab:-/BKP-7901/title`  
  backup titles 'BKP-7901' as 'Expense'; the source's title column says 'Filing fee expense' -- this is the source's CATEGORY column, the text neighbour of the title column: the harvest read text by position, not by role

### balance_lands_nowhere__Calderwood_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 12)

- **FAIL** `map_forward_complete` @ `source_extract:E-PARENT/2999`  
  book balance -96,500.00 on code '2999' is collected by no workpaper row -- the balance lands nowhere, and both sides still foot, which is why only enumeration catches it
- **FAIL** `map_forward_complete` @ `source_extract:E-BRIGHTWATER/2999`  
  book balance -232,200.00 on code '2999' is collected by no workpaper row -- the balance lands nowhere, and both sides still foot, which is why only enumeration catches it
- **FAIL** `map_forward_complete` @ `source_extract:E-COPPERFIELD/2999`  
  book balance -287,400.00 on code '2999' is collected by no workpaper row -- the balance lands nowhere, and both sides still foot, which is why only enumeration catches it
- **FAIL** `map_forward_complete` @ `source_extract:E-ALDERPOINT/2999`  
  book balance -65,950.00 on code '2999' is collected by no workpaper row -- the balance lands nowhere, and both sides still foot, which is why only enumeration catches it
- **FAIL** `map_reverse_traces` @ `workpaper:E-ALDERPOINT/row 7 (3999)`  
  cell carries -65,950.00 but the book supports no balance on that row -- a phantom value is a number somebody authored rather than harvested
- **FAIL** `map_reverse_traces` @ `workpaper:E-BRIGHTWATER/row 7 (3999)`  
  cell carries -232,200.00 but the book supports no balance on that row -- a phantom value is a number somebody authored rather than harvested
- **FAIL** `map_reverse_traces` @ `workpaper:E-COPPERFIELD/row 7 (3999)`  
  cell carries -287,400.00 but the book supports no balance on that row -- a phantom value is a number somebody authored rather than harvested
- **FAIL** `map_reverse_traces` @ `workpaper:E-PARENT/row 7 (3999)`  
  cell carries -96,500.00 but the book supports no balance on that row -- a phantom value is a number somebody authored rather than harvested
- **FAIL** `map_values_exact` @ `workpaper:E-ALDERPOINT/row 7 (3999)`  
  cell carries -65,950.00; the balance column derives 0.00 -- the difference of -65,950.00 is a figure the extract does not support
- **FAIL** `map_values_exact` @ `workpaper:E-BRIGHTWATER/row 7 (3999)`  
  cell carries -232,200.00; the balance column derives 0.00 -- the difference of -232,200.00 is a figure the extract does not support
- **FAIL** `map_values_exact` @ `workpaper:E-COPPERFIELD/row 7 (3999)`  
  cell carries -287,400.00; the balance column derives 0.00 -- the difference of -287,400.00 is a figure the extract does not support
- **FAIL** `map_values_exact` @ `workpaper:E-PARENT/row 7 (3999)`  
  cell carries -96,500.00; the balance column derives 0.00 -- the difference of -96,500.00 is a figure the extract does not support

### book_out_of_balance__Westmere_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 3)

- **FAIL** `src_books_self_balance` @ `source_extract:TB-2029-06-30/books[BK1]`  
  book 'BK1' sums to 500.00, not zero -- an unbalanced extract is incomplete or mid-posting, and nothing populated from it can be trusted
- **FAIL** `map_values_exact` @ `workpaper:E-BRIGHTWATER/row 0 (0106)`  
  cell carries 96,400.00; the balance column derives 96,900.00 -- the difference of -500.00 is a figure the extract does not support
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BK1-0106`  
  backup carries 96,400.00 for 'BK1-0106'; the extract carries 96,900.00

### cell_off_extract__Ashfield_Holdings

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 5)

- **FAIL** `map_values_exact` @ `workpaper:E-COPPERFIELD/row 0 (0106)`  
  cell carries 59,900.00; the balance column derives 58,900.00 -- the difference of 1,000.00 is a figure the extract does not support
- **FAIL** `col_self_balance` @ `workpaper:E-COPPERFIELD/column`  
  column sums to 1,000.00, not zero -- something is unmapped, dropped or half-posted in this column
- **FAIL** `combined_foots` @ `workpaper:-/combined[row 0 (0106)]`  
  combined carries 219,550.00; the cells and eliminations foot to 220,550.00 -- a combined column maintained beside the grid rather than struck from it
- **FAIL** `lnk_links_resolve` @ `workpaper:E-COPPERFIELD/row 0 (0106)`  
  cell carries 59,900.00 but its backup row 'BK2-0106' carries 58,900.00 -- a link that disagrees with its cell looks reviewed and is not
- **FAIL** `twin_exports_match` @ `twin_export:E-COPPERFIELD/row 0 (0106)`  
  the twin carries 58,900.00 where the workpaper carries 59,900.00 -- two formats, two truths, and the reviewer always finds the stale one

### clean__Rivermont_Holdings

**Verdict:** PASS (PASS 24, FLAG 0, FAIL 0)

All controls held.

### column_does_not_foot__Rivermont_Holdings

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 4)

- **FAIL** `map_values_exact` @ `workpaper:E-ALDERPOINT/row 2 (1206)`  
  cell carries 0.00; the balance column derives 940,000.00 -- the difference of -940,000.00 is a figure the extract does not support
- **FAIL** `col_self_balance` @ `workpaper:E-ALDERPOINT/column`  
  column sums to -940,000.00, not zero -- something is unmapped, dropped or half-posted in this column
- **FAIL** `combined_foots` @ `workpaper:-/combined[row 2 (1206)]`  
  combined carries 7,520,000.00; the cells and eliminations foot to 6,580,000.00 -- a combined column maintained beside the grid rather than struck from it
- **FAIL** `twin_exports_match` @ `twin_export:E-ALDERPOINT/row 2 (1206)`  
  the twin carries 940,000.00 where the workpaper carries 0.00 -- two formats, two truths, and the reviewer always finds the stale one

### column_not_in_register__Calderwood_Group

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 2)

- **FAIL** `scope_register_matches_columns` @ `workpaper:-/columns[E-THORNBURY]`  
  column 'E-THORNBURY' is not in the confirmed register -- an unconfirmed column is scope nobody signed off
- **FAIL** `elim_covers_all_columns` @ `workpaper:-/eliminations[E-THORNBURY]`  
  column 'E-THORNBURY' sits outside the eliminations range -- a range that ends at last year's final column silently excludes every column added this year

### combined_maintained_by_hand__Westmere_Partners

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `combined_foots` @ `workpaper:-/combined[row 0 (0106)]`  
  combined carries 219,800.00; the cells and eliminations foot to 219,550.00 -- a combined column maintained beside the grid rather than struck from it

### dormant_column_present__Ashfield_Holdings

**Verdict:** REVIEW (PASS 23, FLAG 1, FAIL 0)

- **FLAG** `dormant_entity_review` @ `workpaper:E-DUNMORE/column`  
  column 'E-DUNMORE' is genuinely empty -- the book carries no balances at all. Confirm the entity is dormant rather than booked somewhere else

### dual_code_half_dropped__Rivermont_Holdings

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 5)

- **FAIL** `map_values_exact` @ `workpaper:E-BRIGHTWATER/row 4 (2001/1601)`  
  cell carries 0.00; the balance column derives -44,200.00 -- the difference of 44,200.00 is a figure the extract does not support
- **FAIL** `map_dual_codes_sum` @ `workpaper:E-BRIGHTWATER/row 4 (2001/1601)`  
  dual-code row collects ['2001', '1601'] and is owed -44,200.00, but carries 0.00 -- part of the balance is stranded on a code the sum ignored
- **FAIL** `col_self_balance` @ `workpaper:E-BRIGHTWATER/column`  
  column sums to 44,200.00, not zero -- something is unmapped, dropped or half-posted in this column
- **FAIL** `combined_foots` @ `workpaper:-/combined[row 4 (2001/1601)]`  
  combined carries -229,250.00; the cells and eliminations foot to -185,050.00 -- a combined column maintained beside the grid rather than struck from it
- **FAIL** `twin_exports_match` @ `twin_export:E-BRIGHTWATER/row 4 (2001/1601)`  
  the twin carries -44,200.00 where the workpaper carries 0.00 -- two formats, two truths, and the reviewer always finds the stale one

### duplicate_entity_id__Calderwood_Group

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `reg_entities_valid` @ `entity_register:REG-2029/entities[E-BRIGHTWATER]`  
  entity id 'E-BRIGHTWATER' appears more than once -- the same entity cannot be rolled forward twice

### duplicate_row_populated__Westmere_Partners

**Verdict:** FAIL (PASS 18, FLAG 0, FAIL 6)

- **FAIL** `map_reverse_traces` @ `workpaper:E-PARENT/row 9 (3300)`  
  cell carries -18,000.00 but the book supports no balance on that row -- a phantom value is a number somebody authored rather than harvested
- **FAIL** `map_values_exact` @ `workpaper:E-PARENT/row 9 (3300)`  
  cell carries -18,000.00; the balance column derives 0.00 -- the difference of -18,000.00 is a figure the extract does not support
- **FAIL** `map_duplicate_row_zero` @ `workpaper:E-PARENT/row 9 (3300)`  
  duplicated row code '3300' carries -18,000.00 on its later instance -- the first instance consumed the code, so this is the same balance twice
- **FAIL** `col_self_balance` @ `workpaper:E-PARENT/column`  
  column sums to -18,000.00, not zero -- something is unmapped, dropped or half-posted in this column
- **FAIL** `combined_foots` @ `workpaper:-/combined[row 9 (3300)]`  
  combined carries 0.00; the cells and eliminations foot to -18,000.00 -- a combined column maintained beside the grid rather than struck from it
- **FAIL** `twin_exports_match` @ `twin_export:E-PARENT/row 9 (3300)`  
  the twin carries 0.00 where the workpaper carries -18,000.00 -- two formats, two truths, and the reviewer always finds the stale one

### elimination_range_short__Ashfield_Holdings

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `elim_covers_all_columns` @ `workpaper:-/eliminations[E-ALDERPOINT]`  
  column 'E-ALDERPOINT' sits outside the eliminations range -- a range that ends at last year's final column silently excludes every column added this year

### final_year_column_kept__Rivermont_Holdings

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 3)

- **FAIL** `scope_final_year_removed` @ `entity_register:REG-2029/entities[E-LARKFIELD]`  
  final-year entity 'E-LARKFIELD' still has a workpaper column -- its last return was prepared off the prior year, and a live column here will be populated by habit
- **FAIL** `scope_register_matches_columns` @ `workpaper:-/columns[E-LARKFIELD]`  
  column 'E-LARKFIELD' is not in the confirmed register -- an unconfirmed column is scope nobody signed off
- **FAIL** `elim_covers_all_columns` @ `workpaper:-/eliminations[E-LARKFIELD]`  
  column 'E-LARKFIELD' sits outside the eliminations range -- a range that ends at last year's final column silently excludes every column added this year

### final_year_fee_charged__Calderwood_Group

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `fee_final_year_suppressed` @ `entity_register:REG-2029/entities[E-LARKFIELD]/fee_due_cents`  
  final-year entity 'E-LARKFIELD' shows a fee of 800.00 -- the fixed fee attaches to the coming year, which this entity will not see

### first_year_no_registration__Westmere_Partners

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `scope_first_year_registered` @ `entity_register:REG-2029/entities[E-ALDERPOINT]/registration_date`  
  first-year entity 'E-ALDERPOINT' carries no readable registration date -- its first-period start is the one fact the preparer cannot infer

### link_dangles__Ashfield_Holdings

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `lnk_links_resolve` @ `workpaper:E-PARENT/row 0 (0106)`  
  link points at 'BKP-0000', which the backup tab does not carry -- a dead link fails exactly when a reviewer follows it

### memo_row_harvested__Rivermont_Holdings

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 2)

- **FAIL** `src_code_rows_only` @ `source_extract:TB-2029-06-30/memo[BKP-9100]`  
  memo-row account 'BKP-9100' was harvested into the backup tab -- memo rows are side-schedule annotations and populating one double counts what a schedule already explains
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BKP-9100`  
  backup account 'BKP-9100' belongs to no mapped book

### missing_artifact__Calderwood_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 53)

- **FAIL** `set_complete` @ `backup_tab:-`  
  required artifact 'backup_tab' is missing -- the cycle cannot be audited from a partial record
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BK1-0106`  
  mapped account 'BK1-0106' is missing from the backup tab -- a figure with no backup row cannot be reviewed
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BK1-1206`  
  mapped account 'BK1-1206' is missing from the backup tab -- a figure with no backup row cannot be reviewed
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BK1-2001`  
  mapped account 'BK1-2001' is missing from the backup tab -- a figure with no backup row cannot be reviewed
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BK1-2936`  
  mapped account 'BK1-2936' is missing from the backup tab -- a figure with no backup row cannot be reviewed
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BK1-2999`  
  mapped account 'BK1-2999' is missing from the backup tab -- a figure with no backup row cannot be reviewed
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BK2-0106`  
  mapped account 'BK2-0106' is missing from the backup tab -- a figure with no backup row cannot be reviewed
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BK2-1206`  
  mapped account 'BK2-1206' is missing from the backup tab -- a figure with no backup row cannot be reviewed
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BK2-2001`  
  mapped account 'BK2-2001' is missing from the backup tab -- a figure with no backup row cannot be reviewed
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BK2-2936`  
  mapped account 'BK2-2936' is missing from the backup tab -- a figure with no backup row cannot be reviewed
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BK2-2999`  
  mapped account 'BK2-2999' is missing from the backup tab -- a figure with no backup row cannot be reviewed
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BK3-0106`  
  mapped account 'BK3-0106' is missing from the backup tab -- a figure with no backup row cannot be reviewed
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BK3-1206`  
  mapped account 'BK3-1206' is missing from the backup tab -- a figure with no backup row cannot be reviewed
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BK3-2001`  
  mapped account 'BK3-2001' is missing from the backup tab -- a figure with no backup row cannot be reviewed
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BK3-2936`  
  mapped account 'BK3-2936' is missing from the backup tab -- a figure with no backup row cannot be reviewed
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BK3-2999`  
  mapped account 'BK3-2999' is missing from the backup tab -- a figure with no backup row cannot be reviewed
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BKP-0106`  
  mapped account 'BKP-0106' is missing from the backup tab -- a figure with no backup row cannot be reviewed
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BKP-0126`  
  mapped account 'BKP-0126' is missing from the backup tab -- a figure with no backup row cannot be reviewed
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BKP-1206`  
  mapped account 'BKP-1206' is missing from the backup tab -- a figure with no backup row cannot be reviewed
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BKP-1222`  
  mapped account 'BKP-1222' is missing from the backup tab -- a figure with no backup row cannot be reviewed
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BKP-1601`  
  mapped account 'BKP-1601' is missing from the backup tab -- a figure with no backup row cannot be reviewed
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BKP-2936`  
  mapped account 'BKP-2936' is missing from the backup tab -- a figure with no backup row cannot be reviewed
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BKP-2973`  
  mapped account 'BKP-2973' is missing from the backup tab -- a figure with no backup row cannot be reviewed
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BKP-2999`  
  mapped account 'BKP-2999' is missing from the backup tab -- a figure with no backup row cannot be reviewed
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BKP-3300`  
  mapped account 'BKP-3300' is missing from the backup tab -- a figure with no backup row cannot be reviewed
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BKP-7829`  
  mapped account 'BKP-7829' is missing from the backup tab -- a figure with no backup row cannot be reviewed
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BKP-7901`  
  mapped account 'BKP-7901' is missing from the backup tab -- a figure with no backup row cannot be reviewed
- **FAIL** `lnk_links_resolve` @ `workpaper:E-ALDERPOINT/row 0 (0106)`  
  link points at 'BK3-0106', which the backup tab does not carry -- a dead link fails exactly when a reviewer follows it
- **FAIL** `lnk_links_resolve` @ `workpaper:E-BRIGHTWATER/row 0 (0106)`  
  link points at 'BK1-0106', which the backup tab does not carry -- a dead link fails exactly when a reviewer follows it
- **FAIL** `lnk_links_resolve` @ `workpaper:E-COPPERFIELD/row 0 (0106)`  
  link points at 'BK2-0106', which the backup tab does not carry -- a dead link fails exactly when a reviewer follows it
- **FAIL** `lnk_links_resolve` @ `workpaper:E-PARENT/row 0 (0106)`  
  link points at 'BKP-0106', which the backup tab does not carry -- a dead link fails exactly when a reviewer follows it
- **FAIL** `lnk_links_resolve` @ `workpaper:E-PARENT/row 1 (0126)`  
  link points at 'BKP-0126', which the backup tab does not carry -- a dead link fails exactly when a reviewer follows it
- **FAIL** `lnk_links_resolve` @ `workpaper:E-ALDERPOINT/row 2 (1206)`  
  link points at 'BK3-1206', which the backup tab does not carry -- a dead link fails exactly when a reviewer follows it
- **FAIL** `lnk_links_resolve` @ `workpaper:E-BRIGHTWATER/row 2 (1206)`  
  link points at 'BK1-1206', which the backup tab does not carry -- a dead link fails exactly when a reviewer follows it
- **FAIL** `lnk_links_resolve` @ `workpaper:E-COPPERFIELD/row 2 (1206)`  
  link points at 'BK2-1206', which the backup tab does not carry -- a dead link fails exactly when a reviewer follows it
- **FAIL** `lnk_links_resolve` @ `workpaper:E-PARENT/row 2 (1206)`  
  link points at 'BKP-1206', which the backup tab does not carry -- a dead link fails exactly when a reviewer follows it
- **FAIL** `lnk_links_resolve` @ `workpaper:E-PARENT/row 3 (1222)`  
  link points at 'BKP-1222', which the backup tab does not carry -- a dead link fails exactly when a reviewer follows it
- **FAIL** `lnk_links_resolve` @ `workpaper:E-ALDERPOINT/row 4 (2001/1601)`  
  link points at 'BK3-2001', which the backup tab does not carry -- a dead link fails exactly when a reviewer follows it
- **FAIL** `lnk_links_resolve` @ `workpaper:E-BRIGHTWATER/row 4 (2001/1601)`  
  link points at 'BK1-2001', which the backup tab does not carry -- a dead link fails exactly when a reviewer follows it
- **FAIL** `lnk_links_resolve` @ `workpaper:E-COPPERFIELD/row 4 (2001/1601)`  
  link points at 'BK2-2001', which the backup tab does not carry -- a dead link fails exactly when a reviewer follows it
- **FAIL** `lnk_links_resolve` @ `workpaper:E-PARENT/row 4 (2001/1601)`  
  link points at 'BKP-1601', which the backup tab does not carry -- a dead link fails exactly when a reviewer follows it
- **FAIL** `lnk_links_resolve` @ `workpaper:E-ALDERPOINT/row 5 (2936)`  
  link points at 'BK3-2936', which the backup tab does not carry -- a dead link fails exactly when a reviewer follows it
- **FAIL** `lnk_links_resolve` @ `workpaper:E-BRIGHTWATER/row 5 (2936)`  
  link points at 'BK1-2936', which the backup tab does not carry -- a dead link fails exactly when a reviewer follows it
- **FAIL** `lnk_links_resolve` @ `workpaper:E-COPPERFIELD/row 5 (2936)`  
  link points at 'BK2-2936', which the backup tab does not carry -- a dead link fails exactly when a reviewer follows it
- **FAIL** `lnk_links_resolve` @ `workpaper:E-PARENT/row 5 (2936)`  
  link points at 'BKP-2936', which the backup tab does not carry -- a dead link fails exactly when a reviewer follows it
- **FAIL** `lnk_links_resolve` @ `workpaper:E-PARENT/row 6 (2973)`  
  link points at 'BKP-2973', which the backup tab does not carry -- a dead link fails exactly when a reviewer follows it
- **FAIL** `lnk_links_resolve` @ `workpaper:E-ALDERPOINT/row 7 (3999)`  
  link points at 'BK3-2999', which the backup tab does not carry -- a dead link fails exactly when a reviewer follows it
- **FAIL** `lnk_links_resolve` @ `workpaper:E-BRIGHTWATER/row 7 (3999)`  
  link points at 'BK1-2999', which the backup tab does not carry -- a dead link fails exactly when a reviewer follows it
- **FAIL** `lnk_links_resolve` @ `workpaper:E-COPPERFIELD/row 7 (3999)`  
  link points at 'BK2-2999', which the backup tab does not carry -- a dead link fails exactly when a reviewer follows it
- **FAIL** `lnk_links_resolve` @ `workpaper:E-PARENT/row 7 (3999)`  
  link points at 'BKP-2999', which the backup tab does not carry -- a dead link fails exactly when a reviewer follows it
- **FAIL** `lnk_links_resolve` @ `workpaper:E-PARENT/row 8 (3300)`  
  link points at 'BKP-3300', which the backup tab does not carry -- a dead link fails exactly when a reviewer follows it
- **FAIL** `lnk_links_resolve` @ `workpaper:E-PARENT/row 10 (7829)`  
  link points at 'BKP-7829', which the backup tab does not carry -- a dead link fails exactly when a reviewer follows it
- **FAIL** `lnk_links_resolve` @ `workpaper:E-PARENT/row 11 (7901)`  
  link points at 'BKP-7901', which the backup tab does not carry -- a dead link fails exactly when a reviewer follows it

### phantom_cell__Westmere_Partners

**Verdict:** FAIL (PASS 18, FLAG 0, FAIL 6)

- **FAIL** `map_reverse_traces` @ `workpaper:E-BRIGHTWATER/row 10 (7829)`  
  cell carries 3,400.00 but the book supports no balance on that row -- a phantom value is a number somebody authored rather than harvested
- **FAIL** `map_values_exact` @ `workpaper:E-BRIGHTWATER/row 10 (7829)`  
  cell carries 3,400.00; the balance column derives 0.00 -- the difference of 3,400.00 is a figure the extract does not support
- **FAIL** `col_self_balance` @ `workpaper:E-BRIGHTWATER/column`  
  column sums to 3,400.00, not zero -- something is unmapped, dropped or half-posted in this column
- **FAIL** `combined_foots` @ `workpaper:-/combined[row 10 (7829)]`  
  combined carries 29,700.00; the cells and eliminations foot to 33,100.00 -- a combined column maintained beside the grid rather than struck from it
- **FAIL** `lnk_links_resolve` @ `workpaper:E-BRIGHTWATER/row 10 (7829)`  
  cell carries 3,400.00 but its backup row 'BK1-0106' carries 96,400.00 -- a link that disagrees with its cell looks reviewed and is not
- **FAIL** `twin_exports_match` @ `twin_export:E-BRIGHTWATER/row 10 (7829)`  
  the twin carries 0.00 where the workpaper carries 3,400.00 -- two formats, two truths, and the reviewer always finds the stale one

### rename_double_counted__Ashfield_Holdings

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 3)

- **FAIL** `scope_renamed_once` @ `prior_structure:PRIOR-2028/renames[E-HAWTHORNE->E-COPPERFIELD]`  
  renamed entity still carries a column under its old identity 'E-HAWTHORNE' beside 'E-COPPERFIELD' -- one entity, two columns, every balance at risk of being counted twice
- **FAIL** `scope_register_matches_columns` @ `workpaper:-/columns[E-HAWTHORNE]`  
  column 'E-HAWTHORNE' is not in the confirmed register -- an unconfirmed column is scope nobody signed off
- **FAIL** `elim_covers_all_columns` @ `workpaper:-/eliminations[E-HAWTHORNE]`  
  column 'E-HAWTHORNE' sits outside the eliminations range -- a range that ends at last year's final column silently excludes every column added this year

### short_first_period__Rivermont_Holdings

**Verdict:** REVIEW (PASS 23, FLAG 1, FAIL 0)

- **FLAG** `reg_short_period_review` @ `entity_register:REG-2029/entities[E-ALDERPOINT]/registration_date`  
  first-year entity 'E-ALDERPOINT' registered 275 days into the fiscal year (band is 90) -- its first period starts 2029-04-02, not at the fiscal start, and the preparer needs that date

### twin_drifts__Calderwood_Group

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 1)

- **FAIL** `twin_exports_match` @ `twin_export:E-BRIGHTWATER/row 0 (0106)`  
  the twin carries 96,475.00 where the workpaper carries 96,400.00 -- two formats, two truths, and the reviewer always finds the stale one

### unknown_entity_status__Westmere_Partners

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 12)

- **FAIL** `reg_entities_valid` @ `entity_register:REG-2029/entities[E-BRIGHTWATER]`  
  status 'pending_review' is not one of ('continuing', 'first_year', 'final_year', 'excluded') -- an uncharacterised entity is one nobody decided the roll-forward treatment for
- **FAIL** `scope_register_matches_columns` @ `workpaper:-/columns[E-BRIGHTWATER]`  
  column 'E-BRIGHTWATER' is not in the confirmed register -- an unconfirmed column is scope nobody signed off
- **FAIL** `map_reverse_traces` @ `workpaper:E-BRIGHTWATER/row 0 (0106)`  
  cell carries 96,400.00 but the book supports no balance on that row -- a phantom value is a number somebody authored rather than harvested
- **FAIL** `map_reverse_traces` @ `workpaper:E-BRIGHTWATER/row 2 (1206)`  
  cell carries 1,820,000.00 but the book supports no balance on that row -- a phantom value is a number somebody authored rather than harvested
- **FAIL** `map_reverse_traces` @ `workpaper:E-BRIGHTWATER/row 4 (2001/1601)`  
  cell carries -44,200.00 but the book supports no balance on that row -- a phantom value is a number somebody authored rather than harvested
- **FAIL** `map_reverse_traces` @ `workpaper:E-BRIGHTWATER/row 5 (2936)`  
  cell carries -1,640,000.00 but the book supports no balance on that row -- a phantom value is a number somebody authored rather than harvested
- **FAIL** `map_reverse_traces` @ `workpaper:E-BRIGHTWATER/row 7 (3999)`  
  cell carries -232,200.00 but the book supports no balance on that row -- a phantom value is a number somebody authored rather than harvested
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BK1-0106`  
  backup account 'BK1-0106' belongs to no mapped book
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BK1-1206`  
  backup account 'BK1-1206' belongs to no mapped book
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BK1-2001`  
  backup account 'BK1-2001' belongs to no mapped book
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BK1-2936`  
  backup account 'BK1-2936' belongs to no mapped book
- **FAIL** `bak_backup_complete` @ `backup_tab:-/BK1-2999`  
  backup account 'BK1-2999' belongs to no mapped book
