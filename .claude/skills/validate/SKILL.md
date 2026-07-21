---
name: validate
description: "Run the read-only Validation Engine over finished workbooks (PASS/REVIEW/FAIL verdicts, byte-identical no-write guarantee). Use to audit workbook artifacts or demo the planted-defect catalogue."
---
# Validation Engine (read-only)

Package `validation_engine` in `audit-automation/`.

## Commands (run from `audit-automation/`)
```bash
python run.py                 # audits the workbook set read-only; prints PASS/REVIEW/FAIL per book
python -m pytest -q           # 4,814 tests incl. planted-defect suite
```

## The one rule
This engine NEVER writes — workbooks open `read_only=True` and the suite asserts sha256 byte-identity after a run. Do not bolt a remediation loop onto it; it is the *sensor* other loops use. If asked to "fix" what it finds, route fixes through the producing engine, then re-validate.
