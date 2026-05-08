---
name: coral-extend
description: Add a new component to the CORAL framework itself — a new agent runtime under `coral/agent/builtin/` (claude_code/codex/cursor_agent style), a new CLI command in `coral/cli/`, a new bundled skill or subagent template under `coral/template/skills/` or `coral/template/agents/`, a new hook in `coral/hooks/`, a new field in `coral/config.py`, or a framework-level extension to the grader stack under `coral/grader/`. NOT for writing a per-task grader or adding an example task — use `coral-new-task` for that. NOT for debugging existing code — use `coral-debug`.
---

# Extending the CORAL framework

For day-to-day debug / reproduce loops see the sibling `coral-debug` skill. For creating a new `examples/<task>/` (seed + task.yaml + grader package) see `coral-new-task`. This skill covers *adding new components to the CORAL package itself*.

## Extending the grader infrastructure

If you're writing a grader for a specific task, use `coral-new-task`. This section is only for changes to the grader **framework** under `coral/grader/`:

- New helpers on `TaskGrader` (`coral/grader/task_grader.py`) — make sure they're useful to multiple existing example graders before adding.
- New `GraderInterface` implementations (`coral/grader/protocol.py` / `base.py`) — the bar is high; the existing protocol covers everything we currently need.
- Daemon-side changes (`coral/grader/daemon.py`) — concurrency, queue caps, worktree isolation, retry policy. Cover with `tests/test_grader_daemon.py`.
- Built-in graders under `coral/grader/builtin/` — `function_grader.py` is the only one today; not wired through `task.yaml`. New built-ins should justify why a `TaskGrader` subclass per task isn't enough.

## A new agent runtime

Adding a new runtime (e.g. another coding-agent CLI) means three small files plus a registry entry.

1. Create `coral/agent/builtin/<name>.py` and subclass `AgentRuntime` (`coral/agent/runtime.py`). Existing runtimes are the canonical reference — `claude_code.py` is the most complete; `codex.py` and `cursor_agent.py` are smaller and easier to mimic.
2. Register the runtime in `coral/agent/registry.py`:
   ```python
   _RUNTIMES["my_runtime"] = MyRuntime
   _ALIASES["mine"] = "my_runtime"
   _DEFAULT_MODELS["my_runtime"] = "default-model-id"
   ```
3. Decide the runtime's native shared-state directory name (`.claude` for Claude Code, `.codex` for Codex, etc.). The worktree symlink uses this; pass it through `shared_dir` so `generate_coral_md(...)` renders the right paths.
4. If the runtime needs special config plumbing (e.g. `cursor_agent.json`, `opencode.json`, gateway port), follow the `opencode` pattern: emit a per-agent config file inside the worktree at startup.
5. Add a smoke test in `tests/test_<runtime>.py` modeled on `tests/test_cursor_agent.py`.

Reference recent additions: PR #79 (cursor_agent), commit `f6f266e` (codex web_search config fix).

## A new CLI command

CLI is an old-school argparse single-file dispatcher.

1. Add a parser block in `coral/cli/__init__.py::main()`. Match the existing style — `_HelpOnErrorParser`, an epilog with `Examples:`, `_CommandHelpFormatter`. Add the new command name to `_VISIBLE_COMMANDS` so "did you mean?" suggestions work.
2. Implement `cmd_<name>(args: argparse.Namespace) -> None` in the most-fitting module under `coral/cli/`:
   - `start.py` — agent lifecycle (start/resume/stop/status)
   - `query.py` — read-only inspection (log/show/notes/skills/runs)
   - `eval.py` — agent-side commands that mutate the worktree (eval/wait/diff/revert/checkout)
   - `heartbeat.py` — heartbeat configuration
   - `ui.py` — dashboard
   - `author.py` — `init` / `validate`
   Create a new module if none of those fit; keep imports lazy so `coral --help` stays fast.
3. Wire the function into the `commands = {...}` dict at the bottom of `main()`.
4. If your command operates on a specific run, accept `--task` / `--run` via `_add_run_args(parser)` and resolve with `coral.cli._helpers.find_coral_dir`.
5. Add an example to `CLAUDE.md`'s Commands section.

## A new bundled skill or subagent template

These ship inside the package and are seeded into every run's `.coral/public/skills/` (or `agents/`) by `coral/workspace/project.py`.

- **Skill** — create `coral/template/skills/<name>/SKILL.md` with frontmatter `name` and `description`. Include `scripts/` and `references/` subdirs as needed; existing examples are `deep-research`, `organize-files`, `skill-creator`.
- **Subagent** — create `coral/template/agents/<name>.md` (single markdown file). Existing examples are `deep-researcher` and `librarian`.
- Add a test in `tests/test_template.py` if the rendering pulls in new template variables.

The seed copy is one-shot per run (`if not dst.exists()`), so iterating on template content during development means deleting `<run_dir>/.coral/public/skills/<name>/` and re-running `coral start`, or just editing the destination directly for that run.

## A new hook

Right now there's only `coral/hooks/post_commit.py`. If you add another hook:
- Define a clear single entrypoint function (model on `submit_eval`).
- Make it pure-function over `coral_dir` + agent_id where possible.
- Atomic writes to `.coral/public/` only; never write to a worktree from a hook.
- Add coverage to `tests/test_hooks.py`.

## Configuration changes

`coral/config.py` is dataclass-based and merged via OmegaConf. When adding a new field:

1. Add it to the right dataclass (`AgentConfig`, `GraderConfig`, ...) with a sensible default.
2. If it deserves runtime validation, add it to the `__post_init__` of that dataclass.
3. Cover the new field in `tests/test_config.py`.
4. Update `examples/<task>/task.yaml` only if the field is task-author facing — internal knobs should stay defaulted.
5. Mention it in `CLAUDE.md` if it changes user-visible behavior; otherwise leave the docs alone (CLAUDE.md describes invariants, not every flag).

## Don't forget

- **Lint + test before pushing**: `uv run ruff check . && uv run ruff format . && uv run pytest tests/ -v`.
- **Backward compatibility for run dirs.** People resume old runs. Anything that reads from `.coral/public/` must tolerate missing files (return defaults), not crash.
- **No agent-side `git`.** All commits go through `coral eval` → `submit_eval`. Don't add helpers that shell out to git from agent context.
