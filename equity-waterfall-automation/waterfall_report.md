# Equity-waterfall & JV-promote control report

**Overall verdict:** FAIL

- Deal files analyzed: 32
- Controls in registry: 30
- PASS / REVIEW / FAIL: 1 / 2 / 29

All data is fictional. The engine is read-only and never writes to a source
artifact. Every accrual and covenant window is measured against the
`as_of_period` month index carried in the file, never the system clock.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `mbr_unique_ids` | FAIL | 1 |
| 3 | `mbr_role_valid` | FAIL | 1 |
| 4 | `mbr_roles_complete` | FAIL | 2 |
| 5 | `mbr_commitment_honored` | FAIL | 1 |
| 6 | `pref_rate_valid` | FAIL | 1 |
| 7 | `pref_accrual_recomputes` | FAIL | 3 |
| 8 | `cap_contribution_recomputes` | FAIL | 1 |
| 9 | `cap_rollforward_zeroes` | FAIL | 1 |
| 10 | `wf_tier_order_valid` | FAIL | 6 |
| 11 | `wf_pari_passu_split` | FAIL | 2 |
| 12 | `wf_tier_allocation_recomputes` | FAIL | 4 |
| 13 | `hurdle_rate_valid` | FAIL | 1 |
| 14 | `hurdle_boundary_recomputes` | FAIL | 2 |
| 15 | `promo_split_ratios_valid` | FAIL | 1 |
| 16 | `promo_carry_recomputes` | FAIL | 1 |
| 17 | `loan_rate_valid` | FAIL | 1 |
| 18 | `loan_repaid_before_distribution` | FAIL | 1 |
| 19 | `dil_method_valid` | FAIL | 1 |
| 20 | `dil_penalty_multiplier` | FAIL | 1 |
| 21 | `dil_recompute` | FAIL | 4 |
| 22 | `dist_no_leakage` | FAIL | 4 |
| 23 | `dist_within_available` | FAIL | 3 |
| 24 | `ret_multiple_recomputes` | FAIL | 5 |
| 25 | `ret_preferred_ties` | FAIL | 3 |
| 26 | `ret_profit_split_ties` | FAIL | 5 |
| 27 | `cov_maturity_window` | FLAG | 1 |
| 28 | `cov_ltc_within_max` | FAIL | 1 |
| 29 | `syn_capital_call_ratio` | FAIL | 1 |
| 30 | `syn_report_due` | FLAG | 1 |

## Deal files

### allocation_wrong__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 2)

- **FAIL** `wf_tier_allocation_recomputes` @ `waterfall_schedule:WATERFALL-2041/entries`  
  the stated waterfall allocations do not recompute from the base facts: stated [('A_preferred_return', 'MBR-DEV', 22039083), ('A_preferred_return', 'MBR-INV', 193391584), ('B_return_of_capital', 'MBR-DEV', 100000000), ('B_return_of_capital', 'MBR-INV', 900000000), ('C_hurdle_split', 'MBR-DEV', 57685388), ('C_hurdle_split', 'MBR-INV', 137099238), ('D_promote_split', 'MBR-DEV', 167408806), ('D_promote_split', 'MBR-INV', 167408806)], recomputed [('A_preferred_return', 'MBR-DEV', 22039083), ('A_preferred_return', 'MBR-INV', 193391584), ('B_return_of_capital', 'MBR-DEV', 100000000), ('B_return_of_capital', 'MBR-INV', 900000000), ('C_hurdle_split', 'MBR-DEV', 57685388), ('C_hurdle_split', 'MBR-INV', 134599238), ('D_promote_split', 'MBR-DEV', 167408806), ('D_promote_split', 'MBR-INV', 167408806)]
- **FAIL** `dist_no_leakage` @ `waterfall_schedule:WATERFALL-2041/total_distributed_cents`  
  the schedule entries sum to 17,450,329.05 but state a total distributed of 17,425,329.05 (leak -25,000.00)

### amount_not_integer__Stonecrest_Communities

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 2)

- **FAIL** `dist_no_leakage` @ `amount:waterfall_schedule.total_distributed_cents`  
  AMOUNT_INVALID: waterfall_schedule.total_distributed_cents must be integer cents, got 1742532905.5 -- amounts are integer cents and are never coerced
- **FAIL** `dist_within_available` @ `amount:waterfall_schedule.total_distributed_cents`  
  AMOUNT_INVALID: waterfall_schedule.total_distributed_cents must be integer cents, got 1742532905.5 -- amounts are integer cents and are never coerced

### bad_role__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `mbr_role_valid` @ `member_register:MEMBERS-2041/members/MBR-ADV/role`  
  member MBR-ADV carries role 'sponsor', which is not one of ('investor', 'developer'); the waterfall cannot place it

### clean__Northmoor_Development_Group

**Verdict:** PASS (PASS 30, FLAG 0, FAIL 0)

All controls held.

### commitment_exceeded__Northmoor_Development_Group

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `mbr_commitment_honored` @ `member_register:MEMBERS-2041/members/MBR-INV/commitment_cents`  
  member MBR-INV funded 9,000,000.00 against a commitment of 5,000,000.00 (over by 4,000,000.00)

### contribution_account_wrong__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `cap_contribution_recomputes` @ `capital_ledger:LEDGER-2041/accounts/MBR-DEV/contribution_account_cents`  
  member MBR-DEV states a Contribution Account of 1,050,000.00; its funded contributions sum to 1,000,000.00

### dilution_interest_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `dil_recompute` @ `dilution_worksheet:DILUTION-2041/diluted_interest_bps`  
  the stated diluted interest 950 bps does not recompute to 925 bps by the 'ratio_method' method

### dilution_method_unknown__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 2)

- **FAIL** `dil_method_valid` @ `dilution_worksheet:DILUTION-2041/method`  
  the dilution worksheet names method 'handshake_method', which is not one of the maintained variants ('ratio_method', 'numerator_denominator_method', 'i_plus_ii_minus_b_method')
- **FAIL** `dil_recompute` @ `dilution_worksheet:DILUTION-2041/diluted_interest_bps`  
  the stated diluted interest 925 bps does not recompute to 0 bps by the 'handshake_method' method

### dilution_penalty_wrong__Northmoor_Development_Group

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 2)

- **FAIL** `dil_penalty_multiplier` @ `deal_terms:TERMS-2041/dilution_penalty_bps`  
  the dilution penalty 15000 is not the statutory 20000 basis points (200%)
- **FAIL** `dil_recompute` @ `dilution_worksheet:DILUTION-2041/penalized_substitute_cents`  
  the stated penalized substitute 800,000.00 does not equal the re-derived 600,000.00

### distribution_leaks__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 2)

- **FAIL** `dist_no_leakage` @ `waterfall_schedule:WATERFALL-2041/total_distributed_cents`  
  the schedule entries sum to 17,425,329.05 but state a total distributed of 17,425,429.05 (leak 100.00)
- **FAIL** `dist_within_available` @ `waterfall_schedule:WATERFALL-2041/total_distributed_cents`  
  the total distributed 17,425,429.05 exceeds the 17,425,329.05 of proceeds available after loans (over by 100.00)

### distribution_over_available__Stonecrest_Communities

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 2)

- **FAIL** `dist_no_leakage` @ `waterfall_schedule:WATERFALL-2041/total_distributed_cents`  
  the schedule entries sum to 17,425,329.05 but state a total distributed of 17,625,329.05 (leak 200,000.00)
- **FAIL** `dist_within_available` @ `waterfall_schedule:WATERFALL-2041/total_distributed_cents`  
  the total distributed 17,625,329.05 exceeds the 17,425,329.05 of proceeds available after loans (over by 200,000.00)

### duplicate_member_id__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 3)

- **FAIL** `mbr_unique_ids` @ `member_register:MEMBERS-2041/members/MBR-INV`  
  member id MBR-INV appears 2 times; its capital account and distributions cannot be attributed to one member
- **FAIL** `mbr_roles_complete` @ `member_register:MEMBERS-2041/members/role/investor`  
  the venture carries 2 member(s) with role 'investor'; the two-sided waterfall requires exactly one
- **FAIL** `dil_recompute` @ `dilution_worksheet:DILUTION-2041/diluted_interest_bps`  
  the stated diluted interest 925 bps does not recompute to 505 bps by the 'ratio_method' method

### ending_not_zero__Northmoor_Development_Group

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `cap_rollforward_zeroes` @ `capital_ledger:LEDGER-2041/accounts/MBR-INV/ending_contribution_account_cents`  
  member MBR-INV states ending accounts of 100,000.00 capital / 0.00 preferred; the roll-forward gives 0.00 / 0.00

### extra_investor__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `mbr_roles_complete` @ `member_register:MEMBERS-2041/members/role/investor`  
  the venture carries 2 member(s) with role 'investor'; the two-sided waterfall requires exactly one

### hurdle_rate_too_low__Stonecrest_Communities

**Verdict:** FAIL (PASS 25, FLAG 0, FAIL 7)

- **FAIL** `wf_tier_allocation_recomputes` @ `waterfall_schedule:WATERFALL-2041/entries`  
  the stated waterfall allocations do not recompute from the base facts: stated [('A_preferred_return', 'MBR-DEV', 22039083), ('A_preferred_return', 'MBR-INV', 193391584), ('B_return_of_capital', 'MBR-DEV', 100000000), ('B_return_of_capital', 'MBR-INV', 900000000), ('C_hurdle_split', 'MBR-DEV', 57685388), ('C_hurdle_split', 'MBR-INV', 134599238), ('D_promote_split', 'MBR-DEV', 167408806), ('D_promote_split', 'MBR-INV', 167408806)], recomputed [('A_preferred_return', 'MBR-DEV', 22039083), ('A_preferred_return', 'MBR-INV', 193391584), ('B_return_of_capital', 'MBR-DEV', 100000000), ('B_return_of_capital', 'MBR-INV', 900000000), ('D_promote_split', 'MBR-DEV', 263551119), ('D_promote_split', 'MBR-INV', 263551119)]
- **FAIL** `hurdle_rate_valid` @ `deal_terms:TERMS-2041/hurdle_rate_bps`  
  hurdle rate 500 does not sit above the preferred rate 1000; the promote boundary is ill-defined
- **FAIL** `hurdle_boundary_recomputes` @ `waterfall_schedule:WATERFALL-2041/hurdle_target_cents`  
  the schedule states a hurdle target of 12,279,908.22; recomputing from the investor's contributions gives 9,921,737.28
- **FAIL** `ret_multiple_recomputes` @ `returns_summary:RETURNS-2041/members/MBR-INV/equity_multiple_bps`  
  member MBR-INV states an equity multiple of 155.04%; recomputing from the waterfall gives 150.77%
- **FAIL** `ret_multiple_recomputes` @ `returns_summary:RETURNS-2041/members/MBR-DEV/equity_multiple_bps`  
  member MBR-DEV states an equity multiple of 347.13%; recomputing from the waterfall gives 385.59%
- **FAIL** `ret_profit_split_ties` @ `returns_summary:RETURNS-2041/members/MBR-INV/profit_split_cents`  
  member MBR-INV states a profit split of 3,020,080.44; its promote receipts recompute to 2,635,511.19
- **FAIL** `ret_profit_split_ties` @ `returns_summary:RETURNS-2041/members/MBR-DEV/profit_split_cents`  
  member MBR-DEV states a profit split of 2,250,941.94; its promote receipts recompute to 2,635,511.19

### hurdle_target_wrong__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `hurdle_boundary_recomputes` @ `waterfall_schedule:WATERFALL-2041/hurdle_target_cents`  
  the schedule states a hurdle target of 12,529,908.22; recomputing from the investor's contributions gives 12,279,908.22

### loan_rate_inverted__Northmoor_Development_Group

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `loan_rate_valid` @ `deal_terms:TERMS-2041/default_loan_rate_bps`  
  default-loan rate 1000 does not sit above the member-loan rate 1400

### loan_repayment_wrong__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `loan_repaid_before_distribution` @ `loan_covenant:COVENANT-2041/member_loan_repayment_cents`  
  the stated member-loan repayment 584,670.95 does not equal the re-derived principal plus interest 574,670.95

### ltc_over_max__Stonecrest_Communities

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `cov_ltc_within_max` @ `loan_covenant:COVENANT-2041/senior_loan_cents`  
  loan-to-cost 78.12% (12,500,000.00 of 16,000,000.00) exceeds the covenant maximum 77.00%

### maturity_soon__Ardenne_Field_Partners

**Verdict:** REVIEW (PASS 29, FLAG 1, FAIL 0)

- **FLAG** `cov_maturity_window` @ `loan_covenant:COVENANT-2041/maturity_period`  
  the financing matures in 3 month(s), inside the 6-month window; a refinance or extension is due to be chased

### missing_artifact__Northmoor_Development_Group

**Verdict:** FAIL (PASS 26, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `returns_summary:-`  
  returns_summary is missing; the controls that read it cannot run and must not be reported as having passed

### multiple_wrong__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `ret_multiple_recomputes` @ `returns_summary:RETURNS-2041/members/MBR-INV/equity_multiple_bps`  
  member MBR-INV states an equity multiple of 155.54%; recomputing from the waterfall gives 155.04%

### pari_passu_broken__Stonecrest_Communities

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 2)

- **FAIL** `wf_pari_passu_split` @ `waterfall_schedule:WATERFALL-2041/entries/tier/A_preferred_return`  
  tier A_preferred_return splits 1,943,915.84 / 210,390.83 to investor / developer; a pari-passu split of 2,154,306.67 on the account balances is 1,933,915.84 / 220,390.83
- **FAIL** `wf_tier_allocation_recomputes` @ `waterfall_schedule:WATERFALL-2041/entries`  
  the stated waterfall allocations do not recompute from the base facts: stated [('A_preferred_return', 'MBR-DEV', 21039083), ('A_preferred_return', 'MBR-INV', 194391584), ('B_return_of_capital', 'MBR-DEV', 100000000), ('B_return_of_capital', 'MBR-INV', 900000000), ('C_hurdle_split', 'MBR-DEV', 57685388), ('C_hurdle_split', 'MBR-INV', 134599238), ('D_promote_split', 'MBR-DEV', 167408806), ('D_promote_split', 'MBR-INV', 167408806)], recomputed [('A_preferred_return', 'MBR-DEV', 22039083), ('A_preferred_return', 'MBR-INV', 193391584), ('B_return_of_capital', 'MBR-DEV', 100000000), ('B_return_of_capital', 'MBR-INV', 900000000), ('C_hurdle_split', 'MBR-DEV', 57685388), ('C_hurdle_split', 'MBR-INV', 134599238), ('D_promote_split', 'MBR-DEV', 167408806), ('D_promote_split', 'MBR-INV', 167408806)]

### pref_accrual_wrong__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `pref_accrual_recomputes` @ `capital_ledger:LEDGER-2041/accounts/MBR-INV/investment_return_account_cents`  
  member MBR-INV states a preferred-return balance of 2,033,915.84; recomputing from its contributions gives 1,933,915.84

### pref_rate_zero__Northmoor_Development_Group

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 11)

- **FAIL** `pref_rate_valid` @ `deal_terms:TERMS-2041/pref_rate_bps`  
  preferred-return rate 0 is not a positive basis-point figure; the preferred tier would accrue nothing
- **FAIL** `pref_accrual_recomputes` @ `capital_ledger:LEDGER-2041/accounts/MBR-INV/investment_return_account_cents`  
  member MBR-INV states a preferred-return balance of 1,933,915.84; recomputing from its contributions gives 0.00
- **FAIL** `pref_accrual_recomputes` @ `capital_ledger:LEDGER-2041/accounts/MBR-DEV/investment_return_account_cents`  
  member MBR-DEV states a preferred-return balance of 220,390.83; recomputing from its contributions gives 0.00
- **FAIL** `wf_pari_passu_split` @ `waterfall_schedule:WATERFALL-2041/entries/tier/A_preferred_return`  
  tier A_preferred_return splits 1,933,915.84 / 220,390.83 to investor / developer; a pari-passu split of 2,154,306.67 on the account balances is 0.00 / 0.00
- **FAIL** `wf_tier_allocation_recomputes` @ `waterfall_schedule:WATERFALL-2041/entries`  
  the stated waterfall allocations do not recompute from the base facts: stated [('A_preferred_return', 'MBR-DEV', 22039083), ('A_preferred_return', 'MBR-INV', 193391584), ('B_return_of_capital', 'MBR-DEV', 100000000), ('B_return_of_capital', 'MBR-INV', 900000000), ('C_hurdle_split', 'MBR-DEV', 57685388), ('C_hurdle_split', 'MBR-INV', 134599238), ('D_promote_split', 'MBR-DEV', 167408806), ('D_promote_split', 'MBR-INV', 167408806)], recomputed [('B_return_of_capital', 'MBR-DEV', 100000000), ('B_return_of_capital', 'MBR-INV', 900000000), ('C_hurdle_split', 'MBR-DEV', 140567496), ('C_hurdle_split', 'MBR-INV', 327990822), ('D_promote_split', 'MBR-DEV', 136987294), ('D_promote_split', 'MBR-INV', 136987293)]
- **FAIL** `ret_multiple_recomputes` @ `returns_summary:RETURNS-2041/members/MBR-INV/equity_multiple_bps`  
  member MBR-INV states an equity multiple of 155.04%; recomputing from the waterfall gives 151.66%
- **FAIL** `ret_multiple_recomputes` @ `returns_summary:RETURNS-2041/members/MBR-DEV/equity_multiple_bps`  
  member MBR-DEV states an equity multiple of 347.13%; recomputing from the waterfall gives 377.55%
- **FAIL** `ret_preferred_ties` @ `returns_summary:RETURNS-2041/members/MBR-INV/preferred_return_cents`  
  member MBR-INV states a preferred return of 1,933,915.84; its tier-A receipts recompute to 0.00
- **FAIL** `ret_preferred_ties` @ `returns_summary:RETURNS-2041/members/MBR-DEV/preferred_return_cents`  
  member MBR-DEV states a preferred return of 220,390.83; its tier-A receipts recompute to 0.00
- **FAIL** `ret_profit_split_ties` @ `returns_summary:RETURNS-2041/members/MBR-INV/profit_split_cents`  
  member MBR-INV states a profit split of 3,020,080.44; its promote receipts recompute to 4,649,781.15
- **FAIL** `ret_profit_split_ties` @ `returns_summary:RETURNS-2041/members/MBR-DEV/profit_split_cents`  
  member MBR-DEV states a profit split of 2,250,941.94; its promote receipts recompute to 2,775,547.90

### preferred_return_wrong__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `ret_preferred_ties` @ `returns_summary:RETURNS-2041/members/MBR-INV/preferred_return_cents`  
  member MBR-INV states a preferred return of 1,953,915.84; its tier-A receipts recompute to 1,933,915.84

### profit_split_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `ret_profit_split_ties` @ `returns_summary:RETURNS-2041/members/MBR-DEV/profit_split_cents`  
  member MBR-DEV states a profit split of 2,280,941.94; its promote receipts recompute to 2,250,941.94

### promote_carry_wrong__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `promo_carry_recomputes` @ `waterfall_schedule:WATERFALL-2041/promote_split_cents`  
  the schedule states a developer promote of 2,325,941.94; its receipts in the hurdle and promote tiers sum to 2,250,941.94

### report_due_soon__Northmoor_Development_Group

**Verdict:** REVIEW (PASS 29, FLAG 1, FAIL 0)

- **FLAG** `syn_report_due` @ `loan_covenant:COVENANT-2041/report_due_period`  
  the syndicate report is due in 2 month(s), inside the 3-month window; it is due to be prepared

### split_does_not_sum__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `promo_split_ratios_valid` @ `deal_terms:TERMS-2041/tier_d_investor_bps`  
  the promote split 5000 / 4000 does not sum to 10,000 basis points

### syndicate_draw_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 1)

- **FAIL** `syn_capital_call_ratio` @ `loan_covenant:COVENANT-2041/syndicate_draw_cents`  
  the stated syndicate draw 172,500.00 does not equal 3350 basis points of the commitment, 167,500.00

### tier_out_of_order__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 29, FLAG 0, FAIL 6)

- **FAIL** `wf_tier_order_valid` @ `waterfall_schedule:WATERFALL-2041/entries/1/tier`  
  tier 'A_preferred_return' pays at entry 1 after a later tier has already begun; the waterfall order is broken
- **FAIL** `wf_tier_order_valid` @ `waterfall_schedule:WATERFALL-2041/entries/2/tier`  
  tier 'A_preferred_return' pays at entry 2 after a later tier has already begun; the waterfall order is broken
- **FAIL** `wf_tier_order_valid` @ `waterfall_schedule:WATERFALL-2041/entries/3/tier`  
  tier 'B_return_of_capital' pays at entry 3 after a later tier has already begun; the waterfall order is broken
- **FAIL** `wf_tier_order_valid` @ `waterfall_schedule:WATERFALL-2041/entries/4/tier`  
  tier 'B_return_of_capital' pays at entry 4 after a later tier has already begun; the waterfall order is broken
- **FAIL** `wf_tier_order_valid` @ `waterfall_schedule:WATERFALL-2041/entries/5/tier`  
  tier 'C_hurdle_split' pays at entry 5 after a later tier has already begun; the waterfall order is broken
- **FAIL** `wf_tier_order_valid` @ `waterfall_schedule:WATERFALL-2041/entries/6/tier`  
  tier 'C_hurdle_split' pays at entry 6 after a later tier has already begun; the waterfall order is broken
