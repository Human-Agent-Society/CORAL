# JobShop Benchmark Workspace

This folder organizes 7 classic JSSP benchmark families into a uniform training/evaluation layout.

## Shared traits

- All families are **classical JSSP** instances: each job has a fixed operation order and each operation uses one machine.
- Objective is to minimize **makespan** (time when all jobs are completed).
- Each family provides benchmark metadata: `optimum` (if known), `lower_bound`, `upper_bound`, and literature `reference`.
- Each family folder has the same files:
  - `README.md`, `README_zh-CN.md`
  - `Task.md`, `Task_zh-CN.md`
  - `baseline/init.py` (simple greedy solver; pure Python, stdlib only)
  - `verification/reference.py` (OR-Tools CP-SAT reference)
  - `verification/evaluate.py` (runs baseline + reference and scores both)

## Key differences

| Family | Count | Typical sizes (jobs x machines) | Difficulty trend |
|---|---:|---|---|
| FT | 3 | 6x6, 10x10, 20x5 | Introductory / teaching-friendly |
| LA | 40 | 10x5 to 30x10 | Standard mid-scale benchmark |
| ABZ | 5 | 10x10, 20x15 | Medium to hard |
| ORB | 10 | 10x10 | Medium; often used for controlled comparisons |
| SWV | 20 | 20x10, 20x15, 50x10 | Larger and harder |
| YN | 4 | 20x20 | Hard and dense |
| TA | 80 | 15x15 to 100x20 | Large-scale stress-test set |

## Scoring conventions used here

- **Best-known score**: `score_best = min(100, 100 * target / makespan)`
  - `target = optimum` if known, otherwise `upper_bound`
- **Theoretical-limit score**: `score_lb = min(100, 100 * lower_bound / makespan)`
  - `100` is the theoretical ceiling under this formula.
- Higher score is better.

## Environment

- Python: `>=3.10`
- Install shared dependencies from repository root:
  - `pip install -r JobShop/requirements.txt`
- Baseline (`baseline/init.py`): Python standard library only.
- Reference + evaluation scripts use the `job_shop_lib` Python package and OR-Tools (`ortools`).
- Benchmark instance data is vendored in this repository at
  `JobShop/data/benchmark_instances.json`, sourced from:
  https://github.com/Pabloo22/job_shop_lib.git

## `evaluate.py` arguments

- `--instances`: optional explicit instance names.
  If omitted, all instances in the selected family are evaluated.
- `--max-instances`: optional cap on selected instances.
  The evaluator keeps the first N instances after optional `--instances` filtering.
- `--reference-time-limit`: time limit (seconds) per instance for reference solver.
  Default: `10.0`.

## Run examples

```bash
python JobShop/ft/verification/evaluate.py --max-instances 3 --reference-time-limit 5
python JobShop/ta/verification/evaluate.py --max-instances 2 --reference-time-limit 5
```

## Integrated with Frontier Eval Unified

All 7 JobShop subtasks are now integrated through unified:

- `task=unified task.benchmark=JobShop/abz`
- `task=unified task.benchmark=JobShop/ft`
- `task=unified task.benchmark=JobShop/la`
- `task=unified task.benchmark=JobShop/orb`
- `task=unified task.benchmark=JobShop/swv`
- `task=unified task.benchmark=JobShop/ta`
- `task=unified task.benchmark=JobShop/yn`

Each family-local `frontier_eval/` metadata points to the shared evaluator:
`benchmarks/JobShop/frontier_eval/evaluate_unified.py`.

## Unified run instructions (dual environment)

Recommended setup:

- `frontier_eval` driver process: `frontier-eval-driver`
- JobShop evaluator Python: `uv-env:frontier-v1-main` (or specify absolute path)

Single-family example (`abz`):

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=JobShop/abz \
  task.runtime.python_path=uv-env:frontier-v1-main \
  algorithm.iterations=0
```

Quick compatibility check (all families, 1 instance each, 1s reference limit):

```bash
for fam in abz ft la orb swv ta yn; do
  python -m frontier_eval \
    task=unified \
    task.benchmark=JobShop/${fam} \
    task.runtime.python_path=uv-env:frontier-v1-main \
    +task.runtime.env.JOBSHOP_EVAL_MAX_INSTANCES=1 \
    +task.runtime.env.JOBSHOP_REFERENCE_TIME_LIMIT=1 \
    algorithm.iterations=0
done
```

Runtime controls (passed via unified runtime env):

- `+task.runtime.env.JOBSHOP_EVAL_MAX_INSTANCES=<N>`: evaluate at most first N instances.
- `+task.runtime.env.JOBSHOP_REFERENCE_TIME_LIMIT=<seconds>`: per-instance reference solver cap.
- `+task.runtime.env.JOBSHOP_EVAL_INSTANCES='ta01 ta02'`: explicit instance subset.

## Runtime notes (default settings)

By default, evaluation uses all family instances with `reference-time-limit=10s`.
A rough upper bound is `instance_count x 10s + modeling/IO overhead`:

| Family | Default instance count | Rough upper bound | Note |
|---|---:|---:|---|
| FT | 3 | ~30s+ | short |
| ABZ | 5 | ~50s+ | short |
| ORB | 10 | ~100s+ | medium |
| YN | 4 | ~40s+ | medium (denser instances) |
| SWV | 20 | ~200s+ | long |
| LA | 40 | ~400s+ | long |
| TA | 80 | ~800s+ | very long stress test |

`LA/SWV/TA` are the most time-consuming in practice, especially `TA`.
For development loops, use smaller `JOBSHOP_EVAL_MAX_INSTANCES` and
`JOBSHOP_REFERENCE_TIME_LIMIT`.

## Why this benchmark is still hard

- A baseline score around `80` is not "near-optimal". When `target = optimum`,
  `gap% = 100 * (100 / score - 1)`, so score `80` still means about `25%` gap.
- The baseline quickly captures easy local improvements, but the remaining gains
  require global combinatorial optimization across all jobs/machines.
- Improvements near high-score regions are expensive: moving from low/mid-80s
  to low/mid-90s usually needs much stronger search and more runtime.
- When `optimum` is unknown, `best-known score` uses `upper_bound`, so a high
  score there still does not prove the solution is close to true optimum.