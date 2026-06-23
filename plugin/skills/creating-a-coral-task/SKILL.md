---
name: creating-a-coral-task
description: Author a new CORAL task — the three pieces that must line up (`task.yaml`, `seed/`, a packaged `grader/`), the `coral init` → `coral validate` → smoke-test loop, and how to pick a grader pattern (stdout float, test pass-rate, ratio-vs-baseline, multi-metric, or an LLM rubric judge). Use whenever the user wants to create a CORAL task, write or wire a grader, port a benchmark into CORAL, score open-ended outputs (reports/memos) with a judge, or debug a grader that crashes on the seed / ranks the leaderboard backwards / leaks the answer key. Deep references for the TaskGrader API, grader patterns, rubric judges, and the full task.yaml schema live alongside this skill.
---

# Creating a CORAL task

A CORAL task is **three things that must line up**. Scaffold them with `coral init`, then iterate `edit → coral validate` until the grader scores the seed.

```
my-task/
├── task.yaml      # config: name, description, grader entrypoint, agent count
├── seed/          # starter code agents see at t=0 (this is workspace.repo_path)
│   └── solution.py
└── grader/        # standalone Python package — gets its own isolated venv
    ├── pyproject.toml
    └── src/my_task_grader/
        ├── __init__.py
        └── grader.py     # class Grader(TaskGrader): ...
```

The packaged grader is the **only supported form** — it gives the grader an isolated venv and bundles everything the eval needs (grader code, helpers, hidden answer keys). There is no `eval/grader.py` auto-discovery anymore.

> **Optimizing code the user already has?** Scaffold inside a `.coral_workspace/` at the root of their project (gitignored), and copy the code to optimize into `seed/` — keeps CORAL's task/results out of their source tree. The `coral-quickstart` skill has the end-to-end `.coral_workspace/` flow; this skill covers the grader you'll write once the code is in `seed/`.
>
> **"Optimize this" is a build instruction, not a question — never answer it with a process menu.** A 1/2/3 like "point me to a task / create one / optimize outside coral" is the failure mode; do not produce it. The absence of a `task.yaml` is not ambiguity — it just means you build one from the current repo. Concretely: (1) dig for what's already measurable — a research/framework repo almost always ships an eval/benchmark script, a test suite, or a metric in its README/paper; that's your target and metric. (2) If no single number is obvious, **construct** one by wrapping the repo's existing evaluation — don't conclude "no measurable objective" just because there's no CORAL scaffold. (3) Scaffold the most plausible target and start building (a `.coral_workspace/` + draft grader is cheap and reversible); state your assumption in one line and proceed. (4) Only as a last resort, if you've actually read the repo and it exposes nothing scorable, propose 2-3 **concrete** optimization targets you found (each with its metric), pick the most likely, and scaffold that — still not a process menu.

## The loop

```bash
coral init my-task        # scaffold all three pieces (a runnable end-to-end example)
cd my-task
# ... edit the three pieces for your problem ...
coral validate .          # bootstraps the grader venv, runs the grader on seed/, prints a score
# repeat edit → validate until the seed scores as you expect
```

**`coral validate` succeeding is the one checkpoint that matters** — it proves the grader can score the seed. Most "agents are stuck, every eval fails" reports trace to a grader that crashes on the seed, which validate would have caught. Always start from `coral init` rather than hand-writing the layout; the generated files are the canonical minimal example.

## The three pieces

**1. The seed** (`seed/`) — what the agent checks out at t=0 and what the grader later scores. The contract between seed and grader is the **program file**: a file (e.g. `solution.py`) with a function or stdout convention the grader invokes, named in `grader.args.program_file`. Put a **real, runnable baseline** here — agents should `coral eval` immediately and get a non-zero score to beat. A skeleton that crashes is a bad baseline. Runtime data goes under `seed/data/` and is read by relative path.

**2. The grader** (`grader/`) — subclass `TaskGrader`, implement `evaluate()`, return a number (or `ScoreBundle`). The minimum:

```python
from coral.grader import TaskGrader

class Grader(TaskGrader):
    def evaluate(self) -> float:
        result = self.run_program(self.args.get("program_file", "solution.py"))
        if result.returncode != 0:
            return self.fail(f"crashed: {result.stderr[:200]}")
        try:
            return float(result.stdout.strip())
        except ValueError:
            return self.fail(f"expected a float, got {result.stdout[:80]!r}")
```

This stdout-float shape is one of several. **Pick the pattern that matches how your task scores** → [references/cookbook.md](references/cookbook.md):

| Score by... | Pattern |
|---|---|
| A number the program prints | stdout float |
| Fraction of hidden tests passing | test pass-rate |
| Improvement over a baseline | ratio vs baseline |
| Several weighted criteria | multi-metric `ScoreBundle` |
| An LLM judging a report/memo/doc | rubric judge → [references/rubric-judges.md](references/rubric-judges.md) |

Full `TaskGrader` surface — every attribute (`self.codebase_path`, `self.private_dir`, `self.args`, `self.eval_logs_dir`, `self.tune`) and method (`run_program`, `run_script`, `run_script_json`, `score`, `fail`, `bundle`) — is in [references/grader-api.md](references/grader-api.md).

**3. The task.yaml** — wiring. The fields that must be right are `grader.entrypoint`, `grader.direction`, and `workspace.repo_path: ./seed`. Full annotated schema (agents, islands, sharing, gateway, all defaults) → [references/task-yaml.md](references/task-yaml.md).

## Hidden data

Answer keys, fixtures, and helper modules go **inside the grader package** so agents can't read them — a `taskdata/` dir next to `grader.py`, resolved with `Path(__file__).parent / "taskdata"`. Only use `grader.private` (read via `self.private_dir`) for files too large to package. Never put an answer key under `seed/` — agents read `seed/` and will game the score.

## Smoke-test, then scale

```bash
coral start -c task.yaml agents.count=1 run.session=local   # one agent, foreground
# watch for one real eval, confirm the score moves, then:
coral stop
```

Once one agent evals cleanly, raise `agents.count`. Driving the run from here is the `running-coral-experiments` skill.

## Common mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| `repo_path` points at the task root, not `./seed` | Grader sees `task.yaml`/`grader/` in `codebase_path` | Point `repo_path` at `./seed`. |
| `direction` backwards | Leaderboard ordered upside down | "ratio, higher better" → `maximize`; "raw error/latency" → `minimize`. |
| Answer key under `seed/` | Agents read it, game the score | Bundle into `taskdata/` or use `grader.private`. |
| Grader writes under `self.codebase_path` and re-reads it | Files vanish — daemon force-removes the worktree after each eval | Write under `self.eval_logs_dir`. |
| Grader uses `sys.executable` | Misses task deps from `workspace.setup` | Use `self.get_python_command()` / `self.run_program` / `self.run_script`. |
| Runtime deps in `grader.setup` | Validate passes, the run fails every eval | Runtime deps → `workspace.setup`; grader-only deps → `grader.setup`. |
| Scoring speed without a correctness gate | Agents "optimize" by returning garbage fast | Gate on correctness first, then score the metric. |
| `parallel.max_workers > 1` with an unsafe grader | Sporadic port/GPU/scratch collisions | Leave at `1` unless provably concurrency-safe. |
| Skipping `coral validate` | Agents start, fail every eval identically | Always validate first. |

When in doubt, run `coral init throwaway` and read the generated files. Full config schema: https://docs.coralxyz.com/api/config
