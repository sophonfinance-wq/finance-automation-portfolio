# Wire & transfer release-control report

**Overall verdict:** FAIL

- Release-control files analyzed: 25
- Controls in registry: 23
- PASS / REVIEW / FAIL: 1 / 1 / 23

All data is fictional. The engine is read-only and never writes to a source
artifact. Every date test is made against the dates carried in the file, never
the system clock.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `sod_two_distinct_signers` | FAIL | 1 |
| 3 | `sod_dual_auth_complete` | FAIL | 1 |
| 4 | `sod_auth_not_before_init` | FAIL | 1 |
| 5 | `sig_initiator_authorized` | FAIL | 1 |
| 6 | `sig_authorizer_authorized` | FAIL | 1 |
| 7 | `sig_within_authority_limit` | FAIL | 2 |
| 8 | `ben_template_exists` | FAIL | 1 |
| 9 | `ben_triplet_matches_template` | FAIL | 2 |
| 10 | `ben_new_account_callback` | FAIL | 1 |
| 11 | `ben_off_template_review` | FLAG | 2 |
| 12 | `aba_classification_fields` | FAIL | 1 |
| 13 | `aba_check_digit_valid` | FAIL | 1 |
| 14 | `aba_resolves_to_bank_name` | FAIL | 2 |
| 15 | `fund_account_exists` | FAIL | 1 |
| 16 | `fund_sufficient_balance` | FAIL | 2 |
| 17 | `dup_wire_ids_unique` | FAIL | 1 |
| 18 | `dup_not_already_posted` | FAIL | 1 |
| 19 | `flow_stage_valid` | FAIL | 1 |
| 20 | `flow_posted_has_approval` | FAIL | 1 |
| 21 | `flow_posted_ref_ties` | FAIL | 2 |
| 22 | `rpt_release_flag_recomputes` | FAIL | 17 |
| 23 | `rpt_report_count_ties` | FAIL | 1 |

## Release-control files

### account_missing__Halbrook_Residential

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 2)

- **FAIL** `fund_account_exists` @ `wire_register:WIRES-2030/wires/W-1006/from_account`  
  packet W-1006 draws on account 'ACCT-999', which is not in the funding-account register; its balance cannot be checked
- **FAIL** `rpt_release_flag_recomputes` @ `release_summary:SUMMARY-2030/wires/W-1006/releasable`  
  packet W-1006 is summarised releasable=True; recomputing from the release evidence gives releasable=False

### already_posted__Stonecrest_Communities

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `dup_not_already_posted` @ `wire_register:WIRES-2030/wires/W-1008/beneficiary_account`  
  packet W-1008 matches an already-posted payment to the same beneficiary for the same amount inside the 5-day window; releasing it would pay twice

### amount_not_integer__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 4)

- **FAIL** `sig_within_authority_limit` @ `amount:wire[W-1001].amount_cents`  
  AMOUNT_INVALID: wire[W-1001].amount_cents must be integer cents, got 120000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `fund_sufficient_balance` @ `amount:wire[W-1001].amount_cents`  
  AMOUNT_INVALID: wire[W-1001].amount_cents must be integer cents, got 120000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `flow_posted_ref_ties` @ `amount:wire[W-1001].amount_cents`  
  AMOUNT_INVALID: wire[W-1001].amount_cents must be integer cents, got 120000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `rpt_release_flag_recomputes` @ `amount:wire[W-1001].amount_cents`  
  AMOUNT_INVALID: wire[W-1001].amount_cents must be integer cents, got 120000000.5 -- amounts are integer cents and are never coerced

### auth_before_init__Westmere

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 2)

- **FAIL** `sod_auth_not_before_init` @ `wire_register:WIRES-2030/wires/W-1004/authorized_date`  
  packet W-1004 is authorized 2030-03-08, before it was initiated 2030-03-09; the authorization cannot precede the request
- **FAIL** `rpt_release_flag_recomputes` @ `release_summary:SUMMARY-2030/wires/W-1004/releasable`  
  packet W-1004 is summarised releasable=True; recomputing from the release evidence gives releasable=False

### authorizer_not_signer__Northmoor_Development_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 2)

- **FAIL** `sig_authorizer_authorized` @ `wire_register:WIRES-2030/wires/W-1002/authorized_by`  
  packet W-1002 was authorized by 'SGN-01', who is not on the authorized-signer register for account ACCT-200
- **FAIL** `rpt_release_flag_recomputes` @ `release_summary:SUMMARY-2030/wires/W-1002/releasable`  
  packet W-1002 is summarised releasable=True; recomputing from the release evidence gives releasable=False

### bad_check_digit__Halbrook_Residential

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 4)

- **FAIL** `ben_triplet_matches_template` @ `wire_register:WIRES-2030/wires/W-1007/beneficiary_account`  
  packet W-1007 beneficiary ('992000025', '8834200156', 'Westmere Holdings LLC') does not match the stored template ('992000024', '8834200156', 'Westmere Holdings LLC'); the payment is bound for an unapproved destination
- **FAIL** `aba_check_digit_valid` @ `wire_register:WIRES-2030/wires/W-1007/receiving_aba`  
  packet W-1007 routing number '992000025' fails the ABA check-digit (mod-10, weights 3-7-1); it cannot be a valid routing number
- **FAIL** `aba_resolves_to_bank_name` @ `wire_register:WIRES-2030/wires/W-1007/receiving_bank_name`  
  packet W-1007 routing number 992000025 resolves to None in the bank directory, but the form names 'Vantage Trust'
- **FAIL** `rpt_release_flag_recomputes` @ `release_summary:SUMMARY-2030/wires/W-1007/releasable`  
  packet W-1007 is summarised releasable=True; recomputing from the release evidence gives releasable=False

### bank_name_mismatch__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 2)

- **FAIL** `aba_resolves_to_bank_name` @ `wire_register:WIRES-2030/wires/W-1002/receiving_bank_name`  
  packet W-1002 routing number 983000033 resolves to 'Kelder Union Bank' in the bank directory, but the form names 'Copperline Federal'
- **FAIL** `rpt_release_flag_recomputes` @ `release_summary:SUMMARY-2030/wires/W-1002/releasable`  
  packet W-1002 is summarised releasable=True; recomputing from the release evidence gives releasable=False

### book_transfer_has_aba__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 2)

- **FAIL** `aba_classification_fields` @ `wire_register:WIRES-2030/wires/W-1003/receiving_aba`  
  book transfer W-1003 carries a receiving ABA/bank name; an internal transfer stays within the bank and names no routing detail
- **FAIL** `rpt_release_flag_recomputes` @ `release_summary:SUMMARY-2030/wires/W-1003/releasable`  
  packet W-1003 is summarised releasable=True; recomputing from the release evidence gives releasable=False

### clean__Northmoor_Development_Group

**Verdict:** PASS (PASS 23, FLAG 0, FAIL 0)

All controls held.

### duplicate_wire_id__Westmere

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `dup_wire_ids_unique` @ `wire_register:WIRES-2030/wires/W-1002`  
  packet id W-1002 appears 2 times; a posting that settles it cannot be attributed to one request

### funding_shortfall__Northmoor_Development_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 2)

- **FAIL** `fund_sufficient_balance` @ `wire_register:WIRES-2030/wires/W-1004/amount_cents`  
  packet W-1004 is 1,000,000.00; account ACCT-200 has 900,000.00 available (short 100,000.00)
- **FAIL** `rpt_release_flag_recomputes` @ `release_summary:SUMMARY-2030/wires/W-1004/releasable`  
  packet W-1004 is summarised releasable=True; recomputing from the release evidence gives releasable=False

### incomplete_dual_auth__Halbrook_Residential

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 2)

- **FAIL** `sod_dual_auth_complete` @ `wire_register:WIRES-2030/wires/W-1002`  
  packet W-1002 is Approved & Scheduled but is missing authorized_date; it cannot have cleared the dual-authorization gate
- **FAIL** `rpt_release_flag_recomputes` @ `release_summary:SUMMARY-2030/wires/W-1002/releasable`  
  packet W-1002 is summarised releasable=True; recomputing from the release evidence gives releasable=False

### initiator_not_signer__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 2)

- **FAIL** `sig_initiator_authorized` @ `wire_register:WIRES-2030/wires/W-1005/initiated_by`  
  packet W-1005 was initiated by 'SGN-03', who is not on the authorized-signer register for account ACCT-100
- **FAIL** `rpt_release_flag_recomputes` @ `release_summary:SUMMARY-2030/wires/W-1005/releasable`  
  packet W-1005 is summarised releasable=True; recomputing from the release evidence gives releasable=False

### missing_artifact__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `release_report:-`  
  release_report is missing; the controls that read it cannot run and must not be reported as having passed

### off_template_no_callback__Westmere

**Verdict:** FAIL (PASS 20, FLAG 1, FAIL 2)

- **FAIL** `ben_new_account_callback` @ `wire_register:WIRES-2030/wires/W-1005/callback_completed`  
  packet W-1005 pays an off-template beneficiary with no completed callback; a new or changed bank detail must be verified before release
- **FLAG** `ben_off_template_review` @ `wire_register:WIRES-2030/wires/W-1005/on_template`  
  packet W-1005 pays an off-template beneficiary; even with a callback on file it should be reviewed before the wire is released
- **FAIL** `rpt_release_flag_recomputes` @ `release_summary:SUMMARY-2030/wires/W-1005/releasable`  
  packet W-1005 is summarised releasable=True; recomputing from the release evidence gives releasable=False

### off_template_with_callback__Northmoor_Development_Group

**Verdict:** REVIEW (PASS 22, FLAG 1, FAIL 0)

- **FLAG** `ben_off_template_review` @ `wire_register:WIRES-2030/wires/W-1004/on_template`  
  packet W-1004 pays an off-template beneficiary; even with a callback on file it should be reviewed before the wire is released

### over_authority_limit__Halbrook_Residential

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 2)

- **FAIL** `sig_within_authority_limit` @ `wire_register:WIRES-2030/wires/W-1005/amount_cents`  
  packet W-1005 is 3,000,000.01; authorizer SGN-02 carries a 3,000,000.00 authority limit on account ACCT-100 (over by 0.01)
- **FAIL** `rpt_release_flag_recomputes` @ `release_summary:SUMMARY-2030/wires/W-1005/releasable`  
  packet W-1005 is summarised releasable=True; recomputing from the release evidence gives releasable=False

### posted_no_approval__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 2)

- **FAIL** `flow_posted_has_approval` @ `wire_register:WIRES-2030/wires/W-1001`  
  posted packet W-1001 is missing authorized_date; it was released with no evidence of a complete secondary approval
- **FAIL** `rpt_release_flag_recomputes` @ `release_summary:SUMMARY-2030/wires/W-1001/releasable`  
  packet W-1001 is summarised releasable=True; recomputing from the release evidence gives releasable=False

### posted_ref_broken__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `flow_posted_ref_ties` @ `wire_register:WIRES-2030/wires/W-1007/posted_ref`  
  posted packet W-1007 references posting 'P-9999', which is not in the posted log; the release cannot be tied to an execution

### release_flag_wrong__Westmere

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `rpt_release_flag_recomputes` @ `release_summary:SUMMARY-2030/wires/W-1005/releasable`  
  packet W-1005 is summarised releasable=False; recomputing from the release evidence gives releasable=True

### report_count_wrong__Northmoor_Development_Group

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `rpt_report_count_ties` @ `release_report:REPORT-2030/releasable_count`  
  the report states 8 releasable / 0 blocked; the release summary recomputes 7 / 0

### same_signer__Halbrook_Residential

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 2)

- **FAIL** `sod_two_distinct_signers` @ `wire_register:WIRES-2030/wires/W-1005/authorized_by`  
  packet W-1005 was initiated and authorized by the same signer 'SGN-01'; segregation of duties requires two distinct signers
- **FAIL** `rpt_release_flag_recomputes` @ `release_summary:SUMMARY-2030/wires/W-1005/releasable`  
  packet W-1005 is summarised releasable=True; recomputing from the release evidence gives releasable=False

### template_missing__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 2)

- **FAIL** `ben_template_exists` @ `wire_register:WIRES-2030/wires/W-1004/template_id`  
  packet W-1004 claims template 'BEN-999', which is not in the approved-beneficiary register
- **FAIL** `rpt_release_flag_recomputes` @ `release_summary:SUMMARY-2030/wires/W-1004/releasable`  
  packet W-1004 is summarised releasable=True; recomputing from the release evidence gives releasable=False

### triplet_mismatch__Ardenne_Field_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 2)

- **FAIL** `ben_triplet_matches_template` @ `wire_register:WIRES-2030/wires/W-1002/beneficiary_account`  
  packet W-1002 beneficiary ('983000033', '5560299999', 'Copperfield Yards Vendors LLC') does not match the stored template ('983000033', '5560294417', 'Copperfield Yards Vendors LLC'); the payment is bound for an unapproved destination
- **FAIL** `rpt_release_flag_recomputes` @ `release_summary:SUMMARY-2030/wires/W-1002/releasable`  
  packet W-1002 is summarised releasable=True; recomputing from the release evidence gives releasable=False

### unknown_stage__Westmere

**Verdict:** FAIL (PASS 22, FLAG 0, FAIL 1)

- **FAIL** `flow_stage_valid` @ `wire_register:WIRES-2030/wires/W-1005/stage`  
  packet W-1005 is in stage 'draft', which is not one of ('pending_secondary_approval', 'approved_scheduled', 'posted'); its place in the release workflow is unknown
