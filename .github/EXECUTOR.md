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

## Example commit series

```
refactor: extract fixture path helper (#12)
feat: exclude test-repos from primary module docs (#12)
test: assert fixture paths omitted from docgen (#12)
```

## Do not

- Leave changes unstaged or uncommitted.
- Combine unrelated changes in one commit.
- Select a named frontier model.
- Act on issues without `radar:approved`.

See AGENTS.md for model routing and repo conventions.
