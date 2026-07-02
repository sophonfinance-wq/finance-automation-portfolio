# Contributing

This is a **portfolio repository** — a set of self-contained finance and tax automation systems
built to be *read, run, and reviewed*. It is not seeking feature contributions, but the guidance
below lets anyone evaluate it end to end, and thoughtful suggestions are welcome via issues.

## Run it locally

- Python **3.12+**
- `pip install -r requirements.txt`
- Each system is self-contained under its own directory, with a `run.py` and a `samples/` set of
  **fully synthetic** inputs.

## Verify it

- Full suite: `pytest -q` from the repo root, or `pytest` inside any system directory.
- CI (GitHub Actions, `.github/workflows/ci.yml`) runs the same suite on every push and pull request.
- Prefer zero setup? Open in **Codespaces** — the `.devcontainer/` is preconfigured.

## Standards

- **No real data, ever.** Every input, name, and figure is invented. See [SECURITY.md](SECURITY.md).
- **Deterministic core, gated AI.** Business logic is deterministic and tested; any LLM-assisted
  step is advisory and human-gated.
- **Small, reviewable changes.** Conventional-style commit messages; tests accompany logic changes.

## Suggestions

Open an issue describing the improvement. For anything security-related, follow
[SECURITY.md](SECURITY.md) and email rather than filing a public issue.
