---
name: ship
description: "Ship changes in this repo: branch, test like CI, commit, push, draft PR, wait for CI, merge. Use for any release of work to main."
---
# Ship-It Workflow (this repo)

1. **Branch**: work on the designated `claude/...` branch. If its PR already merged, restart it: `git fetch origin main && git checkout -B <branch> origin/main`.
2. **Test like CI** (CI runs pytest per package, so a root pytest is NOT equivalent). Derive the
   package list from `ci.yml` rather than hardcoding it — a second copy silently goes stale every
   time an engine lands, and then "test like CI" quietly stops testing like CI:
   ```bash
   for d in $(sed -n 's/.*for dir in \(.*\); do.*/\1/p' .github/workflows/ci.yml | head -1); do
     (cd "$d" && python -m pytest -q) || echo "FAILED: $d"
   done
   ```
   `SWEEP=1` enables the ~1.65M-case grids (skip for normal ships). Install deps once: `pip install -r requirements.txt`.
   Also confirm the count gate before pushing — CI's `test-count.yml` hard-asserts it and only runs on
   `main`, so a drift here fails *after* merge:
   ```bash
   python -m pytest --collect-only -q -m "not site_tooling" | tail -1   # must equal counts.json portfolio_curated
   ```
3. **Commit**: imperative subject, body explains the why; never mention model IDs in artifacts.
4. **Push**: `git push -u origin <branch>` (retry on network errors with backoff).
5. **PR**: draft, mirror `.github/pull_request_template.md` (Summary + Review checklist — tests/CI, coverage, deterministic core, human-gated, no real data, docs).
6. **CI**: workflow `ci.yml`, single `test` job, ~45-90s. Poll check runs; merge only on green.
7. **Merge** (only with the user's standing approval): undraft, merge-commit method, then confirm the merged webhook closed the watch. GitHub Pages redeploys docs/ automatically after merge.
8. Report outcomes faithfully: verdicts, test counts, what was quarantined/skipped.
