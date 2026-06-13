#!/usr/bin/env bash
# Verify an executor branch is ready to push: commits ahead of base, clean tree, tests pass.
set -euo pipefail

ISSUE_NUM="${1:?usage: verify_executor_branch.sh ISSUE_NUM [BASE]}"
BASE="${2:-main}"

# Scan tests rewrite docs/index.* and docs/dashboard.html ephemerally; drop if not part of the issue.
restore_incidental_scan_artifacts() {
  local path
  for path in docs/index.json docs/index.db docs/dashboard.html; do
    if ! git diff --name-only "${BASE}..HEAD" -- "${path}" | grep -q .; then
      git restore --staged --worktree "${path}" 2>/dev/null || true
    fi
  done
}

assert_clean_tree() {
  if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git status --porcelain)" ]; then
    echo "verify_executor_branch: uncommitted changes remain — agent must commit all work" >&2
    git status --short >&2
    exit 1
  fi
}

restore_incidental_scan_artifacts
assert_clean_tree

ahead="$(git rev-list --count "${BASE}..HEAD" 2>/dev/null || echo 0)"
if [ "${ahead}" -lt 1 ]; then
  echo "verify_executor_branch: no commits on branch ahead of ${BASE}" >&2
  exit 1
fi

echo "verify_executor_branch: ${ahead} commit(s) ahead of ${BASE}"
git log --oneline "${BASE}..HEAD"

if git diff --name-only "${BASE}..HEAD" | grep -q '^\.github/workflows/'; then
  echo "verify_executor_branch: changes under .github/workflows/ are blocked for GITHUB_TOKEN pushes." >&2
  echo "Implement CI changes in a separate maintainer PR (PAT required). Revert workflow edits on this branch." >&2
  git diff --name-only "${BASE}..HEAD" | grep '^\.github/workflows/' >&2
  exit 1
fi

python3 run_tests.py

restore_incidental_scan_artifacts
assert_clean_tree
