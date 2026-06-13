#!/usr/bin/env bash
# Verify an executor branch is ready to push: commits ahead of base, clean tree, tests pass.
set -euo pipefail

ISSUE_NUM="${1:?usage: verify_executor_branch.sh ISSUE_NUM [BASE]}"
BASE="${2:-main}"

if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git status --porcelain)" ]; then
  echo "verify_executor_branch: uncommitted changes remain — agent must commit all work" >&2
  git status --short >&2
  exit 1
fi

ahead="$(git rev-list --count "${BASE}..HEAD" 2>/dev/null || echo 0)"
if [ "${ahead}" -lt 1 ]; then
  echo "verify_executor_branch: no commits on branch ahead of ${BASE}" >&2
  exit 1
fi

echo "verify_executor_branch: ${ahead} commit(s) ahead of ${BASE}"
git log --oneline "${BASE}..HEAD"

python3 run_tests.py
