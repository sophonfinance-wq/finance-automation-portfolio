# Capital spending request gate control report

**Overall verdict:** FAIL

- Request packages analyzed: 31
- Controls in registry: 29
- PASS / REVIEW / FAIL: 1 / 2 / 28

All data is fictional. The engine is read-only and never writes to a source
artifact. Every calendar test is made against the `as_of` date carried in the
file, never the system clock.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `trg_ic_before_pursuit_spend` | FAIL | 1 |
| 3 | `trg_ic_before_nonrefundable_deposit` | FAIL | 1 |
| 4 | `trg_ic_before_refundable_deposits` | FAIL | 1 |
| 5 | `seq_phase_known` | FAIL | 1 |
| 6 | `seq_approvals_in_order` | FAIL | 1 |
| 7 | `seq_no_phase_skipped` | FAIL | 1 |
| 8 | `seq_current_phase_approved` | FAIL | 1 |
| 9 | `seq_gate_summary_recomputes` | FAIL | 1 |
| 10 | `del_items_known` | FAIL | 1 |
| 11 | `del_unique_rows` | FAIL | 1 |
| 12 | `del_prior_phase_complete` | FAIL | 1 |
| 13 | `del_current_phase_outstanding` | FLAG | 1 |
| 14 | `del_estimate_basis_matches` | FAIL | 1 |
| 15 | `cty_hard_floor` | FAIL | 1 |
| 16 | `cty_soft_floor` | FAIL | 1 |
| 17 | `cty_split_foots` | FAIL | 1 |
| 18 | `cty_escalation_reserved` | FAIL | 1 |
| 19 | `gro_growth_default` | FAIL | 1 |
| 20 | `fee_cm_rederives` | FAIL | 2 |
| 21 | `fee_dev_rederives` | FAIL | 2 |
| 22 | `fee_tpc_foots` | FAIL | 4 |
| 23 | `fee_variance_rederives` | FAIL | 1 |
| 24 | `cal_basis_matches_waiver` | FAIL | 1 |
| 25 | `cal_template_current` | FLAG | 1 |
| 26 | `evt_type_known` | FAIL | 1 |
| 27 | `evt_interim_request_filed` | FAIL | 1 |
| 28 | `bid_coverage_meets` | FAIL | 1 |
| 29 | `bid_gmp_bindable` | FAIL | 1 |

## Request packages

### amount_not_integer__Halbrook_Residential

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 2)

- **FAIL** `fee_cm_rederives` @ `amount:cost_budget.cm_fee_cents`  
  AMOUNT_INVALID: cost_budget.cm_fee_cents must be integer cents, got 36000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `fee_tpc_foots` @ `amount:cost_budget.cm_fee_cents`  
  AMOUNT_INVALID: cost_budget.cm_fee_cents must be integer cents, got 36000000.5 -- amounts are integer cents and are never coerced

### approvals_out_of_order__Stonecrest_Communities

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `seq_approvals_in_order` @ `approval_log:APPROVALS-2030/approvals/feasibility/approval_date`  
  the feasibility gate was approved 2029-12-01, after the enactment_zoning gate of 2029-06-18; the gates were not entered in sequence

### bid_coverage_short__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `bid_coverage_meets` @ `bid_schedule:BIDS-2030/lines`  
  bid coverage of 18,000,000.00 is under the 80.00% threshold on hard cost 24,000,000.00; construction may not start

### clean__Northmoor_Development_Group

**Verdict:** PASS (PASS 29, FLAG 0, FAIL 0)

All controls held.

### cm_fee_overstated__Westmere

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 2)

- **FAIL** `fee_cm_rederives` @ `cost_budget:BUDGET-2030/cm_fee_cents`  
  the stated CM Fee of 410,000.00 does not re-derive as 1.50% of hard cost 24,000,000.00 = 360,000.00 (off 50,000.00)
- **FAIL** `fee_tpc_foots` @ `cost_budget:BUDGET-2030/total_project_cost_cents`  
  the stated total project cost of 33,108,247.42 does not foot to its components' sum of 33,158,247.42 (off -50,000.00)

### comparison_basis_wrong__Northmoor_Development_Group

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `cal_basis_matches_waiver` @ `plan_comparison:COMPARE-2030/basis`  
  feasibility_waived=True requires the 'actual_plan' comparison basis; the package compares to 'template'

### current_deliverable_outstanding__Halbrook_Residential

**Verdict:** REVIEW (PASS 28, FLAG 1, FAIL 0)

- **FLAG** `del_current_phase_outstanding` @ `deliverable_checklist:DELIVERABLES-2030/items/building_permits`  
  building_permits is required by the current phase (presales_construction) and is not yet complete; it must be in hand before the next gate

### current_phase_unapproved__Stonecrest_Communities

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `seq_current_phase_approved` @ `approval_log:APPROVALS-2030/approvals/presales_construction`  
  the project states it is in presales_construction but no approved Spending Request for that phase is on record; the phase was entered without its gate

### dev_fee_overstated__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 2)

- **FAIL** `fee_dev_rederives` @ `cost_budget:BUDGET-2030/dev_fee_cents`  
  the stated Development Fee of 973,247.42 does not re-derive as 3.00% of (total project cost 33,108,247.42 less financing 1,500,000.00) = 948,247.42 (off 25,000.00)
- **FAIL** `fee_tpc_foots` @ `cost_budget:BUDGET-2030/total_project_cost_cents`  
  the stated total project cost of 33,108,247.42 does not foot to its components' sum of 33,133,247.42 (off -25,000.00)

### duplicate_deliverable__Westmere

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `del_unique_rows` @ `deliverable_checklist:DELIVERABLES-2030/items/title_report`  
  deliverable title_report appears 2 times; two rows can disagree about its state and the gate test becomes ambiguous

### escalation_reserve_missing__Northmoor_Development_Group

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `cty_escalation_reserved` @ `cost_budget:BUDGET-2030/escalation_contingency_cents`  
  a vanterre project must reserve a separate escalation contingency; the budget carries None

### estimate_basis_wrong__Halbrook_Residential

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `del_estimate_basis_matches` @ `cost_budget:BUDGET-2030/estimate_basis`  
  the budget stands on estimate basis 'divisional'; the presales_construction phase requires 'bindable_gmp'

### gate_summary_wrong__Stonecrest_Communities

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `seq_gate_summary_recomputes` @ `gate_summary:GATES-2030/phases/approvals/gate_cleared`  
  the summary states the approvals gate cleared=False; recomputing from the approvals and the deliverable checklist gives cleared=True

### gmp_not_bindable__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `bid_gmp_bindable` @ `bid_schedule:BIDS-2030/gmp_bindable`  
  an owner-GC project at construction start must hold a bindable GMP; the schedule states gmp_bindable=False

### growth_not_default__Westmere

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `gro_growth_default` @ `project_profile:PROFILE-2030/revenue_growth_bps`  
  the growth assumption is 4.50% / 3.00%; the standard is 3.00% / 3.00% and no market-supported alternative is documented

### hard_contingency_below_floor__Northmoor_Development_Group

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `cty_hard_floor` @ `cost_budget:BUDGET-2030/site_contingency_cents`  
  the site contingency of 1,799,999.99 is under the 10.00% floor on site hard cost of 18,000,000.00; the construction-start floor is unmet

### hard_split_does_not_foot__Halbrook_Residential

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `cty_split_foots` @ `cost_budget:BUDGET-2030/hard_cost_cents`  
  site_hard_cost_cents 17,999,900.00 + vertical_hard_cost_cents 6,000,000.00 = 23,999,900.00, which does not foot to hard_cost_cents 24,000,000.00 (off -100.00)

### interim_request_missing__Stonecrest_Communities

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `evt_interim_request_filed` @ `event_log:EVENTS-2030/events/EV-91/interim_request_id`  
  event EV-91 links to interim request INT-09, which is not an interim approval in the approval log

### missing_artifact__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `gate_summary:-`  
  gate_summary is missing; the controls that read it cannot run and must not be reported as having passed

### nonrefundable_before_ic__Westmere

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `trg_ic_before_nonrefundable_deposit` @ `spend_ledger:SPEND-2030/entries/nonrefundable_deposit`  
  the first non-refundable deposit crossed its trigger on 2028-08-20 but the Initial Commitment Request was not approved until 2028-09-15; capital was committed before the gate

### phase_skipped__Northmoor_Development_Group

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `seq_no_phase_skipped` @ `approval_log:APPROVALS-2030/approvals/enactment_zoning`  
  the project is in presales_construction but the enactment_zoning gate has no approved Spending Request on record; a prior gate was skipped

### prior_deliverable_incomplete__Halbrook_Residential

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `del_prior_phase_complete` @ `deliverable_checklist:DELIVERABLES-2030/items/environmental_phase_2`  
  environmental_phase_2 is required by the enactment_zoning phase, which the project has already passed, but is not marked complete

### pursuit_spend_before_ic__Stonecrest_Communities

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `trg_ic_before_pursuit_spend` @ `spend_ledger:SPEND-2030/entries/pursuit_cost`  
  cumulative pursuit-cost spend of 50,000.00 crossed its trigger on 2028-08-01 but the Initial Commitment Request was not approved until 2028-09-15; capital was committed before the gate

### refundable_before_ic__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `trg_ic_before_refundable_deposits` @ `spend_ledger:SPEND-2030/entries/refundable_deposit`  
  cumulative refundable deposits of 100,000.00 crossed its trigger on 2028-08-10 but the Initial Commitment Request was not approved until 2028-09-15; capital was committed before the gate

### soft_contingency_below_floor__Westmere

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `cty_soft_floor` @ `cost_budget:BUDGET-2030/soft_contingency_cents`  
  the soft-cost contingency of 199,999.99 is under the 5.00% marran floor on soft cost of 4,000,000.00 and no justification is documented

### stale_template__Northmoor_Development_Group

**Verdict:** REVIEW (PASS 28, FLAG 1, FAIL 0)

- **FLAG** `cal_template_current` @ `plan_comparison:COMPARE-2030/template_effective_date`  
  the comparison stands on the 2029-06-01 template; the refresh in force at 2030-03-15 is 2030-01-01, so the comparison should be re-run on the current template

### tpc_does_not_foot__Halbrook_Residential

**Verdict:** FAIL (PASS 27, FLAG 0, FAIL 2)

- **FAIL** `fee_dev_rederives` @ `cost_budget:BUDGET-2030/dev_fee_cents`  
  the stated Development Fee of 948,247.42 does not re-derive as 3.00% of (total project cost 33,108,347.42 less financing 1,500,000.00) = 948,250.42 (off -3.00)
- **FAIL** `fee_tpc_foots` @ `cost_budget:BUDGET-2030/total_project_cost_cents`  
  the stated total project cost of 33,108,347.42 does not foot to its components' sum of 33,108,247.42 (off 100.00)

### unknown_deliverable__Stonecrest_Communities

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `del_items_known` @ `deliverable_checklist:DELIVERABLES-2030/items/heliport_clearance`  
  the checklist carries 'heliport_clearance', which is not a deliverable of any phase; it can neither block a gate nor satisfy one

### unknown_event_type__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `evt_type_known` @ `event_log:EVENTS-2030/events/EV-90/event_type`  
  event EV-90 is typed 'meteor_watch', which is not one of the interim-trigger events ('financing_closing', 'additional_commitment', 'condo_construction_start', 'material_change', 'project_at_risk')

### unknown_phase__Westmere

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `seq_phase_known` @ `project_profile:PROFILE-2030/current_phase`  
  the project states phase 'stabilization', which is not one of the ordered gates ('initial_commitment', 'feasibility', 'enactment_zoning', 'approvals', 'presales_construction'); no phase-indexed standard can be looked up

### variance_misstated__Northmoor_Development_Group

**Verdict:** FAIL (PASS 28, FLAG 0, FAIL 1)

- **FAIL** `fee_variance_rederives` @ `plan_comparison:COMPARE-2030/rows/net_operating_income/variance_cents`  
  the stated net_operating_income variance of 151,000.00 does not re-derive as project 2,150,000.00 less plan 2,000,000.00 = 150,000.00
