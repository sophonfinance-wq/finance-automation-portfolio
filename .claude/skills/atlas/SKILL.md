---
name: atlas
description: "Generate the Finance Operations Atlas: a deterministic single-file HTML map of a finance department. Use when asked to build or update the atlas artifact."
---
# Finance Operations Atlas

Packages `atlas_data` + `generate` in `finance-atlas/`.

## Commands (run from `finance-atlas/`)
```bash
python generate.py            # writes out/finance-operations-atlas.html (deterministic, single file)
python -m pytest -q           # 928 tests incl. parametrized deny-list confidentiality linter
```
The test suite lints every shipped file against a hashed deny-list — never add real client/employer terms anywhere in this repo.
