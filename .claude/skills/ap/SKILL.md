---
name: ap
description: "Run the read-only Accounts Payable control engine over posting document sets (30 controls in 6 families, PASS/REVIEW/FAIL verdicts, byte-identical no-write guarantee). Use to check posting integrity, payment release gates, approver routing and duty segregation, information reporting, or commitment hygiene."
---
# Accounts Payable (read-only)

Package `ap_engine` in `accounts-payable-automation/`.

## Commands (run from `accounts-payable-automation/`)
```bash
python run.py                 # generate the fictional corpus, run all 30 controls, write both artifacts
python -m ap_engine ./samples # analyze an existing folder read-only
python -m pytest -q           # 2,223 tests incl. the planted-defect suite
```

Exit codes: `0` PASS · `1` REVIEW · `2` FAIL · `3` usage/IO. The bundled corpus carries one planted defect per control, so it exits `2` by design.

## The one rule
This engine NEVER writes — source artifacts are hashed before and after a run and asserted byte-identical. It has no connection to a ledger, payment provider or approval system, so nothing it produces can post or pay. Do not bolt a remediation loop onto it; like `/validate` it is the *sensor* other loops use. If asked to "fix" what it finds, route the fix to the source system, then re-run.

## What to watch for
- **Absent evidence is not a passing control.** `set_complete` runs first for exactly this reason: a set missing an artifact type would otherwise report clean because the controls reading it returned nothing.
- **A benign notice is not a failure.** A "job-cost entries not created" style line is normal for a ledger-only invoice; only a blocking marker (batch contention, aborted update) is a FAIL. Conflating them turns the control into noise.
- **PASS is not sign-off.** It means the implemented mechanical controls found nothing. Release, approval and posting stay with a person.
- Money is integer cents with exact `==` and no tolerance band anywhere. A non-integer amount is rejected, never coerced.
