# Conflict resolver instructions (scoped executor)

You are resolving **merge conflicts only** after `origin/main` was merged into an open PR
branch. The conflict bot left the repo in an in-progress merge; your job is to finish it.

## Scope (strict)

1. **Only edit files listed in the prompt** — conflicted paths, plus regeneratable docs if
   the prompt asks you to refresh them after resolution.
2. **Do not** implement new features, refactor unrelated code, or touch files outside scope.
3. **Do not** modify `.github/workflows/` — abort and leave conflict markers if workflows
   conflict; maintainers must fix those manually.
4. Preserve **both** sides' intent: the PR branch's changes and correct updates from `main`.
5. Remove **all** conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`).

## Process

1. Read conflicted files and understand PR vs `main` changes (`git log`, `git diff`).
2. Resolve markers; keep tests and behavior consistent with merged intent.
3. Run `python3 run_tests.py` — all tests must pass.
4. `git add` only scoped files (and regenerated docs if applicable).
5. Complete the merge with **one commit**:
   `chore: resolve merge conflicts with main (PR #<N>)`

## Do not

- Run `scan.py` unless resolving conflicts in `docs/index.json` / dashboard artifacts.
- Add dependencies or change CI workflows.
- Select a named frontier model (use Composer 2.5).
- Leave the merge unfinished or conflict markers in the tree.

See AGENTS.md for repo conventions.
