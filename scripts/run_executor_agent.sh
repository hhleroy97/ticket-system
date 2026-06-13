#!/usr/bin/env bash
# Run cursor-agent for an approved issue with plan, snapshots, and issue comments.
set -euo pipefail

ISSUE_NUM="${1:?usage: run_executor_agent.sh ISSUE_NUM [BASE] [PROMPT]}"
BASE="${2:-main}"
PROMPT="${3:?prompt required as third argument}"
ISSUE_TITLE="${ISSUE_TITLE:-GitHub issue ${ISSUE_NUM}}"

chmod +x scripts/finalize_agent_run.py scripts/agent_plan.py scripts/post_agent_progress.py

python3 scripts/agent_plan.py "${ISSUE_NUM}" "${ISSUE_TITLE}" "${BASE}" || true

snapshot_loop() {
  while kill -0 "${AGENT_PID}" 2>/dev/null; do
    sleep 30
    python3 scripts/finalize_agent_run.py "${ISSUE_NUM}" "${BASE}" --snapshot || true
    python3 scripts/post_agent_progress.py "${ISSUE_NUM}" --snapshot || true
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
python3 scripts/post_agent_progress.py "${ISSUE_NUM}" --force || true
exit "${AGENT_EXIT}"
