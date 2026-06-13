#!/usr/bin/env bash
# Run cursor-agent for an approved issue with periodic progress snapshots.
set -euo pipefail

ISSUE_NUM="${1:?usage: run_executor_agent.sh ISSUE_NUM [BASE]}"
BASE="${2:-main}"
PROMPT="${3:?prompt required as third argument}"

chmod +x scripts/finalize_agent_run.py

snapshot_loop() {
  while kill -0 "${AGENT_PID}" 2>/dev/null; do
    sleep 30
    python3 scripts/finalize_agent_run.py "${ISSUE_NUM}" "${BASE}" --snapshot || true
  done
}

python3 scripts/finalize_agent_run.py "${ISSUE_NUM}" "${BASE}" --snapshot || true

cursor-agent -p --force --model composer-2.5 "${PROMPT}" &
AGENT_PID=$!
snapshot_loop &
SNAP_PID=$!

wait "${AGENT_PID}"
AGENT_EXIT=$?

kill "${SNAP_PID}" 2>/dev/null || true
wait "${SNAP_PID}" 2>/dev/null || true

python3 scripts/finalize_agent_run.py "${ISSUE_NUM}" "${BASE}"
exit "${AGENT_EXIT}"
