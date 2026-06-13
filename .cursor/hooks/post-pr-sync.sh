#!/usr/bin/env bash
# Cursor hook: sync local main with origin after PR merge/close or checkout main.
set -euo pipefail

input="$(cat)"
command="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("command",""))' <<<"$input" 2>/dev/null || true)"

if echo "$command" | grep -qE 'gh pr (merge|close|delete)|git checkout main|git switch main'; then
  root="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
  "$root/hooks/sync-origin-main.sh" || true
fi

echo '{}'
exit 0
