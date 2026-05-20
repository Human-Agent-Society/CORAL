<!--
Thanks for contributing to CORAL! A few notes before you submit:

- See CONTRIBUTING.md for the full workflow.
- Keep PRs scoped. Unrelated cleanups belong in a separate PR.
- Make sure `uv run pytest tests/ -v` and `uv run ruff check .` pass locally.
- If you used an AI coding agent to author this PR, also read AGENTS.md.
-->

## Motivation

<!-- Why is this change needed? Link related issues (e.g. "Closes #123"). -->

## Changes

<!-- What does this PR actually do? High-level summary, not a file-by-file rehash. -->

## Test plan

<!--
How did you verify this works? Concrete commands + results, not "I tested it".
Examples:
  - `uv run pytest tests/grader/ -v` (all green)
  - Smoke-ran `coral start -c examples/mnist/task.yaml agents.count=1` to first finalized score
  - `coral validate examples/<new-task>/`
-->

## Affected areas

<!-- Tick what this PR touches so reviewers know where to focus. -->

- [ ] `coral/agent/` (runtime, manager, heartbeat, warmstart)
- [ ] `coral/grader/` (daemon, TaskGrader, subprocess grader, loader)
- [ ] `coral/hub/` (attempts, notes, skills, checkpoint)
- [ ] `coral/workspace/` (project setup, worktrees, grader env)
- [ ] `coral/cli/` (commands, helpers)
- [ ] `coral/hooks/` (post_commit / submit_eval)
- [ ] `coral/template/` (CORAL.md, bundled skills/agents)
- [ ] `coral/gateway/` (LiteLLM gateway)
- [ ] `coral/web/` (dashboard)
- [ ] `examples/` (new or modified task)
- [ ] `docs/` (docs site)
- [ ] CI / tooling / packaging
- [ ] Other: <!-- specify -->

## Checklist

- [ ] Title follows [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `refactor:`, ...).
- [ ] `uv run pytest tests/ -v` passes locally.
- [ ] `uv run ruff check .` and `uv run ruff format --check .` pass.
- [ ] Added or updated tests under `tests/` for any behavior change.
- [ ] Updated docs (`docs/content/`, README, or relevant skill under `.claude/skills/`) for any user-visible or contract change.
- [ ] If this changes a config field, CLI flag, hook, or runtime contract — noted the migration path in the PR description.
- [ ] **New `examples/<task>/`**: `coral validate <task>` succeeds and a smoke run produces at least one finalized score. No hidden answer keys committed under `seed/`.
- [ ] **AI-assisted PR**: a human author has read every changed line and can defend the design. See [AGENTS.md](../AGENTS.md).
