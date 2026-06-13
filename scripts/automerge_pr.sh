#!/usr/bin/env bash
# Merge a PR when it is safe and all checks passed. Idempotent.
set -euo pipefail

PR="${1:?usage: automerge_pr.sh PR_NUMBER}"
REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY required}"

state=$(gh pr view "$PR" --repo "$REPO" --json state,mergeable,statusCheckRollup,headRefName,baseRefName \
  --jq '[.state, .mergeable, .headRefName] | @tsv')
read -r pr_state mergeable head_ref <<<"$state"

if [ "$pr_state" != "OPEN" ]; then
  echo "automerge: PR #$PR not open ($pr_state)"
  exit 0
fi

if [ "$mergeable" != "MERGEABLE" ]; then
  echo "automerge: PR #$PR not mergeable ($mergeable)"
  exit 0
fi

# All required checks must succeed (ignore skipped).
pending=$(gh pr view "$PR" --repo "$REPO" --json statusCheckRollup \
  --jq '[.statusCheckRollup[]? | select(.state != "SUCCESS" and .state != "SKIPPED")] | length')
if [ "${pending:-0}" != "0" ]; then
  echo "automerge: PR #$PR checks not all green"
  exit 0
fi

mapfile -t files < <(gh pr diff "$PR" --repo "$REPO" --name-only)
if [ "${#files[@]}" -eq 0 ]; then
  echo "automerge: PR #$PR has no files"
  exit 0
fi

is_docs_only=true
is_low_risk=true
for f in "${files[@]}"; do
  case "$f" in
    docs/*|test-repos/*/docs/*) ;;
    *) is_docs_only=false ;;
  esac
done
for f in "${files[@]}"; do
  if [[ "$f" == .github/workflows/* ]]; then
    is_low_risk=false
    break
  fi
  if [[ "$f" == docs/* || "$f" == tests/* || "$f" == test-repos/* ]]; then
    continue
  fi
  if [[ "$f" == *.md ]]; then
    continue
  fi
  case "$f" in
    radar_report.py|draft_issues.py|scripts/radar_ticket_lib.py|scripts/create_radar_issues.py|scripts/automerge_pr.sh|scripts/verify_executor_branch.sh)
      continue
      ;;
  esac
  is_low_risk=false
  break
done

auto_merge=false
if [ "$is_docs_only" = true ] && [[ "$head_ref" == bot/* ]]; then
  auto_merge=true
  reason="bot docs PR"
elif [[ "$head_ref" == issue-* ]] && [ "$is_low_risk" = true ]; then
  issue_num="${head_ref#issue-}"
  if gh issue view "$issue_num" --repo "$REPO" --json labels --jq '.labels[].name' 2>/dev/null | grep -qx 'radar:auto-merge'; then
    auto_merge=true
    reason="low-risk executor PR (issue #$issue_num)"
  fi
fi

if [ "$auto_merge" != true ]; then
  echo "automerge: PR #$PR not eligible ($head_ref)"
  exit 0
fi

echo "automerge: merging PR #$PR ($reason)"
gh pr merge "$PR" --repo "$REPO" --merge --delete-branch
echo "automerge: merged PR #$PR"
