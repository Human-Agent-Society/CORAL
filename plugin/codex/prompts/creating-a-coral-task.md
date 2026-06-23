# creating-a-coral-task

Help me author a CORAL task. A task is **three pieces that must line up**: `task.yaml`, `seed/` (starter code agents iterate on), and a packaged `grader/` (its own venv).

Always start by scaffolding — it produces a runnable end-to-end example:

```bash
coral init my-task && cd my-task
```

Then edit:

1. **seed/solution.py** — a real, runnable baseline (agents must get a non-zero score immediately). Runtime data goes under `seed/data/`.
2. **grader/src/<pkg>/grader.py** — subclass `TaskGrader`, implement `evaluate()`:

```python
from coral.grader import TaskGrader

class Grader(TaskGrader):
    def evaluate(self) -> float:
        program_file = self.args.get("program_file", "solution.py")
        result = self.run_program(program_file)              # NOT sys.executable
        if result.returncode != 0:
            return self.fail(f"crashed: {result.stderr[:200]}")
        return self.score(float(result.stdout.strip()), explanation="parsed stdout")
```

On `self`: `codebase_path` (read-only — writes are discarded), `private_dir` (`.coral/private/`, hidden), `args`, `timeout`, `eval_logs_dir` (write artifacts here), `score()`, `fail()`, `get_python_command()`, `run_program()`.

3. **task.yaml** — required: `grader.entrypoint`, `grader.setup: ["uv pip install -e ./grader"]`, `grader.direction` (maximize/minimize), `workspace.repo_path: "./seed"`.

Hidden answer keys / fixtures ship **inside the grader package** (a `taskdata/` subdir resolved via `Path(__file__).parent`), never under `seed/`.

Then validate before running agents:

```bash
coral validate .                                  # grader must score the seed cleanly
coral start -c task.yaml agents.count=1 run.session=local   # smoke test
coral stop
```

Common mistakes: `repo_path` not pointing at `./seed`; `direction` backwards; answer key under `seed/`; grader writing to `codebase_path` (force-removed) instead of `eval_logs_dir`; using `sys.executable` instead of `get_python_command()`; task-runtime deps in `grader.setup` instead of `workspace.setup`.

Config schema: https://docs.coralxyz.com/api/config
