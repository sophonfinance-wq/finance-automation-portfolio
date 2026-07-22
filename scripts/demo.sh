#!/usr/bin/env bash
# One-command demo of the finance automation portfolio.
# Everything below runs on FICTIONAL, seeded data — no real client or employer data.
#
#   Usage:  bash scripts/demo.sh
#
# Tip: open this repo in a GitHub Codespace and run this script in the browser terminal.

set +e
export PYTHONIOENCODING=utf-8
cd "$(dirname "$0")/.." || exit 1

say() { printf "\n\033[1;36m== %s ==\033[0m\n" "$1"; }

say "Test suite — 69,911 tests pin every engine's behavior"
python -m pytest -q

say "Month-End Close Engine — recurring JEs + schedule-to-GL tie-outs"
( cd monthly-close-automation && python run.py --period 2026-03 --out output )

say "Cash & Debt Reconciliation — materiality flagging + evidence log"
( cd cash-reconciliation && python run.py )

say "Tax Surplus / ACB — Canadian foreign-affiliate surplus pools (T1134)"
( cd tax-surplus-engine && python run.py --start 2021 --end 2024 --out out )

say "Partnership 1065 + IRC section 704(c) built-in gain"
( cd partnership-1065-automation && python run.py --out output && python run.py --section704c --out output )

say "Validation Engine — read-only checks (a FAIL verdict on planted defects is the intended demo outcome)"
( cd audit-automation && python run.py )

say "Accounts Payable — read-only payables controls (posting integrity, payment release gates, duty segregation)"
( cd accounts-payable-automation && python run.py )

say "Triangulate — AI separation of duties (preparer / reviewer / specialist / audit / human gate)"
( cd ai-validation-framework && python run.py --sample clean --output output )

say "Knowledge Brain — cite a prior decision word-for-word (verbatim + timestamp)"
( cd knowledge-brain-engine && python -m brain_engine --cite "return of capital beyond basis" )

say "Knowledge Brain — turn a review meeting into an apply-ready, cited fix prompt"
( cd knowledge-brain-engine && python -m brain_engine remediate "Surplus Workpaper Review — Reviewer Corrections" )

say "Done — every output above was generated from fictional, seeded data."
