#!/usr/bin/env bash
# Fetch origin and fast-forward local main to origin/main.
#
# Usage:
#   ./hooks/sync-origin-main.sh           # sync when on main, or checkout main if worktree clean
#   ./hooks/sync-origin-main.sh --stay    # only sync if already on main
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "$ROOT"

STAY=false
for arg in "$@"; do
  case "$arg" in
    --stay) STAY=true ;;
  esac
done

if ! git remote get-url origin >/dev/null 2>&1; then
  exit 0
fi

git fetch origin

if ! git show-ref --verify --quiet refs/remotes/origin/main; then
  exit 0
fi

dirty() {
  ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git status --porcelain)" ]
}

branch="$(git rev-parse --abbrev-ref HEAD)"

if [ "$branch" != "main" ]; then
  if [ "$STAY" = true ]; then
    exit 0
  fi
  if dirty; then
    echo "sync-origin-main: on '$branch' with local changes; commit or stash before syncing main" >&2
    exit 1
  fi
  git checkout main
  branch="main"
fi

if [ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ]; then
  echo "sync-origin-main: main already matches origin/main"
  exit 0
fi

if git merge-base --is-ancestor HEAD origin/main 2>/dev/null; then
  if dirty; then
    git pull --ff-only --autostash origin main
  else
    git merge --ff-only origin/main
  fi
  echo "sync-origin-main: fast-forwarded main to origin/main ($(git rev-parse --short HEAD))"
  exit 0
fi

# Local and remote both moved (e.g. merged PRs on GitHub + local commits): rebase onto origin.
if dirty; then
  git pull --rebase --autostash origin main
else
  git pull --rebase origin main
fi
echo "sync-origin-main: rebased main onto origin/main ($(git rev-parse --short HEAD))"
