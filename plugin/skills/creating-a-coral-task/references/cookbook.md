# Grader cookbook

Worked `evaluate()` patterns. Pick the one whose *shape* matches your task, then adapt. All assume `class Grader(TaskGrader)`. API details: [grader-api.md](grader-api.md).

## Decision: which pattern?

| Your task scores by... | Pattern |
|---|---|
| A number the program prints | **Stdout float** |
| Fraction of held-out tests that pass | **Test pass-rate** |
| How much better than a baseline | **Ratio vs baseline** |
| Several criteria you weight together | **Multi-metric** |
| An LLM judging open-ended text/docs | rubric judge → [rubric-judges.md](rubric-judges.md) |

If the program is expensive to run and the agent sweeps hyperparameters, add a **tune-mode** cheap path (last section) on top of any pattern.

---

## 1. Stdout float (the `coral init` default)

The program prints one number; you parse it. Good for optimization tasks (pack circles → print sum of radii).

```python
def evaluate(self) -> float | ScoreBundle:
    program_file = self.args.get("program_file", "solution.py")
    result = self.run_program(program_file)
    if result.returncode != 0:
        return self.fail(f"{program_file} crashed: {result.stderr[:300]}")
    try:
        value = float(result.stdout.strip())
    except ValueError:
        return self.fail(f"Expected a float on stdout, got {result.stdout[:80]!r}")
    return self.score(value, explanation=f"parsed {value:.4f} from stdout")
```

## 2. Test pass-rate against a hidden test set

Ship the tests inside the grader package (so agents can't read them), copy them next to the agent's code, run pytest, score the pass fraction. `direction: maximize`.

```python
import json, shutil
from pathlib import Path

def evaluate(self) -> float | ScoreBundle:
    tests = Path(__file__).parent / "taskdata" / "test_hidden.py"
    dest = Path(self.codebase_path) / "test_hidden.py"
    shutil.copy(tests, dest)   # codebase_path is force-removed after, so this is safe + temporary

    # A tiny in-process pytest plugin counts pass/fail and prints JSON we parse back.
    out = self.run_script_json(
        "import pytest, json\n"
        "class P:\n"
        "    def __init__(self): self.passed=0; self.failed=0\n"
        "    def pytest_runtest_logreport(self, report):\n"
        "        if report.when=='call':\n"
        "            self.passed += report.passed; self.failed += report.failed\n"
        "p=P(); pytest.main(['-q','test_hidden.py','--tb=no'], plugins=[p])\n"
        "print(json.dumps({'passed': p.passed, 'failed': p.failed}))\n"
    )
    total = out["passed"] + out["failed"]
    if total == 0:
        return self.fail("no tests collected — did the agent delete the entry point?")
    frac = out["passed"] / total
    return self.score(frac, explanation=f"{out['passed']}/{total} hidden tests passed")
```

> `run_script_json` is the clean primitive here: it runs in the codebase env (so the agent's deps are available), parses the JSON you print, and raises with stderr if the script crashes.

## 3. Ratio vs a baseline (speedups, error reduction)

Score relative to a reference so the leaderboard reads as "× better". For a speedup, `direction: maximize` and report `baseline_time / agent_time`.

```python
def evaluate(self) -> float | ScoreBundle:
    out = self.run_script_json(
        "import json, time, importlib.util\n"
        "spec = importlib.util.spec_from_file_location('sol', 'solution.py')\n"
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
        "t0 = time.perf_counter(); result = m.run(); dt = time.perf_counter() - t0\n"
        "print(json.dumps({'dt': dt, 'result': result}))\n"
    )
    # correctness gate first — never reward a fast wrong answer
    if out["result"] != self._expected():
        return self.fail("output incorrect — speed doesn't count until it's correct")
    baseline = float(self.args.get("baseline_seconds", 1.0))
    ratio = baseline / out["dt"]
    return self.score(ratio, explanation=f"{ratio:.2f}× baseline ({out['dt']:.3f}s vs {baseline:.3f}s)")
```

The correctness gate is the important part: gate on correctness, *then* score the thing you're optimizing. Otherwise agents discover that `return 0` is very fast.

## 4. Multi-metric ScoreBundle

Return several named `Score`s plus one `aggregated` number. Each metric shows in `coral show`; `aggregated` is what ranks and what plateau detection watches.

```python
from coral.types import Score, ScoreBundle

def evaluate(self) -> ScoreBundle:
    m = self.run_script_json("...emit {'acc':..,'latency_ms':..,'size_kb':..} ...")
    scores = {
        "accuracy":   Score(value=m["acc"],            name="accuracy"),
        "latency":    Score(value=1000.0 / m["latency_ms"], name="latency", explanation="1/sec"),
        "compactness":Score(value=1.0 / m["size_kb"],   name="compactness"),
    }
    weights = {"accuracy": 0.7, "latency": 0.2, "compactness": 0.1}
    aggregated = sum(scores[k].value * w for k, w in weights.items())
    return ScoreBundle(
        scores=scores,
        aggregated=aggregated,
        feedback=f"acc={m['acc']:.3f} latency={m['latency_ms']:.0f}ms size={m['size_kb']:.1f}kb",
        metadata={"weights": weights},
    )
```

`ScoreBundle` also has `.compute_aggregated(weights)` if you'd rather let it do the weighted average. Convert every metric to a number where bigger = better (or set `direction: minimize` and keep raw values) so the leaderboard ordering is unambiguous.

## 5. Tune mode — a cheap target for hyperparameter sweeps

When the agent runs `coral eval --tune`, `self.tune` is `True` and the attempt **doesn't count against the plateau/heartbeat budget**. Use it to score against a smaller, faster slice so agents can sweep cheaply, then submit a real eval for the full target. Override `describe_tune()` so the agent knows what your tune path does.

```python
def describe_tune(self) -> str:
    return "Tune mode scores on a 500-example dev slice (≈10× faster); real evals use the full test set."

def evaluate(self) -> float | ScoreBundle:
    n = 500 if self.tune else None        # None = full set
    acc = self._score_on(n_examples=n)
    label = "dev slice" if self.tune else "full test set"
    return self.score(acc, explanation=f"accuracy on {label}")
```

If you do nothing, tune evals are identical to real ones (the default `describe_tune()` says so). Adding a cheap path is what makes `--tune` worth using.

---

## Hidden data — always inside the package

Answer keys, fixtures, helper modules live in a `taskdata/` dir next to `grader.py`, resolved at runtime:

```python
from pathlib import Path
_TASKDATA = Path(__file__).parent / "taskdata"
```

This works for editable (`pip install -e`) and wheel installs alike. For files too large to package (multi-GB datasets), list them under `grader.private` in `task.yaml` and read them from `self.private_dir`. Never put answer keys under `seed/` — agents read `seed/`.
