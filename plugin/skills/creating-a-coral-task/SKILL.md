---
name: creating-a-coral-task
description: Author a new CORAL task from scratch — the three pieces that have to line up (`task.yaml`, `seed/`, and a packaged `grader/`), the `TaskGrader` API surface, the `coral init` → `coral validate` → smoke-test loop, and the common mistakes (repo_path pointing at the wrong dir, score direction backwards, hidden answer keys leaking into seed/, grader writing to codebase_path which the daemon force-removes, grader using sys.executable). Use whenever the user wants to create a CORAL task, write a grader, or port a benchmark into CORAL.
---

# Creating a CORAL task

A CORAL task is **three things** that must line up. Scaffold them with `coral init`, then iterate:

```
my-task/
├── task.yaml      # config: name, description, grader entrypoint, agent count
├── seed/          # starter code agents see when they begin (the repo_path)
│   └── solution.py
└── grader/        # standalone Python package — gets its own venv
    ├── pyproject.toml
    └── src/my_task_grader/
        ├── __init__.py
        └── grader.py     # class Grader(TaskGrader): ...
```

The packaged grader is the **only supported form**. It gives the grader an isolated venv and ships everything the eval needs — grader code, helper modules, and hidden data.

## 0. Scaffold

```bash
coral init my-task        # writes task.yaml + seed/solution.py + grader/ package
cd my-task
```

`coral init` produces a runnable task end-to-end (the grader runs `solution.py` and parses a float from stdout). Edit the three pieces from there. Always start here rather than hand-writing the layout.

## 1. The seed

`seed/` is what the agent sees on first checkout — the working directory the grader later scores. The contract between seed and grader is the **program file**: a Python file with a function (or stdout convention) the grader invokes.

Convention across tasks:
- `solution.py` (or `initial_program.py`) defining a top-level `run()` or printing a result.
- The grader reads `program_file: "solution.py"` from `grader.args`.

Put a **real, runnable baseline** here — agents should be able to `coral eval` immediately and get a non-zero score to improve on. A skeleton that crashes is a bad baseline.

Runtime data files (training data, fixtures) go under `seed/data/` and are referenced by relative path from `solution.py`; the grader sees them at `<codebase_path>/data/...`.

## 2. The grader

Subclass `TaskGrader` and implement `evaluate()`:

```python
# grader/src/my_task_grader/grader.py
from coral.grader import TaskGrader
from coral.types import ScoreBundle


class Grader(TaskGrader):
    def evaluate(self) -> float | ScoreBundle:
        program_file = self.args.get("program_file", "solution.py")
        result = self.run_program(program_file)
        if result.returncode != 0:
            return self.fail(f"{program_file} crashed: {result.stderr[:200]}")
        try:
            return self.score(float(result.stdout.strip()), explanation="parsed stdout")
        except ValueError:
            return self.fail(f"Expected a float on stdout, got {result.stdout[:80]!r}")
```

What you have on `self`:

| Attribute / method | Use it for |
|---|---|
| `self.codebase_path` | Path to the commit being graded (detached worktree). **Read-only** — anything written here is discarded after the eval. |
| `self.private_dir` | `.coral/private/`. Answer keys, hidden test data, anything from `grader.private`. |
| `self.args` | `dict` from `task.yaml::grader.args`. `self.args.get("program_file", "solution.py")`. |
| `self.timeout` | Eval timeout in seconds (or `None` if `grader.timeout: 0`). |
| `self.eval_logs_dir` | Per-attempt dir for logs/artifacts that should outlive the grader (the agent sees them post-grade). |
| `self.score(value, explanation=...)` | Build a single-task `ScoreBundle` from a number. |
| `self.fail(reason)` | Return a fail `ScoreBundle` with `reason` as feedback. |
| `self.get_python_command()` | The `python` invocation for the codebase's env (uses `uv run` when a `pyproject.toml` is present). Use this, never `sys.executable`. |
| `self.run_program(filename, *args)` | Run `<codebase_path>/<filename>` as a subprocess via `get_python_command()`. |

### Hidden data — ship it inside the package

Answer keys, fixtures, and helper modules live **inside the grader package** so agents can't read them. Convention: a `taskdata/` subdir next to `grader.py`, resolved with:

```python
from pathlib import Path
_TASKDATA = Path(__file__).parent / "taskdata"
```

This works for editable and wheel installs alike (Hatchling includes non-Python files under `packages`). For files that genuinely can't live in the package (huge datasets), list them under `grader.private` in `task.yaml` and read them via `self.private_dir`.

### Heavy / optional deps

If the grader needs `torch` etc., put them in `[project.optional-dependencies]` and fall back gracefully when absent. Then `grader.setup` becomes `["uv pip install -e ./grader[ml]"]`.

## 3. The task.yaml

Fields that *must* be set; everything else has a sensible default.

```yaml
task:
  name: "My Task"
  description: |                    # rendered into CORAL.md — agents read this verbatim
    What the agent should do. Reference the program file by name and its contract.
  tips: |                           # optional, also rendered into CORAL.md
    - Eval timeout is N seconds. Constraints / scoring details / baselines.

grader:
  entrypoint: "my_task_grader.grader:Grader"   # required
  setup:
    - "uv pip install -e ./grader"             # runs once in .coral/private/grader_venv/
  timeout: 300                       # seconds; 0 disables
  direction: maximize                # or minimize — controls leaderboard ordering
  args:
    program_file: "solution.py"
  private: []                        # extra files copied into .coral/private/ (hidden)
  parallel:
    max_workers: 1                   # bump only when the grader is concurrency-safe
  max_pending_per_agent: 1

agents:
  count: 1                           # raise once the task is stable
  runtime: claude_code               # claude_code | codex | cursor | kiro | opencode
  model: sonnet

workspace:
  repo_path: "./seed"                # MUST point at the seed/ dir
  setup:                             # runs in each agent worktree before agents start
    - "uv pip install numpy"         # task-runtime deps go HERE, not in grader.setup
```

## 4. Validate before running agents

```bash
coral validate .         # or: coral validate my-task
```

This parses `task.yaml`, bootstraps `.coral/private/grader_venv/` and runs `grader.setup`, copies `seed/` into a tempdir, runs the grader against it once, and prints the score. **If `coral validate` succeeds, the grader can score the seed** — the single most important checkpoint. Most "agent stuck" issues trace back to a grader that crashes on the seed.

Then smoke-test with one agent:

```bash
coral start -c task.yaml agents.count=1 run.session=local
# wait for one eval, then:
coral stop
```

## Common mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| `repo_path` points at the task root instead of `./seed` | Grader sees `task.yaml` and `grader/` in `codebase_path` | Point `repo_path` at the seed dir. |
| `direction` backwards | Leaderboard ordered wrong | "ratio vs baseline, >1 better" → `maximize`; "raw error" → `minimize`. |
| Hidden answer key under `seed/` | Agents read it and game the score | Bundle into the grader package (`taskdata/`) or use `grader.private`. |
| Grader writes under `self.codebase_path` and re-reads it | Files vanish — daemon force-removes the worktree after each eval | Write under `self.eval_logs_dir`. |
| Grader uses `sys.executable` | Misses task deps from `workspace.setup` | Use `self.get_python_command()`. |
| Task-runtime deps in `grader.setup` | Grader venv has them, agent worktree doesn't | Runtime deps → `workspace.setup`; grader-only deps → `grader.setup`. |
| `parallel.max_workers > 1` with an unsafe grader | Sporadic collisions on ports/GPU/scratch | Leave at `1` unless provably concurrency-safe. |
| Skipping `coral validate` | Agents start, fail every eval identically | Always validate first. |

When in doubt, run `coral init throwaway` and read the generated files — they are the canonical minimal example. Full schema with every default: https://docs.coralxyz.com/api/config
