---
name: coral-new-task
description: End-to-end recipe for adding a new task under `examples/` — the three pieces that have to line up (`task.yaml`, `seed/`, and `grader/` or legacy `eval/grader.py`), what to put in each, the `TaskGrader` API surface, the `coral validate` → smoke-test loop, and the common mistakes (repo_path pointing at the wrong dir, score direction backwards, hidden answer keys leaking into seed/, grader writing to codebase_path which the daemon force-removes, private-vs-public confusion, missing `run()` signature). Use whenever the user wants to add a new CORAL task, port an existing benchmark into CORAL, or migrate an old `eval/grader.py` example to the packaged grader form.
---

# Creating a new CORAL task

A CORAL task is **three things** that must line up:

```
examples/<task>/
├── task.yaml      # config: name, description, grader entrypoint, agent count
├── seed/          # starter code agents see when they begin (the repo_path)
│   └── solution.py
└── grader/        # standalone Python package (recommended)
    ├── pyproject.toml
    └── src/<task>_grader/
        ├── __init__.py
        └── grader.py     # class Grader(TaskGrader): ...
```

The legacy alternative drops `grader/` and puts the grader at `eval/grader.py` instead. New tasks should use the packaged form — it gives the grader its own venv, lets it ship data files via `importlib.resources`, and avoids the `DeprecationWarning`. Only fall back to legacy if the grader is genuinely trivial *and* has no third-party deps beyond what `coral` already pulls in.

## Reference implementations

Look at these before writing anything new — copy the closest one and edit:

| Reference | When to copy it |
|---|---|
| [examples/erdos/](examples/erdos/) | Minimal packaged grader, single grader file, numpy-only deps |
| [examples/dna_design/](examples/dna_design/) | Packaged grader with bundled data files (`importlib.resources`) and `[ml]` optional-deps for heavy libs |
| [examples/swebench-verified/](examples/swebench-verified/) | Tiered eval (different instance counts per tier), private answer keys, harbor integration |
| [examples/circle_packing/](examples/circle_packing/) | Legacy `eval/grader.py` form — only if you genuinely need the legacy path |
| [examples/mnist/](examples/mnist/) | Legacy form with private answer key under `eval/answers/` |

## 1. The seed

Whatever lives in `seed/` is what the agent sees on first checkout — it's the working directory the grader will later score. The contract between `seed/` and the grader is the **program file**: a Python file with a function the grader imports and calls.

The convention across examples is:
- `solution.py` (or `initial_program.py`) defining a top-level `run()` function.
- The grader passes `program_file: "solution.py"` via `grader.args`.
- `run()`'s signature is whatever the grader expects — usually `() -> result` or `(input_path) -> result`.

Put a real, runnable baseline here. Agents should be able to `coral eval` immediately and get a non-zero score, so they have a starting point to improve. A no-op skeleton that crashes is not a good baseline.

If the task needs data files at runtime (training data, fixtures), put them under `seed/data/` and reference them by relative path from `solution.py`. The grader will see them at `<codebase_path>/data/...`.

## 2. The grader

### Packaged grader — the recommended path

```
grader/
├── pyproject.toml
└── src/<task>_grader/
    ├── __init__.py
    └── grader.py
```

`pyproject.toml` is a thin Hatchling package. Crib from [examples/erdos/grader/pyproject.toml](examples/erdos/grader/pyproject.toml):

```toml
[project]
name = "<task>-grader"
version = "0.1.0"
description = "CORAL grader for the <task> task."
requires-python = ">=3.11"
dependencies = ["coral", "numpy"]   # Whatever the grader actually imports.

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/<task>_grader"]
```

Subclass `TaskGrader` and implement `evaluate()`:

```python
# grader/src/<task>_grader/grader.py
from coral.grader import TaskGrader
from coral.types import ScoreBundle


class Grader(TaskGrader):
    def evaluate(self) -> float | ScoreBundle:
        program_file = self.args.get("program_file", "solution.py")
        # self.codebase_path  — the agent's commit checked out detached
        # self.private_dir    — .coral/private/ (your hidden answer keys live here)
        # self.args           — dict from task.yaml grader.args
        # self.timeout        — grader.timeout in seconds (or None)
        # self.eval_logs_dir  — write subprocess logs / artifacts the agent should see post-grade

        try:
            result = run_program_and_score(...)
        except TimeoutError:
            return self.fail(f"Evaluation timed out after {self.timeout}s")
        except Exception as e:
            return self.fail(f"Evaluation failed: {e}")

        return self.score(result, explanation=f"score={result:.4f}")
```

What you have available on `self`:

| Attribute / method | Use it for |
|---|---|
| `self.codebase_path` | Path to the commit being graded (detached worktree). Read-only — anything written here is discarded after the eval. |
| `self.private_dir` | `.coral/private/`. Your answer keys, hidden test data, anything from `grader.private` lives here. |
| `self.args` | `dict` from `task.yaml::grader.args`. Use `self.args.get("program_file", "solution.py")` etc. |
| `self.timeout` | Eval timeout in seconds (or `None` if `grader.timeout: 0`). |
| `self.eval_logs_dir` | Per-attempt directory for logs/artifacts that should outlive the grader. Symlinked into each agent worktree as `<shared_dir>/eval_logs/<hash>/`. |
| `self.score(value, explanation=...)` | Build a single-task `ScoreBundle` from a numeric score. |
| `self.fail(reason)` | Return a fail `ScoreBundle` with `reason` as feedback. |
| `self.get_python_command()` | List for the `python` binary inside the codebase's env (uses `uv run` if a `pyproject.toml` is present). Always use this instead of `sys.executable` so task-specific deps are visible. |
| `self.run_program(filename, *args)` | Convenience: runs `<codebase_path>/<filename>` as a subprocess via `get_python_command()`. |

### Bundling data files with the grader

If the grader needs reference files (model weights, ground-truth answers, scoring fixtures), ship them inside the package and load via `importlib.resources`:

```python
import importlib.resources
scorer_dir = str(importlib.resources.files("<task>_grader.scorers"))
```

[examples/dna_design/grader/src/dna_design_grader/grader.py](examples/dna_design/grader/src/dna_design_grader/grader.py) is the canonical pattern — note the `scorers/` subpackage. Add the directory to `[tool.hatch.build.targets.wheel]` if it has non-Python files.

### Heavy / optional dependencies

If the grader wants `torch`, `grelu`, etc., put them in `optional-dependencies` and have the grader fall back gracefully when missing — see [examples/dna_design/grader/pyproject.toml](examples/dna_design/grader/pyproject.toml). Then `grader.setup` becomes `["uv pip install -e ./grader[ml]"]` for the full version.

### Legacy `eval/grader.py`

Same `TaskGrader` API, no `pyproject.toml`. CORAL auto-discovers it from `<task>/eval/grader.py` and emits a `DeprecationWarning`. Useful for one-off tasks where packaging is overkill, but new examples should pick the packaged form.

When using legacy, hidden answer keys go under `<task>/eval/<whatever>/` — they get copied into `.coral/private/eval/` automatically. See [examples/mnist/eval/answers/](examples/mnist/eval/).

## 3. The task.yaml

Fields that *must* be set; everything else has a sensible default.

```yaml
task:
  name: "My Task"                       # shows up in results/<slug>/
  description: |                        # rendered into CORAL.md, agents read this
    What the agent should do.
    Reference the program file by name (e.g. solution.py and its run() signature).
  tips: |                               # optional, also rendered into CORAL.md
    - Eval timeout is N seconds.
    - Constraints / scoring details / known baselines.

grader:
  entrypoint: "<task>_grader.grader:Grader"   # packaged path; OR omit and use eval/grader.py
  setup:
    - "uv pip install -e ./grader"            # runs once in .coral/private/grader_venv/
  timeout: 600                          # seconds; 0 disables, default 300
  direction: maximize                   # or minimize — controls leaderboard ordering
  args:                                 # arbitrary dict, read inside grader as self.args
    program_file: "solution.py"
  private: []                           # extra files copied into .coral/private/ (legacy ans-key style)
  parallel:
    max_workers: 1                      # bump only when the grader is concurrency-safe
  max_pending_per_agent: 1              # cap on in-flight submissions per agent

agents:
  count: 1                              # raise once the task is known to be stable
  runtime: claude_code                  # claude_code | codex | cursor_agent | kiro | opencode
  model: sonnet                         # default depends on runtime; see coral/agent/registry.py

workspace:
  results_dir: "./results"              # where each run lands
  repo_path: "./examples/<task>/seed"   # MUST point at the seed/ dir
  setup:                                # runs in each agent worktree before agents start
    - "uv pip install numpy"            # task-runtime deps go here, NOT in grader/setup

run:
  verbose: false
  ui: false
  session: tmux                         # local | tmux | docker
```

The `examples/README.md` documents the full schema with every default. When in doubt, look there before adding fields.

## 4. Validate before running agents

```bash
coral validate examples/<task>
```

This:
1. Parses `task.yaml` and reports schema errors.
2. Bootstraps `.coral/private/grader_venv/` and runs `grader.setup`.
3. Copies `seed/` into a tempdir and runs the grader against it once.
4. Prints the resulting score and explanation.

If `coral validate` succeeds, the grader can score the seed. That's the single most important checkpoint — most "agent stuck" issues trace back to a grader that crashes on the seed.

After validation, smoke-test with one agent:
```bash
coral start -c examples/<task>/task.yaml agents.count=1 run.session=local
# Wait for one eval, then:
coral stop
```

## 5. Wire it into the index

Add a one-line entry to the table in [examples/README.md](examples/README.md) and a short `### <task>` section under "Details" with the bullet points the others use (Agents / Timeout / Session). Skip this only for throwaway local tasks.

## Common mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| `repo_path` points at `examples/<task>/` instead of `examples/<task>/seed/` | Grader sees `task.yaml` and `grader/` in `codebase_path` | Always point `repo_path` at the seed dir. |
| `direction: maximize` for a loss / `minimize` for a benchmark ratio | Leaderboard ordered backwards | Score = "ratio against benchmark, >1 is better" → `maximize`. Score = "raw error" → `minimize`. |
| Hidden answer key under `seed/` | Agents can read it and game the score | Move it into `grader.private` (legacy) or bundle into the grader package via `importlib.resources` (packaged). |
| Grader writes results under `self.codebase_path` and reads them later | Files vanish — daemon force-removes the worktree after each eval | Write under `self.eval_logs_dir`. |
| Grader uses `sys.executable` to run the agent's program | Misses task-specific deps installed via `workspace.setup` | Use `self.get_python_command()` (it switches to `uv run --project` when the codebase has a `pyproject.toml`). |
| Heavy deps in main grader `dependencies` | `coral validate` is slow / fails on machines without the GPU stack | Move to `optional-dependencies` and fall back gracefully. See dna_design's `[ml]` extra. |
| `grader.setup` tries to install task-runtime deps | The grader venv has them but the agent's worktree doesn't | Task-runtime deps go in `workspace.setup`. Grader-only deps go in `grader.setup`. |
| `parallel.max_workers > 1` with a non-concurrency-safe grader | Sporadic failures when two evals collide on Docker ports / GPU / scratch dirs | Leave at `1` unless the grader is provably safe. |
| Forgetting `coral validate` | Agents start, fail every eval with the same error | Always validate first. |

## Migrating a legacy example to packaged

1. Create `<task>/grader/pyproject.toml` and move `eval/grader.py` to `grader/src/<task>_grader/grader.py`. Keep the `class Grader(TaskGrader)` name.
2. Move any data files from `eval/` into the package (with `importlib.resources` access) — or, if they really must stay outside the package, leave them under `eval/` and add `private: ["eval/<dir>"]` to `grader`.
3. Update `task.yaml`:
   ```yaml
   grader:
     entrypoint: "<task>_grader.grader:Grader"
     setup: ["uv pip install -e ./grader"]
   ```
4. Delete the old `eval/grader.py`.
5. `coral validate` — should produce the same score as before.
6. The "Migrated examples" section of `examples/README.md` is the place to mention the new entry.
