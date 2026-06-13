# AGENTS.md — repo-intel

Rules for any Cursor agent working in this repo (editor sessions and headless CLI runs both
read this file).

## Project

A greenfield repository-intelligence devops tool: scan a target git repo, visualize its
state and dependency graph, keep docs current, run a research loop, and draft/execute
tickets through a human-gated pipeline. See HANDOFF.md for the full spec and build plan.

## Model routing (cost discipline — important)

- **Code execution** (editing files, running tests, applying changes): use **Composer 2.5**.
- **Research, synthesis, ticket drafting** (general reasoning, not coding): use **Auto**.
- **Never select a named frontier model** (Claude/GPT/Gemini) in any automated path — that
  bills the metered API credit pool. Auto and Composer 2.5 draw the included subscription
  pool. For unattended runs, prefer the standard Composer tier over Fast.

## Conventions

- The scanner (`scan.py`) is deterministic and must never call an LLM. Keep it stdlib-only;
  do not add dependencies without a clear reason.
- `docs/index.json` is the single source of truth and a stable contract. Additive changes
  only; bump `schema_version` for breaking changes.
- Keep diffs minimal and focused on the issue at hand.
- Prefer opening a PR over committing to main directly.
- Don't act on a GitHub issue unless it carries the `radar:approved` label.

## Run

```bash
TARGET_REPO=/path/to/repo python3 scan.py
open docs/dashboard.html
```
