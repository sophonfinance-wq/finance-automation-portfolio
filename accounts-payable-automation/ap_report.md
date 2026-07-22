# Accounts Payable Control Report (SFS-E10-APX)

> Fully synthetic, seeded data. Invented entities, vendors, jobs and identifiers for demonstration. Not real data.

**Overall verdict:** FAIL

Document sets analyzed: 31 - PASS 1953 / FAIL 22 / FLAG 10 across 30 registered controls.

## Control families

| Family | Controls | PASS | FAIL | FLAG |
| --- | --- | --: | --: | --: |
| Structural precondition (`set_*`) | 1 | 30 | 1 | 0 |
| Posting integrity (`post_*`) | 8 | 332 | 8 | 1 |
| Payment release gate (`gate_*`) | 8 | 619 | 5 | 4 |
| Routing and segregation of duties (`route_*`) | 5 | 398 | 4 | 1 |
| Information reporting (`ir_*`) | 5 | 367 | 3 | 2 |
| Commitment hygiene (`cmt_*`) | 3 | 207 | 1 | 2 |

## Document sets

| Document set | Verdict | PASS | FAIL | FLAG | Controls fired |
| --- | --- | --: | --: | --: | --- |
| blocking_error__Birchwood_Op_Co.json | FAIL | 63 | 1 | 0 | post_no_error_marker |
| clean__Demo_Holdings_LLC.json | PASS | 64 | 0 | 0 | - |
| commitment_id_drift__Harborview_Partners_LP.json | REVIEW | 63 | 0 | 1 | cmt_id_convention |
| direct_post_undeclared__Birchwood_Op_Co.json | REVIEW | 63 | 0 | 1 | route_preapproved_declared |
| duplicate_payment__Demo_Holdings_LLC.json | FAIL | 70 | 1 | 0 | gate_no_duplicate |
| duties_merged__Maple_Fund_LP.json | FAIL | 63 | 1 | 0 | route_duties_segregated |
| filed_count_off__Birchwood_Op_Co.json | FAIL | 63 | 1 | 0 | ir_filed_reconciles |
| funding_unconfirmed__Harborview_Partners_LP.json | FAIL | 63 | 1 | 0 | gate_funding_confirmed |
| gl_recap_out__Cedar_Ridge_Trust.json | FAIL | 63 | 1 | 0 | post_gl_balanced |
| header_date_drift__Harborview_Partners_LP.json | REVIEW | 63 | 0 | 1 | post_header_date_agrees |
| insurance_expired__Birchwood_Op_Co.json | FAIL | 63 | 1 | 0 | gate_insurance_current |
| insurance_thin__Cedar_Ridge_Trust.json | REVIEW | 63 | 0 | 1 | gate_insurance_limits |
| job_unmapped__Cedar_Ridge_Trust.json | FAIL | 63 | 1 | 0 | route_every_job_mapped |
| jobcost_drift__Cedar_Ridge_Trust.json | FAIL | 63 | 1 | 0 | post_jobcost_ties |
| missing_w9__Demo_Holdings_LLC.json | FAIL | 63 | 1 | 0 | gate_w9_on_file |
| no_final_review__Demo_Holdings_LLC.json | FAIL | 63 | 1 | 0 | route_final_review_present |
| nothing_posted__Maple_Fund_LP.json | FAIL | 62 | 2 | 0 | post_actually_posted |
| offcycle_unapproved__Birchwood_Op_Co.json | REVIEW | 63 | 0 | 1 | gate_offcycle_approved |
| orphan_change_order__Demo_Holdings_LLC.json | REVIEW | 63 | 0 | 1 | cmt_co_attaches_to_original |
| proof_nonzero__Birchwood_Op_Co.json | FAIL | 63 | 1 | 0 | post_proof_zero |
| rejected_entries__Demo_Holdings_LLC.json | FAIL | 63 | 1 | 0 | post_no_rejects |
| retention_drift__Maple_Fund_LP.json | REVIEW | 63 | 0 | 2 | gate_retention_present |
| set_incomplete__Maple_Fund_LP.json | FAIL | 56 | 1 | 0 | set_complete |
| sov_lump_sum__Cedar_Ridge_Trust.json | FAIL | 63 | 1 | 0 | cmt_sov_not_lump_sum |
| split_vendor__Maple_Fund_LP.json | REVIEW | 64 | 0 | 1 | ir_no_split_vendor |
| threshold_skipped__Cedar_Ridge_Trust.json | FAIL | 63 | 1 | 0 | ir_threshold_coverage |
| tin_malformed__Demo_Holdings_LLC.json | REVIEW | 63 | 0 | 1 | ir_tin_structure |
| tin_missing__Harborview_Partners_LP.json | FAIL | 62 | 1 | 0 | ir_tin_present |
| totals_out__Harborview_Partners_LP.json | FAIL | 63 | 1 | 0 | post_totals_balanced |
| waiver_gap__Maple_Fund_LP.json | FAIL | 63 | 1 | 0 | gate_lien_waiver |
| workflow_no_approver__Harborview_Partners_LP.json | FAIL | 63 | 1 | 0 | route_workflow_has_approver |

## Exceptions

### blocking_error__Birchwood_Op_Co.json - FAIL

| Status | Control | Location | Message |
| --- | --- | --- | --- |
| FAIL | post_no_error_marker | invoice_posting_report:POST-2026-0008/error_markers | blocking posting error: 'batch contention on the posting queue - update aborted'; the run did not complete and the invoices are not in the ledger |

### clean__Demo_Holdings_LLC.json - PASS

All controls held.

### commitment_id_drift__Harborview_Partners_LP.json - REVIEW

| Status | Control | Location | Message |
| --- | --- | --- | --- |
| FLAG | cmt_id_convention | commitment_register:CMT-2026-0030/commitments[CMT-0002].commitment_id | CMT-0002 does not follow the <job>-<vendor>-<nn> convention (expected the stem 'JOB-2026-0002-VEN-1002-'); it will not be found with its job at close-out |

### direct_post_undeclared__Birchwood_Op_Co.json - REVIEW

| Status | Control | Location | Message |
| --- | --- | --- | --- |
| FLAG | route_preapproved_declared | workflow_routing_matrix:ROUTE-2026-0023/preapproved_direct_post | workflow WF-DIRECT-01 posts directly but is not enumerated as pre-approved |

### duplicate_payment__Demo_Holdings_LLC.json - FAIL

| Status | Control | Location | Message |
| --- | --- | --- | --- |
| FAIL | gate_no_duplicate | payment_selection_register:PAYSEL-2026-0016/payments | duplicate selection: VEN-1001 / INV-2026-1601 appears on both PAY-2026-1601 and PAY-2026-1601-B for the same amount; one of them is a second payment of the same obligation |

### duties_merged__Maple_Fund_LP.json - FAIL

| Status | Control | Location | Message |
| --- | --- | --- | --- |
| FAIL | route_duties_segregated | workflow_routing_matrix:ROUTE-2026-0022/workflows[WF-STD-02].final_review_role | workflow WF-STD-02 has clerk-two on both data entry and final review; the same role-holder can create and approve a payable |

### filed_count_off__Birchwood_Op_Co.json - FAIL

| Status | Control | Location | Message |
| --- | --- | --- | --- |
| FAIL | ir_filed_reconciles | information_reporting_register:IR-2026-0028/filed_counts[Birchwood Op Co] | Birchwood Op Co reports 2 filed form(s) but the register expects 3; the difference is 1 unaccounted vendor(s) |

### funding_unconfirmed__Harborview_Partners_LP.json - FAIL

| Status | Control | Location | Message |
| --- | --- | --- | --- |
| FAIL | gate_funding_confirmed | payment_selection_register:PAYSEL-2026-0015/funding.confirmed | funding is not confirmed for this selection; the run may not be released |

### gl_recap_out__Cedar_Ridge_Trust.json - FAIL

| Status | Control | Location | Message |
| --- | --- | --- | --- |
| FAIL | post_gl_balanced | invoice_posting_report:POST-2026-0004/gl_recap | ledger recap does not balance: debit 22,478.61 vs credit 22,528.61 (difference -50.00) |

### header_date_drift__Harborview_Partners_LP.json - REVIEW

| Status | Control | Location | Message |
| --- | --- | --- | --- |
| FLAG | post_header_date_agrees | invoice_posting_report:POST-2026-0010/header_date | header date 2026-06-30 disagrees with the file name stamp 20260731; the report may be filed against the wrong period |

### insurance_expired__Birchwood_Op_Co.json - FAIL

| Status | Control | Location | Message |
| --- | --- | --- | --- |
| FAIL | gate_insurance_current | payment_selection_register:PAYSEL-2026-0013/payments[PAY-2026-1301].insurance.expires_on | insurance for Ironwood Sandbox Supply Co expired 2026-06-30, before the payment date 2026-07-31; release is not permitted |

### insurance_thin__Cedar_Ridge_Trust.json - REVIEW

| Status | Control | Location | Message |
| --- | --- | --- | --- |
| FLAG | gate_insurance_limits | payment_selection_register:PAYSEL-2026-0014/payments[PAY-2026-1402].insurance.general_liability_cents | Foxglove Mock Freight LLC general liability coverage 500,000.00 is below the contract minimum 1,000,000.00 (short 500,000.00) |

### job_unmapped__Cedar_Ridge_Trust.json - FAIL

| Status | Control | Location | Message |
| --- | --- | --- | --- |
| FAIL | route_every_job_mapped | workflow_routing_matrix:ROUTE-2026-0019/jobs[JOB-2026-0001].workflows | active job JOB-2026-0001 maps to 0 workflow(s); exactly one is required or its invoices route nowhere |

### jobcost_drift__Cedar_Ridge_Trust.json - FAIL

| Status | Control | Location | Message |
| --- | --- | --- | --- |
| FAIL | post_jobcost_ties | invoice_posting_report:POST-2026-0009/job_cost_recap_cents | job-cost recap 4,915.00 does not tie to the payable cost total 4,900.00 (difference 15.00) |

### missing_w9__Demo_Holdings_LLC.json - FAIL

| Status | Control | Location | Message |
| --- | --- | --- | --- |
| FAIL | gate_w9_on_file | payment_selection_register:PAYSEL-2026-0011/payments[PAY-2026-1101].w9_on_file | first payment to Ironwood Sandbox Supply Co has no taxpayer certificate on file; release is not permitted until it is received |

### no_final_review__Demo_Holdings_LLC.json - FAIL

| Status | Control | Location | Message |
| --- | --- | --- | --- |
| FAIL | route_final_review_present | workflow_routing_matrix:ROUTE-2026-0021/workflows[WF-STD-02].final_review_group | workflow WF-STD-02 names no final-review group; invoices routed to it reach payment without an accounting sign-off |

### nothing_posted__Maple_Fund_LP.json - FAIL

| Status | Control | Location | Message |
| --- | --- | --- | --- |
| FAIL | post_actually_posted | invoice_posting_report:POST-2026-0007/posted_counts.invoices | zero invoices posted; the report balances because nothing moved -- the run was filed as though it succeeded |
| FAIL | post_actually_posted | invoice_posting_report:POST-2026-0007/posted_counts.entries | zero entries posted; the report balances because nothing moved -- the run was filed as though it succeeded |

### offcycle_unapproved__Birchwood_Op_Co.json - REVIEW

| Status | Control | Location | Message |
| --- | --- | --- | --- |
| FLAG | gate_offcycle_approved | payment_selection_register:PAYSEL-2026-0018/payments[PAY-2026-1803].off_cycle_approval | off-cycle payment of 6,552.18 to Harborview Demo Services Inc carries no recorded approver and approval date; the compensating control is absent |

### orphan_change_order__Demo_Holdings_LLC.json - REVIEW

| Status | Control | Location | Message |
| --- | --- | --- | --- |
| FLAG | cmt_co_attaches_to_original | commitment_register:CMT-2026-0031/commitments[JOB-2026-0001-VEN-1001-01].change_orders[JOB-2026-0001-VEN-1001-01-CO-01] | change order JOB-2026-0001-VEN-1001-01-CO-01 attaches to 'JOB-2026-0099-VEN-1099-01', which is not a commitment in this register; the obligation is not reflected on any commitment |

### proof_nonzero__Birchwood_Op_Co.json - FAIL

| Status | Control | Location | Message |
| --- | --- | --- | --- |
| FAIL | post_proof_zero | invoice_posting_report:POST-2026-0003/posting_proof_cents | posting proof is 25.00, not zero; the run wrote a one-sided entry and the ledger is out of balance |

### rejected_entries__Demo_Holdings_LLC.json - FAIL

| Status | Control | Location | Message |
| --- | --- | --- | --- |
| FAIL | post_no_rejects | invoice_posting_report:POST-2026-0006/rejected.entries | 2 rejected entries; the run reports success but those documents never reached the ledger |

### retention_drift__Maple_Fund_LP.json - REVIEW

| Status | Control | Location | Message |
| --- | --- | --- | --- |
| FLAG | gate_retention_present | payment_selection_register:PAYSEL-2026-0017/payments[PAY-2026-1701].retention_cents | progress billing for Ironwood Sandbox Supply Co: retention 655.00 does not equal 1000 bps of gross 6,400.00 (640.00) |
| FLAG | gate_retention_present | payment_selection_register:PAYSEL-2026-0017/payments[PAY-2026-1701].retention_cents | progress billing for Ironwood Sandbox Supply Co: tax 504.00 does not equal 875 bps of the net (502.68) |

### set_incomplete__Maple_Fund_LP.json - FAIL

| Status | Control | Location | Message |
| --- | --- | --- | --- |
| FAIL | set_complete | document_set/documents | the document set is missing 1 of 5 required artifact type(s): commitment_register; the controls that read them cannot run and their silence is not a passing control |

### sov_lump_sum__Cedar_Ridge_Trust.json - FAIL

| Status | Control | Location | Message |
| --- | --- | --- | --- |
| FAIL | cmt_sov_not_lump_sum | commitment_register:CMT-2026-0029/commitments[JOB-2026-0001-VEN-1001-01].schedule_of_values | subcontract JOB-2026-0001-VEN-1001-01 carries 1 schedule-of-values line(s); a lump-sum schedule leaves progress billings with nothing to bill against |

### split_vendor__Maple_Fund_LP.json - REVIEW

| Status | Control | Location | Message |
| --- | --- | --- | --- |
| FLAG | ir_no_split_vendor | information_reporting_register:IR-2026-0027/vendors | vendor records VEN-1001, VEN-1091 share identifier 00-1000271; year-to-date payments are split across them and each half may sit under the reporting threshold |

### threshold_skipped__Cedar_Ridge_Trust.json - FAIL

| Status | Control | Location | Message |
| --- | --- | --- | --- |
| FAIL | ir_threshold_coverage | information_reporting_register:IR-2026-0024/vendors[VEN-1001].evaluated | VEN-1001 paid 27,550.00 year to date, over the 600.00 threshold, but was never evaluated for reporting |

### tin_malformed__Demo_Holdings_LLC.json - REVIEW

| Status | Control | Location | Message |
| --- | --- | --- | --- |
| FLAG | ir_tin_structure | information_reporting_register:IR-2026-0026/vendors[VEN-1003].tin | VEN-1003 identifier '000000001' does not match the expected structure; the filing will be rejected on validation |

### tin_missing__Harborview_Partners_LP.json - FAIL

| Status | Control | Location | Message |
| --- | --- | --- | --- |
| FAIL | ir_tin_present | information_reporting_register:IR-2026-0025/vendors[VEN-1002].tin | reportable vendor VEN-1002 has no taxpayer identification number; the year-end form cannot be filed |

### totals_out__Harborview_Partners_LP.json - FAIL

| Status | Control | Location | Message |
| --- | --- | --- | --- |
| FAIL | post_totals_balanced | invoice_posting_report:POST-2026-0005/posting_totals | posting totals do not balance: debit 19,496.15 vs credit 19,421.15 (difference 75.00); the batch was only partially applied |

### waiver_gap__Maple_Fund_LP.json - FAIL

| Status | Control | Location | Message |
| --- | --- | --- | --- |
| FAIL | gate_lien_waiver | payment_selection_register:PAYSEL-2026-0012/payments[PAY-2026-1201].lien_waiver | lower-tier lien waiver(s) not received from VEN-2002; a lower-tier lien survives payment to Ironwood Sandbox Supply Co |

### workflow_no_approver__Harborview_Partners_LP.json - FAIL

| Status | Control | Location | Message |
| --- | --- | --- | --- |
| FAIL | route_workflow_has_approver | workflow_routing_matrix:ROUTE-2026-0020/workflows[WF-STD-01].approvers | workflow WF-STD-01 names no approver; every invoice routed to it has no reviewer |

## Registered controls

| Control | Family |
| --- | --- |
| set_complete | Structural precondition |
| post_proof_zero | Posting integrity |
| post_gl_balanced | Posting integrity |
| post_totals_balanced | Posting integrity |
| post_no_rejects | Posting integrity |
| post_actually_posted | Posting integrity |
| post_no_error_marker | Posting integrity |
| post_jobcost_ties | Posting integrity |
| post_header_date_agrees | Posting integrity |
| gate_w9_on_file | Payment release gate |
| gate_lien_waiver | Payment release gate |
| gate_insurance_current | Payment release gate |
| gate_insurance_limits | Payment release gate |
| gate_funding_confirmed | Payment release gate |
| gate_no_duplicate | Payment release gate |
| gate_retention_present | Payment release gate |
| gate_offcycle_approved | Payment release gate |
| route_every_job_mapped | Routing and segregation of duties |
| route_workflow_has_approver | Routing and segregation of duties |
| route_final_review_present | Routing and segregation of duties |
| route_duties_segregated | Routing and segregation of duties |
| route_preapproved_declared | Routing and segregation of duties |
| ir_threshold_coverage | Information reporting |
| ir_tin_present | Information reporting |
| ir_tin_structure | Information reporting |
| ir_no_split_vendor | Information reporting |
| ir_filed_reconciles | Information reporting |
| cmt_sov_not_lump_sum | Commitment hygiene |
| cmt_id_convention | Commitment hygiene |
| cmt_co_attaches_to_original | Commitment hygiene |
