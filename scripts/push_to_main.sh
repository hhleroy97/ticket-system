#!/usr/bin/env bash
# Commit selected paths and push to main (used by bot workflows — no PR, no workflow approval gate).
set -euo pipefail

MESSAGE="${1:?usage: push_to_main.sh \"commit message\" [path ...]}"
shift
PATHS=("${@:-docs/}")

git config user.name "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"

git add "${PATHS[@]}"
if git diff --cached --quiet; then
  echo "push_to_main: nothing to commit"
  exit 0
fi

git commit -m "$MESSAGE"
git push origin HEAD:main
echo "push_to_main: pushed to main"
