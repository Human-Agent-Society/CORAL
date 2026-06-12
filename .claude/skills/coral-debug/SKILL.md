---
name: coral-debug
description: Verify and debug changes to CORAL itself — smallest reproduce loop per area (grader / daemon / CLI / hooks / manager / workspace / hub / template / config / web), where to look when something breaks (hung graders, agent restart loops, stalled agents, missing heartbeat actions, corrupted shared state, broken worktree symlinks, grader import errors, wrong-task resume), how to inspect a live or finished run under `.coral/public/`, and the canonical lint/test commands. Use when editing code under `coral/` or chasing a CORAL bug, NOT when adding a new task or extending the framework.
---

# CORAL debug & change-verification workflows

This skill is for people (and Claude Code) hacking on the CORAL package itself, not for users authoring a task. For authoring guides see the siblings:
- `coral-new-task` — creating a new `examples/<task>/` (seed + task.yaml + grader)
- `coral-extend` — extending CORAL itself (new runtime, new CLI command, new bundled skill, ...)

## Reproduce loops

Pick the smallest one that exercises your change.

| Editing... | Fastest reproduce |
|---|---|
| `coral/grader/{task_grader,loader,subprocess_grader}.py` or a builtin grader | `uv run coral validate examples/circle_packing` (or any example with a packaged grader) |
| `coral/grader/daemon.py` (parallel grading, queueing, worktree isolation) | `uv run pytest tests/test_grader_daemon.py -v` |
| `coral/grader/{base,protocol}.py` | `uv run pytest tests/test_grader.py tests/test_subprocess_grader.py -v` |
| `coral/cli/*.py` (argparse, dispatch, output formatting) | Run the command directly: `uv run coral log --help`, `uv run coral status`, etc. against a `latest` run under `examples/<task>/results/` |
| `coral/hooks/post_commit.py` (`submit_eval`) | `uv run pytest tests/test_hooks.py -v`, then end-to-end via `coral start -c task.yaml agents.count=1` and watch `.coral/public/attempts/` |
| `coral/agent/manager.py`, `state.py`, `exit_classifier.py` | `uv run pytest tests/test_manager_reliability.py tests/test_manager_seen_attempts.py -v` |
| `coral/agent/builtin/*.py` (a runtime) | `uv run pytest tests/test_<runtime>.py` if it exists, then `coral start -c task.yaml agents.runtime=<name> agents.count=1` |
| `coral/workspace/{project,worktree,repo,grader_env}.py` | `uv run pytest tests/test_workspace.py tests/test_grader_env.py -v` |
| `coral/hub/{attempts,notes,skills,checkpoint,heartbeat}.py` | `uv run pytest tests/test_hub.py tests/test_checkpoint.py tests/test_heartbeat.py -v` |
| `coral/template/coral_md.py` or templates | `uv run pytest tests/test_template.py -v` |
| `coral/config.py` | `uv run pytest tests/test_config.py -v` |
| `coral/web/*` (dashboard) | `uv run coral ui` against any existing run; reload the browser after edits |

End-to-end smoke (slow but exercises the whole pipeline):
```bash
uv run coral start -c examples/circle_packing/task.yaml agents.count=1 run.session=local
# Wait for one eval to land in .coral/public/attempts/, then:
uv run coral stop
```

## Where to look when X breaks

| Symptom | First place to look |
|---|---|
| Grader hangs / pending attempts pile up | `.coral/public/grader_daemon.pid` (is daemon alive?), `.coral/public/grader_daemon_heartbeat` (mtime), `.coral/public/eval_logs/<hash>/` for grader stdout/stderr |
| `coral eval` errors out | The pending JSON itself: `.coral/public/attempts/<hash>.json` — `status` and `feedback` fields. Source: `coral/hooks/post_commit.py::submit_eval` |
| Agent restart loop | `coral status` shows pause state. Source: `coral/agent/manager.py` (`restart_burst_threshold`, `restart_burst_window`). Per-agent runtime stdout/stderr is captured under the worktree. |
| Stalled agent | `agents.timeout` watchdog in `coral/agent/manager.py`. Grader-queue exemption (`grader_pending_max_age`) skips the watchdog while a recent submission is still pending. |
| Heartbeat actions not firing | `.coral/public/heartbeat/<agent_id>.json` (per-agent action list), `.coral/public/eval_count` (global counter). Logic: `coral/agent/heartbeat.py::HeartbeatRunner.check`. |
| Shared state corrupted / race | `.coral/public/.git/` is a real git repo — `git -C .coral/public log` shows checkpoint history; `coral notes --history` is the friendly view. |
| Worktree symlinks missing | `coral/workspace/worktree.py` — symlinks `.coral/public/` into each agent worktree under the runtime-specific name (`.claude` / `.codex` / `.opencode`). |
| Grader can't import its package | Check `.coral/private/grader_venv/` — `setup_grader_env` ran `uv venv` + `grader.setup` once at run start. Re-running `coral start` on the same `run_dir` does NOT re-bootstrap; delete the venv to force it. |
| Resume picks up wrong task | `coral resume` reads `.coral/config.yaml` and `.coral/config_dir`. The `latest` symlink at `results/<task-slug>/latest` decides which run is resumed. |

## Inspect a live or finished run

```bash
RUN=$(readlink -f results/<task-slug>/latest)
ls "$RUN/.coral/public/"            # attempts/, notes/, skills/, agents/, logs/, eval_logs/, eval_count
cat "$RUN/.coral/public/attempts/<hash>.json" | jq .
ls "$RUN/agents/"                    # one worktree per agent
cat "$RUN/.coral/config.yaml"        # exact config used (post-merge)
```

The web dashboard (`coral ui`) reads the same files; if you're debugging dashboard rendering, `coral/web/api.py` is the route handler and `coral/web/static/` is the built React bundle.

## Test + lint

```bash
uv sync --extra dev                  # one-time, gets pytest + ruff
uv run pytest tests/ -v              # full suite (~seconds, no docker)
uv run pytest tests/test_<thing>.py -v -k <pattern>
uv run ruff check .                  # lint
uv run ruff format .                 # autoformat
```

There is no separate type-check step in CI yet; tests cover the contract.

## Quick task scaffold for ad-hoc testing

When you need a throwaway task to exercise a code change:
```bash
uv run coral init /tmp/coral-scratch
# edit /tmp/coral-scratch/grader/src/coral_scratch_grader/grader.py to return a simple float
uv run coral validate /tmp/coral-scratch
uv run coral start -c /tmp/coral-scratch/task.yaml agents.count=1 run.session=local
```

`coral validate` runs the grader against `seed/` in a tempdir without spawning agents — the fastest way to confirm a grader change compiles and produces a `Score`.

## Conventions

- **No `git` from agents.** All commits go through `coral eval`. If you're adding a feature that needs to commit, route it through `coral/hooks/post_commit.py` or `coral/hub/checkpoint.py`.
- **Atomic writes** for any JSON in `.coral/public/`. Use `coral.hub.attempts.write_attempt` (tmp + rename) as the model.
- **Idempotent setup.** `setup_run_dir`, `setup_grader_env`, `init_checkpoint_repo` must all be safe to call twice.
- **Shared dir is configurable.** Don't hardcode `.claude`; thread `shared_dir` through (see `coral/template/coral_md.py`).
- **Lazy imports in CLI dispatch** (`coral/cli/__init__.py`) — keep `coral --help` fast.
