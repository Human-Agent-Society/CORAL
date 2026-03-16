# CORAL

An orchestration system for **autonomous coding agents** — agents follow a CORAL.md guide, run experiments, share knowledge, and loop forever.

## How It Works

```
coral start --config task.yaml
  → Creates .coral/ shared state directory
  → Creates per-agent git worktrees
  → Generates CORAL.md in each worktree
  → Spawns coding agents (Claude Code, Codex, OpenCode)

Each agent:
  → Reads CORAL.md for instructions
  → Makes changes, commits
  → Agent runs `coral eval -m "description"`
  → Eval writes attempt JSON to .coral/attempts/
  → Agent sees score, decides next move
  → Shares notes in .coral/notes/
  → Packages tools as skills in .coral/skills/
```

**Core pattern**: Spawn agents → agents read CORAL.md → commit changes → eval runs → repeat

## Key Concepts

- **Agents are the optimizers** — Claude Code / Codex / OpenCode subprocesses working in git worktrees
- **Shared state via `.coral/`** — attempts, notes, skills (symlinked into each worktree)
- **Eval loop** — agents call `coral eval -m "..."` to stage, commit, and grade
- **CLI orchestration** — `coral start/stop/status/eval/log` and more
- **Web dashboard** — `coral ui` for real-time monitoring

## Installation

```bash
git clone https://github.com/yanyh528/CORAL.git
cd CORAL
uv sync                    # Basic install
uv sync --extra dev        # With pytest, ruff, mypy
uv sync --all-extras       # Everything
```

## Quick Start

1. **Create a task** with a config YAML and grader:

```yaml
# my-task/task.yaml
task:
  name: my-task
  description: "Optimize the function in solution.py"

grader:
  type: function
  module: eval.grader

agents:
  count: 2
  model: claude-sonnet-4-20250514
  max_turns: 200
```

2. **Write a grader** (`my-task/eval/grader.py`):

```python
from coral.grader import TaskGrader

class Grader(TaskGrader):
    def evaluate(self) -> float:
        # Run the agent's code and return a score
        result = self.run_program("solution.py")
        return float(result.stdout.strip())
```

3. **Launch agents**:

```bash
coral start --config my-task/task.yaml
coral ui          # Open web dashboard
coral status      # CLI leaderboard
coral log         # View attempts
coral stop        # Stop all agents
```

## CLI Commands

```bash
coral init my-task                 # Scaffold a new task
coral validate my-task             # Test the grader
coral start -c task.yaml           # Launch agents
coral stop                         # Stop all agents
coral status                       # Agent health + leaderboard
coral log                          # Leaderboard (top 20)
coral log -n 5 --recent            # Recent attempts
coral log --search "query"         # Search attempts
coral show <hash>                  # Attempt details + diff
coral notes                        # Browse shared notes
coral skills                       # Browse shared skills
coral runs                         # List all runs
coral ui                           # Web dashboard
coral eval -m "description"        # Stage, commit, evaluate (agent use)
coral diff                         # Show uncommitted changes
coral revert                       # Undo last commit
coral checkout <hash>              # Reset to previous attempt
coral heartbeat                    # View/modify heartbeat actions
```

## Architecture

| Directory | Purpose |
|-----------|---------|
| `coral/types.py` | Core types: Task, Score, ScoreBundle, Attempt |
| `coral/config.py` | YAML-based project configuration |
| `coral/agent/` | Agent spawning and lifecycle management |
| `coral/workspace/` | Per-agent git worktrees, hook installation |
| `coral/grader/` | Grader protocol, base class, builtin graders |
| `coral/hub/` | Shared state: attempts, notes, skills |
| `coral/hooks/` | Eval implementation, workspace guard, skill reminder |
| `coral/template/` | CORAL.md generator |
| `coral/cli/` | CLI entry point |
| `coral/web/` | Web dashboard (Starlette + React) |
| `examples/` | Example task configurations |

### Grading System

Graders implement the `GraderInterface` protocol:

```python
class GraderInterface(Protocol):
    async def grade(self, codebase_path: str, tasks: list[Task], **kwargs) -> ScoreBundle: ...
```

Built-in graders:
- **TaskGrader** — base class for task-specific graders with helpers (`run_program`, `read_eval`, `score`, `fail`)
- **FunctionGrader** — wrap any `(codebase_path, tasks) -> Score|float|bool` callable

## Tech Stack

- **Python 3.11+** with Hatchling build system
- **uv** for environment management
- **React + TypeScript** web dashboard (Vite)
- **Key deps**: `pyyaml`, `starlette`
- **Optional**: `swebench`, `datasets`, `docker`

## Examples

See `examples/` for task configurations including:
- `circle_packing` — geometric optimization
- `erdos` — math conjecture
- `kernel_builder` — VLIW SIMD kernel optimization
- `mnist` — ML classification
- `spaceship_titanic` — Kaggle competition
- `kernel_engineering` — GPU kernel optimization
- `stanford_covid_vaccine` — mRNA degradation prediction

## License

MIT License — see [LICENSE](LICENSE) for details.
