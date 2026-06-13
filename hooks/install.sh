#!/usr/bin/env bash
# One-time setup: point git at repo hooks (pre-commit, post-merge, post-checkout).
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
git config core.hooksPath hooks
echo "core.hooksPath set to hooks/"
echo "Hooks: pre-commit, post-merge, post-checkout"
echo "Run ./hooks/sync-origin-main.sh anytime to fetch and fast-forward main."
