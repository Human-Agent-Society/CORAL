# TaskGrader API reference

The full surface a grader subclass sees. `TaskGrader` (`coral.grader.TaskGrader`) is the recommended base — subclass it and implement `evaluate()`. The framework sets the attributes below *before* calling `evaluate()`, then runs the grader inside a detached worktree pinned to the commit being scored.

## The one method you must implement

```python
def evaluate(self) -> float | ScoreBundle: ...
```

Return a plain `float` (the framework wraps it), or a `ScoreBundle` you build with the helpers. Returning `self.fail(...)` is how you record "this attempt didn't even produce a gradeable result" — distinct from a low score.

## Attributes (set before `evaluate()` runs)

| Attribute | Type | What it is |
|---|---|---|
| `self.codebase_path` | `str` | The commit being graded, checked out in a detached worktree. **Read-only in practice** — the daemon force-removes this worktree after each eval, so anything you write here is discarded. |
| `self.private_dir` | `str` | Path to `.coral/private/`. Answer keys, hidden fixtures, anything from `grader.private`. Agents cannot see this. |
| `self.args` | `dict` | `grader.args` from `task.yaml`. Read config like `self.args.get("program_file", "solution.py")`. |
| `self.timeout` | `int \| None` | Eval timeout in seconds. `None` when `grader.timeout: 0`. `run_program` already respects it. |
| `self.eval_logs_dir` | `Path` | Per-attempt dir for artifacts that must **outlive** the grader (logs, traces, recordings). The agent can read these after the eval; `self.codebase_path` writes cannot. This is where you put anything you want to survive. |
| `self.tune` | `bool` | `True` when the agent submitted with `coral eval --tune`. Branch on this to score against a cheaper target (dev split, smoke harness). See [cookbook.md](cookbook.md) → tune mode. |
| `self.island_id` | `str \| int \| None` | Island identifier for multi-island runs; usually ignore it. |
| `self.config` | `GraderConfig` | The raw grader config object (rarely needed directly — use `self.args`/`self.timeout`). |
| `self.tasks` | `list[Task]` | The tasks being evaluated. Single-task graders ignore this. |

## Running the agent's code

Always run the agent's program through these — they pick the right interpreter (`uv run` when the codebase has a `pyproject.toml`, so task deps from `workspace.setup` are present). **Never use `sys.executable`** — it points at the grader venv, which lacks the task's runtime deps.

| Method | Returns | Use it for |
|---|---|---|
| `self.get_python_command()` | `list[str]` | The python invocation for the codebase env. The primitive the others build on. |
| `self.run_program(filename, *cmd_args)` | `CompletedProcess[str]` | Run `<codebase_path>/<filename>` as a subprocess (`capture_output=True, text=True`, respects `self.timeout`). Raises `FileNotFoundError` if the file is missing. The workhorse. |
| `self.run_script(script, *, timeout=300)` | `CompletedProcess[str]` | Run an inline Python string with the codebase interpreter. Use when you want to import the agent's module and probe it rather than exec a file. |
| `self.run_script_json(script, *, timeout=300)` | `dict` | Like `run_script`, but the script prints JSON to stdout and you get the parsed dict. Handles the common failure modes for you: non-zero exit → `RuntimeError` with stderr; empty stdout → `RuntimeError`; stray prints before the JSON → scans for the last JSON line. The cleanest way to pull structured results out of agent code. |

## Returning a score

| Method | Returns | Use it for |
|---|---|---|
| `self.score(value, explanation="", feedback=None, metadata=None)` | `ScoreBundle` | The common case: one number. Wraps it as a single score named `"eval"`. `explanation` shows in `coral show`; `feedback` is the message the agent reads to improve. |
| `self.bundle(value, explanation="", feedback=None, metadata=None)` | `ScoreBundle` | Same as `score()` — alias kept for readability when you mean "build the final bundle". |
| `self.fail(explanation="", feedback=None)` | `ScoreBundle` | Record a failed eval (score value `None`, not `0.0`). Use for crashes, malformed output, missing files — anything where there's no meaningful number. The agent sees `explanation` and learns what broke. |

`feedback` is the highest-leverage field you control: it's the text the agent reads on its next loop. A grader that returns `self.fail("solution.py crashed: <stderr>")` teaches the agent far more than a bare `0.0`.

## Score / ScoreBundle shapes (`coral.types`)

```python
@dataclass
class Score:
    value: float | int | None      # None when ungradeable (timeout, crash). Convert pass/fail to a float yourself.
    name: str                       # "correctness", "efficiency", ...
    explanation: str | None = None
    metadata: dict = field(default_factory=dict)

@dataclass
class ScoreBundle:
    scores: dict[str, Score]        # name -> Score
    aggregated: float | None = None # the single number used for ranking + plateau detection
    is_public: bool = True          # False hides the score from the agent
    feedback: str | None = None     # message the agent reads
    metadata: dict = field(default_factory=dict)
```

`aggregated` is what the leaderboard sorts on and what plateau/heartbeat logic watches. With `self.score(x)` it's just `x`. For multiple metrics you set it explicitly — see the multi-metric pattern in [cookbook.md](cookbook.md).

## Mental model

```
daemon picks up pending attempt
  → git worktree add --detach <commit>        (this becomes self.codebase_path)
  → instantiate your Grader, set attributes
  → call evaluate()
      ├─ run_program / run_script(_json)       (run agent code in the codebase env)
      ├─ compare against self.private_dir       (hidden answer key)
      └─ return self.score(...) / self.fail(...)
  → write ScoreBundle back to the attempt JSON
  → force-remove the worktree                  (codebase_path writes vanish here)
```
