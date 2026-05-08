---
name: coral-author
description: Authoring guides for adding new pieces to the CORAL package — a new TaskGrader subclass or builtin grader, a new agent runtime under `coral/agent/builtin/`, a new CLI command in `coral/cli/`, a new bundled skill or subagent template under `coral/template/`, or a new hook. Use when adding to CORAL itself, NOT when authoring a user-facing task or running agents.
---

# Authoring guides for CORAL internals

For day-to-day reproduce/debug loops see the sibling `coral-dev` skill. This one covers *adding new pieces* to the CORAL package.

## A new task grader (the common case)

Two paths. Pick by where the grader will live.

### Path A — packaged grader (recommended)

Use this when the grader has its own dependencies, lives outside the task dir, or you want it imported by `module.path:ClassName`.

1. Subclass `TaskGrader`:
   ```python
   # my_pkg/grader.py
   from coral.grader import TaskGrader

   class Grader(TaskGrader):
       def evaluate(self) -> float:
           # self.codebase_path  — agent's commit checked out detached
           # self.private_dir    — .coral/private/
           # self.args           — dict from task.yaml grader.args
           # return a float, or use self.score(value, explanation) /
           # self.fail(reason) for richer ScoreBundle output
           return 0.0
   ```
2. Wire it in `task.yaml`:
   ```yaml
   grader:
     entrypoint: "my_pkg.grader:Grader"
     setup: ["uv pip install -e ./grader"]   # runs once in .coral/private/grader_venv/
     timeout: 600
     direction: maximize
     args: { program_file: "initial_program.py" }
     parallel: { max_workers: 1 }            # bump only when grader is concurrency-safe
     max_pending_per_agent: 1
   ```
3. Validate: `uv run coral validate my-task`. The validator dry-runs the grader against `seed/` in a tempdir.

The daemon resolves the entrypoint via `coral/grader/loader.py` and runs each eval in a `SubprocessGrader` worker inside the venv, so import errors surface as a failed Attempt with `feedback` instead of crashing the daemon.

### Path B — legacy `eval/grader.py`

Still supported (emits `DeprecationWarning`). Drop a `Grader` class into `<task>/eval/grader.py` and leave `grader.entrypoint` empty. Runs in-process — fine for trivial graders, but no venv isolation.

### Built-in graders

`coral/grader/builtin/function_grader.py` wraps any `(codebase_path, tasks) -> Score | float | bool` callable. It is no longer wired through `task.yaml`; if you need it, ship a thin `TaskGrader` subclass that delegates to your function.

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
