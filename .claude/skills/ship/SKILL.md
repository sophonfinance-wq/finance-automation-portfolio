---
name: ship
description: "Ship changes in this repo: branch, test like CI, commit, push, draft PR, wait for CI, merge. Use for any release of work to main."
---
# Ship-It Workflow (this repo)

1. **Branch**: work on the designated `claude/...` branch. If its PR already merged, restart it: `git fetch origin main && git checkout -B <branch> origin/main`.
2. **Test like CI** (CI runs pytest per package, so a root pytest is NOT equivalent):
   ```bash
   for d in monthly-close-automation cash-reconciliation cash-management tax-surplus-engine partnership-1065-automation audit-automation ai-validation-framework knowledge-brain-engine accounts-payable-automation finance-atlas site-datasheets; do (cd $d && python -m pytest -q); done
   ```
   `SWEEP=1` enables the ~1.26M-case grids (skip for normal ships). Install deps once: `pip install -r requirements.txt`.
3. **Commit**: imperative subject, body explains the why; never mention model IDs in artifacts.
4. **Push**: `git push -u origin <branch>` (retry on network errors with backoff).
5. **PR**: draft, mirror `.github/pull_request_template.md` (Summary + Review checklist — tests/CI, coverage, deterministic core, human-gated, no real data, docs).
6. **CI**: workflow `ci.yml`, single `test` job, ~45-90s. Poll check runs; merge only on green.
7. **Merge** (only with the user's standing approval): undraft, merge-commit method, then confirm the merged webhook closed the watch. GitHub Pages redeploys docs/ automatically after merge.
8. Report outcomes faithfully: verdicts, test counts, what was quarantined/skipped.
