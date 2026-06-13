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
- Don't act on a GitHub issue unless it carries the `radar:approved` label.

## Git workflow (human and editor agents)

**Do not push directly to `main`.** All code, workflow, and doc changes go through a PR so
`test.yml` runs on the branch before merge.

1. Branch from updated `main`: `git checkout main && ./hooks/sync-origin-main.sh`
2. Work on a named branch: `feat/…`, `fix/…`, `docs/…`, or `issue-<N>` for executor tickets
3. **Logical commits** as you go (feat / fix / test / docs — separate concerns)
4. Push the branch and open a PR: `git push -u origin HEAD && gh pr create …`
5. Wait for CI green, then merge (**Rebase and merge** or **Merge commit** — not squash)

**Exceptions (automated bots only):** scheduled RADAR and scan/docs jobs may use
`scripts/push_to_main.sh` to avoid workflow-approval gates on bot PRs. Executor work always
opens a PR on `issue-<N>`. Maintainers never bypass PRs for hand-edited changes.

## Executor (approved issues, headless CI)

When implementing an approved issue on branch `issue-<N>`:

- Read `.github/EXECUTOR.md` for the full checklist.
- **One commit per logical change** — do not rely on CI to squash; uncommitted work fails the workflow.
- Use conventional prefixes (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`) and reference `(#N)` in messages.
- Run `python3 run_tests.py` before the final commit; all tests must pass.
- Prefer **Rebase and merge** or **Merge commit** on GitHub — avoid squash if preserving commit history.
- Never push directly to `main`; open a PR and let `test.yml` run first (see **Git workflow** above).

## Run

```bash
TARGET_REPO=/path/to/repo python3 scan.py
open docs/dashboard.html
```
