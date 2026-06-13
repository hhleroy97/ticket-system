# Executor instructions (headless CI)

You are implementing an approved GitHub issue on branch `issue-<N>`. The workflow
**does not** squash your work into one commit — you must commit logically yourself.

## Commit rules

1. **One commit per logical change** — separate implementation, tests, and docs.
2. Use **conventional prefixes**: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`.
3. Reference the issue in each subject or footer: `(#<N>)` or `fix: #<N> …`.
4. **Run `python3 run_tests.py`** before your last commit; all tests must pass.
5. **Commit everything** — uncommitted files cause the workflow to fail (no auto-squash).
6. Keep each diff minimal and focused on the issue.
7. Do **not** run `scan.py` unless the issue requires it; `run_tests.py` may refresh `docs/index.*` ephemerally (CI restores them if uncommitted).
8. The CI wrapper logs progress to `docs/agent-runs/issue-<N>/run.json` (snapshots every 30s during the run).

## Example commit series

```
refactor: extract fixture path helper (#12)
feat: exclude test-repos from primary module docs (#12)
test: assert fixture paths omitted from docgen (#12)
```

## Do not

- Leave changes unstaged or uncommitted.
- Combine unrelated changes in one commit.
- **Modify `.github/workflows/`** — `GITHUB_TOKEN` cannot push workflow file changes; verify will fail. Open CI changes in a separate maintainer PR using a PAT with `workflow` scope.
- Select a named frontier model.
- Act on issues without `radar:approved`.

See AGENTS.md for model routing and repo conventions.
