---
name: tax-1065
description: "Run the Partnership 1065 engine: book-to-tax bridge, Schedule K/K-1 mapping, section 704(c) built-in gain, review checks. Use for partnership tax demos."
---
# Partnership 1065 Engine

Package `partnership_tax` in `partnership-1065-automation/`.

## Commands (run from `partnership-1065-automation/`)
```bash
python -m partnership_tax                    # full package: workpapers, 1065 preview JSON, K-1s, review checks
python -m partnership_tax --section704c      # IRC 704(c) built-in gain module (ceiling rule)
python -m partnership_tax --no-xlsx --out output
python -m pytest -q                          # 1,605 tests
```
Outputs land in `output/`: `tax_workpapers.md`, `form_1065_preview.json`, `section704c_k1_*.md`, `review_checks.md`. Review checks must all be OK for READY FOR REVIEW status.
