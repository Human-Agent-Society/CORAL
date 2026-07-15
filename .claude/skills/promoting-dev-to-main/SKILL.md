---
name: promoting-dev-to-main
description: Use when preparing, reviewing, resolving conflicts for, or merging a CORAL release pull request from the long-lived dev branch into main.
---

# Promoting dev to main

## Core rule

Merge `dev → main` release PRs with a **merge commit**. Never squash or rebase
these promotions.

Ordinary contribution PRs still target `dev` and may be squash-merged. The
release promotion is the exception because `main` must retain `dev` in its
ancestry. Squashing a promotion makes the next release re-present old commits
and can create large false conflicts.

## Workflow

1. Confirm the PR is exactly `base=main`, `head=dev` and no duplicate release
   PR is open.
2. Review `main..dev`, required CI, and deployment checks.
3. In GitHub, open the merge-method dropdown and choose **Create a merge
   commit**. With the CLI, use:

   ```bash
   gh pr merge <number> --repo Human-Agent-Society/CORAL --merge
   ```

4. Keep the long-lived `dev` branch. Do not delete or force-push it.
5. Fetch both branches and verify the released `dev` tip is an ancestor of
   `main`:

   ```bash
   git fetch origin dev main
   git merge-base --is-ancestor origin/dev origin/main
   ```

   Exit status `0` is required.
6. Confirm post-merge CI, release automation, deployments, and production
   smoke checks.

## If GitHub reports conflicts

Do not force-rebase the shared `dev` branch. First inspect the topology and
reproduce conflicts with `git merge-tree`.

If an earlier release was squash-merged, `main` may have the same tree as an
earlier `dev` commit without sharing its ancestry. Verify tree equivalence
before choosing a repair. Prefer merging `main` back into `dev` and pushing
normally; use an ancestry-only `ours` merge only when exact tree equality
proves `main` contains no unique content to preserve.

## Red flags

- GitHub's primary button says **Squash and merge**.
- A command uses `--squash`, `--rebase`, or a force-push.
- The release workflow proposes deleting `dev`.
- Conflict resolution starts before checking commit topology and tree equality.

Stop when any red flag appears and return to the workflow above.

## Quick reference

| PR | Allowed merge method |
|---|---|
| Feature/fix/docs branch → `dev` | Repository default; usually squash |
| `dev` → `main` release promotion | Merge commit only |
