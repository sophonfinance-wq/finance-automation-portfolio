# LinkedIn Post Draft

I spent time hardening three finance automation patterns that matter in real accounting work:

- advisory prechecks before reconciliation
- dry-run annual schedule rollforward planning
- review-package assembly with human sign-off

The common thread is not "AI does the accounting." The common thread is controlled automation:

- dry-run by default
- copy, never delete
- local outputs only
- action logs for every file operation
- fictional fixtures in tests
- no client data in code, docs, tests, or public repos
- humans still decide what ships

After build-out, each new private tool suite was run through 1,100 clean repeated local test loops
on fictional fixtures. That is not a replacement for finance review; it is an engineering control
that makes the review process more dependable.

This is the discipline I am trying to show in my public portfolio: finance automation should be
deterministic, evidence-backed, conservative around source files, and safe to explain to audit,
tax, IT, and leadership.

Public portfolio:
https://github.com/sophonfinance-wq/finance-automation-portfolio
