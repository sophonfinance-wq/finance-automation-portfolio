#!/usr/bin/env bash

# Run every engine the same way CI does, while allowing all packages to finish
# so a failure in one cannot hide the result of another.

set -u

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="$repo_root/.venv/bin/python"

engines=(
  monthly-close-automation
  cash-reconciliation
  cash-management
  tax-surplus-engine
  partnership-1065-automation
  audit-automation
  ai-validation-framework
  knowledge-brain-engine
  finance-atlas
)

if [[ ! -x "$python_bin" ]]; then
  echo "Python environment not found at $python_bin"
  echo "Run: uv venv --python 3.12 .venv"
  exit 2
fi

overall=0
failed=()

for engine in "${engines[@]}"; do
  echo
  echo "==> Testing $engine"
  if ! (cd "$repo_root/$engine" && "$python_bin" -m pytest -q); then
    overall=1
    failed+=("$engine")
  fi
done

echo
if ((overall == 0)); then
  echo "All engines passed."
else
  echo "Failed engines: ${failed[*]}"
fi

exit "$overall"

