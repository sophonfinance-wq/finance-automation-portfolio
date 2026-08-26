# Baseline & version drift control report

**Overall verdict:** FAIL

- Cycle files analyzed: 27
- Controls in registry: 25
- PASS / REVIEW / FAIL: 1 / 3 / 23

All data is fictional. The engine is read-only and never writes to a source
artifact. Every date is tested against the reporting period carried in the
file, never the system clock. Category sets are reconciled before any value
is compared, totals are summed from the lines rather than read from a stated
figure, and the materiality threshold grades a difference that has already
been found -- it never decides whether one exists.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `ver_versions_declared` | FAIL | 1 |
| 3 | `ver_single_baseline` | FAIL | 1 |
| 4 | `ver_baseline_postdates_agreement` | FAIL | 1 |
| 5 | `ver_prepared_within_period` | FAIL | 1 |
| 6 | `lin_categories_reconcile` | FAIL | 15 |
| 7 | `lin_values_agree` | FAIL | 3 |
| 8 | `lin_immaterial_drift_review` | FLAG | 2 |
| 9 | `lin_totals_agree` | FAIL | 5 |
| 10 | `lin_phase_totals_tie` | FAIL | 2 |
| 11 | `lin_reclass_review` | FLAG | 2 |
| 12 | `stl_cost_through_current` | FAIL | 1 |
| 13 | `stl_summary_not_superseded` | FLAG | 1 |
| 14 | `amd_change_columns_foot` | FAIL | 1 |
| 15 | `amd_changes_trace_to_log` | FAIL | 3 |
| 16 | `amd_pending_not_billed` | FAIL | 1 |
| 17 | `amd_locked_lines_unchanged` | FAIL | 2 |
| 18 | `drv_inputs_declared` | FAIL | 1 |
| 19 | `drv_milestones_populated` | FAIL | 1 |
| 20 | `drv_instalments_conserve` | FAIL | 1 |
| 21 | `drv_base_net_of_advances` | FAIL | 1 |
| 22 | `drv_cap_not_exceeded` | FAIL | 1 |
| 23 | `eqt_commitments_agree` | FAIL | 1 |
| 24 | `eqt_split_matches_phase` | FAIL | 2 |
| 25 | `eqt_contributed_within_commitment` | FAIL | 1 |

## Cycle files

### advances_exceed_cap__Copperfield_Yards

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `drv_cap_not_exceeded` @ `derived_schedule:DS-1/advances_cents`  
  schedule sponsor_fee has advanced 540,000.00 against a cap of 480,000.00, 60,000.00 beyond it

### amount_not_integer__Alderpoint_Terraces

**Verdict:** FAIL (PASS 18, FLAG 2, FAIL 17)

- **FAIL** `lin_categories_reconcile` @ `amount:budget_version[BV-WORK]/lines[9]/amount_cents`  
  AMOUNT_INVALID: budget_version[BV-WORK]/lines[9]/amount_cents must be integer cents, got 23630200.5 -- amounts are integer cents and are never coerced
- **FAIL** `lin_categories_reconcile` @ `budget_version:BV-WORK/lines/Consultants`  
  category 'Consultants' is in the baseline but absent from BV-WORK (working_model); a category present in one copy and not another is what a renamed or split line looks like, and pairing on names alone would skip it
- **FAIL** `lin_categories_reconcile` @ `budget_version:BV-WORK/lines/Contingency`  
  category 'Contingency' is in the baseline but absent from BV-WORK (working_model); a category present in one copy and not another is what a renamed or split line looks like, and pairing on names alone would skip it
- **FAIL** `lin_categories_reconcile` @ `budget_version:BV-WORK/lines/Finance Costs`  
  category 'Finance Costs' is in the baseline but absent from BV-WORK (working_model); a category present in one copy and not another is what a renamed or split line looks like, and pairing on names alone would skip it
- **FAIL** `lin_categories_reconcile` @ `budget_version:BV-WORK/lines/Insurance`  
  category 'Insurance' is in the baseline but absent from BV-WORK (working_model); a category present in one copy and not another is what a renamed or split line looks like, and pairing on names alone would skip it
- **FAIL** `lin_categories_reconcile` @ `budget_version:BV-WORK/lines/Land`  
  category 'Land' is in the baseline but absent from BV-WORK (working_model); a category present in one copy and not another is what a renamed or split line looks like, and pairing on names alone would skip it
- **FAIL** `lin_categories_reconcile` @ `budget_version:BV-WORK/lines/Legal and Accounting`  
  category 'Legal and Accounting' is in the baseline but absent from BV-WORK (working_model); a category present in one copy and not another is what a renamed or split line looks like, and pairing on names alone would skip it
- **FAIL** `lin_categories_reconcile` @ `budget_version:BV-WORK/lines/Loan Interest`  
  category 'Loan Interest' is in the baseline but absent from BV-WORK (working_model); a category present in one copy and not another is what a renamed or split line looks like, and pairing on names alone would skip it
- **FAIL** `lin_categories_reconcile` @ `budget_version:BV-WORK/lines/Marketing`  
  category 'Marketing' is in the baseline but absent from BV-WORK (working_model); a category present in one copy and not another is what a renamed or split line looks like, and pairing on names alone would skip it
- **FAIL** `lin_categories_reconcile` @ `budget_version:BV-WORK/lines/Permits`  
  category 'Permits' is in the baseline but absent from BV-WORK (working_model); a category present in one copy and not another is what a renamed or split line looks like, and pairing on names alone would skip it
- **FAIL** `lin_categories_reconcile` @ `budget_version:BV-WORK/lines/Site Works`  
  category 'Site Works' is in the baseline but absent from BV-WORK (working_model); a category present in one copy and not another is what a renamed or split line looks like, and pairing on names alone would skip it
- **FAIL** `lin_categories_reconcile` @ `budget_version:BV-WORK/lines/Sponsor Fee`  
  category 'Sponsor Fee' is in the baseline but absent from BV-WORK (working_model); a category present in one copy and not another is what a renamed or split line looks like, and pairing on names alone would skip it
- **FAIL** `lin_categories_reconcile` @ `budget_version:BV-WORK/lines/Vertical Construction`  
  category 'Vertical Construction' is in the baseline but absent from BV-WORK (working_model); a category present in one copy and not another is what a renamed or split line looks like, and pairing on names alone would skip it
- **FAIL** `lin_values_agree` @ `amount:budget_version[BV-WORK]/lines[9]/amount_cents`  
  AMOUNT_INVALID: budget_version[BV-WORK]/lines[9]/amount_cents must be integer cents, got 23630200.5 -- amounts are integer cents and are never coerced
- **FLAG** `lin_immaterial_drift_review` @ `amount:budget_version[BV-WORK]/lines[9]/amount_cents`  
  AMOUNT_INVALID: budget_version[BV-WORK]/lines[9]/amount_cents must be integer cents, got 23630200.5 -- amounts are integer cents and are never coerced
- **FAIL** `lin_totals_agree` @ `amount:budget_version[BV-WORK]/lines[9]/amount_cents`  
  AMOUNT_INVALID: budget_version[BV-WORK]/lines[9]/amount_cents must be integer cents, got 23630200.5 -- amounts are integer cents and are never coerced
- **FAIL** `lin_phase_totals_tie` @ `amount:budget_version[BV-WORK]/lines[9]/amount_cents`  
  AMOUNT_INVALID: budget_version[BV-WORK]/lines[9]/amount_cents must be integer cents, got 23630200.5 -- amounts are integer cents and are never coerced
- **FLAG** `lin_reclass_review` @ `amount:budget_version[BV-WORK]/lines[9]/amount_cents`  
  AMOUNT_INVALID: budget_version[BV-WORK]/lines[9]/amount_cents must be integer cents, got 23630200.5 -- amounts are integer cents and are never coerced
- **FAIL** `amd_locked_lines_unchanged` @ `amount:budget_version[BV-WORK]/lines[9]/amount_cents`  
  AMOUNT_INVALID: budget_version[BV-WORK]/lines[9]/amount_cents must be integer cents, got 23630200.5 -- amounts are integer cents and are never coerced

### base_ignores_advances__Dunmore_Flats

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `drv_base_net_of_advances` @ `derived_schedule:DS-1/base_cents`  
  schedule sponsor_fee amortises 1,417,813.00 where total less advances is 1,037,813.00; the advanced portion would be paid a second time across the instalments

### baseline_predates_agreement__Brightwater_Commons

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `ver_baseline_postdates_agreement` @ `budget_version:BV-BASE/prepared_date`  
  baseline BV-BASE prepared 2030-08-04, before the agreement was executed 2030-11-18; an exhibit cannot predate the agreement it is attached to

### category_renamed_in_copy__Copperfield_Yards

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 2)

- **FAIL** `lin_categories_reconcile` @ `budget_version:BV-WORK/lines/Marketing`  
  category 'Marketing' is in the baseline but absent from BV-WORK (working_model); a category present in one copy and not another is what a renamed or split line looks like, and pairing on names alone would skip it
- **FAIL** `lin_categories_reconcile` @ `budget_version:BV-WORK/lines/Marketing and Sales`  
  category 'Marketing and Sales' appears in BV-WORK (working_model) but not in the baseline; it entered the budget without entering the governing copy

### change_without_amendment__Alderpoint_Terraces

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `amd_changes_trace_to_log` @ `budget_version:BV-BILL/lines/Legal and Accounting`  
  Legal and Accounting: current change of 30,000.00 is backed by 0.00 of approved amendments; a movement is only as good as the approval behind it

### clean__Brightwater_Commons

**Verdict:** PASS (PASS 25, FLAG 0, FAIL 0)

All controls held.

### commitment_differs_by_copy__Dunmore_Flats

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `eqt_commitments_agree` @ `budget_version:-/commitments/investor`  
  investor is committed for 2 different amounts across the copies (BV-BASE=5,000,000.00, BV-BILL=5,000,000.00, BV-SUMM=5,047,369.00, BV-WORK=5,000,000.00); the remaining-commitment figure on a funding request depends on which copy was open

### contributed_over_commitment__Brightwater_Commons

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `eqt_contributed_within_commitment` @ `funding_register:FR-1/members/sponsor/contributed_cents`  
  sponsor has contributed 5,125,000.00 against a commitment of 5,000,000.00, 125,000.00 beyond it

### instalments_do_not_conserve__Copperfield_Yards

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `drv_instalments_conserve` @ `derived_schedule:DS-1/instalments_cents`  
  schedule sponsor_fee instalments sum to 1,040,313.00 against a base of 1,037,813.00; an amortisation that does not conserve its base pays out a different figure than the one approved

### line_differs_immaterially__Alderpoint_Terraces

**Verdict:** REVIEW (PASS 23, FLAG 2, FAIL 0)

- **FLAG** `lin_immaterial_drift_review` @ `budget_version:BV-SUMM/lines/Permits`  
  Permits: BV-SUMM differs from the baseline by 41.00, below the 1,000.00 threshold -- reported so it is reconciled now rather than after it has grown
- **FLAG** `lin_totals_agree` @ `budget_version:BV-SUMM/lines`  
  BV-SUMM (summary_memo) totals 31,834,626.00 against the baseline 31,834,585.00, a difference of 41.00, below the 1,000.00 threshold -- reported for review rather than as a failure, because the aggregate of a sub-threshold line difference is the same difference

### line_differs_materially__Dunmore_Flats

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 2)

- **FAIL** `lin_values_agree` @ `budget_version:BV-WORK/lines/Consultants`  
  Consultants: BV-WORK (working_model) carries 1,650,000.00 against the baseline 1,600,000.00, a difference of 50,000.00 at or above the 1,000.00 materiality threshold
- **FAIL** `lin_totals_agree` @ `budget_version:BV-WORK/lines`  
  BV-WORK (working_model) totals 31,884,585.00 against the baseline 31,834,585.00, a difference of 50,000.00; each copy can be internally perfect and still disagree

### line_missing_phase__Brightwater_Commons

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `lin_phase_totals_tie` @ `budget_version:BV-WORK/lines/phase`  
  BV-WORK phase totals sum to 31,256,585.00 against a budget total of 31,834,585.00; a line with no phase sits in the total while belonging to neither side of the split

### locked_line_moved__Copperfield_Yards

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 3)

- **FAIL** `lin_values_agree` @ `budget_version:BV-WORK/lines/Land`  
  Land: BV-WORK (working_model) carries 6,650,000.00 against the baseline 6,500,000.00, a difference of 150,000.00 at or above the 1,000.00 materiality threshold
- **FAIL** `lin_totals_agree` @ `budget_version:BV-WORK/lines`  
  BV-WORK (working_model) totals 31,984,585.00 against the baseline 31,834,585.00, a difference of 150,000.00; each copy can be internally perfect and still disagree
- **FAIL** `amd_locked_lines_unchanged` @ `budget_version:BV-WORK/lines/Land`  
  Land is locked at 6,500,000.00 but BV-WORK carries 6,650,000.00; a locked line moving is a term being renegotiated, not a budget being revised

### milestone_blanked__Alderpoint_Terraces

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `drv_milestones_populated` @ `derived_schedule:DS-1/input_milestones/construction_end`  
  schedule sponsor_fee amortises across milestone 'construction_end', which carries no date; the schedule will not error, it will silently keep its last amortisation

### missing_artifact__Dunmore_Flats

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 2)

- **FAIL** `set_complete` @ `amendment_log:-`  
  no amendment_log document in the cycle file; every control that reads it stands down rather than inventing the artifact
- **FAIL** `amd_changes_trace_to_log` @ `budget_version:BV-BILL/lines/Consultants`  
  Consultants: current change of 50,000.00 is backed by 0.00 of approved amendments; a movement is only as good as the approval behind it

### offsetting_reclass__Brightwater_Commons

**Verdict:** REVIEW (PASS 24, FLAG 1, FAIL 0)

- **FLAG** `lin_reclass_review` @ `budget_version:BV-WORK/lines/Finance Costs`  
  BV-WORK (working_model) moves 484,877.00 from Finance Costs to Loan Interest with the total unchanged -- a re-carve of the same money rather than a budget change, and it still needs an approval behind it

### pending_amendment_billed__Copperfield_Yards

**Verdict:** FAIL (PASS 23, FLAG 0, FAIL 2)

- **FAIL** `amd_changes_trace_to_log` @ `budget_version:BV-BILL/lines/Permits`  
  Permits: current change of 20,000.00 is backed by 0.00 of approved amendments; a movement is only as good as the approval behind it
- **FAIL** `amd_pending_not_billed` @ `budget_version:BV-BILL/lines/Permits`  
  Permits: 20,000.00 billed as a current change while its amendment is still pending; billing it decides the question the counterparty has not answered

### revised_typed_not_computed__Alderpoint_Terraces

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `amd_change_columns_foot` @ `budget_version:BV-BILL/lines/Insurance`  
  Insurance: revised reads 578,000.00 but approved plus changes derives 565,500.00, a difference of 12,500.00; the revised column was typed rather than computed

### schedule_input_unknown__Dunmore_Flats

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `drv_inputs_declared` @ `derived_schedule:DS-1/input_milestones/substantial_completion`  
  schedule sponsor_fee declares milestone 'substantial_completion' as an input, but no such milestone exists

### split_wrong_for_phase__Brightwater_Commons

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 2)

- **FAIL** `eqt_split_matches_phase` @ `funding_register:FR-1/members/investor/split_bps`  
  investor funds at 9000 bps in the register but the agreement sets 5000 bps for phase 'pre_conversion'; the ratio changes with the phase, and the wrong one is only visibly wrong once money moves
- **FAIL** `eqt_split_matches_phase` @ `funding_register:FR-1/members/sponsor/split_bps`  
  sponsor funds at 1000 bps in the register but the agreement sets 5000 bps for phase 'pre_conversion'; the ratio changes with the phase, and the wrong one is only visibly wrong once money moves

### stated_total_typed__Copperfield_Yards

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `lin_totals_agree` @ `budget_version:BV-SUMM/stated_total_cents`  
  BV-SUMM states a total of 31,841,266.07 but its own lines sum to 31,834,585.00; the stated figure was typed, not computed

### summary_superseded__Alderpoint_Terraces

**Verdict:** REVIEW (PASS 24, FLAG 1, FAIL 0)

- **FLAG** `stl_summary_not_superseded` @ `budget_version:BV-SUMM/prepared_date`  
  summary BV-SUMM prepared 2031-05-02 restates a budget the working model has moved past (2031-06-20); a memo already in circulation is quoting figures that changed after it left

### two_baselines__Dunmore_Flats

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `ver_single_baseline` @ `budget_version:-`  
  2 versions carry role 'contractual_baseline'; exactly one must, because every variance in the reporting pack is measured against it

### unknown_version_role__Brightwater_Commons

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `ver_versions_declared` @ `budget_version:BV-SUMM/role`  
  version BV-SUMM declares role 'draft_for_discussion', not one of contractual_baseline, working_model, billing_instrument, summary_memo

### version_from_next_period__Copperfield_Yards

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `ver_prepared_within_period` @ `budget_version:BV-SUMM/prepared_date`  
  version BV-SUMM prepared 2031-08-12, after the period ended 2031-06-30; it is evidence for a later cycle, not this one

### working_model_stale__Alderpoint_Terraces

**Verdict:** FAIL (PASS 24, FLAG 0, FAIL 1)

- **FAIL** `stl_cost_through_current` @ `budget_version:BV-WORK/cost_through_date`  
  BV-WORK (working_model) reports cost only through 2031-01-31, 150 days behind the period end 2031-06-30 and outside the 45-day band; it is stale rather than wrong, which is why nobody notices
