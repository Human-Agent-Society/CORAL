# CORAL

An orchestration system for **autonomous coding agents** — agents follow a CORAL.md guide, run experiments, share knowledge, and loop forever.

## Project Overview

Core pattern: **Spawn agents → agents read CORAL.md → commit changes → eval runs → repeat**

Key concepts:
- **Agents are the optimizers** — Claude Code subprocesses working in git worktrees
- **Shared state via `.coral/`** — attempts, notes, skills (symlinked into each worktree)
- **Eval loop** — agents call `coral eval -m "..."` to stage, commit, and grade
- **CLI orchestration** — `coral start/stop/status/eval/log` and 12 more commands

## Directory Structure

| Directory | Purpose |
|-----------|---------|
| `coral/types.py` | Core types: Task, Score, ScoreBundle, Attempt |
| `coral/config.py` | YAML-based project configuration |
| `coral/agent/` | Agent spawning (manager.py) and Claude Code lifecycle (runtime.py) |
| `coral/workspace/` | Per-agent git worktrees, hook installation, symlinks |
| `coral/grader/` | Grader protocol, base class, builtin graders |
| `coral/grader/builtin/` | FunctionGrader (wrap callables as graders) |
| `coral/hub/` | Shared state: attempts CRUD, notes, skills |
| `coral/hooks/` | Eval implementation, workspace guard, skill reminder hooks |
| `coral/template/` | CORAL.md generator (agent instructions per task) |
| `coral/web/` | Web dashboard (Starlette backend) |
| `coral/cli/` | CLI package (17 commands across start, query, eval, heartbeat, ui modules) |
| `examples/` | Example task config YAMLs |
| `tests/` | Test suite |

## How It Works

```
coral start --config task.yaml
  → Creates .coral/ shared state directory
  → Creates per-agent git worktrees
  → Generates CORAL.md in each worktree
  → Spawns Claude Code agents

Each agent:
  → Reads CORAL.md for instructions
  → Makes changes, commits
  → Agent runs `coral eval -m "description"`
  → Eval writes attempt JSON to .coral/attempts/
  → Agent sees score, decides next move
  → Shares notes in .coral/notes/
  → Packages tools as skills in .coral/skills/
```

## Tech Stack

- **Python 3.11+** with Hatchling build system
- **uv** for environment management
- **Key dep**: `pyyaml`
- **Optional**: `swebench`, `datasets`, `docker`, `harbor`

## Commands

```bash
# Install
uv sync                    # Basic
uv sync --extra dev        # With pytest, ruff, mypy
uv sync --all-extras       # Everything

# CLI
coral init my-task                 # Scaffold a new task
coral validate my-task             # Test the grader
coral start -c task.yaml                          # Launch agents
coral start -c task.yaml agents.count=4           # Override config via dotlist
coral start -c task.yaml run.verbose=true         # Verbose output
coral start -c task.yaml run.ui=true              # Also launch web dashboard
coral start -c task.yaml run.session=local           # No tmux session
coral resume                                      # Resume a previous run
coral resume agents.model=opus                    # Resume with model override
coral resume -i "Try greedy approaches"           # Resume with additional instruction
coral stop                         # Stop all agents
coral status                       # Agent health + leaderboard
coral log                          # Leaderboard (top 20)
coral log -n 5 --recent            # Recent attempts
coral log --search "query"         # Search attempts
coral show <hash>                  # Attempt details + file summary
coral show <hash> --diff           # Attempt details + full code diff
coral notes                        # Browse shared notes
coral skills                       # Browse shared skills
coral runs                         # List all runs
coral ui                           # Web dashboard
coral eval -m "description"        # Stage, commit, evaluate (agent use)
coral diff                         # Show uncommitted changes
coral revert                       # Undo last commit
coral checkout <hash>              # Reset to previous attempt
coral heartbeat                    # View/modify heartbeat actions

# Tests
uv run pytest tests/ -v

# Lint
uv run ruff check .
uv run ruff format .
```

## Code Patterns

1. **GraderInterface protocol** (`@runtime_checkable`):
   ```python
   class GraderInterface(Protocol):
       async def grade(self, codebase_path: str, tasks: list[Task], **kwargs) -> ScoreBundle: ...
   ```

2. **BaseGrader** with helpers: `_make_score()`, `_make_bundle()`, `grade_sync()`

3. **FunctionGrader** wraps any `(codebase_path, tasks) -> Score|float|bool` callable

4. **Attempt** dataclass: commit_hash, agent_id, title, score, status, feedback

5. **Hub modules**: attempts (JSON CRUD + search), notes (Markdown + YAML frontmatter), skills (directories with SKILL.md)

6. **Config**: YAML-based `CoralConfig` with task, grader, agents, sharing, workspace, run sections

## Key Files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Package config, dependencies |
| `coral/types.py` | Task, Score, ScoreBundle, Attempt |
| `coral/config.py` | CoralConfig YAML loading |
| `coral/grader/protocol.py` | GraderInterface protocol |
| `coral/grader/base.py` | BaseGrader base class |
| `coral/grader/task_grader.py` | TaskGrader base class for task-specific graders |
| `coral/grader/loader.py` | Grader discovery and loading |
| `coral/grader/builtin/function_grader.py` | Wrap functions as graders |
| `coral/hub/attempts.py` | Attempt CRUD + leaderboard |
| `coral/hub/notes.py` | Note listing/reading |
| `coral/hub/skills.py` | Skill listing/reading |
| `coral/workspace/setup.py` | Worktree creation, hooks, symlinks |
| `coral/agent/manager.py` | Multi-agent lifecycle |
| `coral/agent/runtime.py` | Claude Code subprocess |
| `coral/hooks/post_commit.py` | Eval-on-commit implementation |
| `coral/template/coral_md.py` | Agent instructions generator |
| `coral/cli/` | CLI package (grouped commands) |
