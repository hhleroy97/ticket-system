#!/usr/bin/env bash
# Scoped cursor-agent run to resolve merge conflicts on a PR branch (CI/local).
set -euo pipefail

PR_NUM="${1:?usage: run_conflict_agent.sh PR_NUM HEAD_REF CONFLICT_CSV}"
HEAD_REF="${2:?HEAD_REF required}"
CONFLICT_CSV="${3:?comma-separated conflicted paths required}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ -z "${CURSOR_API_KEY:-}" ]; then
  echo "run_conflict_agent: CURSOR_API_KEY not set" >&2
  exit 1
fi

RUN_DIR="docs/agent-runs/pr-${PR_NUM}"
mkdir -p "${RUN_DIR}"

# Pretty list for the prompt
CONFLICT_LIST=""
IFS=',' read -ra FILES <<< "${CONFLICT_CSV}"
for f in "${FILES[@]}"; do
  f="${f#"${f%%[![:space:]]*}"}"
  f="${f%"${f##*[![:space:]]}"}"
  [ -n "$f" ] || continue
  CONFLICT_LIST+=$'\n- '"${f}"
done

PROMPT="Read .github/CONFLICT_RESOLVER.md and AGENTS.md.

Resolve merge conflicts on PR #${PR_NUM} (branch ${HEAD_REF}) after merging origin/main.
The repository is in an in-progress merge — finish it.

SCOPE — you may ONLY edit these conflicted files:${CONFLICT_LIST}

Rules:
- Remove all conflict markers; preserve PR intent AND correct main branch changes.
- Do NOT modify .github/workflows/ or any file outside the scope list.
- Do NOT refactor or add features beyond what the merge requires.
- Run python3 run_tests.py before committing; all tests must pass.
- Stage resolved files and complete the merge with ONE commit:
  chore: resolve merge conflicts with main (PR #${PR_NUM})"

echo "run_conflict_agent: PR #${PR_NUM} resolving: ${CONFLICT_CSV}"

python3 - <<PY
import json
from datetime import datetime, timezone
from pathlib import Path

run_dir = Path("${RUN_DIR}")
payload = {
    "pr_number": int("${PR_NUM}"),
    "branch": "${HEAD_REF}",
    "base": "main",
    "conflict_files": [f.strip() for f in "${CONFLICT_CSV}".split(",") if f.strip()],
    "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
}
(run_dir / "run.json").write_text(json.dumps(payload, indent=2))
PY

cursor-agent -p --force --model composer-2.5 "${PROMPT}"
AGENT_EXIT=$?

python3 - <<PY
import json
from datetime import datetime, timezone
from pathlib import Path

run_path = Path("${RUN_DIR}") / "run.json"
payload = json.loads(run_path.read_text())
payload["finished_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
payload["agent_exit"] = int("${AGENT_EXIT}")
run_path.write_text(json.dumps(payload, indent=2))
PY

exit "${AGENT_EXIT}"
