#!/usr/bin/env bash
# Fetch origin and fast-forward local main to origin/main when possible.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "$ROOT"

if ! git remote get-url origin >/dev/null 2>&1; then
  exit 0
fi

git fetch origin

branch="$(git rev-parse --abbrev-ref HEAD)"
if [ "$branch" != "main" ]; then
  exit 0
fi

if ! git show-ref --verify --quiet refs/remotes/origin/main; then
  exit 0
fi

if git merge-base --is-ancestor HEAD origin/main 2>/dev/null; then
  git merge --ff-only origin/main
elif [ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ]; then
  exit 0
else
  echo "sync-origin-main: main diverged from origin/main; skipping fast-forward" >&2
  exit 0
fi
