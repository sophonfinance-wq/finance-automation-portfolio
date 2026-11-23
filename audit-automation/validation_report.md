# Validation Report

**Overall verdict:** FAIL

Workbooks validated: 7

| Workbook | Verdict | PASS | FAIL | FLAG |
| --- | --- | --: | --: | --: |
| cap_leftover__Sandbox_Capital_LLC.xlsx | REVIEW | 6 | 0 | 1 |
| clean__Demo_Holdings_LLC.xlsx | PASS | 7 | 0 | 0 |
| hardcoded_total__Maple_Fund_LP.xlsx | FAIL | 5 | 1 | 1 |
| json_mismatch__Demo_Holdings_LLC.xlsx | FAIL | 6 | 1 | 0 |
| reversed_lineage__Harborview_Partners_LP.xlsx | REVIEW | 6 | 0 | 1 |
| stale_note__Cedar_Ridge_Trust.xlsx | REVIEW | 6 | 0 | 1 |
| unbalanced_tb__Birchwood_Op_Co.xlsx | FAIL | 6 | 1 | 0 |

## cap_leftover__Sandbox_Capital_LLC.xlsx — REVIEW

| Status | Rule | Location | Message |
| --- | --- | --- | --- |
| FLAG | cap_logic_leftover | Summary!B2 | leftover MIN/MAX cap logic: =MAX(0, 'Surplus-Detail'!B6) |

## clean__Demo_Holdings_LLC.xlsx — PASS

All checks passed.

## hardcoded_total__Maple_Fund_LP.xlsx — FAIL

| Status | Rule | Location | Message |
| --- | --- | --- | --- |
| FAIL | expected_formula | Surplus-Detail!B6 | expected a formula but found hardcoded value: 900 |
| FLAG | lineage_direction | Surplus-Detail!B6 | detail driver should be a formula but is a literal: 900 |

## json_mismatch__Demo_Holdings_LLC.xlsx — FAIL

| Status | Rule | Location | Message |
| --- | --- | --- | --- |
| FAIL | json_tieout | json:closing_surplus | JSON closing_surplus=1725 != workbook closing surplus=1700 |

## reversed_lineage__Harborview_Partners_LP.xlsx — REVIEW

| Status | Rule | Location | Message |
| --- | --- | --- | --- |
| FLAG | lineage_direction | Evidence!B2 | evidence input should be a literal but is a formula: =Opening+0 |

## stale_note__Cedar_Ridge_Trust.xlsx — REVIEW

| Status | Rule | Location | Message |
| --- | --- | --- | --- |
| FLAG | forbidden_text | Surplus-Detail!D2 | forbidden text 'todo' in cell: 'TODO: reviewer decision pending on FY2024 income' |

## unbalanced_tb__Birchwood_Op_Co.xlsx — FAIL

| Status | Rule | Location | Message |
| --- | --- | --- | --- |
| FAIL | debit_credit_balance | Trial-Balance!B:C | trial balance does NOT tie out: debit=885 vs credit=875 (diff=10) |
