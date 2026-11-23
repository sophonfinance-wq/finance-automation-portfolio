# Insurance compliance control report

**Overall verdict:** FAIL

- Compliance files analyzed: 24
- Controls in registry: 22
- PASS / REVIEW / FAIL: 1 / 2 / 21

All data is fictional. The engine is read-only and never writes to a source
artifact. Every expiry and renewal test is made against the `as_of` date carried
in the file, never the system clock.

## Controls

| # | Rule | Severity | Exceptions |
|---|------|----------|------------|
| 1 | `set_complete` | FAIL | 1 |
| 2 | `party_unique_ids` | FAIL | 1 |
| 3 | `party_type_valid` | FAIL | 1 |
| 4 | `party_coverage_declared` | FAIL | 1 |
| 5 | `party_matrix_defined` | FAIL | 2 |
| 6 | `cert_required_fields` | FAIL | 1 |
| 7 | `cert_policy_no_unique` | FAIL | 1 |
| 8 | `cert_term_runs_forward` | FAIL | 1 |
| 9 | `cert_party_exists` | FAIL | 1 |
| 10 | `cov_coverage_type_valid` | FAIL | 1 |
| 11 | `cov_required_present` | FAIL | 2 |
| 12 | `cov_per_occurrence_meets` | FAIL | 2 |
| 13 | `cov_aggregate_meets` | FAIL | 1 |
| 14 | `cov_no_uninsured_gap` | FAIL | 1 |
| 15 | `end_additional_insured_present` | FAIL | 1 |
| 16 | `end_waiver_of_subrogation_present` | FAIL | 1 |
| 17 | `exp_not_expired` | FAIL | 1 |
| 18 | `exp_renewal_lead_time` | FLAG | 1 |
| 19 | `exp_workers_comp_present` | FAIL | 1 |
| 20 | `rpt_party_compliant_recomputes` | FAIL | 9 |
| 21 | `rpt_report_count_ties` | FAIL | 1 |
| 22 | `rpt_watchlist_ties` | FLAG | 1 |

## Compliance files

### aggregate_short__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 2)

- **FAIL** `cov_aggregate_meets` @ `certificate_register:CERTS-2029/certificates/COI-1001/aggregate_cents`  
  party PTY-101 carries 3,900,000.00 aggregate on commercial_general_liability; the contract requires 4,000,000.00 (short 100,000.00)
- **FAIL** `rpt_party_compliant_recomputes` @ `coverage_summary:SUMMARY-2029/parties/PTY-101/compliant`  
  party PTY-101 is summarised compliant=True; recomputing from its certificates gives compliant=False

### amount_not_integer__Stonecrest_Communities

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 2)

- **FAIL** `cov_per_occurrence_meets` @ `amount:certificate[COI-1001].per_occurrence_cents`  
  AMOUNT_INVALID: certificate[COI-1001].per_occurrence_cents must be integer cents, got 200000000.5 -- amounts are integer cents and are never coerced
- **FAIL** `rpt_party_compliant_recomputes` @ `amount:certificate[COI-1001].per_occurrence_cents`  
  AMOUNT_INVALID: certificate[COI-1001].per_occurrence_cents must be integer cents, got 200000000.5 -- amounts are integer cents and are never coerced

### bad_party_type__Ardenne_Field_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `party_type_valid` @ `party_register:PARTIES-2029/parties/PTY-104/party_type`  
  party PTY-104 is typed 'vendor', which is not one of ('consultant', 'general_contractor', 'subcontractor'); its requirement cannot be looked up

### cert_missing_field__Northmoor_Development_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `cert_required_fields` @ `certificate_register:CERTS-2029/certificates/COI-1003`  
  certificate COI-1003 is missing carrier

### clean__Northmoor_Development_Group

**Verdict:** PASS (PASS 22, FLAG 0, FAIL 0)

All controls held.

### compliant_flag_wrong__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `rpt_party_compliant_recomputes` @ `coverage_summary:SUMMARY-2029/parties/PTY-101/compliant`  
  party PTY-101 is summarised compliant=False; recomputing from its certificates gives compliant=True

### coverage_gap__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `cov_no_uninsured_gap` @ `certificate_register:CERTS-2029/certificates/COI-1001/inception_date`  
  party PTY-101 commercial_general_liability expires 2029-06-01 on COI-1002 and does not resume until 2029-08-01 on COI-1001, leaving 61 uninsured day(s)

### duplicate_party_id__Ardenne_Field_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `party_unique_ids` @ `party_register:PARTIES-2029/parties/PTY-101`  
  party id PTY-101 appears 2 times; a certificate that names it cannot be attributed to one party

### duplicate_policy_no__Northmoor_Development_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `cert_policy_no_unique` @ `certificate_register:CERTS-2029/certificates/policy_no/PN-1012`  
  policy number PN-1012 appears on 2 certificates; they cannot both be independent evidence of coverage

### expired_certificate__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 2)

- **FAIL** `exp_not_expired` @ `certificate_register:CERTS-2029/certificates/COI-1006/expiration_date`  
  party PTY-102 commercial_general_liability certificate COI-1006 expired 2029-09-01, on or before the review date 2029-10-01; the party is uninsured on this line
- **FAIL** `rpt_party_compliant_recomputes` @ `coverage_summary:SUMMARY-2029/parties/PTY-102/compliant`  
  party PTY-102 is summarised compliant=True; recomputing from its certificates gives compliant=False

### invalid_coverage_type__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `cov_coverage_type_valid` @ `certificate_register:CERTS-2029/certificates/COI-2002/coverage_type`  
  certificate COI-2002 attests coverage 'cyber_liability', which is not a known coverage line

### inverted_cert_term__Ardenne_Field_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `cert_term_runs_forward` @ `certificate_register:CERTS-2029/certificates/COI-1010/inception_date`  
  certificate COI-1010 incepts 2031-06-01 and expires 2030-06-01; the term does not run forwards

### matrix_row_missing__Northmoor_Development_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 2)

- **FAIL** `party_matrix_defined` @ `requirement_matrix:MATRIX-2029/requirements/subcontractor/automobile_liability`  
  the requirement matrix has no row for subcontractor/automobile_liability, which party PTY-102 must carry; its limit cannot be tested
- **FAIL** `party_matrix_defined` @ `requirement_matrix:MATRIX-2029/requirements/subcontractor/automobile_liability`  
  the requirement matrix has no row for subcontractor/automobile_liability, which party PTY-104 must carry; its limit cannot be tested

### missing_additional_insured__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 2)

- **FAIL** `end_additional_insured_present` @ `certificate_register:CERTS-2029/certificates/COI-1001/additional_insured`  
  party PTY-101 commercial_general_liability certificate COI-1001 does not carry the additional-insured endorsement the contract requires
- **FAIL** `rpt_party_compliant_recomputes` @ `coverage_summary:SUMMARY-2029/parties/PTY-101/compliant`  
  party PTY-101 is summarised compliant=True; recomputing from its certificates gives compliant=False

### missing_artifact__Stonecrest_Communities

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 1)

- **FAIL** `set_complete` @ `compliance_report:-`  
  compliance_report is missing; the controls that read it cannot run and must not be reported as having passed

### missing_required_cert__Ardenne_Field_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 2)

- **FAIL** `cov_required_present` @ `certificate_register:CERTS-2029/certificates/PTY-101/umbrella_excess`  
  party PTY-101 is required to carry umbrella_excess but has no certificate on file for it
- **FAIL** `rpt_party_compliant_recomputes` @ `coverage_summary:SUMMARY-2029/parties/PTY-101/compliant`  
  party PTY-101 is summarised compliant=True; recomputing from its certificates gives compliant=False

### missing_waiver__Northmoor_Development_Group

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 2)

- **FAIL** `end_waiver_of_subrogation_present` @ `certificate_register:CERTS-2029/certificates/COI-1004/waiver_of_subrogation`  
  party PTY-101 workers_compensation certificate COI-1004 does not carry the waiver-of-subrogation endorsement the contract requires
- **FAIL** `rpt_party_compliant_recomputes` @ `coverage_summary:SUMMARY-2029/parties/PTY-101/compliant`  
  party PTY-101 is summarised compliant=True; recomputing from its certificates gives compliant=False

### missing_wc_cert__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 19, FLAG 0, FAIL 3)

- **FAIL** `cov_required_present` @ `certificate_register:CERTS-2029/certificates/PTY-102/workers_compensation`  
  party PTY-102 is required to carry workers_compensation but has no certificate on file for it
- **FAIL** `exp_workers_comp_present` @ `certificate_register:CERTS-2029/certificates/PTY-102/workers_compensation`  
  party PTY-102 has no workers' compensation certificate on file; it is a statutory floor for anyone with employees on site
- **FAIL** `rpt_party_compliant_recomputes` @ `coverage_summary:SUMMARY-2029/parties/PTY-102/compliant`  
  party PTY-102 is summarised compliant=True; recomputing from its certificates gives compliant=False

### per_occurrence_short__Stonecrest_Communities

**Verdict:** FAIL (PASS 20, FLAG 0, FAIL 2)

- **FAIL** `cov_per_occurrence_meets` @ `certificate_register:CERTS-2029/certificates/COI-1001/per_occurrence_cents`  
  party PTY-101 carries 1,900,000.00 per-occurrence on commercial_general_liability; the contract requires 2,000,000.00 (short 100,000.00)
- **FAIL** `rpt_party_compliant_recomputes` @ `coverage_summary:SUMMARY-2029/parties/PTY-101/compliant`  
  party PTY-101 is summarised compliant=True; recomputing from its certificates gives compliant=False

### renewal_due_soon__Ardenne_Field_Group

**Verdict:** REVIEW (PASS 21, FLAG 1, FAIL 0)

- **FLAG** `exp_renewal_lead_time` @ `certificate_register:CERTS-2029/certificates/COI-1012/expiration_date`  
  party PTY-104 commercial_general_liability certificate COI-1012 expires 2029-10-20, in 19 day(s); inside the 30-day renewal window and due to be chased

### report_count_wrong__Northmoor_Development_Group

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `rpt_report_count_ties` @ `compliance_report:REPORT-2029/compliant_count`  
  the report states 5 compliant / 0 non-compliant; the coverage summary recomputes 4 / 0

### undeclared_coverage__Halbrook_Residential_Partners

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `party_coverage_declared` @ `party_register:PARTIES-2029/parties/PTY-103/required_coverages`  
  party PTY-103 declares no contract-required coverage; its coverage controls would pass on an empty requirement

### unknown_party_cert__Stonecrest_Communities

**Verdict:** FAIL (PASS 21, FLAG 0, FAIL 1)

- **FAIL** `cert_party_exists` @ `certificate_register:CERTS-2029/certificates/COI-2001/party_id`  
  certificate COI-2001 names party 'PTY-999', which is not in the party register

### watchlist_overstated__Ardenne_Field_Group

**Verdict:** REVIEW (PASS 21, FLAG 1, FAIL 0)

- **FLAG** `rpt_watchlist_ties` @ `renewal_watchlist:WATCHLIST-2029/entries/COI-1001`  
  the watchlist lists certificate COI-1001 as due for renewal, but it is not inside the lead-time window as of 2029-10-01
