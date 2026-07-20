# Sophon Finance Systems

This repository contains deterministic finance and tax engines built only on
seeded, fictional data. The public site lives in `docs/`; changes merged to
`main` are published through GitHub Pages.

## Environment

- Use Python 3.12 from `.venv/bin/python`.
- Recreate the environment with `uv venv --python 3.12 .venv`.
- Install local tools with
  `uv pip install --python .venv/bin/python -r requirements.txt "ruff>=0.6" "mypy>=1.11"`.
- Install the Cloudflare worker dependencies with
  `npm install --no-package-lock --prefix worker`.

## Repository layout

Each engine is self-contained and must be run or tested from its own directory:

- `monthly-close-automation`
- `cash-reconciliation`
- `cash-management`
- `tax-surplus-engine`
- `partnership-1065-automation`
- `audit-automation`
- `ai-validation-framework`
- `knowledge-brain-engine`
- `finance-atlas`

The marketing site is in `docs/`, generated reports are in `reports/`, and the
Sophie Cloudflare worker is in `worker/`.

## Verification

- Relevant engine: `cd <engine> && ../.venv/bin/python -m pytest -q`
- All engines, with aggregate results: `scripts/test-all.sh`
- Full property sweep: `SWEEP=1 scripts/test-all.sh` (only when explicitly requested)
- Lint check: `.venv/bin/ruff check <changed-files>`
- Format check: `.venv/bin/ruff format --check <changed-files>`

Prefer targeted tests while iterating, then run the affected engine's complete
suite before declaring work finished. Do not run the million-case sweep by
default.

## Engineering rules

- Never introduce real client, employer, bank, or taxpayer data.
- Preserve deterministic output: use integer cents, seeded generators, and
  byte-stable rendering.
- Engines refuse or escalate when a result cannot be proven; never invent a
  number to make a reconciliation pass.
- Validation paths remain read-only. Human approval gates must remain explicit.
- No material output may rest on a single model's unverified answer.
- Treat existing worktree changes as user-owned. Do not overwrite unrelated
  edits or files another active assistant may be changing.
- Keep `CLAUDE.md` and `.claude/` intact for Claude Code. Put Codex-wide,
  repository-durable instructions in this file.

